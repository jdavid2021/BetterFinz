"use client";

import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, CalendarClock, CheckCircle2, FileText, ReceiptText, TriangleAlert } from "lucide-react";
import { useParams } from "next/navigation";
import { Shell } from "@/components/shell";
import { Money } from "@/components/status";
import { api } from "@/lib/api";

type Statement={id:string;statement_date:string;due_date:string;opening_balance:string;new_balance:string;payments_and_credits:string;minimum_payment:string;interest_rate:string|null;interest_paid:string};
type Payment={id:string;amount:string;minimum_amount:string;due_date:string;scheduled_date:string;paid_date:string|null;status:string;confirmation_number:string|null};
type Upload={id:string;filename:string;file_format:string;file_size:number;status:string;uploaded_at:string;statement_start_date:string|null;statement_end_date:string|null;transactions_added:number;duplicates_skipped:number;error_message:string};
type HistoryData={account:{id:string;name:string;kind:string;mask:string;institution_name:string|null};period_start:string;period_end:string;statements:Statement[];payments:Payment[];uploads:Upload[]};
const day=(value:string|null)=>value?new Date(value+(value.includes("T")?"":"T12:00:00")).toLocaleDateString("en-US",{month:"short",day:"numeric",year:"numeric"}):"—";

export default function AccountHistoryPage(){
  const {accountId}=useParams<{accountId:string}>();
  const {data,isLoading,error}=useQuery({queryKey:["account-history",accountId],queryFn:()=>api<HistoryData>(`/api/v1/accounts/${accountId}/history?months=12`)});
  return <Shell>
    <div className="page-title history-title"><div><a className="back-link" href="/accounts"><ArrowLeft size={15}/>Accounts</a><p className="eyebrow">Account archive</p><h1>{data?.account.name||"12-month history"}</h1><p className="subtitle">Statements, planned payments, and uploads retained for easy reference.</p></div>{data&&<span className="history-period">{day(data.period_start)} – {day(data.period_end)}</span>}</div>
    {isLoading?<div className="skeleton-page"><div/><div/></div>:error||!data?<div className="empty"><TriangleAlert/><h2>We couldn’t load this history</h2><p>{error instanceof Error?error.message:"Try again."}</p></div>:<div className="history-stack">
      <section className="panel history-panel"><div className="panel-head"><div><h2>Monthly statements</h2><p>{data.statements.length} statement snapshot{data.statements.length===1?"":"s"}</p></div><CalendarClock/></div>{data.statements.length?data.statements.map(row=><details className="history-statement" key={row.id}><summary><div><strong>{day(row.statement_date)}</strong><span>Due {day(row.due_date)}</span></div><div><small>Statement balance</small><strong><Money value={row.new_balance}/></strong></div><div><small>Minimum</small><strong><Money value={row.minimum_payment}/></strong></div></summary><div className="history-detail-grid"><div><span>Opening balance</span><strong><Money value={row.opening_balance}/></strong></div><div><span>Payments and credits</span><strong><Money value={row.payments_and_credits}/></strong></div><div><span>Interest charged</span><strong><Money value={row.interest_paid}/></strong></div><div><span>Interest rate</span><strong>{row.interest_rate?`${row.interest_rate}%`:"Not detected"}</strong></div></div></details>):<div className="empty compact"><FileText/><h2>No statement snapshots yet</h2><p>Upload monthly liability statements from the Accounts page to build this history.</p></div>}</section>
      <section className="panel history-panel"><div className="panel-head"><div><h2>Payment history</h2><p>Planned, scheduled, and paid amounts for this account</p></div><ReceiptText/></div>{data.payments.length?<div className="history-table"><div className="history-table-head"><span>Scheduled</span><span>Due</span><span>Amount</span><span>Status</span></div>{data.payments.map(row=><div className="history-table-row" key={row.id}><span>{day(row.scheduled_date)}</span><span>{day(row.due_date)}</span><strong><Money value={row.amount}/></strong><span className={`history-status ${row.status}`}>{row.status.replaceAll("_"," ")}{row.paid_date?` · ${day(row.paid_date)}`:""}</span></div>)}</div>:<div className="empty compact"><p>No payment-plan records for this account in the period.</p></div>}</section>
      <section className="panel history-panel"><div className="panel-head"><div><h2>Upload history</h2><p>Every successful or failed statement attempt from now forward</p></div><FileText/></div>{data.uploads.length?<div className="upload-history-list">{data.uploads.map(row=><article key={row.id}><span className={row.status==="completed"?"upload-result-icon good":"upload-result-icon bad"}>{row.status==="completed"?<CheckCircle2/>:<TriangleAlert/>}</span><div><strong>{row.filename}</strong><p>{row.file_format.toUpperCase()} · uploaded {day(row.uploaded_at)}{row.statement_end_date?` · statement through ${day(row.statement_end_date)}`:""}</p>{row.error_message&&<small>{row.error_message}</small>}</div><div><strong>{row.status}</strong><span>{row.status==="completed"?`${row.transactions_added} added · ${row.duplicates_skipped} duplicates`:"Needs review"}</span></div></article>)}</div>:<div className="empty compact"><p>No uploads have been logged since account history was enabled.</p></div>}</section>
    </div>}
  </Shell>;
}
