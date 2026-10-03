"use client";
import { FormEvent, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Banknote,
  CalendarClock,
  Car,
  ChevronDown,
  CircleDollarSign,
  CreditCard,
  ExternalLink,
  HandCoins,
  Home,
  GitMerge,
  Pencil,
  PiggyBank,
  Plus,
  ReceiptText,
  Scale,
  Trash2,
  Upload,
  WalletCards,
  X,
} from "lucide-react";
import { Shell } from "@/components/shell";
import { Money } from "@/components/status";
import { Account, LedgerCategory, api } from "@/lib/api";
import { AccountOnboardingWizard } from "@/components/account-onboarding-wizard";
import { TransactionWorkspace } from "@/components/transaction-workspace";

const isInstallmentKind = (kind: string) =>
  ["mortgage", "auto_loan", "buy_now_pay_later", "loan", "other"].includes(
    kind,
  );
const assetKinds = ["checking", "savings", "money_market", "cash_management", "investment"];
const isAssetKind = (kind: string) => assetKinds.includes(kind);
const signedAmount = (account: Account) => {
  const value = isAssetKind(account.kind)
    ? ["cash_management", "investment"].includes(account.kind) ? account.balance : account.available_balance
    : account.balance;
  return isAssetKind(account.kind)
    ? Math.abs(Number(value))
    : -Math.abs(Number(value));
};
type TrialLine = {id:string;code:string;name:string;account_type:string;debit:string;credit:string};
type TrialBalance = {rows:TrialLine[]};
type AccountingGroup = "asset" | "liability" | "equity" | "income" | "expense";
type ImportResult = {
  detected_format: string;
  diagnostics: string[];
  added: number;
  duplicates: number;
  uncategorized: number;
  balance: string;
  available_balance: string;
  available_balance_updated: boolean;
  liability_statement_captured: boolean;
  balance_updated: boolean;
  balance_as_of_date: string | null;
  statement_end_date: string | null;
  balance_update_reason: string;
  missing_transactions: number;
  review_only: boolean;
  online_connected: boolean;
};
const accountVisual = (kind: string) =>
  kind === "checking"
    ? { Icon: WalletCards, tone: "asset" }
    : kind === "savings" || kind === "money_market"
      ? { Icon: PiggyBank, tone: "asset" }
      : kind === "investment" || kind === "cash_management"
        ? { Icon: CircleDollarSign, tone: "asset" }
        : kind === "credit_card"
          ? { Icon: CreditCard, tone: "liability" }
          : kind === "mortgage"
            ? { Icon: Home, tone: "liability" }
            : kind === "auto_loan"
              ? { Icon: Car, tone: "liability" }
              : kind === "buy_now_pay_later"
                ? { Icon: ReceiptText, tone: "liability" }
                : kind === "loan" || kind === "other"
                  ? { Icon: HandCoins, tone: "liability" }
                  : { Icon: Banknote, tone: "asset" };

export default function Accounts() {
  const initialParams=typeof window!=="undefined"?new URLSearchParams(window.location.search):new URLSearchParams();
  const qc = useQueryClient(),
    [selectedAccountId,setSelectedAccountId]=useState(initialParams.get("account_id")||""),
    [show, setShow] = useState(initialParams.get("add") === "manual"),
    [editing, setEditing] = useState<Account | null>(null),
    [deleting, setDeleting] = useState<Account | null>(null),
    [merging, setMerging] = useState<Account | null>(null),
    [mergeTargetId, setMergeTargetId] = useState(""),
    [expandedGroups, setExpandedGroups] = useState<Record<AccountingGroup, boolean>>({asset:true,liability:true,equity:false,income:false,expense:false}),
    [accountType, setAccountType] = useState("checking"),
    [error, setError] = useState(""),
    [uploadAccount, setUploadAccount] = useState<Account | null>(null),
    [onboarding, setOnboarding] = useState(false),
    [importResult, setImportResult] = useState<ImportResult | null>(null);
  const { data = [] } = useQuery({
    queryKey: ["accounts"],
    queryFn: () => api<Account[]>("/api/v1/accounts"),
  });
  const {data:ledgerCategories=[]}=useQuery({queryKey:["ledger-categories"],queryFn:()=>api<LedgerCategory[]>("/api/v1/accounting/categories")});
  const today=new Date().toISOString().slice(0,10);
  const {data:trial}=useQuery({queryKey:["report-tb",today],queryFn:()=>api<TrialBalance>("/api/v1/accounting/reports/trial-balance?as_of="+today)});
  const toggleGroup=(group:AccountingGroup)=>setExpandedGroups(current=>({...current,[group]:!current[group]}));
  const assetTotal = data
    .filter((a) => isAssetKind(a.kind))
    .reduce((sum, a) => sum + Math.abs(Number(["cash_management", "investment"].includes(a.kind) ? a.balance : a.available_balance)), 0);
  const liabilityTotal = data
    .filter((a) => !isAssetKind(a.kind))
    .reduce((sum, a) => sum + Math.abs(Number(a.balance)), 0);
  const netTotal = assetTotal - liabilityTotal;
  const save = useMutation({
    mutationFn: ({
      path,
      method,
      body,
    }: {
      path: string;
      method: string;
      body: object;
    }) => api(path, { method, body: JSON.stringify(body) }),
    onSuccess: () => {
      setShow(false);
      setEditing(null);
      setError("");
      qc.invalidateQueries({ queryKey: ["accounts"] });
    },
    onError: (e) => setError(e.message),
  });
  const upload = useMutation({
    mutationFn: (body: FormData) =>
      api<ImportResult>("/api/v1/statements/import", { method: "POST", body }),
    onSuccess: (r) => {
      setImportResult(r);
      qc.invalidateQueries({ queryKey: ["accounts"] });
      qc.invalidateQueries({ queryKey: ["transactions"] });
    },
    onError: (e) => setError(e.message),
  });
  const remove = useMutation({
    mutationFn: (id: string) =>
      api(`/api/v1/accounts/${id}`, { method: "DELETE" }),
    onSuccess: () => {
      setDeleting(null);
      qc.invalidateQueries({ queryKey: ["accounts"] });
      qc.invalidateQueries({ queryKey: ["today"] });
      qc.invalidateQueries({ queryKey: ["payments"] });
    },
    onError: (e) => setError(e.message),
  });
  const merge = useMutation({
    mutationFn: ({survivorId, duplicateId}: {survivorId:string; duplicateId:string}) =>
      api<{account_id:string;archived_account_id:string}>("/api/v1/accounts/merge", {method:"POST",body:JSON.stringify({survivor_account_id:survivorId,duplicate_account_id:duplicateId})}),
    onSuccess: (result) => {
      setMerging(null);
      setMergeTargetId("");
      setSelectedAccountId(result.account_id);
      setError("");
      qc.invalidateQueries({queryKey:["accounts"]});
      qc.invalidateQueries({queryKey:["transactions"]});
      qc.invalidateQueries({queryKey:["payments"]});
      qc.invalidateQueries({queryKey:["liabilities"]});
      qc.invalidateQueries({queryKey:["ledger-categories"]});
    },
    onError: (e) => setError(e.message),
  });
  function open(account: Account | null = null) {
    setEditing(account);
    setAccountType(account?.kind || "checking");
    setError("");
    setShow(true);
  }
  function importStatement(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError("");
    setImportResult(null);
    const body = new FormData(e.currentTarget);
    if (!String(body.get("ending_balance") || "").trim())
      body.delete("ending_balance");
    if (uploadAccount?.connection_id) {
      body.set(
        "transaction_mode",
        importResult?.review_only && importResult.missing_transactions > 0
          ? "import_missing"
          : "review",
      );
    }
    upload.mutate(body);
  }
  function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const v = Object.fromEntries(new FormData(e.currentTarget));
    const mortgage = v.kind === "mortgage",
      credit = v.kind === "credit_card",
      installment = isInstallmentKind(String(v.kind));
    const body = {
      name: v.name,
      kind: v.kind,
      mask: v.mask,
      balance: v.balance,
      available_balance: installment ? "0" : v.available_balance,
      original_balance: mortgage ? v.original_balance : null,
      reserve: credit || installment ? "0" : v.reserve || "0",
      institution_name: v.institution_name,
      bank_login_url: v.bank_login_url,
      connection_mode: "manual",
    };
    save.mutate({
      path: editing ? `/api/v1/accounts/${editing.id}` : "/api/v1/accounts",
      method: editing ? "PUT" : "POST",
      body,
    });
  }
  const selectedAccount = data.find((account) => account.id === selectedAccountId);
  const uploadUsesOnlineFeed = Boolean(uploadAccount?.connection_id);
  return (
    <Shell>
      <div className="page-title">
        <div>
          <p className="eyebrow">Your money</p>
          <h1>Accounts</h1>
          <p className="subtitle">
            Browse the accounting tree, then expand an account or category for detail.
          </p>
        </div>
        <button className="primary" onClick={() => setOnboarding(true)}>
          <Plus size={17} />
          Add account
        </button>
      </div>
      <section className="accounts-total" aria-label="Account totals">
        <div>
          <span>Net total</span>
          <strong
            className={netTotal >= 0 ? "positive-amount" : "negative-amount"}
          >
            <Money value={netTotal} />
          </strong>
          <small>Assets minus liabilities</small>
        </div>
        <div>
          <span>Assets</span>
          <strong className="positive-amount">
            <Money value={assetTotal} />
          </strong>
        </div>
        <div>
          <span>Liabilities</span>
          <strong className="negative-amount">
            <Money value={-liabilityTotal} />
          </strong>
        </div>
      </section>
      <div className="accounts-workspace-grid">
        <aside className="accounts-master-pane">
          <button className={selectedAccountId?"all-accounts-choice":"all-accounts-choice selected"} onClick={()=>setSelectedAccountId("")}><span><strong>All accounts</strong><small>{data.length} accounts</small></span><strong><Money value={netTotal}/></strong></button>
      <section className="accounts-list">
        {(["asset","liability"] as const).map(group => {
          const groupAccounts=data.filter(account=>group==="asset"?isAssetKind(account.kind):!isAssetKind(account.kind));
          const groupTotal=group==="asset"?assetTotal:-liabilityTotal;
          const accountGroups=Object.entries(groupAccounts.reduce<Record<string,Account[]>>((groups,account)=>{const institution=account.institution_name?.trim()||"Other";(groups[institution]||=[]).push(account);return groups},{})).sort(([left],[right])=>left.localeCompare(right));
          const GroupIcon=group==="asset"?WalletCards:CreditCard;
          return <section className="account-tree-group flat-account-group" key={group}>
            <button className="account-tree-root flat-account-root" aria-expanded={expandedGroups[group]} onClick={()=>toggleGroup(group)}>
              <span className={"account-root-icon "+group}><GroupIcon/></span>
              <span><strong>{group==="asset"?"Assets":"Liabilities"}</strong><small>{groupAccounts.length} account{groupAccounts.length===1?"":"s"}</small></span>
              <strong className={group==="asset"?"positive-amount":"negative-amount"}><Money value={groupTotal}/></strong>
              <ChevronDown/>
            </button>
            {expandedGroups[group]&&<div className="flat-account-list">
              {accountGroups.map(([institution,accounts])=><div className="passive-institution-group" key={institution}>
                {accounts.length>1&&<div className="passive-institution-label"><Banknote/><strong>{institution}</strong></div>}
                {accounts.map((account)=>{
                  const {Icon,tone}=accountVisual(account.kind);
                  const amount=signedAmount(account);
                  return <button className={"compact-account-row"+(selectedAccountId===account.id?" selected":"")} key={account.id} onClick={()=>setSelectedAccountId(account.id)}>
                    <span className={"compact-account-icon "+tone}><Icon/></span>
                    <span title={account.name}>{account.name}</span>
                    <strong className={amount<0?"negative-amount":"positive-amount"}><Money value={amount}/></strong>
                  </button>;
                })}
              </div>)}
            </div>}
          </section>;
        })}
        {(["equity","income","expense"] as const).map(group=>{
          const rows=(trial?.rows||[]).filter(row=>row.account_type===group);
          const total=rows.reduce((sum,row)=>sum+(group==="expense"?Number(row.debit)-Number(row.credit):Number(row.credit)-Number(row.debit)),0);
          const categories=ledgerCategories.filter(row=>row.account_type===group&&row.depth>1&&!row.code.startsWith("FA-"));
          const RootIcon=group==="equity"?Scale:group==="income"?Banknote:ReceiptText;
          const title=group==="equity"?"Equity":group==="income"?"Income":"Expenses";
          return <section className="account-tree-group" key={group}>
            <button className="account-tree-root" aria-expanded={expandedGroups[group]} onClick={()=>toggleGroup(group)}>
              <span className={"account-root-icon "+group}><RootIcon/></span>
              <span><strong>{title}</strong><small>{categories.length} categories</small></span>
              <strong><Money value={total}/></strong>
              <ChevronDown/>
            </button>
            {expandedGroups[group]&&<div className="ledger-tree-children">
              {categories.map(category=>{const balance=rows.find(row=>row.id===category.id);const amount=balance?(group==="expense"?Number(balance.debit)-Number(balance.credit):Number(balance.credit)-Number(balance.debit)):0;return <div className={"ledger-tree-row depth-"+category.depth} key={category.id}><span><i>{category.code}</i><strong>{category.name}</strong></span><Money value={amount}/></div>})}
            </div>}
          </section>
        })}
      </section>
        </aside>
        <section className="account-activity-pane">
          <TransactionWorkspace
            embedded
            selectedAccountId={selectedAccountId}
            onAccountChange={setSelectedAccountId}
            accountActions={selectedAccount ? <>
              <a className="secondary" href={"/accounts/"+selectedAccount.id+"/history"}><CalendarClock/>History</a>
              <a className="secondary" href={"/accounts/"+selectedAccount.id+"/reconcile"}><Scale/>Reconcile</a>
              <button className="secondary" type="button" onClick={()=>{setError("");setImportResult(null);setUploadAccount(selectedAccount)}}><Upload/>Import</button>
              <button className="secondary" type="button" onClick={()=>open(selectedAccount)}><Pencil/>Edit</button>
              <button className="secondary" type="button" onClick={()=>{const suggested=data.find(account=>account.id!==selectedAccount.id&&account.kind===selectedAccount.kind&&account.mask===selectedAccount.mask);setError("");setMergeTargetId(suggested?.id||"");setMerging(selectedAccount)}}><GitMerge/>Merge</button>
              <button className="secondary danger-action" type="button" onClick={()=>{setError("");setDeleting(selectedAccount)}}><Trash2/>Delete</button>
              {selectedAccount.bank_login_url
                ? <a className="primary" href={selectedAccount.bank_login_url} target="_blank" rel="noreferrer"><ExternalLink/>Open bank</a>
                : <button className="primary" type="button" onClick={()=>open(selectedAccount)}><ExternalLink/>Add bank website</button>}
            </> : undefined}
          />
        </section>
      </div>
      {show && (
        <div className="modal-backdrop">
          <form className="modal account-modal" onSubmit={submit}>
            <div className="modal-head">
              <div>
                <p className="eyebrow">Manual account</p>
                <h2>{editing ? `Edit ${editing.name}` : "Add an account"}</h2>
                <p>No usernames, passwords, or MFA codes are stored.</p>
              </div>
              <button
                type="button"
                className="icon-button"
                aria-label="Close"
                onClick={() => setShow(false)}
              >
                <X />
              </button>
            </div>
            <label>
              Account name
              <input
                name="name"
                required
                maxLength={100}
                defaultValue={editing?.name || ""}
                placeholder="Everyday Checking"
              />
            </label>
            <div className="form-grid">
              <label>
                Account type
                <select
                  name="kind"
                  value={accountType}
                  onChange={(e) => setAccountType(e.target.value)}
                >
                  <option value="checking">Checking</option>
                  <option value="savings">Savings</option>
                  <option value="credit_card">Credit card</option>
                  <option value="money_market">Money market</option>
                  <option value="cash_management">Cash management</option>
                  <option value="mortgage">Mortgage</option>
                  <option value="auto_loan">Auto loan</option>
                  <option value="buy_now_pay_later">
                    Buy now, pay later (Affirm)
                  </option>
                  <option value="loan">Personal / other loan</option>
                  <option value="investment">Investment</option>
                  <option value="other">Other</option>
                </select>
              </label>
              <label>
                Last 2–4 characters
                <input
                  name="mask"
                  required
                  minLength={2}
                  maxLength={4}
                  pattern="[A-Za-z0-9]{2,4}"
                  defaultValue={editing?.mask || ""}
                  placeholder="2048"
                />
              </label>
            </div>
            {accountType === "credit_card" ? (
              <>
                <div className="form-grid">
                  <label>
                    Current balance
                    <input
                      name="balance"
                      required
                      type="number"
                      min="0"
                      step="0.01"
                      defaultValue={editing?.balance || ""}
                    />
                  </label>
                  <label>
                    Available credit
                    <input
                      name="available_balance"
                      required
                      type="number"
                      min="0"
                      step="0.01"
                      defaultValue={editing?.available_balance || ""}
                    />
                  </label>
                </div>
                <p className="field-help">
                  Protected reserve does not apply to credit-card accounts.
                </p>
              </>
            ) : accountType === "mortgage" ? (
              <>
                <div className="form-grid">
                  <label>
                    Original mortgage amount
                    <input
                      name="original_balance"
                      required
                      type="number"
                      min="0"
                      step="0.01"
                      defaultValue={editing?.original_balance || ""}
                    />
                  </label>
                  <label>
                    Current mortgage balance
                    <input
                      name="balance"
                      required
                      type="number"
                      min="0"
                      step="0.01"
                      defaultValue={editing?.balance || ""}
                    />
                  </label>
                </div>
                <p className="field-help">
                  Available balance and protected reserve do not apply to
                  mortgage accounts.
                </p>
              </>
            ) : isInstallmentKind(accountType) ? (
              <>
                <div className="form-grid single-field">
                  <label>
                    Current outstanding balance
                    <input
                      name="balance"
                      required
                      type="number"
                      min="0"
                      step="0.01"
                      defaultValue={editing?.balance || ""}
                    />
                  </label>
                </div>
                <p className="field-help">
                  Available balance, available credit, and protected reserve do
                  not apply to installment debt.
                </p>
              </>
            ) : (
              <>
                <div className="form-grid">
                  <label>
                    Current balance
                    <input
                      name="balance"
                      required
                      type="number"
                      min="0"
                      step="0.01"
                      defaultValue={editing?.balance || ""}
                    />
                  </label>
                  <label>
                    Available balance
                    <input
                      name="available_balance"
                      required
                      type="number"
                      min="0"
                      step="0.01"
                      defaultValue={editing?.available_balance || ""}
                    />
                  </label>
                </div>
                <label>
                  Protected reserve
                  <input
                    name="reserve"
                    type="number"
                    min="0"
                    step="0.01"
                    defaultValue={editing?.reserve || "0"}
                  />
                </label>
              </>
            )}
            <label>
              Bank or institution name
              <input
                name="institution_name"
                required
                maxLength={120}
                defaultValue={editing?.institution_name || ""}
                placeholder="Example: Chase"
              />
            </label>
            <label>
              Public bank login URL
              <input
                name="bank_login_url"
                required
                type="url"
                pattern="https://.*"
                defaultValue={editing?.bank_login_url || ""}
                placeholder="https://www.examplebank.com/"
              />
              <span className="muted">
                HTTPS links only. Never put credentials in this URL.
              </span>
            </label>
            {error && (
              <div className="error-box" role="alert">
                {error}
              </div>
            )}
            <button className="primary wide" disabled={save.isPending}>
              {save.isPending
                ? "Saving…"
                : editing
                  ? "Save changes"
                  : "Add account"}
            </button>
          </form>
        </div>
      )}
      {uploadAccount && (
        <div className="modal-backdrop">
          <form className="modal" onSubmit={importStatement}>
            <div className="modal-head">
              <div>
                <p className="eyebrow">Statement import</p>
                <h2>Upload {uploadAccount.name} statement</h2>
                <p>
                  Download PDF, CSV, QBO, QBX, QFX, or OFX from the bank
                  website, then import it here.
                </p>
              </div>
              <button
                type="button"
                className="icon-button"
                aria-label="Close"
                onClick={() => setUploadAccount(null)}
              >
                <X />
              </button>
            </div>
            <input type="hidden" name="account_id" value={uploadAccount.id} />
            {uploadUsesOnlineFeed && (
              <div className="whatif-note">
                <p>
                  This account downloads transactions through {uploadAccount.connection_provider === "simplefin" ? "SimpleFIN" : uploadAccount.connection_provider || "its online connection"}. FinLeash will compare the statement first and will not add transactions until you approve any missing items.
                </p>
              </div>
            )}
            <label>
              Closing balance override
              <input
                name="ending_balance"
                type="number"
                min="0"
                step="0.01"
                placeholder="Only if it cannot be read from the statement"
              />
              <span className="muted">
                Usually detected automatically. Enter only to correct or supply
                a missing balance.
              </span>
            </label>
            <label className="file-input">
              <Upload />
              Choose PDF, QBO, QBX, QFX, OFX, or CSV
              <input
                name="file"
                type="file"
                required
                accept=".pdf,.csv,.ofx,.qfx,.qbo,.qbx"
              />
            </label>
            {error && (
              <div className="error-box" role="alert">
                {error}
              </div>
            )}
            {importResult && (
              <div className="import-result">
                <strong>
                  {importResult.review_only ? "Statement reviewed" : "Import complete"} · {importResult.detected_format.toUpperCase()}
                </strong>
                {importResult.review_only ? (
                  <p>
                    {importResult.duplicates} already in the online feed · {importResult.missing_transactions}{" "}
                    not found online · no statement transactions added
                  </p>
                ) : (
                  <p>
                    {importResult.added} added · {importResult.duplicates}{" "}
                    duplicates skipped · {importResult.uncategorized} need review
                  </p>
                )}
                <p>
                  {importResult.balance_updated ? (
                    <>
                      Account balance updated to{" "}
                      <Money value={importResult.balance} /> as of{" "}
                      {importResult.balance_as_of_date
                        ? new Date(
                            importResult.balance_as_of_date + "T12:00:00",
                          ).toLocaleDateString()
                        : "the statement date"}
                      .
                    </>
                  ) : importResult.balance_update_reason ===
                    "older_statement" ? (
                    <>
                      Balance remains{" "}
                      <Money value={importResult.balance} /> as of{" "}
                      {importResult.balance_as_of_date
                        ? new Date(
                            importResult.balance_as_of_date + "T12:00:00",
                          ).toLocaleDateString()
                        : "the newer statement"}{" "}
                      because this statement is older.
                    </>
                  ) : (
                    <>
                      No closing balance was found, so the account balance was unchanged.
                    </>
                  )}
                </p>
                {importResult.liability_statement_captured && (
                  <p>
                    Statement due date, minimum payment, and debt details were
                    added to Monthly Plan.
                  </p>
                )}
                {importResult.available_balance_updated && (
                  <p>
                    Available balance / credit updated to{" "}
                    <Money value={importResult.available_balance} />.
                  </p>
                )}
                {importResult.diagnostics.length > 0 && (
                  <div className="import-diagnostics">
                    <strong>Automatic recovery</strong>
                    {importResult.diagnostics.map((note) => (
                      <p key={note}>{note}</p>
                    ))}
                  </div>
                )}
              </div>
            )}
            {importResult?.review_only && importResult.missing_transactions === 0 ? (
              <button className="primary wide" type="button" onClick={() => setUploadAccount(null)}>
                Done
              </button>
            ) : (
              <button className="primary wide" disabled={upload.isPending}>
                {upload.isPending
                  ? "Analyzing and comparing…"
                  : importResult?.review_only
                    ? `Import ${importResult.missing_transactions} missing transaction${importResult.missing_transactions === 1 ? "" : "s"}`
                    : uploadUsesOnlineFeed
                      ? "Review statement"
                      : "Import and classify"}
              </button>
            )}
          </form>
        </div>
      )}
      {merging && (
        <div className="modal-backdrop">
          <section className="modal confirm-modal" role="dialog" aria-modal="true" aria-labelledby="merge-account-title">
            <div className="delete-icon"><GitMerge/></div>
            <div><h2 id="merge-account-title">Merge {merging.name}?</h2><p>Choose the account to keep. Transactions, statements, reconciliations, payment links, and any live provider connection will be consolidated. {merging.name} will then leave active views.</p></div>
            <label>Account to keep<select value={mergeTargetId} onChange={event=>setMergeTargetId(event.target.value)} required><option value="">Choose matching account</option>{data.filter(account=>account.id!==merging.id&&account.kind===merging.kind).map(account=><option key={account.id} value={account.id}>{account.name} · •••• {account.mask} · {account.connection_mode}</option>)}</select></label>
            {error&&<div className="error-box" role="alert">{error}</div>}
            <div className="modal-actions"><button className="secondary" onClick={()=>{setMerging(null);setMergeTargetId("")}}>Cancel</button><button className="danger-button" disabled={!mergeTargetId||merge.isPending} onClick={()=>merge.mutate({survivorId:mergeTargetId,duplicateId:merging.id})}>{merge.isPending?"Merging…":"Merge accounts"}</button></div>
          </section>
        </div>
      )}
      {deleting && (
        <div className="modal-backdrop">
          <section
            className="modal confirm-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="delete-account-title"
          >
            <div className="delete-icon">
              <Trash2 />
            </div>
            <div>
              <h2 id="delete-account-title">Delete {deleting.name}?</h2>
              <p>
                This removes the account from active views. Transaction history
                is retained, and scheduled payments using this account will need
                a new funding account.
              </p>
            </div>
            {error && (
              <div className="error-box" role="alert">
                {error}
              </div>
            )}
            <div className="modal-actions">
              <button className="secondary" onClick={() => setDeleting(null)}>
                Cancel
              </button>
              <button
                className="danger-button"
                disabled={remove.isPending}
                onClick={() => remove.mutate(deleting.id)}
              >
                {remove.isPending ? "Deleting…" : "Delete account"}
              </button>
            </div>
          </section>
        </div>
      )}
      {onboarding && <AccountOnboardingWizard onClose={()=>setOnboarding(false)} onManual={()=>open()} onComplete={()=>{setOnboarding(false);qc.invalidateQueries({queryKey:["accounts"]});qc.invalidateQueries({queryKey:["transactions"]});qc.invalidateQueries({queryKey:["monthly-plan"]})}}/>}
    </Shell>
  );
}
