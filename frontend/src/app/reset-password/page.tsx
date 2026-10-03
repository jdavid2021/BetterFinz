"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { FormEvent, Suspense, useState } from "react";
import { AuthCard } from "@/components/auth-card";
import { api } from "@/lib/api";
import { authRoutes } from "@/lib/frontend-routes";

export default function ResetPasswordPage() {
  return <Suspense fallback={<AuthCard eyebrow="Account recovery" title="Choose a new password" description="Loading your secure reset link."><p role="status">Loading reset link…</p></AuthCard>}><ResetPasswordContent /></Suspense>;
}

function ResetPasswordContent() {
  const searchParams = useSearchParams();
  const token = searchParams.get("token") || "";
  const [password, setPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [complete, setComplete] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError("");
    if (password.length < 12) return setError("Use at least 12 characters.");
    if (password !== confirmation) return setError("Passwords do not match.");
    if (!token) return setError("This reset link is incomplete. Request a new one.");
    setBusy(true);
    try {
      await api(authRoutes.resetPassword, {
        method: "POST",
        body: JSON.stringify({ token, password }),
      });
      setComplete(true);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to reset your password.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <AuthCard eyebrow="Account recovery" title={complete ? "Password updated" : "Choose a new password"} description={complete ? "You can now sign in with your new password." : "Use a unique password with at least 12 characters."}>
      {complete ? (
        <Link className="primary wide auth-primary-link" href="/">Continue to sign in</Link>
      ) : (
        <form onSubmit={submit}>
          <label>New password<input required minLength={12} type="password" autoComplete="new-password" value={password} onChange={(event) => setPassword(event.target.value)} /></label>
          <label>Confirm new password<input required minLength={12} type="password" autoComplete="new-password" value={confirmation} onChange={(event) => setConfirmation(event.target.value)} /></label>
          {error && <div className="error-box" role="alert">{error}</div>}
          <button className="primary wide" disabled={busy}>{busy ? "Updating…" : "Update password"}</button>
        </form>
      )}
      {!complete && <p className="auth-footer"><Link href="/forgot-password">Request a new link</Link></p>}
    </AuthCard>
  );
}
