"use client";

import {useState} from "react";
import {useQuery} from "@tanstack/react-query";
import {BookOpen,CheckCircle2,Scale} from "lucide-react";
import {Shell} from "@/components/shell";
import {Money} from "@/components/status";
import {AccountingSegment,api} from "@/lib/api";

type Line={id:string;name:string;amount:string};
type Pnl={income:Line[];expenses:Line[];total_income:string;total_expenses:string;net_income:string;date_from:string;date_to:string};
type TbLine={id:string;code:string;name:string;account_type:string;debit:string;credit:string};
type Tb={rows:TbLine[];total_debit:string;total_credit:string;balanced:boolean;as_of:string};
type Bs={assets:Line[];liabilities:Line[];equity:Line[];total_assets:string;total_liabilities:string;total_equity:string;difference:string;balanced:boolean;as_of:string};
type Tab="pnl"|"tb"|"bs";

function iso(date:Date){return [date.getFullYear(),String(date.getMonth()+1).padStart(2,"0"),String(date.getDate()).padStart(2,"0")].join("-")}
function StatementSection({title,rows,total}:{title:string;rows:Line[];total:string}){return <section className="statement-section"><h3>{title}</h3>{rows.length?rows.map(row=><div key={row.id}><span>{row.name}</span><Money value={row.amount}/></div>):<p>No activity in this period.</p>}<footer><strong>Total {title.toLowerCase()}</strong><strong><Money value={total}/></strong></footer></section>}

export default function Reports(){
  const today=new Date();
  const [tab,setTab]=useState<Tab>("pnl");
  const [segmentId,setSegmentId]=useState("");
  const [dateFrom,setDateFrom]=useState(`${today.getFullYear()}-01-01`);
  const [dateTo,setDateTo]=useState(iso(today));
  const segmentSettings=useQuery({queryKey:["segment-settings"],queryFn:()=>api<{label:string}>("/api/v1/accounting/segment-settings")});
  const segments=useQuery({queryKey:["accounting-segments"],queryFn:()=>api<AccountingSegment[]>("/api/v1/accounting/segments")});
  const scope=segmentId?"&segment_id="+encodeURIComponent(segmentId):"";
  const pnl=useQuery({queryKey:["report-pnl",segmentId,dateFrom,dateTo],queryFn:()=>api<Pnl>(`/api/v1/accounting/reports/profit-loss?date_from=${dateFrom}&date_to=${dateTo}${scope}`),enabled:tab==="pnl"&&dateFrom<=dateTo});
  const tb=useQuery({queryKey:["report-tb",segmentId,dateTo],queryFn:()=>api<Tb>("/api/v1/accounting/reports/trial-balance?as_of="+dateTo),enabled:tab==="tb"});
  const bs=useQuery({queryKey:["report-bs",segmentId,dateTo],queryFn:()=>api<Bs>("/api/v1/accounting/reports/balance-sheet?as_of="+dateTo),enabled:tab==="bs"});
  const selectedName=segments.data?.find(row=>row.id===segmentId)?.name||"All segments";

  return <Shell>
    <div className="page-title"><div><p className="eyebrow">Accounting</p><h1>Financial reports</h1><p className="subtitle">Review the shared books and compare profit across reporting segments.</p></div>{tab==="pnl"&&<div className="report-scope"><label>{segmentSettings.data?.label||"Segment"}<select value={segmentId} onChange={e=>setSegmentId(e.target.value)}><option value="">All {segmentSettings.data?.label||"segments"}</option>{segments.data?.map(segment=><option key={segment.id} value={segment.id}>{segment.name}</option>)}</select></label></div>}</div>
    <section className="panel report-controls">
      <div className="tabs"><button className={tab==="pnl"?"active":""} onClick={()=>setTab("pnl")}>Profit & loss</button><button className={tab==="tb"?"active":""} onClick={()=>setTab("tb")}>Trial balance</button><button className={tab==="bs"?"active":""} onClick={()=>setTab("bs")}>Balance sheet</button></div>
      <div className="report-dates">{tab==="pnl"&&<label>From<input type="date" value={dateFrom} onChange={e=>setDateFrom(e.target.value)}/></label>}<label>{tab==="pnl"?"To":"As of"}<input type="date" value={dateTo} onChange={e=>setDateTo(e.target.value)}/></label><span><BookOpen/> Cash-basis · automatically posted</span></div>
    </section>
    {dateFrom>dateTo&&<div className="error-box">From date must be on or before To date.</div>}

    {tab==="pnl"&&pnl.data&&<section className="panel financial-statement">
      <header><div><h2>Profit & loss</h2><p>{selectedName} · {pnl.data.date_from} to {pnl.data.date_to}</p></div><strong className={Number(pnl.data.net_income)>=0?"report-positive":"report-negative"}><span>Net income</span><Money value={pnl.data.net_income}/></strong></header>
      <StatementSection title="Income" rows={pnl.data.income} total={pnl.data.total_income}/>
      <StatementSection title="Expenses" rows={pnl.data.expenses} total={pnl.data.total_expenses}/>
      <div className="statement-grand-total"><strong>Net income</strong><strong><Money value={pnl.data.net_income}/></strong></div>
    </section>}

    {tab==="tb"&&tb.data&&<section className="panel financial-statement">
      <header><div><h2>Trial balance</h2><p>Combined books · As of {tb.data.as_of}</p></div><span className={tb.data.balanced?"report-balanced":"report-unbalanced"}><Scale/>{tb.data.balanced?"Balanced":"Out of balance"}</span></header>
      <div className="report-table"><div className="report-table-head"><span>Code</span><span>Account</span><span>Type</span><span>Debit</span><span>Credit</span></div>{tb.data.rows.map(row=><div key={row.id}><span>{row.code}</span><strong>{row.name}</strong><span>{row.account_type}</span><span>{Number(row.debit)?<Money value={row.debit}/>:"—"}</span><span>{Number(row.credit)?<Money value={row.credit}/>:"—"}</span></div>)}<footer><span></span><strong>Totals</strong><span></span><strong><Money value={tb.data.total_debit}/></strong><strong><Money value={tb.data.total_credit}/></strong></footer></div>
    </section>}

    {tab==="bs"&&bs.data&&<section className="panel financial-statement">
      <header><div><h2>Balance sheet</h2><p>Combined books · As of {bs.data.as_of}</p></div><span className={bs.data.balanced?"report-balanced":"report-unbalanced"}><CheckCircle2/>{bs.data.balanced?"Balanced":"Needs review"}</span></header>
      <div className="balance-sheet-grid"><StatementSection title="Assets" rows={bs.data.assets} total={bs.data.total_assets}/><div><StatementSection title="Liabilities" rows={bs.data.liabilities} total={bs.data.total_liabilities}/><StatementSection title="Equity" rows={bs.data.equity} total={bs.data.total_equity}/><div className="statement-grand-total"><strong>Liabilities + equity</strong><strong><Money value={String(Number(bs.data.total_liabilities)+Number(bs.data.total_equity))}/></strong></div></div></div>
      {!bs.data.balanced&&<div className="report-note">Accounting difference: <Money value={bs.data.difference}/>. Review uncategorized activity and opening balances.</div>}
    </section>}

    {(pnl.isLoading||tb.isLoading||bs.isLoading)&&<div className="skeleton-page"><div/><div/></div>}
  </Shell>;
}
