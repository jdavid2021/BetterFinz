"use client";
import {useMutation,useQuery,useQueryClient} from "@tanstack/react-query";
import {Power,SlidersHorizontal,Trash2} from "lucide-react";
import {Shell} from "@/components/shell";
import {LedgerCategory,api} from "@/lib/api";

type Rule={id:string;pattern:string;sample_description:string;category:string;category_id:string|null;is_active:boolean;match_count:number;last_matched_at:string|null;created_at:string};

export default function Rules(){
  const qc=useQueryClient();
  const {data=[]}=useQuery({queryKey:["categorization-rules"],queryFn:()=>api<Rule[]>("/api/v1/categorization-rules")});
  const categories=useQuery({queryKey:["ledger-categories"],queryFn:()=>api<LedgerCategory[]>("/api/v1/accounting/categories")});
  const posting=(categories.data||[]).filter(row=>row.allow_posting&&row.is_active);
  const update=useMutation({mutationFn:({id,body}:{id:string;body:object})=>api(`/api/v1/categorization-rules/${id}`,{method:"PATCH",body:JSON.stringify(body)}),onSuccess:()=>qc.invalidateQueries({queryKey:["categorization-rules"]})});
  const remove=useMutation({mutationFn:(id:string)=>api(`/api/v1/categorization-rules/${id}`,{method:"DELETE"}),onSuccess:()=>qc.invalidateQueries({queryKey:["categorization-rules"]})});
  return <Shell>
    <div className="page-title"><div><p className="eyebrow">Automation you control</p><h1>Learned rules</h1><p className="subtitle">Manual corrections teach FinLeash how to categorize similar future transactions.</p></div></div>
    {data.length?<section className="panel rules-panel"><div className="rules-head"><span>Learned pattern</span><span>Category</span><span>Uses</span><span>Status</span><span></span></div>{data.map(rule=><article className={rule.is_active?"rule-row":"rule-row inactive"} key={rule.id}><div><strong>{rule.pattern}</strong><small>Learned from: {rule.sample_description}</small></div><select aria-label={`Category for ${rule.pattern}`} value={rule.category_id||""} onChange={e=>update.mutate({id:rule.id,body:{category_id:e.target.value}})}>{posting.map(c=><option key={c.id} value={c.id}>{c.path}</option>)}</select><span>{rule.match_count}</span><button className="rule-status" onClick={()=>update.mutate({id:rule.id,body:{is_active:!rule.is_active}})}><Power/>{rule.is_active?"Active":"Paused"}</button><button className="icon-button danger-action" aria-label={`Delete ${rule.pattern}`} onClick={()=>remove.mutate(rule.id)}><Trash2/></button></article>)}</section>:<div className="empty panel"><SlidersHorizontal/><h2>No learned rules yet</h2><p>Reclassify a transaction and FinLeash will safely learn its normalized merchant pattern for future statement imports.</p></div>}
  </Shell>;
}
