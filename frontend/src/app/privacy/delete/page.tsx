"use client";

import Link from "next/link";
import {useEffect, useState} from "react";
import {AuthCard} from "@/components/auth-card";
import {api} from "@/lib/api";

export default function DeletionLinkPage(){
  const [message,setMessage]=useState("Checking your single-use link…");
  const [cancelUrl,setCancelUrl]=useState("");
  useEffect(()=>{
    const values=new URLSearchParams(window.location.search);
    const confirm=values.get("confirm"),cancel=values.get("cancel");
    const path=confirm?"/api/v1/privacy/deletion/confirm":cancel?"/api/v1/privacy/deletion/cancel":"";
    const token=confirm||cancel;
    if(!path||!token){setMessage("This deletion link is incomplete.");return;}
    api<{status:string;execute_after?:string;grace_days?:number;development_cancel_url?:string|null}>(path,{method:"POST",body:JSON.stringify({token})})
      .then(result=>{
        if(result.status==="cancelled")setMessage("Account deletion was cancelled. You may sign in again.");
        else{
          setMessage(`Account deletion is scheduled after the ${result.grace_days||30}-day grace period${result.execute_after?`, on ${new Date(result.execute_after).toLocaleString()}`:""}. All existing sessions were invalidated and SimpleFIN synchronization was paused.`);
          setCancelUrl(result.development_cancel_url||"");
        }
        window.history.replaceState(null,"","/privacy/delete");
      })
      .catch(reason=>setMessage(reason instanceof Error?reason.message:"This link is invalid or has expired."));
  },[]);
  return <AuthCard eyebrow="Privacy request" title="Account deletion" description={message}>
    {cancelUrl&&<Link className="secondary wide" href={cancelUrl}>Cancel deletion in development</Link>}
    <Link className="primary wide auth-primary-link" href="/">Return to sign in</Link>
  </AuthCard>;
}
