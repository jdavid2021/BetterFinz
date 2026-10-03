"use client";

import {useEffect,useMemo,useState,type ReactNode} from "react";
import {useMutation,useQuery,useQueryClient} from "@tanstack/react-query";
import {ArrowDown,ArrowUp,CheckSquare,GitMerge,Plus,Search,X} from "lucide-react";
import {Money} from "@/components/status";
import {Dialog} from "@/components/dialog";
import {SearchPicker,type SearchPickerOption} from "@/components/search-picker";
import {Account,AccountingSegment,LedgerCategory,api} from "@/lib/api";

type Tx={id:string;description:string;merchant:string;amount:string;direction:"credit"|"debit"|"unknown";date:string;pending:boolean;category:string;category_id:string|null;segment_id:string|null;account_id:string;data_source:string;is_transfer:boolean};
type DuplicateGroup={key:string;transactions:Tx[]};
type ObligationMatch={payment_id:string;payee:string;due_date:string;amount:string;score?:number;confidence?:"high"|"medium";reason?:string;status?:string;match_type?:string};
type BillMatchContext={matched:ObligationMatch|null;suggestions:ObligationMatch[];options:ObligationMatch[]};
type SortField="transaction"|"date"|"category"|"amount";
type CreateContext={ids:string[];direction:"credit"|"debit"|"unknown"};
type DuplicateMergeChoice={keep:Tx;duplicate:Tx};
type AccountMetric={label:string;value:string};

const categoryCollator=new Intl.Collator(undefined,{numeric:true,sensitivity:"base"});
const categoryRootNames=new Set(["Assets","Liabilities","Equity","Income","Expenses"]);

function compactCategoryPath(path:string){
  const parts=path.split(" › ");
  if(categoryRootNames.has(parts[0]))parts.shift();
  return parts.join(" → ");
}

function categoryGroup(category:LedgerCategory){
  if(category.code.startsWith("FA-")||category.account_type==="asset"||category.account_type==="liability")return "Transfers & account payments";
  if(category.account_type==="expense")return "Expenses";
  if(category.account_type==="income")return "Income";
  return "Accounting adjustments";
}

function buildCategoryOptions(categories:LedgerCategory[],accounts:Account[],direction:Tx["direction"]):SearchPickerOption[]{
  const accountByPrefix=new Map(accounts.map(account=>[account.id.slice(0,12),account]));
  const groupOrder=direction==="credit"?["Income","Transfers & account payments","Expenses","Accounting adjustments"]:["Expenses","Transfers & account payments","Income","Accounting adjustments"];
  const options=categories.map(category=>{
    const account=category.code.startsWith("FA-")?accountByPrefix.get(category.code.slice(3)):undefined;
    const group=categoryGroup(category);
    return {
      value:category.id,
      label:account?`${account.name} · •••• ${account.mask}`:compactCategoryPath(category.path),
      description:account?`${account.institution_name||"Account"} · ${account.kind.replaceAll("_"," ")}`:category.path,
      keywords:`${category.name} ${category.path} ${category.code} ${account?.institution_name||""} ${account?.mask||""}`,
      group,
      sortKey:account?`${account.institution_name||""} ${account.name} ${account.mask}`:compactCategoryPath(category.path),
    };
  });
  options.sort((left,right)=>groupOrder.indexOf(left.group)-groupOrder.indexOf(right.group)||categoryCollator.compare(left.sortKey,right.sortKey));
  return [...options.map(option=>({value:option.value,label:option.label,description:option.description,keywords:option.keywords,group:option.group})),{value:"__create__",label:"＋ Create new category…",description:"Add a reusable category",group:"Actions"}];
}

function accountMetrics(account:Account):AccountMetric[]{
  if(account.kind==="cash_management")return [{label:"Total account value",value:account.balance},{label:"Spendable cash",value:account.available_balance},{label:"Investment holdings",value:account.investment_balance},{label:"Protected reserve",value:account.reserve}];
  if(account.kind==="investment")return [{label:"Total value",value:account.balance},{label:"Cash available",value:account.available_balance},{label:"Investment holdings",value:account.investment_balance}];
  if(account.kind==="credit_card")return [{label:"Current balance",value:account.balance},{label:"Available credit",value:account.available_balance}];
  if(account.kind==="mortgage")return [{label:"Current mortgage balance",value:account.balance},{label:"Original mortgage",value:account.original_balance||"0"}];
  if(["auto_loan","buy_now_pay_later","loan","other"].includes(account.kind))return [{label:"Outstanding balance",value:account.balance},{label:"Original balance",value:account.original_balance||"0"}];
  const estimated=account.balance_source==="calculated_activity";
  return [{label:estimated?"Estimated current balance":"Current balance",value:account.balance},{label:estimated?"Estimated available balance":"Available balance",value:account.available_balance},{label:"Protected reserve",value:account.reserve}];
}

export function TransactionWorkspace({embedded=false,selectedAccountId,onAccountChange,accountActions}:{embedded?:boolean;selectedAccountId?:string;onAccountChange?:(id:string)=>void;accountActions?:ReactNode}){
  const qc=useQueryClient();
  const initialParams=typeof window!=="undefined"?new URLSearchParams(window.location.search):new URLSearchParams();
  const [q,setQ]=useState("");
  const [filtersOpen,setFiltersOpen]=useState(false);
  const [localAccountId,setLocalAccountId]=useState(initialParams.get("account_id")||"");
  const accountId=selectedAccountId??localAccountId;
  const setAccountId=(id:string)=>{setLocalAccountId(id);onAccountChange?.(id)};
  const [categoryId,setCategoryId]=useState("");
  const [segmentId,setSegmentId]=useState("");
  const [amount,setAmount]=useState("");
  const [selectedDate,setSelectedDate]=useState("");
  const [dateFrom,setDateFrom]=useState(initialParams.get("date_from")||"");
  const [dateTo,setDateTo]=useState(initialParams.get("date_to")||"");
  const [selected,setSelected]=useState<Set<string>>(new Set());
  const [bulkCategory,setBulkCategory]=useState("");
  const [bulkSegment,setBulkSegment]=useState("");
  const [error,setError]=useState("");
  const [page,setPage]=useState(1);
  const [sortBy,setSortBy]=useState<SortField>("date");
  const [sortDir,setSortDir]=useState<"asc"|"desc">("desc");
  const [createContext,setCreateContext]=useState<CreateContext|null>(null);
  const [newName,setNewName]=useState("");
  const [newParent,setNewParent]=useState("");
  const [matchingTransaction,setMatchingTransaction]=useState<Tx|null>(null);
  const [billSearch,setBillSearch]=useState("");
  const [duplicateMergeChoice,setDuplicateMergeChoice]=useState<DuplicateMergeChoice|null>(null);

  const accounts=useQuery({queryKey:["accounts"],queryFn:()=>api<Account[]>("/api/v1/accounts")});
  const segments=useQuery({queryKey:["accounting-segments"],queryFn:()=>api<AccountingSegment[]>("/api/v1/accounting/segments")});
  const segmentSettings=useQuery({queryKey:["segment-settings"],queryFn:()=>api<{label:string}>("/api/v1/accounting/segment-settings")});
  const categoryQuery=useQuery({queryKey:["ledger-categories"],queryFn:()=>api<LedgerCategory[]>("/api/v1/accounting/categories")});
  const postingCategories=useMemo(()=>(categoryQuery.data||[]).filter(row=>row.allow_posting&&row.is_active),[categoryQuery.data]);
  const parentCategories=useMemo(()=>(categoryQuery.data||[]).filter(row=>row.is_active&&row.depth<3),[categoryQuery.data]);
  const categoryOptions=useMemo(()=>buildCategoryOptions(postingCategories,accounts.data||[],"unknown"),[postingCategories,accounts.data]);
  const debitCategoryOptions=useMemo(()=>buildCategoryOptions(postingCategories,accounts.data||[],"debit"),[postingCategories,accounts.data]);
  const creditCategoryOptions=useMemo(()=>buildCategoryOptions(postingCategories,accounts.data||[],"credit"),[postingCategories,accounts.data]);
  const filterCategoryOptions=useMemo(()=>[{value:"",label:"All categories",description:"Do not filter by category"},...categoryOptions.filter(option=>option.value!=="__create__")],[categoryOptions]);
  const accountOptions=useMemo(()=>[{value:"",label:"All accounts",description:"Transactions from every account"},...(accounts.data||[]).slice().sort((left,right)=>categoryCollator.compare(`${left.institution_name||""} ${left.name} ${left.mask}`,`${right.institution_name||""} ${right.name} ${right.mask}`)).map(account=>({value:account.id,label:account.name,description:`${account.institution_name||"Account"} · •••• ${account.mask}`,keywords:`${account.mask} ${account.kind}`}))],[accounts.data]);
  const segmentOptions=useMemo(()=>[{value:"__unassigned__",label:"Unassigned",description:`Clear the ${segmentSettings.data?.label||"segment"}`},...(segments.data||[]).slice().sort((left,right)=>categoryCollator.compare(left.name,right.name)).map(segment=>({value:segment.id,label:segment.name}))],[segments.data,segmentSettings.data?.label]);

  useEffect(()=>{setPage(1);setSelected(new Set())},[q,accountId,categoryId,segmentId,amount,selectedDate,dateFrom,dateTo]);
  const query=new URLSearchParams({q,page:String(page),page_size:"100",sort_by:sortBy,sort_dir:sortDir});
  if(accountId)query.set("account_id",accountId);
  if(categoryId)query.set("category_id",categoryId);
  if(segmentId)query.set("segment_id",segmentId);
  if(amount)query.set("amount",amount);
  if(selectedDate)query.set("selected_date",selectedDate);
  else{if(dateFrom)query.set("date_from",dateFrom);if(dateTo)query.set("date_to",dateTo)}
  const {data,isLoading}=useQuery({queryKey:["transactions",q,accountId,categoryId,segmentId,amount,selectedDate,dateFrom,dateTo,page,sortBy,sortDir],queryFn:()=>api<{items:Tx[];page:number;page_size:number;total:number;pages:number}>(`/api/v1/transactions?${query}`),enabled:!(dateFrom&&dateTo&&dateFrom>dateTo)});
  const duplicateReview=useQuery({queryKey:["duplicate-review",accountId],queryFn:()=>api<{count:number;groups:DuplicateGroup[]}>("/api/v1/reconciliations/duplicates/review"+(accountId?"?account_id="+encodeURIComponent(accountId):""))});
  const visibleTransactionIds=(data?.items||[]).map(row=>row.id);
  const matchContexts=useQuery({queryKey:["transaction-match-context",visibleTransactionIds.join(",")],queryFn:()=>api<Record<string,BillMatchContext>>("/api/v1/transactions/payment-match-context",{method:"POST",body:JSON.stringify({transaction_ids:visibleTransactionIds})}),enabled:visibleTransactionIds.length>0});
  const matchObligation=useMutation({mutationFn:({paymentId,transactionId}:{paymentId:string;transactionId:string})=>api("/api/v1/payments/"+paymentId+"/reconcile",{method:"POST",body:JSON.stringify({transaction_id:transactionId})}),onSuccess:()=>{setMatchingTransaction(null);setError("");qc.invalidateQueries({queryKey:["transaction-match-context"]});qc.invalidateQueries({queryKey:["monthly-plan"]});qc.invalidateQueries({queryKey:["today"]})},onError:e=>setError(e.message)});
  const mergeDuplicate=useMutation({mutationFn:({keep,duplicate}:{keep:string;duplicate:string})=>api("/api/v1/reconciliations/merge",{method:"POST",body:JSON.stringify({keep_transaction_id:keep,duplicate_transaction_id:duplicate})}),onSuccess:()=>{setDuplicateMergeChoice(null);setError("");qc.invalidateQueries({queryKey:["transactions"]});qc.invalidateQueries({queryKey:["duplicate-review"]})},onError:e=>setError(e.message)});

  const classify=useMutation({
    mutationFn:({ids,next}:{ids:string[];next:string})=>api<{updated:number}>("/api/v1/transactions/categories",{method:"PATCH",body:JSON.stringify({transaction_ids:ids,category_id:next})}),
    onSuccess:()=>{setSelected(new Set());setBulkCategory("");setError("");qc.invalidateQueries({queryKey:["transactions"]});qc.invalidateQueries({queryKey:["categorization-rules"]})},
    onError:e=>setError(e.message),
  });
  const assignSegment=useMutation({
    mutationFn:({ids,next}:{ids:string[];next:string|null})=>api<{updated:number}>("/api/v1/accounting/transaction-segments",{method:"PATCH",body:JSON.stringify({transaction_ids:ids,segment_id:next})}),
    onSuccess:()=>{setBulkSegment("");setError("");qc.invalidateQueries({queryKey:["transactions"]});qc.invalidateQueries({queryKey:["report-pnl"]})},
    onError:e=>setError(e.message),
  });
  const createCategory=useMutation({
    mutationFn:()=>api<LedgerCategory>("/api/v1/accounting/categories",{method:"POST",body:JSON.stringify({name:newName,parent_id:newParent})}),
    onSuccess:async row=>{const ids=createContext?.ids||[];setCreateContext(null);setNewName("");setNewParent("");await qc.invalidateQueries({queryKey:["ledger-categories"]});if(ids.length)classify.mutate({ids,next:row.id})},
    onError:e=>setError(e.message),
  });

  const items=data?.items||[];
  const allSelected=items.length>0&&items.every(t=>selected.has(t.id));
  function toggle(id:string){setSelected(current=>{const next=new Set(current);if(next.has(id))next.delete(id);else next.add(id);return next})}
  function toggleAll(){setSelected(allSelected?new Set():new Set(items.map(t=>t.id)))}
  function sort(field:SortField){setSortDir(current=>sortBy===field?(current==="asc"?"desc":"asc"):"asc");setSortBy(field);setPage(1);setSelected(new Set())}
  function sortHeader(field:SortField,label:string){const active=sortBy===field;return <button type="button" className={active?"transaction-sort active":"transaction-sort"} onClick={()=>sort(field)} aria-label={`Sort by ${label} ${active&&sortDir==="asc"?"descending":"ascending"}`} aria-pressed={active}>{label}{active&&(sortDir==="asc"?<ArrowUp/>:<ArrowDown/>)}</button>}
  function openCreate(ids:string[],direction:CreateContext["direction"]){
    const rootType=direction==="credit"?"income":"expense";
    const root=(categoryQuery.data||[]).find(row=>row.account_type===rootType&&row.depth===1);
    setNewParent(root?.id||"");setNewName("");setCreateContext({ids,direction});
  }
  function chooseCategory(value:string,ids:string[],direction:CreateContext["direction"]){
    if(value==="__create__")openCreate(ids,direction);
    else if(value)classify.mutate({ids,next:value});
  }
  function openBillMatch(transaction:Tx){setBillSearch("");setMatchingTransaction(transaction)}
  const activeCategory=postingCategories.find(row=>row.id===categoryId);
  const billMatchOptions=matchContexts.data?.[matchingTransaction?.id||""]?.options||[];
  const visibleBillMatches=billMatchOptions.filter(row=>{const terms=billSearch.toLowerCase().trim().split(/\s+/).filter(Boolean);const text=`${row.payee} ${row.amount} ${row.due_date} ${row.reason||""}`.toLowerCase();return terms.every(term=>text.includes(term))});

  const selectedAccount=accounts.data?.find(account=>account.id===accountId);
  return <>
    {!embedded&&<div className="page-title"><div><p className="eyebrow">Activity</p><h1>Transactions</h1><p className="subtitle">Categorize normally; balanced accounting entries are created automatically.</p></div></div>}
    {embedded&&<div className="embedded-transaction-head"><div className="embedded-account-identity"><p className="eyebrow">Activity</p><h2>{selectedAccount?.name||"All accounts"}</h2><p>{selectedAccount?(selectedAccount.institution_name||"Account")+" · •••• "+selectedAccount.mask:"Transactions across every connected account"}</p>{selectedAccount?.balance_source==="calculated_activity"&&<p>Estimated from posted activity since {selectedAccount.balance_anchor_date?new Date(selectedAccount.balance_anchor_date+"T12:00:00").toLocaleDateString():"the latest income deposit"}. {selectedAccount.connection_provider==="simplefin"?"SimpleFIN":"The provider"} reports <Money value={selectedAccount.reported_available_balance}/>.</p>}</div>{selectedAccount&&<div className="embedded-account-metrics">{accountMetrics(selectedAccount).map(metric=><div key={metric.label}><small>{metric.label}{selectedAccount.balance_as_of_date?" · as of "+new Date(selectedAccount.balance_as_of_date+"T12:00:00").toLocaleDateString():""}</small><strong><Money value={metric.value}/></strong></div>)}</div>}</div>}
    {embedded&&accountActions&&<div className="embedded-account-actions" aria-label="Selected account actions">{accountActions}</div>}
    {!!duplicateReview.data?.count&&<section className="panel reconcile-candidates transaction-duplicate-review"><div className="panel-head"><div><h2>Possible duplicates · {duplicateReview.data.count}</h2><p>Review each pair before merging. Provider records are preserved in the audit history.</p></div><GitMerge/></div>{duplicateReview.data.groups.map(group=><article key={group.key} className="duplicate-group">{group.transactions.map(tx=><div key={tx.id}><div><strong>{tx.merchant}</strong><p>{tx.description}</p><small>{new Date(tx.date+"T12:00").toLocaleDateString()} · {accounts.data?.find(a=>a.id===tx.account_id)?.name} · {tx.data_source}</small></div><strong>{tx.direction==="credit"?"+":"−"}<Money value={tx.amount}/></strong></div>)}{group.transactions.length===2?<div className="duplicate-actions"><span>Choose which transaction details to keep:</span>{group.transactions.map((keep,index)=>{const duplicate=group.transactions[1-index];const sameLabel=keep.merchant===duplicate.merchant&&keep.description===duplicate.description;return <button type="button" key={keep.id} disabled={mergeDuplicate.isPending} onClick={()=>setDuplicateMergeChoice({keep,duplicate})}>{sameLabel?("Keep "+(index===0?"first":"second")+" row"):("Keep "+keep.merchant)}</button>})}</div>:<p className="field-help">This group has more than two candidates; reconcile the account before merging them.</p>}</article>)}</section>}
    <section className="panel transaction-panel">
      <div className={"filter-bar "+(filtersOpen?"mobile-open":"mobile-collapsed")}><button type="button" className="secondary mobile-filter-toggle" aria-expanded={filtersOpen} onClick={()=>setFiltersOpen(value=>!value)}>{filtersOpen?"Close filters":"Filters"}</button>
        <Search/><input aria-label="Search transactions" placeholder="Search descriptions or merchants" value={q} onChange={e=>setQ(e.target.value)}/>
        <SearchPicker className="filter-search-picker" ariaLabel="Filter by account" value={accountId} options={accountOptions} placeholder="All accounts" searchPlaceholder="Search accounts by name or last four…" onChange={next=>{setAccountId(next);setSelected(new Set())}}/>
        <SearchPicker className="filter-search-picker" ariaLabel="Filter by category" value={categoryId} options={filterCategoryOptions} placeholder="All categories" searchPlaceholder="Search categories or accounts…" onChange={next=>{setCategoryId(next);setSelected(new Set())}}/>
        <select aria-label="Filter by segment" value={segmentId} onChange={e=>{setSegmentId(e.target.value);setSelected(new Set())}}><option value="">All {segmentSettings.data?.label||"segments"}</option>{segments.data?.map(segment=><option key={segment.id} value={segment.id}>{segment.name}</option>)}</select>
        <label className="date-filter"><span>Selected date</span><input type="date" aria-label="Filter by selected date" value={selectedDate} onChange={e=>{setSelectedDate(e.target.value);if(e.target.value){setDateFrom("");setDateTo("")}setSelected(new Set())}}/></label><span className="date-filter-or">or</span>
        <label className="date-filter"><span>From</span><input type="date" aria-label="Filter from date" value={dateFrom} onChange={e=>{setDateFrom(e.target.value);if(e.target.value)setSelectedDate("");setSelected(new Set())}}/></label>
        <label className="date-filter"><span>To</span><input type="date" aria-label="Filter to date" value={dateTo} onChange={e=>{setDateTo(e.target.value);if(e.target.value)setSelectedDate("");setSelected(new Set())}}/></label>
        {(selectedDate||dateFrom||dateTo)&&<button type="button" onClick={()=>{setSelectedDate("");setDateFrom("");setDateTo("");setSelected(new Set())}}>Clear dates</button>}
        {q&&<button type="button" className="active-filter" onClick={()=>{setQ("");setSelected(new Set())}}>Description: {q} ×</button>}
        {activeCategory&&<button type="button" className="active-filter" onClick={()=>{setCategoryId("");setSelected(new Set())}}>Category: {activeCategory.name} ×</button>}
        {amount&&<button type="button" className="active-filter" onClick={()=>{setAmount("");setSelected(new Set())}}>Amount: <Money value={amount}/> ×</button>}
      </div>
      <div className="context-filter-hint">Right-click a description, date, category, or amount to filter matching transactions while keeping the filters above.</div>
      {dateFrom&&dateTo&&dateFrom>dateTo&&<div className="error-box transaction-error" role="alert">From date must be on or before To date.</div>}
      {selected.size>0&&<div className="bulk-category-bar"><CheckSquare/><strong>{selected.size} selected</strong><div className="bulk-selection-action"><SearchPicker className="bulk-search-picker" ariaLabel="Bulk category" value={bulkCategory} options={categoryOptions} placeholder="Choose category" searchPlaceholder="Search categories or accounts…" onChange={next=>{setBulkCategory(next);if(next==="__create__")openCreate([...selected],"unknown")}}/><button className="primary" disabled={!bulkCategory||bulkCategory==="__create__"||classify.isPending} onClick={()=>classify.mutate({ids:[...selected],next:bulkCategory})}>{classify.isPending?"Updating…":"Apply category"}</button></div><div className="bulk-selection-action"><SearchPicker className="bulk-segment-picker" ariaLabel={`Bulk ${segmentSettings.data?.label||"segment"}`} value={bulkSegment} options={segmentOptions} placeholder={`Choose ${segmentSettings.data?.label||"segment"}`} searchPlaceholder={`Search ${(segmentSettings.data?.label||"segments").toLowerCase()}…`} onChange={setBulkSegment}/><button className="secondary" disabled={!bulkSegment||assignSegment.isPending} onClick={()=>assignSegment.mutate({ids:[...selected],next:bulkSegment==="__unassigned__"?null:bulkSegment})}>{assignSegment.isPending?"Updating…":`Apply ${segmentSettings.data?.label||"segment"}`}</button></div><button className="text-button" onClick={()=>{setSelected(new Set());setBulkCategory("");setBulkSegment("")}}>Clear</button></div>}
      {error&&<div className="error-box transaction-error" role="alert">{error}</div>}
      {isLoading?<div className="skeleton-page"><div/><div/></div>:items.length?<div className="transaction-list">
        <div className="transaction-head"><input type="checkbox" aria-label="Select all visible transactions" checked={allSelected} onChange={toggleAll}/><span></span>{sortHeader("transaction","Transaction")}{sortHeader("date","Date")}{sortHeader("category","Category")}<span>{segmentSettings.data?.label||"Segment"}</span>{sortHeader("amount","Amount")}</div>
        {items.map(t=><div className={selected.has(t.id)?"transaction-row selected":"transaction-row"} key={t.id}>
          <input type="checkbox" aria-label={`Select ${t.merchant}`} checked={selected.has(t.id)} onChange={()=>toggle(t.id)}/>
          <span className="merchant-avatar">{t.merchant[0]||"?"}</span>
          <div className="context-filter-target" tabIndex={0} role="button" aria-label={`Filter by `} onKeyDown={e=>{if(e.key==="Enter"||e.key===" "){e.preventDefault();setQ(t.merchant)}}} title="Filter similar descriptions" onContextMenu={e=>{e.preventDefault();setQ(t.merchant);setSelected(new Set())}}><strong>{t.merchant}</strong><p>{t.description} {t.pending&&<em>Pending</em>} {t.is_transfer&&<em>Internal transfer</em>}</p><small>{accounts.data?.find(a=>a.id===t.account_id)?.name}</small></div>
          <span className="context-filter-target" title="Right-click to filter this date" onContextMenu={e=>{e.preventDefault();setSelectedDate(t.date);setDateFrom("");setDateTo("");setSelected(new Set())}}>{new Date(t.date+"T12:00").toLocaleDateString("en-US",{month:"short",day:"numeric",year:"numeric"})}</span>
          <div className="transaction-classification" onContextMenu={e=>{e.preventDefault();if(t.category_id)setCategoryId(t.category_id);setSelected(new Set())}}><SearchPicker className={t.category==="Uncategorized"?"category-search-picker review":"category-search-picker"} ariaLabel={"Category for "+t.merchant} value={t.category_id||""} options={t.direction==="credit"?creditCategoryOptions:debitCategoryOptions} placeholder={t.category||"Choose category"} searchPlaceholder="Search categories or accounts…" disabled={classify.isPending} onChange={next=>chooseCategory(next,[t.id],t.direction)}/>{matchContexts.data?.[t.id]?.matched?<span className="obligation-match matched" title="This posted transaction confirms the scheduled obligation"><b>Matched</b>{matchContexts.data[t.id].matched?.payee}</span>:matchContexts.data?.[t.id]?.suggestions[0]?<button type="button" className="obligation-match suggested" onClick={()=>openBillMatch(t)} title={matchContexts.data[t.id].suggestions[0].reason}><b>{matchContexts.data[t.id].suggestions[0].confidence} match</b>{matchContexts.data[t.id].suggestions[0].payee}</button>:matchContexts.data?.[t.id]?.options[0]&&postingCategories.find(category=>category.id===t.category_id)?.account_type==="expense"?<button type="button" className="obligation-match suggested manual" onClick={()=>openBillMatch(t)} title="Review a possible scheduled bill"><b>Review</b>Match bill</button>:null}</div>
          <select className="segment-select" aria-label="Transaction segment" value={t.segment_id||""} disabled={assignSegment.isPending} onChange={e=>assignSegment.mutate({ids:[t.id],next:e.target.value||null})}><option value="">Unassigned</option>{segments.data?.map(segment=><option key={segment.id} value={segment.id}>{segment.name}</option>)}</select>
          <strong className={`context-filter-target ${t.direction==="credit"?"transaction-credit":""}`} title="Right-click to filter this amount" onContextMenu={e=>{e.preventDefault();setAmount(t.amount);setSelected(new Set())}}>{t.direction==="credit"?"+":t.direction==="debit"?"−":""}<Money value={t.amount}/></strong>
        </div>)}
      </div>:<div className="empty compact"><h2>No transactions found</h2><p>{accountId||categoryId||q||amount||selectedDate||dateFrom||dateTo?"Try changing the account, category, or search filters.":"Open an account from the Accounts page and upload its statement."}</p></div>}
      {!!data&&data.total>0&&<div className="transaction-pagination"><span>Showing {(data.page-1)*data.page_size+1}–{Math.min(data.page*data.page_size,data.total)} of {data.total}</span><div><button className="secondary" disabled={page<=1||isLoading} onClick={()=>setPage(current=>Math.max(1,current-1))}>Previous</button><strong>Page {data.page} of {data.pages}</strong><button className="secondary" disabled={page>=data.pages||isLoading} onClick={()=>setPage(current=>Math.min(data.pages,current+1))}>Next</button></div></div>}
    </section>
    {duplicateMergeChoice&&<Dialog title="Merge duplicate transaction" onClose={()=>{if(!mergeDuplicate.isPending)setDuplicateMergeChoice(null)}} className="duplicate-merge-dialog"><div className="modal-head"><div><p className="eyebrow">Review duplicate</p><h2>Merge these transactions?</h2><p>Confirm which provider record should remain in your active transaction history.</p></div><button type="button" className="icon-button" aria-label="Close" disabled={mergeDuplicate.isPending} onClick={()=>setDuplicateMergeChoice(null)}><X/></button></div><div className="duplicate-merge-compare"><article className="duplicate-keep"><span>Keep</span><strong>{duplicateMergeChoice.keep.merchant}</strong><small>{new Date(duplicateMergeChoice.keep.date+"T12:00").toLocaleDateString()} · {duplicateMergeChoice.keep.data_source}</small><b>{duplicateMergeChoice.keep.direction==="credit"?"+":"−"}<Money value={duplicateMergeChoice.keep.amount}/></b></article><article className="duplicate-remove"><span>Remove duplicate</span><strong>{duplicateMergeChoice.duplicate.merchant}</strong><small>{new Date(duplicateMergeChoice.duplicate.date+"T12:00").toLocaleDateString()} · {duplicateMergeChoice.duplicate.data_source}</small><b>{duplicateMergeChoice.duplicate.direction==="credit"?"+":"−"}<Money value={duplicateMergeChoice.duplicate.amount}/></b></article></div><div className="whatif-note"><GitMerge/><p>The removed provider identity stays in the audit history and is blocked from reappearing during later syncs.</p></div>{mergeDuplicate.error&&<div className="error-box" role="alert">{mergeDuplicate.error.message}</div>}<div className="modal-actions"><button type="button" className="secondary" disabled={mergeDuplicate.isPending} onClick={()=>setDuplicateMergeChoice(null)}>Cancel</button><button type="button" className="danger-button" disabled={mergeDuplicate.isPending} onClick={()=>mergeDuplicate.mutate({keep:duplicateMergeChoice.keep.id,duplicate:duplicateMergeChoice.duplicate.id})}>{mergeDuplicate.isPending?"Merging…":"Merge duplicate"}</button></div></Dialog>}
    {matchingTransaction&&<Dialog title="Match scheduled obligation" onClose={()=>{setMatchingTransaction(null);setBillSearch("")}} className="match-dialog"><div className="modal-head"><div><p className="eyebrow">Categorize and reconcile</p><h2>Match this transaction</h2><p>Choose the bill this posted debit paid. Its accounting category remains independently editable.</p></div><button type="button" className="icon-button" aria-label="Close" onClick={()=>{setMatchingTransaction(null);setBillSearch("")}}><X/></button></div><div className="match-transaction-summary"><span>{matchingTransaction.merchant}<small>{new Date(matchingTransaction.date+"T12:00").toLocaleDateString()}</small></span><strong>−<Money value={matchingTransaction.amount}/></strong></div><label className="match-search"><Search/><input autoFocus aria-label="Search scheduled bills" placeholder="Search by bill, amount, or due date…" value={billSearch} onChange={event=>setBillSearch(event.target.value)}/><span>{visibleBillMatches.length} of {billMatchOptions.length}</span></label><div className="match-list">{visibleBillMatches.length?visibleBillMatches.map(row=><button type="button" className="match-row" key={row.payment_id} disabled={matchObligation.isPending} onClick={()=>matchObligation.mutate({paymentId:row.payment_id,transactionId:matchingTransaction.id})}><span><strong>{row.payee}</strong><small>Due {new Date(row.due_date+"T12:00").toLocaleDateString()} · planned <Money value={row.amount}/></small></span><span><small>{row.reason}</small><small className={"match-confidence "+row.confidence}>{row.confidence} confidence</small></span></button>):<div className="search-picker-empty">No scheduled bills match “{billSearch}”. Try the merchant name or amount.</div>}</div><p className="field-help">Matching marks the scheduled obligation paid; it does not move money or overwrite your category.</p></Dialog>}
    {createContext&&<Dialog title="Create a category" onClose={()=>setCreateContext(null)}><form onSubmit={e=>{e.preventDefault();createCategory.mutate()}}>
      <div className="modal-head"><div><h2>Create a category</h2><p>It will appear in Settings and be applied to {createContext.ids.length} transaction{createContext.ids.length===1?"":"s"}.</p></div><button type="button" className="icon-button" aria-label="Close" onClick={()=>setCreateContext(null)}><X/></button></div>
      <label>Category name<input autoFocus value={newName} onChange={e=>setNewName(e.target.value)} placeholder="For example, Client hosting" required/></label>
      <label>Parent category<select value={newParent} onChange={e=>setNewParent(e.target.value)} required><option value="">Choose parent</option>{parentCategories.map(row=><option key={row.id} value={row.id}>{row.path}</option>)}</select></label>
      <div className="whatif-note"><Plus/><p>The parent determines whether this is an asset, liability, equity, income, or expense category.</p></div>
      <div className="modal-actions"><button type="button" className="secondary" onClick={()=>setCreateContext(null)}>Cancel</button><button className="primary" disabled={createCategory.isPending}>{createCategory.isPending?"Creating…":"Create and apply"}</button></div>
    </form></Dialog>}
  </>;
}
