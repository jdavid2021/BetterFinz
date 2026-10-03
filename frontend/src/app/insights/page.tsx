"use client";

import Link from "next/link";
import {useQuery} from "@tanstack/react-query";
import {AlertTriangle,ArrowRight,CheckCircle2,CircleDollarSign,Copy,Landmark,TrendingDown} from "lucide-react";
import {Shell} from "@/components/shell";
import {Money,Status} from "@/components/status";
import {api,Payment,TodayData} from "@/lib/api";

type DebtStrategy={priority:{account_name:string}[];advice:string;generated_at:string};
const formatDate=(value:string)=>new Date(value+"T12:00").toLocaleDateString("en-US",{month:"short",day:"numeric"});

export default function Insights(){
  const forecast=useQuery({queryKey:["today"],queryFn:()=>api<TodayData>("/api/v1/today")});
  const strategy=useQuery({queryKey:["debt-strategy"],queryFn:()=>api<DebtStrategy|null>("/api/v1/debt/strategy")});
  if(forecast.isLoading)return <Shell><div className="skeleton-page"><div/><div/><div/></div></Shell>;
  if(forecast.error||!forecast.data)return <Shell><div className="empty panel"><AlertTriangle/><h2>Insights could not be refreshed</h2><p>{forecast.error instanceof Error?forecast.error.message:"Try again."}</p></div></Shell>;

  const data=forecast.data;
  const attention=data.payments.filter(payment=>!["covered","covered_but_tight"].includes(payment.coverage_status));
  const missingFunding=data.payments.filter(payment=>payment.coverage_status==="funding_account_not_selected");
  const paymentGroups=new Map<string,Payment[]>();
  data.payments.forEach(payment=>{const key=`${payment.payee.toLowerCase()}|${payment.amount}|${payment.withdrawal_date}`;paymentGroups.set(key,[...(paymentGroups.get(key)||[]),payment])});
  const possibleDuplicates=[...paymentGroups.values()].filter(group=>group.length>1);
  const nextIncome=data.income.filter(item=>item.reliability==="guaranteed"||item.reliability==="high_confidence").sort((a,b)=>a.date.localeCompare(b.date))[0];
  const sameDay=nextIncome?data.payments.filter(payment=>payment.account_id===nextIncome.account_id&&payment.withdrawal_date===nextIncome.date):[];
  const focus=strategy.data?.priority[0]?.account_name;

  return <Shell attention={attention.length}>
    <div className="page-title"><div><p className="eyebrow">Live guidance</p><h1>Insights</h1><p className="subtitle">Calculated from your current balances, confirmed income, and payment plan—no sample records.</p></div><span className="estimate">Refreshed from current plan</span></div>
    <section className={attention.length?"answer warning":"answer good"}><div className="answer-icon">{attention.length?<AlertTriangle/>:<CheckCircle2/>}</div><div><span>Cash-flow insight</span><h2>{data.status}</h2><p>{data.reason}</p></div><Link href="/monthly-plan">Review plan <ArrowRight/></Link></section>

    <section className="insight-grid">
      <article className="panel insight-card"><div className="insight-card-icon"><CircleDollarSign/></div><span>Next reliable income</span><h2>{nextIncome?<><Money value={nextIncome.amount}/> on {formatDate(nextIncome.date)}</>:"Not confirmed"}</h2><p>{sameDay.length?`Applied before ${sameDay.map(payment=>payment.payee).join(", ")} because they share the same date.`:"No same-day funded payments were found."}</p></article>
      <article className="panel insight-card"><div className="insight-card-icon"><Landmark/></div><span>Funding setup</span><h2>{missingFunding.length} payment{missingFunding.length===1?"":"s"} need an account</h2><p>{missingFunding.length?missingFunding.map(payment=>payment.payee).join(", "):"Every planned payment has a funding account."}</p></article>
      <article className="panel insight-card"><div className="insight-card-icon"><Copy/></div><span>Duplicate review</span><h2>{possibleDuplicates.length} possible duplicate{possibleDuplicates.length===1?"":"s"}</h2><p>{possibleDuplicates.length?possibleDuplicates.map(group=>`${group[0].payee} · ${formatDate(group[0].withdrawal_date)}`).join(", "):"No same-payee, same-amount, same-date duplicates detected."}</p></article>
      <article className="panel insight-card"><div className="insight-card-icon"><TrendingDown/></div><span>Debt focus</span><h2>{focus||"Strategy not generated"}</h2><p>{strategy.data?.advice||"Open Debts and choose Strategize payments when the latest statements are ready."}</p></article>
    </section>

    <section className="panel insight-attention"><div className="panel-head"><div><h2>What needs attention</h2><p>Ordered from the current payment forecast</p></div><strong>{attention.length}</strong></div>{attention.slice(0,8).map(payment=><Link href="/monthly-plan" className="insight-attention-row" key={payment.id}><div><strong>{payment.payee}</strong><p>{formatDate(payment.withdrawal_date)} · <Money value={payment.amount}/></p></div><Status value={payment.coverage_status}/><span>{payment.reason}</span><ArrowRight/></Link>)}{attention.length===0&&<div className="empty compact"><CheckCircle2/><p>No cash-flow decisions need attention.</p></div>}</section>
  </Shell>
}
