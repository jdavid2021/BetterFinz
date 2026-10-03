"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { AuthCard } from "@/components/auth-card";
import { api } from "@/lib/api";
import { signupSchema } from "@/lib/auth-validation";
import { authRoutes } from "@/lib/frontend-routes";

type SignupForm = {name:string;email:string;password:string;confirmPassword:string};
type LegalConfig = {terms:{version:string};privacy:{version:string}};

export default function SignupPage() {
  const [error, setError] = useState("");
  const [pendingEmail, setPendingEmail] = useState("");
  const [resendStatus, setResendStatus] = useState("");
  const [developmentUrl, setDevelopmentUrl] = useState("");
  const [resending, setResending] = useState(false);
  const [acceptTerms, setAcceptTerms] = useState(false);
  const [acceptPrivacy, setAcceptPrivacy] = useState(false);
  const [legal, setLegal] = useState<LegalConfig | null>(null);
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<SignupForm>({ resolver: zodResolver(signupSchema) });

  useEffect(() => {
    api<LegalConfig>("/api/v1/legal").then(setLegal).catch(() => setError("Legal documents are temporarily unavailable."));
  }, []);

  async function submit(values: SignupForm) {
    setError("");
    if (!legal || !acceptTerms || !acceptPrivacy) {
      setError("Accept the current Terms and Privacy Notice to continue.");
      return;
    }
    try {
      const result = await api<{ development_url?: string | null }>(authRoutes.signup, {
        method: "POST",
        body: JSON.stringify({
          name: values.name,
          email: values.email,
          password: values.password,
          accept_terms: acceptTerms,
          accept_privacy: acceptPrivacy,
          terms_version: legal.terms.version,
          privacy_version: legal.privacy.version,
        }),
      });
      setPendingEmail(values.email);
      setDevelopmentUrl(result.development_url || "");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to create your account.");
    }
  }

  async function resend() {
    setResending(true);
    setResendStatus("");
    try {
      const result = await api<{ development_url?: string | null }>(authRoutes.resendVerification, {
        method: "POST",
        body: JSON.stringify({ email: pendingEmail }),
      });
      setResendStatus("A new verification email has been requested.");
      setDevelopmentUrl(result.development_url || "");
    } catch (reason) {
      setResendStatus(reason instanceof Error ? reason.message : "Unable to resend the verification email.");
    } finally {
      setResending(false);
    }
  }

  return (
    <AuthCard eyebrow="Get started" title={pendingEmail ? "Check your email" : "Create your FinLeash account"} description={pendingEmail ? `We sent a verification link to ${pendingEmail}. Open it to finish creating your account.` : "Build a private plan around the accounts and income you choose to add."}>
      {pendingEmail ? <div className="auth-success" role="status">
        <strong>Verification required</strong>
        <p>The link is time-limited. You will be signed in and taken to setup after verification.</p>
        {developmentUrl && <Link className="secondary wide" href={developmentUrl}>Open development verification link</Link>}
        <button className="secondary wide" type="button" onClick={resend} disabled={resending}>{resending ? "Resending…" : "Resend verification email"}</button>
        {resendStatus && <p>{resendStatus}</p>}
      </div> : <form onSubmit={handleSubmit(submit)} noValidate>
        <label>Full name<input autoComplete="name" {...register("name")} /><span className="field-error">{errors.name?.message}</span></label>
        <label>Email address<input type="email" autoComplete="email" {...register("email")} /><span className="field-error">{errors.email?.message}</span></label>
        <label>Password<input type="password" autoComplete="new-password" {...register("password")} /><span className="field-error">{errors.password?.message}</span></label>
        <label>Confirm password<input type="password" autoComplete="new-password" {...register("confirmPassword")} /><span className="field-error">{errors.confirmPassword?.message}</span></label>
        <label className="legal-consent"><input type="checkbox" checked={acceptTerms} onChange={event => setAcceptTerms(event.target.checked)}/><span>I agree to the <Link href="/terms" target="_blank">Terms of Service</Link>.</span></label>
        <label className="legal-consent"><input type="checkbox" checked={acceptPrivacy} onChange={event => setAcceptPrivacy(event.target.checked)}/><span>I acknowledge the <Link href="/privacy" target="_blank">Privacy Notice</Link>.</span></label>
        {error && <div className="error-box" role="alert">{error}</div>}
        <button className="primary wide" disabled={isSubmitting || !legal}>{isSubmitting ? "Creating account…" : "Create account"}</button>
      </form>}
      <p className="auth-footer">Already have an account? <Link href="/">Sign in</Link></p>
    </AuthCard>
  );
}
