"use client";
import Image from "next/image";
import Link from "next/link";
import {useEffect, useState} from "react";
import {useRouter} from "next/navigation";
import {useForm} from "react-hook-form";
import {zodResolver} from "@hookform/resolvers/zod";
import {ArrowRight, CheckCircle2, KeyRound, Mail, ShieldCheck, WalletCards} from "lucide-react";
import {startAuthentication} from "@simplewebauthn/browser";
import {api, API} from "@/lib/api";
import {loginSchema} from "@/lib/auth-validation";

type Form = {email:string;password:string};
type AuthMethods = {google:boolean;magic_link:boolean;passkeys:boolean};

function GoogleMark() {
  return <svg width="18" height="18" viewBox="0 0 48 48" aria-hidden="true"><path fill="#EA4335" d="M24 9.5c3.54 0 6.7 1.22 9.19 3.6l6.85-6.85C35.9 2.38 30.47 0 24 0 14.62 0 6.51 5.38 2.56 13.22l7.98 6.19C12.43 13.72 17.74 9.5 24 9.5z"/><path fill="#4285F4" d="M46.98 24.55c0-1.57-.15-3.09-.38-4.55H24v9.02h12.94c-.58 2.96-2.26 5.48-4.78 7.18l7.73 6c4.51-4.18 7.09-10.36 7.09-17.65z"/><path fill="#FBBC05" d="M10.53 28.59c-.48-1.45-.76-2.99-.76-4.59s.27-3.14.76-4.59l-7.98-6.19C.92 16.46 0 20.12 0 24c0 3.88.92 7.54 2.56 10.78l7.97-6.19z"/><path fill="#34A853" d="M24 48c6.48 0 11.93-2.13 15.89-5.81l-7.73-6c-2.15 1.45-4.92 2.3-8.16 2.3-6.26 0-11.57-4.22-13.47-9.91l-7.98 6.19C6.51 42.62 14.62 48 24 48z"/></svg>;
}

export default function Login() {
  const router = useRouter();
  const [error, setError] = useState("");
  const [magicEmail, setMagicEmail] = useState("");
  const [magicStatus, setMagicStatus] = useState("");
  const [magicDevelopmentUrl, setMagicDevelopmentUrl] = useState("");
  const [magicBusy, setMagicBusy] = useState(false);
  const [passkeyBusy, setPasskeyBusy] = useState(false);
  const [methods, setMethods] = useState<AuthMethods>({google:false,magic_link:true,passkeys:true});
  const {register, handleSubmit, formState: {errors, isSubmitting}} = useForm<Form>({resolver: zodResolver(loginSchema)});

  useEffect(() => {
    api<AuthMethods>("/api/v1/auth/methods").then(setMethods).catch(() => undefined);
    const message = new URLSearchParams(window.location.search).get("auth_error");
    if (message) {
      setError(message);
      window.history.replaceState(null, "", "/");
    }
  }, []);

  async function submit(values: Form) {
    setError("");
    try {
      await api("/api/v1/auth/login", {method: "POST", body: JSON.stringify(values)});
      router.push("/setup");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unable to sign in.");
    }
  }

  async function passkeySignIn() {
    setError("");
    setPasskeyBusy(true);
    try {
      const optionsResponse = await fetch(`${API}/api/v1/auth/webauthn/login/start`, {method: "POST", credentials: "include"});
      if (!optionsResponse.ok) throw new Error("Passkey sign-in is unavailable right now.");
      const optionsJSON = await optionsResponse.json();
      const credential = await startAuthentication({optionsJSON});
      await api("/api/v1/auth/webauthn/login/finish", {method: "POST", body: JSON.stringify({credential})});
      router.push("/setup");
    } catch (e) {
      if (e instanceof Error && e.name === "NotAllowedError") setError("Passkey sign-in was cancelled.");
      else setError(e instanceof Error ? e.message : "Passkey sign-in failed.");
    } finally {
      setPasskeyBusy(false);
    }
  }

  async function sendMagicLink(event: React.FormEvent) {
    event.preventDefault();
    setError("");
    setMagicStatus("");
    setMagicDevelopmentUrl("");
    if (!/^\S+@\S+\.\S+$/.test(magicEmail)) {
      setMagicStatus("Enter a valid email address first.");
      return;
    }
    setMagicBusy(true);
    try {
      const result = await api<{delivery: string; throttled: boolean; development_url?: string | null}>("/api/v1/auth/magic/start", {method: "POST", body: JSON.stringify({email: magicEmail})});
      if (result.throttled) setMagicStatus("A link was sent moments ago. Check your inbox or wait a minute before retrying.");
      else if (result.delivery === "email") setMagicStatus("Check your inbox for a one-time sign-in link. It expires in 15 minutes.");
      else {
        setMagicStatus("Development email delivery is active.");
        setMagicDevelopmentUrl(result.development_url || "");
      }
    } catch (e) {
      setMagicStatus(e instanceof Error ? e.message : "The link could not be sent.");
    } finally {
      setMagicBusy(false);
    }
  }

  return <main className="login">
    <section className="login-story">
      <Link className="login-brand-link" href="/" aria-label="FinLeash"><Image src="/brand/finleash-primary-lockup-transparent.png" alt="FinLeash — Keep your finances in control" width={1249} height={750} className="brand-logo" priority/></Link>
      <div>
        <p className="eyebrow">Your money, in the right order</p>
        <h1>Know what will clear<br/>before it leaves.</h1>
        <p className="lede">FinLeash follows each paycheck and scheduled payment by account and date, so there are fewer expensive surprises.</p>
        <ul className="trust-list">
          <li><ShieldCheck/>Protect essentials and reserves</li>
          <li><WalletCards/>Track manual payments and autopay</li>
          <li><CheckCircle2/>See a plain-language answer today</li>
        </ul>
      </div>
      <p className="fine">Private planning · FinLeash never moves your money</p>
    </section>
    <section className="login-form">
      <div className="form-card">
        <div className="mobile-brand"><Image src="/brand/finleash-primary-lockup-transparent.png" alt="FinLeash — Keep your finances in control" width={1249} height={750} className="brand-logo"/></div>
        <p className="eyebrow">Welcome back</p>
        <h2>Sign in to your plan</h2>
        <p className="muted">Use your email and password or another secure sign-in method.</p>
        <div className="auth-methods">
          {methods.google && <a className="secondary wide" href={`${API}/api/v1/auth/google/start`}><GoogleMark/>Continue with Google</a>}
          {methods.passkeys && <button type="button" className="secondary wide" onClick={passkeySignIn} disabled={passkeyBusy}><KeyRound size={17}/>{passkeyBusy ? "Waiting for your passkey…" : "Sign in with a passkey"}</button>}
        </div>
        {methods.magic_link && <form className="magic-form" onSubmit={sendMagicLink} noValidate>
          <label>Email me a one-time sign-in link
            <div className="magic-row">
              <input type="email" autoComplete="email" placeholder="you@example.com" value={magicEmail} onChange={e => setMagicEmail(e.target.value)}/>
              <button className="secondary" disabled={magicBusy}><Mail size={16}/>{magicBusy ? "Sending…" : "Send link"}</button>
            </div>
          </label>
          {magicStatus && <p className="magic-status">{magicStatus}</p>}
          {magicDevelopmentUrl && <Link className="secondary wide" href={magicDevelopmentUrl}>Open development sign-in link</Link>}
        </form>}
        <div className="income-form-divider">or use a password</div>
        <form onSubmit={handleSubmit(submit)} noValidate>
          <label>Email address<input type="email" autoComplete="email" {...register("email")}/><span className="field-error">{errors.email?.message}</span></label>
          <label>Password<input type="password" autoComplete="current-password" {...register("password")}/><span className="field-error">{errors.password?.message}</span></label>
          <div className="auth-links"><Link href="/forgot-password">Forgot password?</Link></div>
          {error && <div className="error-box" role="alert">{error}</div>}
          <button className="primary wide" disabled={isSubmitting}>{isSubmitting ? "Signing in…" : "Sign in"}<ArrowRight size={18}/></button>
        </form>
        <p className="auth-footer">New to FinLeash? <Link href="/signup">Create an account</Link></p>
      </div>
    </section>
  </main>;
}
