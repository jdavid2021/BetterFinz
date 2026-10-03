"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useRef, useState } from "react";
import { AuthCard } from "@/components/auth-card";
import { api } from "@/lib/api";
import { authRoutes } from "@/lib/frontend-routes";

export default function VerifyEmailPage() {
  return <Suspense fallback={<AuthCard eyebrow="Email verification" title="Verifying your email" description="Please wait while FinLeash confirms your account."><p role="status">Checking verification link…</p></AuthCard>}><VerifyEmailContent /></Suspense>;
}

function VerifyEmailContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const started = useRef(false);
  const token = searchParams.get("token") || "";
  const [error, setError] = useState("");

  useEffect(() => {
    if (started.current) return;
    started.current = true;
    if (!token) {
      setError("This verification link is incomplete.");
      return;
    }
    api(authRoutes.verifyEmail, {
      method: "POST",
      body: JSON.stringify({ token }),
    }).then(() => {
      router.replace("/setup");
    }).catch((reason) => {
      setError(reason instanceof Error ? reason.message : "Email verification failed.");
    });
  }, [router, token]);

  return (
    <AuthCard eyebrow="Email verification" title={error ? "We couldn’t verify this link" : "Verifying your email"} description={error ? "The link may be incomplete, expired, or already used." : "Please wait while FinLeash confirms your account."}>
      {error ? <div className="error-box" role="alert">{error}</div> : <div className="auth-success" role="status"><strong>Checking verification link…</strong><p>You’ll continue to guided setup automatically.</p></div>}
      {error && <p className="auth-footer"><Link href="/signup">Return to signup</Link></p>}
    </AuthCard>
  );
}
