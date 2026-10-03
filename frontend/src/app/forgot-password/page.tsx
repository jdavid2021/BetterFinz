"use client";

import Link from "next/link";
import { FormEvent, useState } from "react";
import { AuthCard } from "@/components/auth-card";
import { api } from "@/lib/api";
import { authRoutes } from "@/lib/frontend-routes";

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [sent, setSent] = useState(false);
  const [developmentUrl, setDevelopmentUrl] = useState("");

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const result = await api<{ development_url?: string | null }>(authRoutes.forgotPassword, {
        method: "POST",
        body: JSON.stringify({ email }),
      });
      setSent(true);
      setDevelopmentUrl(result.development_url || "");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to send a reset link.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <AuthCard eyebrow="Account recovery" title="Reset your password" description="Enter your email and we’ll send a time-limited reset link if an account exists.">
      {sent ? (
        <div className="auth-success" role="status">
          <strong>Check your inbox</strong>
          <p>If an account exists for {email}, a reset link is on its way.</p>
          {developmentUrl && <Link className="secondary wide" href={developmentUrl}>Open development reset link</Link>}
        </div>
      ) : (
        <form onSubmit={submit}>
          <label>Email address<input required type="email" autoComplete="email" value={email} onChange={(event) => setEmail(event.target.value)} /></label>
          {error && <div className="error-box" role="alert">{error}</div>}
          <button className="primary wide" disabled={busy}>{busy ? "Sending…" : "Send reset link"}</button>
        </form>
      )}
      <p className="auth-footer"><Link href="/">Back to sign in</Link></p>
    </AuthCard>
  );
}
