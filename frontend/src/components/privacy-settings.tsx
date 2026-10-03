"use client";

import Link from "next/link";
import {useEffect, useState} from "react";
import {API, api} from "@/lib/api";

type DeletionStatus={status:string;execute_after:string|null};

export function PrivacySettings(){
  const [password,setPassword]=useState("");
  const [status,setStatus]=useState<DeletionStatus>({status:"none",execute_after:null});
  const [message,setMessage]=useState("");
  const [busy,setBusy]=useState(false);
  useEffect(()=>{api<DeletionStatus>("/api/v1/privacy/deletion").then(setStatus).catch(()=>undefined);},[]);
  async function download(){
    setBusy(true);setMessage("");
    try{
      const response=await fetch(`${API}/api/v1/privacy/export`,{method:"POST",credentials:"include",headers:{"Content-Type":"application/json"},body:JSON.stringify({password})});
      if(!response.ok){const body=await response.json().catch(()=>null);throw new Error(body?.error?.message||"The export could not be created.");}
      const url=URL.createObjectURL(await response.blob());const anchor=document.createElement("a");anchor.href=url;anchor.download="FinLeash-data-export.zip";anchor.click();URL.revokeObjectURL(url);setMessage("Your secret-safe ZIP export was downloaded.");
    }catch(reason){setMessage(reason instanceof Error?reason.message:"The export could not be created.");}finally{setBusy(false);}
  }
  async function requestDeletion(){
    if(!window.confirm("Send a purpose-bound email to confirm account deletion?"))return;
    setBusy(true);setMessage("");
    try{
      const result=await api<{status:string;development_confirmation_url:string|null}>("/api/v1/privacy/deletion/request",{method:"POST",body:JSON.stringify({password})});
      setStatus({status:result.status,execute_after:null});setMessage("Check your email to confirm deletion. No deletion is scheduled until you use that link.");
      if(result.development_confirmation_url)window.location.assign(result.development_confirmation_url);
    }catch(reason){setMessage(reason instanceof Error?reason.message:"Deletion could not be requested.");}finally{setBusy(false);}
  }
  return <section className="panel import-card danger-zone">
    <div>
      <p className="eyebrow">Privacy controls</p><h2>Your data</h2>
      <p>Re-enter your password to export your household data. Account deletion uses a purpose-bound email confirmation as its step-up check. Exports exclude passwords, access URLs, token hashes, passkey material, and provider identifiers.</p>
      <label>Password<input type="password" autoComplete="current-password" value={password} onChange={event=>setPassword(event.target.value)}/></label>
      <div className="privacy-actions">
        <button className="secondary" type="button" disabled={!password||busy} onClick={download}>Download ZIP export</button>
        <button className="secondary danger-action" type="button" disabled={busy||status.status==="pending"} onClick={requestDeletion}>Request account deletion</button>
      </div>
      {status.status==="pending"&&<p>Your account is scheduled for deletion {status.execute_after?`on ${new Date(status.execute_after).toLocaleString()}`:"after the grace period"}. Use the single-use cancellation link emailed to you to stop it.</p>}
      {status.status==="cancelled"&&<p>The previous deletion request was cancelled.</p>}
      {message&&<div className="import-result" role="status"><p>{message}</p></div>}
      <p><Link href="/privacy">Privacy Notice</Link> · <Link href="/terms">Terms of Service</Link></p>
    </div>
  </section>;
}
