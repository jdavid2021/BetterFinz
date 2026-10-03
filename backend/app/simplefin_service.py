import base64,hashlib,json,logging,re,secrets,urllib.error,urllib.parse,urllib.request
from contextlib import contextmanager
from datetime import datetime,timedelta,timezone
from decimal import Decimal
from cryptography.fernet import Fernet
from redis import Redis
from redis.exceptions import RedisError
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.config import settings
from app.accounting_service import ensure_household_accounting,rebuild_opening_balances,sync_transaction_journal
from app.models import CategorizationRule,FinancialAccount,FinancialConnection,LedgerAccount,PaymentMatch,Transaction,TransactionMerge
from app.statement_service import classify_rule,descriptions_similar,qualified_provider_id
from app.categorization_service import learned_classification
from app.bill_service import match_open_scheduled_payments

logger = logging.getLogger("finleash.simplefin")

class SimpleFinError(ValueError):pass
class SimpleFinBusy(SimpleFinError):pass
CORE_SWEEP=re.compile(r"\b(?:(?P<purchase>PURCHASE INTO)|REDEMPTION FROM) CORE ACCOUNT\b.*\bFDIC INSURED DEPOSIT\b",re.I)
def is_fidelity_core_sweep(description):return bool(CORE_SWEEP.search(description or ""))
def core_sweep_direction(description):
 # Fidelity reports both sweep legs as positive amounts, so the provider sign cannot be trusted here.
 match=CORE_SWEEP.search(description or "")
 if not match:return None
 return "debit" if match.group("purchase") else "credit"

def classify_core_cash_sweeps(db,hid):
 ensure_household_accounting(db,hid)
 transfer=db.scalar(select(LedgerAccount).where(LedgerAccount.household_id==hid,LedgerAccount.code=="1100",LedgerAccount.entity_id.is_(None)))
 rows=list(db.scalars(select(Transaction).where(Transaction.household_id==hid,Transaction.data_source=="simplefin")))
 changed=[];accounts=set()
 for row in rows:
  direction=core_sweep_direction(row.original_description)
  if not direction:continue
  if row.is_transfer and row.category=="Transfer" and row.category_id==transfer.id and row.direction==direction:continue
  if row.direction!=direction:row.direction=direction;accounts.add(row.account_id)
  row.is_transfer=True;row.category="Transfer";row.category_id=transfer.id;row.classification_source="provider_rule";row.classification_confidence=Decimal("1");sync_transaction_journal(db,row);changed.append(row.id)
 if accounts:db.flush();rebuild_opening_balances(db,hid,list(accounts))
 db.commit();return {"updated":len(changed),"transaction_ids":changed}
class NoRedirect(urllib.request.HTTPRedirectHandler):
 def redirect_request(self,req,fp,code,msg,headers,newurl):
  raise SimpleFinError('SimpleFIN returned an unsafe redirect.')

def cipher():
 raw=(settings.simplefin_encryption_key or settings.secret_key).encode()
 return Fernet(base64.urlsafe_b64encode(hashlib.sha256(raw).digest()))
def encrypt(v):return cipher().encrypt(v.encode()).decode()
def decrypt(v):return cipher().decrypt(v.encode()).decode()
def allowed(url,credentials=False):
 p=urllib.parse.urlsplit(url.strip());hosts={x.strip().lower() for x in settings.simplefin_allowed_hosts.split(',')}
 if p.scheme!='https' or not p.hostname or p.hostname.lower() not in hosts or p.fragment or (credentials and (not p.username or not p.password)):raise SimpleFinError('The token does not point to an approved SimpleFIN Bridge host.')
 return url.strip()
def request(req,stage='access'):
 req.add_header('User-Agent','FinLeash/1.0')
 try:
  with urllib.request.build_opener(NoRedirect).open(req,timeout=20) as r:
   body=r.read(10*1024*1024+1)
   if len(body)>10*1024*1024:raise SimpleFinError('The SimpleFIN response was unexpectedly large.')
   return body
 except SimpleFinError:raise
 except urllib.error.HTTPError as e:
  if e.code in {401,403} and stage=='claim':message='SimpleFIN rejected this Setup Token. It may already have been used; create a new token.'
  elif e.code in {401,403}:message='SimpleFIN claimed the token but rejected account access. Retry this saved connection.'
  else:message='SimpleFIN could not complete the request.'
  raise SimpleFinError(message) from e
 except (urllib.error.URLError,TimeoutError,OSError) as e:raise SimpleFinError('SimpleFIN is temporarily unavailable.') from e
def claim(token):
 try:
  raw=token.strip().encode();url=base64.urlsafe_b64decode(raw+b'='*(-len(raw)%4)).decode()
 except Exception as e:raise SimpleFinError('The SimpleFIN Setup Token is invalid.') from e
 url=allowed(url);return allowed(request(urllib.request.Request(url,data=b'',method='POST'),stage='claim').decode().strip(),True)
def fetch(access,start=None):
 p=urllib.parse.urlsplit(allowed(access,True));host=p.hostname or '';host+=f':{p.port}' if p.port else ''
 base=urllib.parse.urlunsplit((p.scheme,host,p.path.rstrip('/'),'',''));q={'version':'2'}
 start=start or datetime.now(timezone.utc)-timedelta(days=89);q['start-date']=str(int(start.timestamp()))
 auth=base64.b64encode((urllib.parse.unquote(p.username or '')+':'+urllib.parse.unquote(p.password or '')).encode()).decode()
 data=json.loads(request(urllib.request.Request(f'{base}/accounts?{urllib.parse.urlencode(q)}',headers={'Authorization':f'Basic {auth}','Accept':'application/json'})))
 if not isinstance(data.get('accounts'),list):raise SimpleFinError('SimpleFIN returned an invalid account list.')
 return data
def account_mask(a):
 raw="".join(char for char in str(a.get("account-number") or "") if char.isdigit())
 if len(raw)>=4:return raw[-4:],"account_number"
 match=re.search(r"\((\d{4})\)\s*$",str(a.get("name") or ""))
 return (match.group(1),"name_suffix") if match else ("0000","missing")
def public_account(a,payload=None):
 org=a.get("org") or {};connections={str(c.get("conn_id") or c.get("id")):c for c in (payload or {}).get("connections",[]) if isinstance(c,dict)};conn=connections.get(str(a.get("conn_id")),{})
 mask,mask_source=account_mask(a)
 return {"id":str(a.get("id","")),"name":str(a.get("name") or "Account")[:100],"mask":mask,"mask_source":mask_source,"institution_name":str(org.get("name") or conn.get("name") or a.get("conn_name") or "")[:120],"currency":str(a.get("currency") or "USD"),"balance":str(a.get("balance") or "0")}
def _aware(value):
 return value if value is None or value.tzinfo else value.replace(tzinfo=timezone.utc)
def sync_health(row,now=None):
 now=now or datetime.now(timezone.utc);started=_aware(row.sync_started_at);last_success=_aware(row.last_successful_sync_at);next_sync=_aware(row.next_sync_at)
 if row.status=="syncing" and started and now-started<timedelta(seconds=settings.simplefin_sync_lock_seconds):return "syncing"
 if row.status=="error":return "error"
 if last_success and now-last_success>timedelta(hours=settings.simplefin_sync_stale_hours):return "stale"
 if next_sync and now-next_sync>timedelta(minutes=15):return "overdue"
 return "healthy" if last_success else "pending"
def status(db,hid):
 rows=db.scalars(select(FinancialConnection).where(FinancialConnection.household_id==hid,FinancialConnection.provider=='simplefin')).all()
 return [{'id':r.id,'status':r.status,'sync_health':sync_health(r),'last_sync_at':r.last_sync_at.isoformat() if r.last_sync_at else None,'last_successful_sync_at':r.last_successful_sync_at.isoformat() if r.last_successful_sync_at else None,'sync_started_at':r.sync_started_at.isoformat() if r.sync_started_at else None,'next_sync_at':r.next_sync_at.isoformat() if r.next_sync_at else None,'consecutive_failures':r.consecutive_failures,'automatic_sync_enabled':r.status!='pending','sync_interval_minutes':settings.simplefin_sync_interval_minutes,'last_error':r.last_error} for r in rows]
def institution_match(left,right):
 left_key="".join(char for char in (left or "").lower() if char.isalnum());right_key="".join(char for char in (right or "").lower() if char.isalnum())
 return not left_key or not right_key or left_key in right_key or right_key in left_key
def account_name_score(left,right):
 ignored={'account','bank','checking','checkings','saving','savings','credit','card','debit','primary'}
 def tokens(value):return {token for token in re.findall(r'[a-z0-9]+',(value or '').lower()) if token not in ignored and not token.isdigit()}
 return len(tokens(left)&tokens(right))
def payment_signature(description):
 words=[word[:-1] if word.endswith('s') and len(word)>4 else word for word in re.findall(r'[a-z0-9]+',(description or '').lower())]
 markers={'autopay','payment','pmt','paymt'};noise=markers|{'ach','bill','debit','fbt','from','online','to','transfer','web','xfer'}
 return bool(set(words)&markers),frozenset(word for word in words if word not in noise and not word.isdigit())
def cross_source_descriptions_similar(left,right):
 if descriptions_similar(left,right):return True
 left_payment,left_signature=payment_signature(left);right_payment,right_signature=payment_signature(right)
 return left_payment and right_payment and bool(left_signature) and left_signature==right_signature
def matching_cross_source_transactions(db,hid,account_id,posted_date,amount,direction,description):
 candidates=list(db.scalars(select(Transaction).where(Transaction.household_id==hid,Transaction.account_id==account_id,Transaction.posted_date==posted_date,Transaction.amount==amount,Transaction.direction==direction,Transaction.data_source!='simplefin')))
 return [candidate for candidate in candidates if cross_source_descriptions_similar(candidate.original_description,description)]
def merge_simplefin_transaction(db,survivor,imported):
 survivor_match=db.scalar(select(PaymentMatch).where(PaymentMatch.transaction_id==survivor.id));imported_match=db.scalar(select(PaymentMatch).where(PaymentMatch.transaction_id==imported.id))
 if survivor_match and imported_match:return False
 if imported_match:imported_match.transaction_id=survivor.id
 provider_id=imported.provider_id;imported.provider_id=None;db.flush();survivor.provider_id=provider_id;survivor.pending=imported.pending;survivor.is_transfer=survivor.is_transfer or imported.is_transfer
 if survivor.category=='Uncategorized' and imported.category!='Uncategorized':
  survivor.category=imported.category;survivor.classification_source=imported.classification_source;survivor.classification_confidence=imported.classification_confidence
 if not survivor.notes and imported.notes:survivor.notes=imported.notes
 db.delete(imported);return True
def reconcile_existing_duplicates(db,hid,row,dry_run=True):
 imported=list(db.scalars(select(Transaction).join(FinancialAccount,FinancialAccount.id==Transaction.account_id).where(Transaction.household_id==hid,FinancialAccount.connection_id==row.id,Transaction.data_source=='simplefin')))
 matches=[];conflicts=0
 for transaction in imported:
  candidates=matching_cross_source_transactions(db,hid,transaction.account_id,transaction.posted_date,transaction.amount,transaction.direction,transaction.original_description)
  if len(candidates)!=1:continue
  survivor=candidates[0];survivor_match=db.scalar(select(PaymentMatch).where(PaymentMatch.transaction_id==survivor.id));imported_match=db.scalar(select(PaymentMatch).where(PaymentMatch.transaction_id==transaction.id))
  if survivor_match and imported_match:conflicts+=1;continue
  matches.append((survivor,transaction))
 if not dry_run:
  for survivor,transaction in matches:merge_simplefin_transaction(db,survivor,transaction)
  db.flush();rebuild_opening_balances(db,hid,list({survivor.account_id for survivor,_ in matches}))
  db.commit()
 return {'matched':len(matches),'conflicts':conflicts}

def preview(db,hid,row,payload):
 locals=list(db.scalars(select(FinancialAccount).where(FinancialAccount.household_id==hid,FinancialAccount.is_active,FinancialAccount.connection_id.is_(None))))
 result=[];candidates=[]
 for remote in payload['accounts']:
  item=public_account(remote,payload);item['kind']=infer_kind(item['name']);item['transaction_count']=len(remote.get('transactions') or [])
  matches=[account for account in locals if item['mask']!='0000' and account.mask==item['mask'] and account.kind==item['kind'] and institution_match(item['institution_name'],account.institution_name)]
  item['suggested_existing_account_id']=None;item['suggestion_confidence']=None;item['match_reasons']=[];result.append(item);candidates.append(matches)
 contenders: dict[str, list[int]] = {}
 for index,matches in enumerate(candidates):
  if len(matches)==1:contenders.setdefault(matches[0].id,[]).append(index)
 for account_id,indexes in contenders.items():
  if len(indexes)==1:
   index=indexes[0];result[index]['suggested_existing_account_id']=account_id;result[index]['suggestion_confidence']='strong' if result[index]['mask_source']=='account_number' else 'possible';result[index]['match_reasons']=['same institution','same account type','same ending digits']
   continue
  local=next(account for account in locals if account.id==account_id);ranked=sorted(((account_name_score(result[index]['name'],local.name),index) for index in indexes),reverse=True)
  if ranked[0][0]>0 and ranked[0][0]>ranked[1][0]:
   index=ranked[0][1];result[index]['suggested_existing_account_id']=account_id;result[index]['suggestion_confidence']='possible';result[index]['match_reasons']=['same institution','same account type','same ending digits','similar account name']
 return {'connection_id':row.id,'accounts':result,'estimated_transaction_count':sum(item['transaction_count'] for item in result)}
def connect(db,hid,token):
 access=claim(token);row=FinancialConnection(household_id=hid,provider='simplefin',encrypted_access_url=encrypt(access),status='pending',data_source='simplefin');db.add(row);db.commit()
 try:return preview(db,hid,row,fetch(access))
 except SimpleFinError as e:row.status='error';row.last_error=str(e)[:255];db.commit();raise
def infer_kind(name):
 n=name.lower()
 if 'mortgage' in n:return 'mortgage'
 if 'auto loan' in n:return 'auto_loan'
 if 'loan' in n:return 'loan'
 if 'credit' in n or 'card' in n or 'quicksilver' in n:return 'credit_card'
 if 'saving' in n:return 'savings'
 if 'money market' in n:return 'money_market'
 return 'checking'

@contextmanager
def connection_sync_lock(connection_id):
 client=Redis.from_url(settings.redis_url,decode_responses=True,socket_connect_timeout=1,socket_timeout=1)
 key=f"finleash:simplefin:sync:{connection_id}";token=secrets.token_urlsafe(18);acquired=False
 try:
  acquired=bool(client.set(key,token,nx=True,ex=settings.simplefin_sync_lock_seconds))
 except RedisError as exc:
  if settings.is_secure_environment:raise SimpleFinError("Synchronization protection is temporarily unavailable.") from exc
  logger.warning("SimpleFIN lock unavailable in development: %s",type(exc).__name__);acquired=True
 if not acquired:raise SimpleFinBusy("This SimpleFIN connection is already synchronizing.")
 try:yield
 finally:
  if acquired:
   try:client.eval("if redis.call('get',KEYS[1])==ARGV[1] then return redis.call('del',KEYS[1]) else return 0 end",1,key,token)
   except RedisError:logger.warning("SimpleFIN lock release failed for connection %s",connection_id)

def sync_connection(db,hid,row,payload=None):
 with connection_sync_lock(row.id):
  return sync(db,hid,row,payload)

def sync(db,hid,row,payload=None):
 now=datetime.now(timezone.utc);row.last_sync_at=now;row.sync_started_at=now;row.status='syncing';row.last_error='';db.commit()
 try:
  payload=payload or fetch(decrypt(row.encrypted_access_url),_aware(row.last_successful_sync_at)-timedelta(days=5) if row.last_successful_sync_at else now-timedelta(days=90));added=duplicates=matched_existing=0
  ensure_household_accounting(db,hid);transfer_category=db.scalar(select(LedgerAccount).where(LedgerAccount.household_id==hid,LedgerAccount.code=="1100",LedgerAccount.entity_id.is_(None)))
  removed_provider_ids=set()
  for snapshot in db.scalars(select(TransactionMerge.removed_snapshot).where(TransactionMerge.household_id==hid)):
   try:
    removed_id=json.loads(snapshot).get("provider_id")
    if removed_id:removed_provider_ids.add(removed_id)
   except (TypeError,ValueError):pass
  rules=list(db.scalars(select(CategorizationRule).where(CategorizationRule.household_id==hid,CategorizationRule.is_active)))
  for remote in payload['accounts']:
   account=db.scalar(select(FinancialAccount).where(FinancialAccount.household_id==hid,FinancialAccount.connection_id==row.id,FinancialAccount.provider_account_id==str(remote.get('id'))))
   if not account:continue
   stamp=datetime.fromtimestamp(int(remote.get('balance-date') or now.timestamp()),timezone.utc);synced_balance=abs(Decimal(str(remote.get('balance') or 0)))
   account.balance=synced_balance;account.balance_as_of_date=stamp.date()
   if account.kind in {'checking','savings','money_market'}:
    account.available_balance=synced_balance
   for t in remote.get('transactions') or []:
    posted=int(t.get('posted') or t.get('transacted_at') or 0)
    if not t.get('id') or posted<=0:continue
    pid=qualified_provider_id(hid,account.id,'simplefin:'+str(t.get('id')))
    if pid and (pid in removed_provider_ids or db.scalar(select(Transaction.id).where(Transaction.provider_id==pid))):duplicates+=1;continue
    amount=Decimal(str(t.get('amount') or 0));desc=str(t.get('description') or 'Transaction')[:255];direction=core_sweep_direction(desc) or ('credit' if amount>=0 else 'debit');sweep=is_fidelity_core_sweep(desc);cat,conf,source=("Transfer",Decimal("1"),"provider_rule") if sweep else learned_classification(desc,rules) or classify_rule(desc)
    existing=matching_cross_source_transactions(db,hid,account.id,datetime.fromtimestamp(posted,timezone.utc).date(),abs(amount),direction,desc)
    if len(existing)==1:
     existing[0].provider_id=pid
     if sweep:
      existing[0].is_transfer=True;existing[0].category="Transfer";existing[0].category_id=transfer_category.id;existing[0].classification_source="provider_rule";existing[0].classification_confidence=Decimal("1");sync_transaction_journal(db,existing[0])
     matched_existing+=1;continue
    db.add(Transaction(household_id=hid,account_id=account.id,provider_id=pid,original_description=desc,merchant=desc[:120].title(),amount=abs(amount),direction=direction,posted_date=datetime.fromtimestamp(posted,timezone.utc).date(),pending=bool(t.get('pending',False)),category=cat,category_id=transfer_category.id if sweep else None,classification_source=source,classification_confidence=conf,is_transfer=sweep,data_source='simplefin'));added+=1
  db.flush();account_ids=list(db.scalars(select(FinancialAccount.id).where(FinancialAccount.household_id==hid,FinancialAccount.connection_id==row.id)));rebuild_opening_balances(db,hid,account_ids);match_open_scheduled_payments(db,hid)
  row.status='active';row.last_successful_sync_at=now;row.sync_started_at=None;row.next_sync_at=now+timedelta(minutes=settings.simplefin_sync_interval_minutes);row.consecutive_failures=0;row.last_error='';db.commit();return {'added':added,'duplicates':duplicates,'matched_existing':matched_existing}
 except Exception as e:
  connection_id=row.id;db.rollback();row=db.get(FinancialConnection,connection_id)
  if row:
   row.status='error';row.last_sync_at=now;row.sync_started_at=None;row.consecutive_failures+=1
   retry_minutes=min(settings.simplefin_sync_interval_minutes,settings.simplefin_sync_retry_base_minutes*(2**min(row.consecutive_failures-1,6)))
   row.next_sync_at=now+timedelta(minutes=retry_minutes);row.last_error=str(e)[:255];db.commit()
  raise
