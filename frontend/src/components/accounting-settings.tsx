"use client";

import {useEffect,useMemo,useState} from "react";
import {useMutation,useQuery,useQueryClient} from "@tanstack/react-query";
import {BookOpen,Building2,FolderTree,Plus,Pencil,Users} from "lucide-react";
import {AccountingSegment,LedgerCategory,api} from "@/lib/api";

const workspaceOptions=[
  ["individual","Individual"],
  ["home","Home"],
  ["home_business","Home & business"],
  ["small_business","Small business"],
  ["enterprise","Enterprise"],
] as const;

export function AccountingSettings(){
  const qc=useQueryClient();
  const workspace=useQuery({queryKey:["accounting-workspace"],queryFn:()=>api<{workspace_type:string}>("/api/v1/accounting/workspace")});
  const segments=useQuery({queryKey:["accounting-segments"],queryFn:()=>api<AccountingSegment[]>("/api/v1/accounting/segments")});
  const segmentSettings=useQuery({queryKey:["segment-settings"],queryFn:()=>api<{label:string}>("/api/v1/accounting/segment-settings")});
  const categories=useQuery({queryKey:["ledger-categories"],queryFn:()=>api<LedgerCategory[]>("/api/v1/accounting/categories?include_inactive=true")});
  const [workspaceType,setWorkspaceType]=useState("individual");
  const [segmentName,setSegmentName]=useState("");
  const [segmentLabel,setSegmentLabel]=useState("Business");
  const [categoryName,setCategoryName]=useState("");
  const [parentId,setParentId]=useState("");
  const [error,setError]=useState("");
  useEffect(()=>{if(workspace.data)setWorkspaceType(workspace.data.workspace_type)},[workspace.data]);
  useEffect(()=>{if(segmentSettings.data)setSegmentLabel(segmentSettings.data.label)},[segmentSettings.data]);
  const refresh=async()=>{await Promise.all([
    qc.invalidateQueries({queryKey:["accounting-segments"]}),
    qc.invalidateQueries({queryKey:["ledger-categories"]}),
    qc.invalidateQueries({queryKey:["accounts"]}),
    qc.invalidateQueries({queryKey:["transactions"]}),
  ])};
  const workspaceUpdate=useMutation({mutationFn:(next:string)=>api("/api/v1/accounting/workspace",{method:"PATCH",body:JSON.stringify({workspace_type:next})}),onSuccess:()=>{setError("");qc.invalidateQueries({queryKey:["accounting-workspace"]})},onError:e=>setError(e.message)});
  const labelUpdate=useMutation({mutationFn:()=>api("/api/v1/accounting/segment-settings",{method:"PATCH",body:JSON.stringify({label:segmentLabel})}),onSuccess:()=>{setError("");qc.invalidateQueries({queryKey:["segment-settings"]})},onError:e=>setError(e.message)});
  const addSegment=useMutation({mutationFn:()=>api("/api/v1/accounting/segments",{method:"POST",body:JSON.stringify({name:segmentName})}),onSuccess:async()=>{setSegmentName("");setError("");await refresh()},onError:e=>setError(e.message)});
  const addCategory=useMutation({mutationFn:()=>api("/api/v1/accounting/categories",{method:"POST",body:JSON.stringify({name:categoryName,parent_id:parentId})}),onSuccess:async()=>{setCategoryName("");setError("");await refresh()},onError:e=>setError(e.message)});
  const editCategory=useMutation({mutationFn:({id,body}:{id:string;body:object})=>api(`/api/v1/accounting/categories/${id}`,{method:"PATCH",body:JSON.stringify(body)}),onSuccess:refresh,onError:e=>setError(e.message)});
  const parentOptions=useMemo(()=>(categories.data||[]).filter(row=>row.is_active&&row.depth<3),[categories.data]);
  const visibleCategories=(categories.data||[]).filter(row=>row.is_active);

  function rename(row:LedgerCategory){
    const name=window.prompt("Category name",row.name)?.trim();
    if(name&&name!==row.name)editCategory.mutate({id:row.id,body:{name}});
  }

  return <div className="accounting-settings-stack">
    <section className="panel accounting-intro">
      <span className="big-icon"><BookOpen/></span>
      <div>
        <h2>Accounting workspace</h2>
        <p>Keep everyday categorization simple while FinLeash creates balanced journal entries behind the scenes.</p>
        <label>Starting template
          <select value={workspaceType} onChange={e=>{setWorkspaceType(e.target.value);workspaceUpdate.mutate(e.target.value)}}>
            {workspaceOptions.map(([value,label])=><option key={value} value={value}>{label}</option>)}
          </select>
        </label>
        <small>Templates add sensible defaults only. Your categories and prior assignments are never removed.</small>
      </div>
    </section>

    <section className="panel accounting-settings-panel">
      <div className="panel-head"><div><h2><Building2/> Reporting segments</h2><p>Compare profitability across businesses, divisions, departments, products, or other parts of the same books.</p></div></div>
      <form className="accounting-inline-form" onSubmit={e=>{e.preventDefault();labelUpdate.mutate()}}>
        <input aria-label="Segment label" value={segmentLabel} onChange={e=>setSegmentLabel(e.target.value)} placeholder="Business, Division, Product…" required/>
        <button className="secondary" disabled={labelUpdate.isPending}>Save label</button>
      </form>
      <div className="segment-grid">
        {(segments.data||[]).map(segment=><article key={segment.id}><span><Users/></span><div><strong>{segment.name}</strong><small>{segmentLabel}</small></div></article>)}
      </div>
      <form className="accounting-inline-form" onSubmit={e=>{e.preventDefault();addSegment.mutate()}}>
        <input aria-label="Segment name" placeholder="For example, Retail or Product A" value={segmentName} onChange={e=>setSegmentName(e.target.value)} required/>
        <button className="secondary" disabled={addSegment.isPending}><Plus/> Add segment</button>
      </form>
    </section>

    <section className="panel accounting-settings-panel category-tree-panel">
      <div className="panel-head"><div><h2><FolderTree/> Category tree</h2><p>Assets, liabilities, equity, income, and expenses are fixed roots. Customize up to three levels.</p></div></div>
      <div className="category-tree">
        {visibleCategories.map(row=><div className={`category-node depth-${row.depth}`} key={row.id}><span><i>{row.code}</i><strong>{row.name}</strong>{row.allow_posting&&<small>{row.account_type}</small>}</span>{row.parent_id&&<button className="icon-button" aria-label={`Rename ${row.name}`} onClick={()=>rename(row)}><Pencil/></button>}</div>)}
      </div>
      <form className="accounting-inline-form category-add-form" onSubmit={e=>{e.preventDefault();addCategory.mutate()}}>
        <input aria-label="New category name" placeholder="New category" value={categoryName} onChange={e=>setCategoryName(e.target.value)} required/>
        <select aria-label="Parent category" value={parentId} onChange={e=>setParentId(e.target.value)} required><option value="">Choose parent</option>{parentOptions.map(row=><option key={row.id} value={row.id}>{row.path}</option>)}</select>
        <button className="secondary" disabled={addCategory.isPending}><Plus/> Add category</button>
      </form>
    </section>
    {error&&<div className="error-box" role="alert">{error}</div>}
  </div>;
}
