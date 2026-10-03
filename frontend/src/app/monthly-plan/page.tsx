"use client";
import { FormEvent, useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import {
  ChevronLeft,
  ChevronRight,
  Download,
  ExternalLink,
  Plus,
  Pencil,
  Repeat2,
  Sparkles,
  X,
} from "lucide-react";
import { Shell } from "@/components/shell";
import {Dialog} from "@/components/dialog";
import { Money } from "@/components/status";
import { API, api } from "@/lib/api";

type PlanRow = {
  id: string;
  group: string;
  account_name: string;
  account_kind: string;
  due_date: string | null;
  paid_status: string;
  current_balance: string | null;
  statement_balance: string | null;
  statement_date: string | null;
  minimum_payment: string;
  scheduled_date: string | null;
  paid_date: string | null;
  status_source: string | null;
  payment_amount: string;
  balance_after_payment: string | null;
  funding_account_id: string | null;
  payment_id: string | null;
  biller_website_url?: string | null;
  biller_contact?: BillerSuggestion | null;
  bill_payment_method?: string | null;
};
type BillerSuggestion = {id:string;name:string;website_url:string;domains:string[];support_url:string|null;chat_url:string|null;customer_service_phone:string|null;confidence:string;verified:boolean};
type BillCandidate = {
  id: string;
  name: string;
  merchant_pattern: string;
  account_id: string;
  account_name: string;
  typical_amount: string;
  last_amount: string;
  last_paid: string;
  next_date: string;
  frequency: string;
  occurrences: number;
  confidence: string;
  amount_type: string;
  category: string;
  biller_suggestion: BillerSuggestion | null;
};
type PlanAccount = {
  id: string;
  name: string;
  kind: string;
  institution_name: string | null;
  bank_login_url: string | null;
};
type ExistingBill = {id:string;name:string;merchant_pattern:string;category:string;bill_type:string;amount_type:string;typical_amount:string;frequency:string;due_day:number;default_account_id:string|null;website_url:string|null;biller_id:string|null;payment_method:string;remaining_balance:string|null;installments_remaining:number|null};
type RecurringCharge={id:string;name:string;merchant_pattern:string;account_id:string;account_name:string;account_kind?:string;typical_amount:string;last_charge:string;next_expected:string;frequency:string;occurrences:number;confidence:string;annual_cost:string;suggested_type?:"subscription"|"recurring_bill";series_type?:"subscription"|"recurring_bill";reason?:string};
type RecurringOverview={candidates:RecurringCharge[];confirmed:RecurringCharge[];annual_subscription_cost:string;review_count:number};
type PlanData = {
  month: string;
  starting_available_cash: string;
  planned_payments: string;
  outstanding_debt: string;
  unscheduled_count: number;
  accounts: PlanAccount[];
  income: {
    id: string;
    name: string;
    date: string;
    amount: string;
    reliability: string;
    account_id: string;
  }[];
  rows: PlanRow[];
};
type MatchCandidate={id:string;merchant:string;description:string;amount:string;date:string;account_id:string;account_name:string;account_matches:boolean;score:number;confidence:"high"|"medium"|"low";reason:string};
type PaymentBody = {
  payment_id: string | null;
  obligation_account_id: string | null;
  checking_account_id: string;
  due_date: string;
  scheduled_date: string;
  amount: number;
  status: string;
  paid_date: string | null;
  confirmation_number: string | null;
};
const formatDate = (value: string | null) =>
  value
    ? new Date(value + "T12:00:00").toLocaleDateString("en-US", {
        month: "short",
        day: "numeric",
      })
    : "—";
const statusCode = (value: string) =>
  value === "paid" || value === "cleared"
    ? "P"
    : value === "not_planned" || value === "not_scheduled"
      ? "NP"
      : value === "awaiting_confirmation"
        ? "S · Confirm"
        : "S";
export default function Plan() {
  const focusHandled=useRef(false);
  const router=useRouter();
  const qc = useQueryClient(),
    now = new Date(),
    [month, setMonth] = useState(
      `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`,
    ),
    [editing, setEditing] = useState<PlanRow | null>(null),
    [matching,setMatching]=useState<PlanRow|null>(null),
    [paymentStatus, setPaymentStatus] = useState("scheduled"),
    [fundingId, setFundingId] = useState(""),
    [billPickerOpen, setBillPickerOpen] = useState(false),
    [billCandidateQuery, setBillCandidateQuery] = useState(""),
    [editingBill, setEditingBill] = useState<{bill:ExistingBill;dueDate:string}|null>(null),
    [editBillWebsite, setEditBillWebsite] = useState(""),
    [editBillerSuggestion, setEditBillerSuggestion] = useState<BillerSuggestion|null>(null),
    [useEditSuggestedBiller, setUseEditSuggestedBiller] = useState(false),
    [editPaymentMethod, setEditPaymentMethod] = useState("manual_online"),
    [billDraft, setBillDraft] = useState<BillCandidate | "manual" | null>(null),
    [billType, setBillType] = useState("recurring"),
    [billPaymentMethod, setBillPaymentMethod] = useState("manual_online"),
    [billName, setBillName] = useState(""),
    [billWebsite, setBillWebsite] = useState(""),
    [billerSuggestion, setBillerSuggestion] = useState<BillerSuggestion | null>(null),
    [useSuggestedBiller, setUseSuggestedBiller] = useState(false),
    [errorMessage, setErrorMessage] = useState("");
  const [yearValue, monthValue] = month.split("-").map(Number);
  const { data, isLoading, error } = useQuery({
    queryKey: ["monthly-plan", month],
    queryFn: () =>
      api<PlanData>(
        `/api/v1/monthly-plan?year=${yearValue}&month=${monthValue}`,
      ),
  });
  const { data: billCandidates = [] } = useQuery({
    queryKey: ["bill-candidates"],
    queryFn: () => api<BillCandidate[]>("/api/v1/bills/candidates"),
  });
  const { data: bills = [] } = useQuery({queryKey:["bills"],queryFn:()=>api<ExistingBill[]>("/api/v1/bills")});
  const {data:recurring={candidates:[],confirmed:[],annual_subscription_cost:"0",review_count:0}}=useQuery({queryKey:["recurring-charges"],queryFn:()=>api<RecurringOverview>("/api/v1/recurring-charges")});
  const matchCandidates=useQuery({queryKey:["payment-match-candidates",matching?.payment_id],queryFn:()=>api<MatchCandidate[]>("/api/v1/payments/"+matching!.payment_id+"/match-candidates"),enabled:!!matching?.payment_id});
  useEffect(()=>{
    if(!data||focusHandled.current)return;
    const params=new URLSearchParams(window.location.search);
    const requestedMonth=params.get("month");
    if(requestedMonth&&requestedMonth!==month){const frame=window.requestAnimationFrame(()=>setMonth(requestedMonth));return()=>window.cancelAnimationFrame(frame)}
    const paymentId=params.get("payment");
    if(!paymentId)return;
    const target=data.rows.find(row=>row.payment_id===paymentId);
    if(!target)return;
    focusHandled.current=true;
    const frame=window.requestAnimationFrame(()=>{document.getElementById("payment-"+paymentId)?.scrollIntoView({behavior:"smooth",block:"center"});if(params.get("action")==="match"&&target.payment_id&&!["paid","cleared"].includes(target.paid_status)){setErrorMessage("");setMatching(target)}});
    return()=>window.cancelAnimationFrame(frame);
  },[data,month]);
  function closeMatching(){const returnTo=new URLSearchParams(window.location.search).get("returnTo");setMatching(null);if(returnTo&&returnTo.startsWith("/")&&!returnTo.startsWith("//"))router.replace(returnTo)}
  const matchPayment=useMutation({mutationFn:(candidate:MatchCandidate)=>api("/api/v1/payments/"+matching!.payment_id+"/reconcile",{method:"POST",body:JSON.stringify({transaction_id:candidate.id,confirm_account_change:!candidate.account_matches})}),onSuccess:()=>{closeMatching();setErrorMessage("");qc.invalidateQueries({queryKey:["monthly-plan"]});qc.invalidateQueries({queryKey:["today"]});qc.invalidateQueries({queryKey:["audit-events"]})},onError:e=>setErrorMessage(e.message)});
  const addBill = useMutation({
    mutationFn: (body: Record<string, unknown>) =>
      api<{ id: string }>("/api/v1/bills", { method: "POST", body: JSON.stringify(body) }),
    onSuccess: () => {
      setBillDraft(null);
      setErrorMessage("");
      qc.invalidateQueries({ queryKey: ["bill-candidates"] });
      qc.invalidateQueries({ queryKey: ["monthly-plan"] });
      qc.invalidateQueries({ queryKey: ["today"] });
    },
    onError: (e) => setErrorMessage(e.message),
  });
  const saveBill = useMutation({
    mutationFn:({id,body}:{id:string;body:Record<string,unknown>})=>api(`/api/v1/bills/${id}`,{method:"PUT",body:JSON.stringify(body)}),
    onSuccess:()=>{setEditingBill(null);setErrorMessage("");qc.invalidateQueries({queryKey:["bills"]});qc.invalidateQueries({queryKey:["monthly-plan"]});qc.invalidateQueries({queryKey:["today"]});},
    onError:(e)=>setErrorMessage(e.message),
  });
  const ignoreBill = useMutation({
    mutationFn: (merchant_pattern: string) => api("/api/v1/bills/candidates/ignore", { method: "POST", body: JSON.stringify({ merchant_pattern }) }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["bill-candidates"] }),
    onError: (e) => setErrorMessage(e.message),
  });
  const reviewRecurring=useMutation({mutationFn:({row,decision}:{row:RecurringCharge;decision:"subscription"|"recurring_bill"|"dismissed"})=>api("/api/v1/recurring-charges/decision",{method:"POST",body:JSON.stringify({account_id:row.account_id,merchant_pattern:row.merchant_pattern,decision})}),onSuccess:()=>{setErrorMessage("");qc.invalidateQueries({queryKey:["recurring-charges"]});qc.invalidateQueries({queryKey:["today"]})},onError:e=>setErrorMessage(e.message)});
  const findBiller = useMutation({
    mutationFn: (name:string) => api<BillerSuggestion[]>(`/api/v1/billers?q=${encodeURIComponent(name)}`),
    onSuccess: (matches) => { setBillerSuggestion(matches[0] || null); setUseSuggestedBiller(false); },
    onError: (e) => setErrorMessage(e.message),
  });
  const findEditBiller = useMutation({
    mutationFn:(name:string)=>api<BillerSuggestion[]>(`/api/v1/billers?q=${encodeURIComponent(name)}`),
    onSuccess:(matches)=>{setEditBillerSuggestion(matches[0]||null);setUseEditSuggestedBiller(false);},
    onError:(e)=>setErrorMessage(e.message),
  });
  const save = useMutation({
    mutationFn: (body: PaymentBody) =>
      api<{ id: string }>("/api/v1/monthly-plan/payment", {
        method: "PUT",
        body: JSON.stringify(body),
      }),
    onSuccess: () => {
      setEditing(null);
      setErrorMessage("");
      qc.invalidateQueries({ queryKey: ["monthly-plan"] });
      qc.invalidateQueries({ queryKey: ["today"] });
    },
    onError: (e) => setErrorMessage(e.message),
  });
  function move(delta: number) {
    const next = new Date(yearValue, monthValue - 1 + delta, 1);
    setMonth(
      `${next.getFullYear()}-${String(next.getMonth() + 1).padStart(2, "0")}`,
    );
  }
  function openPayment(row: PlanRow) {
    const checking =
      data?.accounts.find((a) => a.id === row.funding_account_id) ||
      data?.accounts.find((a) => a.kind === "checking");
    setFundingId(checking?.id || "");
    setPaymentStatus(
      row.paid_status === "paid" || row.paid_status === "cleared"
        ? "paid"
        : row.paid_status === "not_planned"
          ? "not_planned"
          : "scheduled",
    );
    setErrorMessage("");
    setEditing(row);
  }
  function submitPayment(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!editing) return;
    const values = new FormData(event.currentTarget);
    save.mutate({
      payment_id: editing.payment_id,
      obligation_account_id:
        editing.account_kind === "expense" ? null : editing.id,
      checking_account_id: String(values.get("checking_account_id")),
      due_date: String(values.get("due_date")),
      scheduled_date: String(values.get("scheduled_date")),
      amount: Number(values.get("amount")),
      status: String(values.get("status")),
      paid_date:
        paymentStatus === "paid" ? String(values.get("paid_date")) : null,
      confirmation_number:
        String(values.get("confirmation_number") || "").trim() || null,
    });
  }
  function submitBill(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const values = new FormData(event.currentTarget);
    addBill.mutate({
      name: String(values.get("name")),
      merchant_pattern: String(values.get("merchant_pattern") || values.get("name")),
      category: String(values.get("category")),
      bill_type: String(values.get("bill_type")),
      amount_type: String(values.get("amount_type")),
      typical_amount: Number(values.get("typical_amount")),
      frequency: String(values.get("frequency")),
      due_date: String(values.get("due_date")),
      default_account_id: String(values.get("default_account_id") || "") || null,
      website_url: billWebsite || null,
      biller_id: useSuggestedBiller ? billerSuggestion?.id || null : null,
      payment_method: billPaymentMethod,
      remaining_balance: values.get("remaining_balance") ? Number(values.get("remaining_balance")) : null,
      installments_remaining: values.get("installments_remaining") ? Number(values.get("installments_remaining")) : null,
    });
  }
  function submitBillEdit(event:FormEvent<HTMLFormElement>){
    event.preventDefault();if(!editingBill)return;const values=new FormData(event.currentTarget);
    saveBill.mutate({id:editingBill.bill.id,body:{name:String(values.get("name")),merchant_pattern:editingBill.bill.merchant_pattern,category:String(values.get("category")),bill_type:String(values.get("bill_type")),amount_type:String(values.get("amount_type")),typical_amount:Number(values.get("typical_amount")),frequency:String(values.get("frequency")),due_date:String(values.get("due_date")),default_account_id:String(values.get("default_account_id")||"")||null,website_url:editBillWebsite||null,biller_id:useEditSuggestedBiller?editBillerSuggestion?.id||null:editingBill.bill.biller_id,payment_method:editPaymentMethod,remaining_balance:values.get("remaining_balance")?Number(values.get("remaining_balance")):null,installments_remaining:values.get("installments_remaining")?Number(values.get("installments_remaining")):null}});
  }
  function openBill(draft:BillCandidate|"manual") {
    setBillPickerOpen(false);
    setBillDraft(draft);setBillType("recurring");setBillPaymentMethod("manual_online");setErrorMessage("");
    setBillName(draft==="manual"?"":draft.name);setBillWebsite("");
    setBillerSuggestion(draft==="manual"?null:draft.biller_suggestion);setUseSuggestedBiller(false);
  }
  const monthLabel = new Date(yearValue, monthValue - 1, 1).toLocaleDateString(
      "en-US",
      { month: "long", year: "numeric" },
    ),
    checkingAccounts =
      data?.accounts.filter((a) => ["checking", "cash_management"].includes(a.kind)) || [],
    selectedFunding = data?.accounts.find((a) => a.id === fundingId),
    creditor = data?.accounts.find((a) => a.id === editing?.id);
  const visibleBillCandidates = billCandidates.filter((candidate) => {
    const query = billCandidateQuery.trim().toLowerCase();
    return !query || `${candidate.name} ${candidate.category} ${candidate.frequency}`.toLowerCase().includes(query);
  });
  const visibleExistingBills = bills.filter((bill) => {
    const query=billCandidateQuery.trim().toLowerCase();
    return !query||`${bill.name} ${bill.merchant_pattern} ${bill.category}`.toLowerCase().includes(query);
  });
  function editExistingBill(bill:ExistingBill){
    const today=new Date(),next=new Date(today.getFullYear(),today.getMonth(),bill.due_day);
    if(next<new Date(today.getFullYear(),today.getMonth(),today.getDate()))next.setMonth(next.getMonth()+1);
    const dueDate=`${next.getFullYear()}-${String(next.getMonth()+1).padStart(2,"0")}-${String(next.getDate()).padStart(2,"0")}`;
    openExistingBillEditor(bill,dueDate);
  }
  function openExistingBillEditor(bill:ExistingBill,dueDate:string){
    setBillPickerOpen(false);setErrorMessage("");setEditingBill({bill,dueDate});
    setEditBillWebsite(bill.website_url||"");setEditBillerSuggestion(null);setUseEditSuggestedBiller(false);
    setEditPaymentMethod(bill.payment_method||"manual_online");
    findEditBiller.mutate(bill.name);
  }
  let group = "";
  return (
    <Shell>
      <div className="page-title">
        <div>
          <p className="eyebrow">Plan ahead</p>
          <h1>Monthly Payment Plan</h1>
          <p className="subtitle">
            {monthLabel} · Plan, schedule, and track your monthly bills and debt
            payments.
          </p>
        </div>
        <div className="month-actions">
          <div className="month-picker">
            <button aria-label="Previous month" onClick={() => move(-1)}>
              <ChevronLeft />
            </button>
            <strong>{monthLabel}</strong>
            <button aria-label="Next month" onClick={() => move(1)}>
              <ChevronRight />
            </button>
          </div>
          <a
            className="secondary"
            href={`${API}/api/v1/exports/monthly-plan.xlsx?year=${yearValue}&month=${monthValue}`}
          >
            <Download size={16} />
            Export Excel
          </a>
        </div>
      </div>
      {isLoading ? (
        <div className="skeleton-page">
          <div />
          <div />
        </div>
      ) : error || !data ? (
        <div className="empty">
          <h2>We couldn’t load this month</h2>
          <p>{error instanceof Error ? error.message : "Try again."}</p>
        </div>
      ) : (
        <>
          <section className="plan-summary">
            <article>
              <span>Starting available cash</span>
              <strong>
                <Money value={data.starting_available_cash} />
              </strong>
            </article>
            <article>
              <span>Total planned payments</span>
              <strong>
                <Money value={data.planned_payments} />
              </strong>
            </article>
            <article>
              <span>Total outstanding debt</span>
              <strong>
                <Money value={data.outstanding_debt} />
              </strong>
            </article>
            <article>
              <span>Not yet scheduled</span>
              <strong>{data.unscheduled_count}</strong>
            </article>
          </section>
          <section className="panel recurring-center" id="subscriptions">
            <div className="panel-head"><div><h2>Subscriptions & recurring charges</h2><p>Detected from posted activity. Confirm each suggestion before FinLeash treats it as recurring.</p></div><div className="recurring-summary"><span>{recurring.review_count} to review</span><strong><Money value={recurring.annual_subscription_cost}/> / year</strong></div></div>
            {errorMessage&&<div className="error-box recurring-error" role="alert">{errorMessage}</div>}
            {recurring.candidates.length>0&&<div className="recurring-section"><h3>Needs your review</h3>{recurring.candidates.map(row=><article className="recurring-row candidate" key={row.id}><span className="recurring-icon"><Repeat2/></span><div><strong>{row.name}</strong><p>{row.reason} · {row.account_name}</p><small>Last charged {formatDate(row.last_charge)} · next expected {formatDate(row.next_expected)}</small></div><div className="recurring-cost"><strong><Money value={row.typical_amount}/></strong><small>{row.frequency} · <Money value={row.annual_cost}/> yearly</small><span className={`match-confidence ${row.confidence}`}>{row.confidence} confidence</span></div><div className="recurring-actions"><button className="primary compact-button" disabled={reviewRecurring.isPending} onClick={()=>reviewRecurring.mutate({row,decision:"subscription"})}>Subscription</button><button className="secondary compact-button" disabled={reviewRecurring.isPending} onClick={()=>reviewRecurring.mutate({row,decision:"recurring_bill"})}>Recurring bill</button><button className="text-button" disabled={reviewRecurring.isPending} onClick={()=>reviewRecurring.mutate({row,decision:"dismissed"})}>Not recurring</button></div></article>)}</div>}
            {recurring.confirmed.length>0&&<div className="recurring-section confirmed"><h3>Confirmed</h3>{recurring.confirmed.map(row=><article className="recurring-row candidate confirmed-row" key={row.id}><span className="recurring-icon confirmed"><Repeat2/></span><div><strong>{row.name}</strong><p>{row.account_name} · {row.series_type==="subscription"?"Subscription":"Recurring bill"}</p><small>Last charged {formatDate(row.last_charge)} · next expected {formatDate(row.next_expected)}</small></div><div className="recurring-cost"><strong><Money value={row.typical_amount}/></strong><small>{row.frequency} · <Money value={row.annual_cost}/> yearly</small></div><div className="recurring-actions"><button className="secondary compact-button" disabled={reviewRecurring.isPending} onClick={()=>reviewRecurring.mutate({row,decision:row.series_type==="subscription"?"recurring_bill":"subscription"})}>{row.series_type==="subscription"?"Change to recurring bill":"Change to subscription"}</button><button className="text-button" disabled={reviewRecurring.isPending} onClick={()=>reviewRecurring.mutate({row,decision:"dismissed"})}>Stop tracking</button></div></article>)}</div>}
            {recurring.candidates.length===0&&recurring.confirmed.length===0&&<div className="empty compact"><Repeat2/><p>No recurring charges detected yet. FinLeash needs at least two consistent posted charges and remains conservative to avoid false matches.</p></div>}
          </section>
          <section className="panel table-panel">
            <div className="panel-head">
              <div>
                <h2>Monthly expenses and debt payments</h2>
                <p>
                  Due date is separate from the schedule and payment status.
                </p>
              </div>
              <button className="secondary" onClick={() => { setBillCandidateQuery(""); setBillPickerOpen(true); }}>
                <Plus size={16} /> Add bill
                {billCandidates.length > 0 && <span className="bill-count">{billCandidates.length}</span>}
              </button>
            </div>
            <div className="real-plan-table">
              <div className="real-plan-head">
                <span>Account</span>
                <span>Due</span>
                <span>Current balance</span>
                <span>Statement balance</span>
                <span>Minimum</span>
                <span>Schedule / status</span>
                <span>Payment</span>
                <span>After payment</span>
                <span></span>
              </div>
              {data.rows.map((row) => {
                const showGroup = group !== row.group;
                group = row.group;
                return (
                  <div key={row.id} id={row.payment_id?"payment-"+row.payment_id:undefined} className="payment-plan-anchor">
                    {showGroup && (
                      <div className="plan-group-row">{row.group}</div>
                    )}
                    <div className="real-plan-row">
                      <div>
                        <strong>{row.account_name}</strong>
                        <small>
                          {row.statement_date
                            ? `Statement ${formatDate(row.statement_date)}`
                            : row.account_kind.replaceAll("_", " ")}
                        </small>
                        {row.account_kind==="bill"&&row.bill_payment_method&&row.bill_payment_method!=="manual_online"&&<small className="autopay-note">{row.bill_payment_method==="company_autopay"?`Autopay · Company website · ${data.accounts.find((account)=>account.id===row.funding_account_id)?.name||"funding account"}`:row.bill_payment_method==="bank_bill_pay"?`Autopay · ${data.accounts.find((account)=>account.id===row.funding_account_id)?.institution_name||data.accounts.find((account)=>account.id===row.funding_account_id)?.name||"Bank"} bill pay`:`Paper check · ${data.accounts.find((account)=>account.id===row.funding_account_id)?.name||"funding account"}`}</small>}
                      </div>
                      <div>
                        <strong>{formatDate(row.due_date)}</strong>
                      </div>
                      <div>
                        {row.current_balance !== null ? (
                          <Money value={row.current_balance} />
                        ) : (
                          "—"
                        )}
                      </div>
                      <div>
                        {row.statement_balance !== null ? (
                          <Money value={row.statement_balance} />
                        ) : (
                          "—"
                        )}
                      </div>
                      <div>
                        <Money value={row.minimum_payment} />
                      </div>
                      <div className="schedule-status">
                        <span>{formatDate(row.scheduled_date)}</span>
                        <span
                          className={`obligation-status ${statusCode(row.paid_status) === "P" ? "paid" : statusCode(row.paid_status) === "NP" ? "missing" : "planned"}`}
                        >
                          {statusCode(row.paid_status)}
                        </span>
                        {row.paid_date && (
                          <small>Paid {formatDate(row.paid_date)}</small>
                        )}
                      </div>
                      <div>
                        <strong>
                          <Money value={row.payment_amount} />
                        </strong>
                      </div>
                      <div
                        className={
                          row.balance_after_payment !== null
                            ? "balance-after"
                            : ""
                        }
                      >
                        {row.balance_after_payment !== null ? (
                          <Money value={row.balance_after_payment} />
                        ) : (
                          "—"
                        )}
                      </div>
                      <div>
                        {row.account_kind === "bill" && bills.some((bill) => bill.id === row.id) && (
                          <button className="text-button row-edit-bill" onClick={() => { const bill=bills.find((item)=>item.id===row.id);if(bill)openExistingBillEditor(bill,row.due_date||`${month}-${String(bill.due_day).padStart(2,"0")}`); }}><Pencil size={13}/> Edit bill</button>
                        )}
                        <button className="secondary compact-button" onClick={() => openPayment(row)}>Payment</button>{row.payment_id&&!["paid","cleared"].includes(row.paid_status)&&<button className="text-button" onClick={()=>{setErrorMessage("");setMatching(row)}}>Match transaction</button>}
                      </div>
                    </div>
                  </div>
                );
              })}
              {data.rows.length === 0 && (
                <div className="empty compact">
                  <h2>No obligations found</h2>
                  <p>
                    Add liability accounts or scheduled payments, then upload
                    the latest statements.
                  </p>
                </div>
              )}
            </div>
          </section>
          {data.income.length > 0 && (
            <section className="panel income-panel">
              <div className="panel-head">
                <div>
                  <h2>Money expected</h2>
                  <p>Only real income entries for {monthLabel}</p>
                </div>
              </div>
              {data.income.map((item) => (
                <div className="income-row" key={item.id}>
                  <span className={`reliability ${item.reliability}`} />
                  <div>
                    <strong>{item.name}</strong>
                    <p>{item.reliability.replaceAll("_", " ")}</p>
                  </div>
                  <span>{formatDate(item.date)}</span>
                  <strong>
                    +<Money value={item.amount} />
                  </strong>
                </div>
              ))}
            </section>
          )}
        </>
      )}
      {billPickerOpen && (
        <div className="modal-backdrop">
          <div className="modal bill-picker-modal" role="dialog" aria-modal="true" aria-labelledby="bill-picker-title">
            <div className="modal-head">
              <div><p className="eyebrow">Add billing account</p><h2 id="bill-picker-title">Choose a detected bill</h2><p>Review a recurring payment, or enter a bill yourself.</p></div>
              <button type="button" className="icon-button" aria-label="Close" onClick={() => setBillPickerOpen(false)}><X /></button>
            </div>
            {billCandidates.length > 0 && <input className="bill-picker-search" value={billCandidateQuery} onChange={(event) => setBillCandidateQuery(event.target.value)} placeholder="Search detected bills…" autoFocus />}
            <div className="bill-picker-scroll">
              {visibleBillCandidates.length > 0 && <div className="bill-picker-section-title">New suggestions</div>}
              {visibleBillCandidates.map((candidate) => (
                <article className="bill-picker-row" key={candidate.id}>
                  <Sparkles size={18} />
                  <div><strong>{candidate.name}</strong><p>{candidate.occurrences} payments · {candidate.frequency} · last paid {formatDate(candidate.last_paid)}</p></div>
                  <div><Money value={candidate.typical_amount} /><small>{candidate.confidence} confidence</small></div>
                  <div className="bill-candidate-actions"><button className="secondary compact-button" onClick={() => openBill(candidate)}>Review</button><button className="text-button" onClick={() => ignoreBill.mutate(candidate.merchant_pattern)}>Not a bill</button></div>
                </article>
              ))}
              {visibleExistingBills.length > 0 && <div className="bill-picker-section-title">Already added</div>}
              {visibleExistingBills.map((bill)=><article className="bill-picker-row existing" key={bill.id}><span className="bill-added-check">✓</span><div><strong>{bill.name}</strong><p>{bill.frequency} · due day {bill.due_day} · paid by {data?.accounts.find((account)=>account.id===bill.default_account_id)?.institution_name||"account not selected"}</p></div><div><Money value={bill.typical_amount}/><small>already added</small></div><div className="bill-candidate-actions"><button className="secondary compact-button" onClick={()=>editExistingBill(bill)}><Pencil size={13}/> Edit</button></div></article>)}
              {visibleBillCandidates.length === 0 && visibleExistingBills.length === 0 && <div className="empty compact"><p>No new or existing bills match your search.</p></div>}
            </div>
            <div className="bill-picker-footer"><span>Can’t find it?</span><button className="primary" onClick={() => openBill("manual")}><Plus size={16}/> Enter bill manually</button></div>
          </div>
        </div>
      )}
      {billDraft && data && (
        <div className="modal-backdrop">
          <form className="modal" onSubmit={submitBill}>
            <div className="modal-head"><div><p className="eyebrow">{billDraft === "manual" ? "Add a bill" : "Confirm suggested bill"}</p><h2>{billDraft === "manual" ? "Bill details" : billDraft.name}</h2><p>Only the essentials are required. You can schedule payment afterward.</p></div><button type="button" className="icon-button" aria-label="Close" onClick={() => setBillDraft(null)}><X /></button></div>
            <input type="hidden" name="merchant_pattern" value={billDraft === "manual" ? "" : billDraft.merchant_pattern} />
            <div className="form-grid">
              <label>Bill name<input name="name" required value={billName} onChange={(e)=>{setBillName(e.target.value);setBillerSuggestion(null);setUseSuggestedBiller(false);}} onBlur={()=>billName.trim().length>=3&&findBiller.mutate(billName)} placeholder="Water, electricity, HOA…" /></label>
              <label>Category<select name="category" defaultValue={billDraft === "manual" ? "Bill" : billDraft.category}><option>Bill</option><option>Utilities</option><option>Housing</option><option>Insurance</option><option>Phone & Internet</option><option>Other</option></select></label>
            </div>
            <div className="form-grid">
              <label>Bill type<select name="bill_type" value={billType} onChange={(e) => setBillType(e.target.value)}><option value="recurring">Regular bill</option><option value="statement_balance">Statement balance</option><option value="installment">Installment plan</option><option value="one_time">One-time bill</option></select></label>
              <label>Amount behavior<select name="amount_type" defaultValue={billDraft === "manual" ? "variable" : billDraft.amount_type}><option value="fixed">Usually fixed</option><option value="variable">May vary</option></select></label>
            </div>
            <div className="form-grid">
              <label>Expected amount<input name="typical_amount" type="number" min="0.01" step="0.01" required defaultValue={billDraft === "manual" ? "" : billDraft.typical_amount} /></label>
              <label>Next due date<input name="due_date" type="date" required defaultValue={billDraft === "manual" ? "" : billDraft.next_date} /></label>
            </div>
            <div className="form-grid">
              <label>Frequency<select name="frequency" defaultValue={billType === "one_time" ? "one_time" : billDraft === "manual" ? "monthly" : billDraft.frequency}><option value="monthly">Monthly</option><option value="quarterly">Quarterly</option><option value="annual">Annual</option><option value="one_time">One time</option></select></label>
              <label>Pay from<select name="default_account_id" defaultValue={billDraft === "manual" ? "" : billDraft.account_id}><option value="">Choose later</option>{checkingAccounts.map((account) => <option key={account.id} value={account.id}>{account.name}</option>)}</select></label>
            </div>
            <label>Payment method<select name="payment_method" value={billPaymentMethod} onChange={(event)=>setBillPaymentMethod(event.target.value)}><option value="manual_online">Manual online payment</option><option value="company_autopay">Auto Pay at company website</option><option value="bank_bill_pay">Automatic bank bill pay</option><option value="paper_check">Paper check</option></select></label>
            {billPaymentMethod!=="manual_online"&&<p className="field-help">Choose the checking account above that funds this payment. FinLeash marks it paid only after confirmation or transaction matching.</p>}
            {billType === "installment" && <div className="form-grid"><label>Remaining balance<input name="remaining_balance" type="number" min="0" step="0.01" required /></label><label>Payments remaining<input name="installments_remaining" type="number" min="1" max="600" required /></label></div>}
            <label>Company payment website <span>optional</span><input name="website_url" type="url" pattern="https://.*" value={billWebsite} onChange={(e)=>{setBillWebsite(e.target.value);if(e.target.value!==billerSuggestion?.website_url)setUseSuggestedBiller(false);}} placeholder="https://www.company.com/" /></label>
            {billerSuggestion&&<div className="duplicate-account"><ExternalLink/><div><strong>Verified company website</strong><p>{billerSuggestion.name} · {billerSuggestion.domains[0]}</p></div><label><input type="checkbox" checked={useSuggestedBiller} onChange={(e)=>{setUseSuggestedBiller(e.target.checked);if(e.target.checked)setBillWebsite(billerSuggestion.website_url);}}/> Confirm</label></div>}
            {!billerSuggestion&&billName.trim().length>=3&&<button type="button" className="secondary" disabled={findBiller.isPending} onClick={()=>findBiller.mutate(billName)}>{findBiller.isPending?"Looking up…":"Find official website"}</button>}
            <p className="field-help">A due date is not proof of payment. FinLeash marks it paid only after your confirmation or a matching transaction.</p>
            {errorMessage && <div className="error-box" role="alert">{errorMessage}</div>}
            <button className="primary wide" disabled={addBill.isPending}>{addBill.isPending ? "Adding…" : "Add to Payment Plan"}</button>
          </form>
        </div>
      )}
      {editingBill && data && (
        <div className="modal-backdrop">
          <form className="modal" onSubmit={submitBillEdit}>
            <div className="modal-head"><div><p className="eyebrow">Billing account</p><h2>Edit {editingBill.bill.name}</h2><p>Changes apply to future unpaid occurrences. Paid and scheduled history is preserved.</p></div><button type="button" className="icon-button" aria-label="Close" onClick={()=>setEditingBill(null)}><X/></button></div>
            <div className="form-grid"><label>Bill name<input name="name" required defaultValue={editingBill.bill.name}/></label><label>Category<select name="category" defaultValue={editingBill.bill.category}><option>Bill</option><option>Utilities</option><option>Housing</option><option>Insurance</option><option>Phone & Internet</option><option>Other</option></select></label></div>
            <div className="form-grid"><label>Bill type<select name="bill_type" defaultValue={editingBill.bill.bill_type}><option value="recurring">Regular bill</option><option value="statement_balance">Statement balance</option><option value="installment">Installment plan</option><option value="one_time">One-time bill</option></select></label><label>Amount behavior<select name="amount_type" defaultValue={editingBill.bill.amount_type}><option value="fixed">Usually fixed</option><option value="variable">May vary</option></select></label></div>
            <div className="form-grid"><label>Expected amount<input name="typical_amount" type="number" min="0.01" step="0.01" required defaultValue={editingBill.bill.typical_amount}/></label><label>Next due date<input name="due_date" type="date" required defaultValue={editingBill.dueDate}/></label></div>
            <div className="form-grid"><label>Frequency<select name="frequency" defaultValue={editingBill.bill.frequency}><option value="monthly">Monthly</option><option value="quarterly">Quarterly</option><option value="annual">Annual</option><option value="one_time">One time</option></select></label><label>Pay from<select name="default_account_id" defaultValue={editingBill.bill.default_account_id||""}><option value="">Choose later</option>{checkingAccounts.map((account)=><option key={account.id} value={account.id}>{account.name}</option>)}</select></label></div>
            <label>Payment method<select name="payment_method" value={editPaymentMethod} onChange={(event)=>setEditPaymentMethod(event.target.value)}><option value="manual_online">Manual online payment</option><option value="company_autopay">Auto Pay at company website</option><option value="bank_bill_pay">Automatic bank bill pay</option><option value="paper_check">Paper check</option></select></label>
            {editPaymentMethod!=="manual_online"&&<p className="field-help">Autopay remains expected until a matching transaction or your confirmation marks it paid.</p>}
            {editingBill.bill.bill_type === "installment" && <div className="form-grid"><label>Remaining balance<input name="remaining_balance" type="number" min="0" step="0.01" defaultValue={editingBill.bill.remaining_balance||""}/></label><label>Payments remaining<input name="installments_remaining" type="number" min="1" max="600" defaultValue={editingBill.bill.installments_remaining||""}/></label></div>}
            <label>Company payment website <span>optional</span><input name="website_url" type="url" pattern="https://.*" value={editBillWebsite} onChange={(event)=>{setEditBillWebsite(event.target.value);if(event.target.value!==editBillerSuggestion?.website_url)setUseEditSuggestedBiller(false);}}/></label>
            {editBillerSuggestion&&<div className="duplicate-account"><ExternalLink/><div><strong>Verified company website</strong><p>{editBillerSuggestion.name} · {editBillerSuggestion.domains[0]}</p></div><label><input type="checkbox" checked={useEditSuggestedBiller} onChange={(event)=>{setUseEditSuggestedBiller(event.target.checked);if(event.target.checked)setEditBillWebsite(editBillerSuggestion.website_url);}}/> Confirm</label></div>}
            {!editBillerSuggestion&&<button type="button" className="secondary" disabled={findEditBiller.isPending} onClick={()=>findEditBiller.mutate(editingBill.bill.name)}>{findEditBiller.isPending?"Looking up…":"Find official website"}</button>}
            {errorMessage&&<div className="error-box" role="alert">{errorMessage}</div>}
            <button className="primary wide" disabled={saveBill.isPending}>{saveBill.isPending?"Saving…":"Save bill changes"}</button>
          </form>
        </div>
      )}
      {matching&&<Dialog title="Match bank transaction" onClose={closeMatching} className="match-dialog"><div className="modal-head"><div><p className="eyebrow">Confirm payment</p><h2>Match a bank transaction</h2><p>Select a likely posted debit, ranked by amount, date, and payee. You make the final confirmation; this never moves money.</p></div><button type="button" className="icon-button" aria-label="Close" onClick={closeMatching}><X/></button></div>{errorMessage&&<div className="error-box" role="alert">{errorMessage}</div>}<div className="match-list">{matchCandidates.isLoading?<p>Finding eligible transactions…</p>:matchCandidates.data?.length?matchCandidates.data.map(row=><button type="button" className="match-row" key={row.id} onClick={()=>matchPayment.mutate(row)} disabled={matchPayment.isPending}><span><strong>{row.merchant}</strong><small>{row.description}</small><small>{row.account_name}</small></span><span>{formatDate(row.date)}<small>{row.reason}</small>{!row.account_matches&&<small className="account-change-note">Matching will change the funding account to {row.account_name}</small>}<small className={`match-confidence ${row.confidence}`}>{row.confidence} confidence</small></span><Money value={row.amount}/></button>):<div className="empty compact"><p>No plausible posted debits matched this payment. You can mark it paid manually from Payment.</p></div>}</div></Dialog>}
      {editing && (
        <div className="modal-backdrop">
          <form className="modal" onSubmit={submitPayment}>
            <div className="modal-head">
              <div>
                <p className="eyebrow">Payment plan</p>
                <h2>{editing.account_name}</h2>
                <p>
                  FinLeash records the plan. Schedule the payment securely at
                  your bank or creditor.
                </p>
              </div>
              <button
                type="button"
                className="icon-button"
                aria-label="Close"
                onClick={() => setEditing(null)}
              >
                <X />
              </button>
            </div>
            {editing.account_kind === "bill" && bills.some((bill)=>bill.id===editing.id) && (
              <button type="button" className="secondary wide edit-bill-from-payment" onClick={()=>{const bill=bills.find((item)=>item.id===editing.id);if(bill){setEditing(null);openExistingBillEditor(bill,editing.due_date||`${month}-${String(bill.due_day).padStart(2,"0")}`);}}}>
                <Pencil size={15}/> Edit bill details &amp; website
              </button>
            )}
            <label>
              Funding checking account
              <select
                name="checking_account_id"
                required
                value={fundingId}
                onChange={(e) => setFundingId(e.target.value)}
              >
                <option value="">Choose checking account</option>
                {checkingAccounts.map((account) => (
                  <option key={account.id} value={account.id}>
                    {account.name}
                    {account.institution_name
                      ? ` · ${account.institution_name}`
                      : ""}
                  </option>
                ))}
              </select>
            </label>
            <div className="form-grid">
              <label>
                Due date
                <input
                  name="due_date"
                  type="date"
                  required
                  defaultValue={editing.due_date || ""}
                />
              </label>
              <label>
                Scheduled date
                <input
                  name="scheduled_date"
                  type="date"
                  required
                  defaultValue={
                    editing.scheduled_date || editing.due_date || ""
                  }
                />
              </label>
            </div>
            <div className="form-grid">
              <label>
                Payment amount
                <input
                  name="amount"
                  type="number"
                  min="0.01"
                  step="0.01"
                  required
                  defaultValue={
                    Number(editing.payment_amount) > 0
                      ? editing.payment_amount
                      : editing.minimum_payment
                  }
                />
              </label>
              <label>
                Status
                <select
                  name="status"
                  value={paymentStatus}
                  onChange={(e) => setPaymentStatus(e.target.value)}
                >
                  <option value="not_planned">NP · Not planned</option>
                  <option value="scheduled">S · Scheduled</option>
                  <option value="paid">P · Paid</option>
                </select>
              </label>
            </div>
            {paymentStatus === "paid" && (
              <label>
                Actual paid date
                <input
                  name="paid_date"
                  type="date"
                  required
                  defaultValue={
                    editing.paid_date || new Date().toISOString().slice(0, 10)
                  }
                />
              </label>
            )}
            <label>
              Confirmation number
              <input
                name="confirmation_number"
                maxLength={80}
                placeholder="Optional confirmation from bank or creditor"
              />
            </label>
            <div className="payment-site-actions">
              {selectedFunding?.bank_login_url && (
                <a
                  className="secondary"
                  href={selectedFunding.bank_login_url}
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  Open{" "}
                  {selectedFunding.institution_name || selectedFunding.name}{" "}
                  bill pay <ExternalLink size={14} />
                </a>
              )}
              {creditor?.bank_login_url &&
                creditor.id !== selectedFunding?.id && (
                  <a
                    className="secondary"
                    href={creditor.bank_login_url}
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    Open creditor website <ExternalLink size={14} />
                  </a>
                )}
              {editing.biller_website_url && (
                <a className="secondary" href={editing.biller_website_url} target="_blank" rel="noopener noreferrer">Open company website <ExternalLink size={14} /></a>
              )}
            </div>
            {editing.biller_contact && (
              <div className="account-support-links">
                <small>Verified help &amp; payment</small>
                <a href={editing.biller_contact.website_url} target="_blank" rel="noopener noreferrer">Pay online</a>
                {editing.biller_contact.customer_service_phone && <a href={`tel:${editing.biller_contact.customer_service_phone.replace(/[^+\d]/g, "")}`}>{editing.biller_contact.customer_service_phone}</a>}
                {editing.biller_contact.support_url && <a href={editing.biller_contact.support_url} target="_blank" rel="noopener noreferrer">Customer service</a>}
                {editing.biller_contact.chat_url && <a href={editing.biller_contact.chat_url} target="_blank" rel="noopener noreferrer">Chat</a>}
              </div>
            )}
            <p className="field-help">
              A scheduled date becomes “S · Confirm” when reached. It becomes
              Paid only after you confirm it or a posted transaction is
              reconciled.
            </p>
            {errorMessage && (
              <div className="error-box" role="alert">
                {errorMessage}
              </div>
            )}
            <button className="primary wide" disabled={save.isPending}>
              {save.isPending ? "Saving…" : "Save payment plan"}
            </button>
          </form>
        </div>
      )}
    </Shell>
  );
}
