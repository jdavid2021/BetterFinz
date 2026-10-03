"use client";

import Link from "next/link";
import {useEffect, useState} from "react";
import {useRouter} from "next/navigation";
import {AuthCard} from "@/components/auth-card";
import {api} from "@/lib/api";

type LegalStatus = {
  required:boolean;
  documents:{terms:{version:string};privacy:{version:string}};
};

export default function LegalReviewPage(){
  const router=useRouter();
  const [status,setStatus]=useState<LegalStatus|null>(null);
  const [terms,setTerms]=useState(false);
  const [privacy,setPrivacy]=useState(false);
  const [error,setError]=useState("");
  const [busy,setBusy]=useState(false);
  useEffect(()=>{api<LegalStatus>("/api/v1/legal/status").then(value=>{setStatus(value);if(!value.required)router.replace("/today");}).catch(reason=>setError(reason instanceof Error?reason.message:"Unable to load the legal review."));},[router]);
  async function accept(){
    if(!status||!terms||!privacy)return;
    setBusy(true);setError("");
    try{
      await api("/api/v1/legal/accept",{method:"POST",body:JSON.stringify({accept_terms:true,accept_privacy:true,terms_version:status.documents.terms.version,privacy_version:status.documents.privacy.version})});
      router.replace("/today");
    }catch(reason){setError(reason instanceof Error?reason.message:"Unable to save acceptance.");setBusy(false);}
  }
  return <AuthCard eyebrow="Legal update" title="Review before continuing" description="The current legal documents apply to your use of FinLeash. Existing accounts are not marked accepted automatically.">
    <label className="legal-consent"><input type="checkbox" checked={terms} onChange={event=>setTerms(event.target.checked)}/><span>I reviewed and agree to the <Link href="/terms" target="_blank">Terms of Service</Link>.</span></label>
    <label className="legal-consent"><input type="checkbox" checked={privacy} onChange={event=>setPrivacy(event.target.checked)}/><span>I reviewed and acknowledge the <Link href="/privacy" target="_blank">Privacy Notice</Link>.</span></label>
    {error&&<div className="error-box" role="alert">{error}</div>}
    <button className="primary wide" disabled={!status||!terms||!privacy||busy} onClick={accept}>{busy?"Saving…":"Accept and continue"}</button>
  </AuthCard>;
}
