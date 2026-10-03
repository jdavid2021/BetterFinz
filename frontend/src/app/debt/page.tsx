"use client";

import Link from "next/link";
import {FormEvent,useState} from "react";
import {useMutation,useQuery,useQueryClient} from "@tanstack/react-query";
import {ArrowRight,Plus,TrendingDown,Upload,X} from "lucide-react";
import {Shell} from "@/components/shell";
import {Money} from "@/components/status";
import {Account,api} from "@/lib/api";

type Liability={id:string;account_id:string;account_name:string;opening_balance:string;new_balance:string;new_payments:string;statement_date:string;due_date:string;minimum_payment:string;interest_rate:string|null;interest_paid:string};
type Strategy={minimum_total:string;priority:Liability[];method:string;advice:string;generated_at:string};
const liabilityKinds=["credit_card","mortgage","auto_loan","buy_now_pay_later","loan","other"];
const formatDate=(value:string)=>new Date(value+"T12:00").toLocaleDateString("en-US",{month:"short",day:"numeric",year:"numeric"});

export default function Debt(){
  const qc=useQueryClient();
  const [show,setShow]=useState(false),[uploadShow,setUploadShow]=useState(false);
  const liabilities=useQuery({queryKey:["liabilities"],queryFn:()=>api<Liability[]>("/api/v1/liabilities")});
  const strategy=useQuery({queryKey:["debt-strategy"],queryFn:()=>api<Strategy|null>("/api/v1/debt/strategy")});
  const accounts=useQuery({queryKey:["accounts"],queryFn:()=>api<Account[]>("/api/v1/accounts")});
  const refresh=()=>{qc.invalidateQueries({queryKey:["liabilities"]});qc.invalidateQueries({queryKey:["accounts"]})};
  const strategize=useMutation({mutationFn:()=>api<Strategy>("/api/v1/debt/strategy",{method:"POST"}),onSuccess:data=>qc.setQueryData(["debt-strategy"],data)});
  const upload=useMutation({mutationFn:(body:FormData)=>api("/api/v1/liabilities/import",{method:"POST",body}),onSuccess:()=>{setUploadShow(false);refresh()}});
  const add=useMutation({mutationFn:(body:object)=>api("/api/v1/liabilities",{method:"POST",body:JSON.stringify(body)}),onSuccess:()=>{setShow(false);refresh()}});
  function uploadStatement(e:FormEvent<HTMLFormElement>){e.preventDefault();upload.mutate(new FormData(e.currentTarget))}
  function addStatement(e:FormEvent<HTMLFormElement>){e.preventDefault();const values=Object.fromEntries(new FormData(e.currentTarget));add.mutate({...values,interest_rate:values.interest_rate||null})}

  const debtAccounts=accounts.data?.filter(a=>liabilityKinds.includes(a.kind));
  const current=liabilities.data||[];
  const priorityIds=strategy.data?.priority.map(item=>item.account_id)||[];
  const ordered=[...current].sort((a,b)=>{
    const ai=priorityIds.indexOf(a.account_id),bi=priorityIds.indexOf(b.account_id);
    if(ai>=0||bi>=0)return (ai<0?Number.MAX_SAFE_INTEGER:ai)-(bi<0?Number.MAX_SAFE_INTEGER:bi);
    return Number(b.interest_rate||-1)-Number(a.interest_rate||-1);
  });
  const totalDebt=current.reduce((sum,item)=>sum+Number(item.new_balance),0);
  const totalMinimum=current.reduce((sum,item)=>sum+Number(item.minimum_payment),0);
  const interestPaid=current.reduce((sum,item)=>sum+Number(item.interest_paid),0);
  const knownApr=current.filter(item=>item.interest_rate!==null);
  const weightedApr=knownApr.length?knownApr.reduce((sum,item)=>sum+Number(item.new_balance)*Number(item.interest_rate),0)/knownApr.reduce((sum,item)=>sum+Number(item.new_balance),0):null;

  return <Shell>
    <div className="page-title">
      <div><p className="eyebrow">Long-term reduction</p><h1>Debts</h1><p className="subtitle">Choose the payoff order and understand where interest is costing you most.</p></div>
      <div className="modal-actions"><button className="secondary" onClick={()=>setUploadShow(true)}><Upload/>Upload PDF</button><button className="secondary" onClick={()=>setShow(true)}><Plus/>Add statement details</button></div>
    </div>

    <section className="debt-strategy-summary" aria-label="Debt portfolio summary">
      <article><span>Total debt</span><strong><Money value={totalDebt}/></strong><small>Latest statement balances</small></article>
      <article><span>Monthly minimums</span><strong><Money value={totalMinimum}/></strong><small>Protect these before extra payments</small></article>
      <article><span>Weighted APR</span><strong>{weightedApr===null?"—":`${weightedApr.toFixed(2)}%`}</strong><small>{knownApr.length} of {current.length} APRs known</small></article>
      <article><span>Interest charged</span><strong><Money value={interestPaid}/></strong><small>Across latest statements</small></article>
    </section>

    <section className="panel strategy-panel">
      <div className="strategy-icon"><TrendingDown/></div>
      <div className="strategy-content"><span>Saved dynamic strategy</span>{strategy.data?<><h2>{strategy.data.priority[0]?`Focus extra payments on ${strategy.data.priority[0].account_name}`:"Add liability statements to build a strategy"}</h2><p>{strategy.data.advice}</p><small>Generated {new Date(strategy.data.generated_at).toLocaleString()}</small></>:<><h2>No saved payoff strategy yet</h2><p>Generate one when your latest debt statements are ready. It remains unchanged until you choose to run it again.</p></>}</div>
      <button className="primary strategy-action" disabled={strategize.isPending} onClick={()=>strategize.mutate()}>{strategize.isPending?"Strategizing…":strategy.data?"Strategize again":"Strategize payments"}</button>
      {strategize.error&&<div className="error-box">{strategize.error.message}</div>}
    </section>

    <div className="debt-section-head"><div><p className="eyebrow">Payoff order</p><h2>Where each debt stands</h2><p>Payment dates and statuses are managed separately in Payment Plan.</p></div><Link className="secondary" href="/monthly-plan">Open Payment Plan <ArrowRight/></Link></div>
    <section className="debt-priority-grid">
      {ordered.map(item=>{const rank=priorityIds.indexOf(item.account_id)+1;return <article className={rank===1?"panel debt-priority-card focus":"panel debt-priority-card"} key={item.id}>
        <div className="debt-priority-head"><span className="debt-priority-rank">{rank?`#${rank}`:"—"}</span><div><h3>{item.account_name}</h3><p>Statement {formatDate(item.statement_date)}</p></div>{rank===1&&<span className="focus-badge">Extra-payment focus</span>}</div>
        <div className="debt-priority-balance"><span>Current debt</span><strong><Money value={item.new_balance}/></strong></div>
        <div className="debt-priority-metrics"><div><span>APR</span><strong>{item.interest_rate?`${item.interest_rate}%`:"Unknown"}</strong></div><div><span>Minimum</span><strong><Money value={item.minimum_payment}/></strong></div><div><span>Interest charged</span><strong><Money value={item.interest_paid}/></strong></div><div><span>Next due</span><strong>{formatDate(item.due_date)}</strong></div></div>
        <div className="debt-recommendation"><strong>Recommended action</strong><p>{!strategy.data?"Generate a strategy to assign this debt a payoff priority.":rank===1?"Pay the minimum, then direct safe extra funds here after this month’s obligations and reserve are protected.":"Protect the minimum. Redirect extra funds here after higher-priority debts are cleared."}</p></div>
      </article>})}
      {current.length===0&&<div className="panel empty"><h2>No debt statements yet</h2><p>Upload a lender statement or enter its latest balance, APR, minimum, and due date.</p></div>}
    </section>

    {uploadShow&&<div className="modal-backdrop"><form className="modal" onSubmit={uploadStatement}><div className="modal-head"><div><h2>Upload debt statement</h2><p>Balances, APR, interest, minimum, and due date are extracted locally.</p></div><button type="button" className="icon-button" aria-label="Close" onClick={()=>setUploadShow(false)}><X/></button></div><label>Liability account<select name="account_id" required defaultValue=""><option value="" disabled>Choose debt</option>{debtAccounts?.map(a=><option key={a.id} value={a.id}>{a.name}</option>)}</select></label><label className="file-input"><Upload/>Choose PDF statement<input name="file" type="file" accept="application/pdf,.pdf" required/></label>{upload.error&&<div className="error-box">{upload.error.message}</div>}<button className="primary wide" disabled={upload.isPending}>{upload.isPending?"Extracting…":"Extract statement details"}</button></form></div>}
    {show&&<div className="modal-backdrop"><form className="modal account-modal" onSubmit={addStatement}><div className="modal-head"><div><h2>Add statement details</h2><p>Use values reported by the lender; do not estimate missing terms.</p></div><button type="button" className="icon-button" aria-label="Close" onClick={()=>setShow(false)}><X/></button></div><label>Liability account<select name="account_id" required defaultValue=""><option value="" disabled>Choose debt</option>{debtAccounts?.map(a=><option key={a.id} value={a.id}>{a.name}</option>)}</select></label><div className="form-grid"><label>Opening balance<input name="opening_balance" type="number" min="0" step=".01" required/></label><label>New balance<input name="new_balance" type="number" min="0" step=".01" required/></label></div><div className="form-grid"><label>New payments<input name="new_payments" type="number" min="0" step=".01" defaultValue="0"/></label><label>Interest charged<input name="interest_paid" type="number" min="0" step=".01" defaultValue="0"/></label></div><div className="form-grid"><label>APR %<input name="interest_rate" type="number" min="0" max="100" step=".0001"/></label><label>Minimum payment<input name="minimum_payment" type="number" min=".01" step=".01" required/></label></div><div className="form-grid"><label>Statement date<input name="statement_date" type="date" required/></label><label>Due date<input name="due_date" type="date" required/></label></div>{add.error&&<div className="error-box">{add.error.message}</div>}<button className="primary wide" disabled={add.isPending}>Save statement details</button></form></div>}
  </Shell>
}
