"use client";
import {useCallback, useEffect, useState} from "react";
import {KeyRound} from "lucide-react";
import {startRegistration} from "@simplewebauthn/browser";
import {Shell} from "@/components/shell";
import {SimpleFinSettings} from "@/components/simplefin-settings";
import {AccountingSettings} from "@/components/accounting-settings";
import {PrivacySettings} from "@/components/privacy-settings";
import {NotificationPreferences} from "@/components/notification-preferences";
import {api, API} from "@/lib/api";

type Passkey = {id: string; label: string; created_at: string; last_used_at: string | null};

function Passkeys() {
  const [passkeys, setPasskeys] = useState<Passkey[]>([]);
  const [status, setStatus] = useState("");
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(async () => {
    try {
      setPasskeys(await api<Passkey[]>("/api/v1/auth/webauthn/credentials"));
    } catch {
      setPasskeys([]);
    }
  }, []);
  useEffect(() => {void refresh();}, [refresh]);

  async function addPasskey() {
    setStatus("");
    setBusy(true);
    try {
      const optionsResponse = await fetch(`${API}/api/v1/auth/webauthn/register/start`, {method: "POST", credentials: "include"});
      if (!optionsResponse.ok) throw new Error("Passkey setup is unavailable right now.");
      const optionsJSON = await optionsResponse.json();
      const credential = await startRegistration({optionsJSON});
      const label = window.prompt("Name this passkey (for example: Laptop, Phone)", "This device") || "This device";
      await api("/api/v1/auth/webauthn/register/finish", {method: "POST", body: JSON.stringify({credential, label})});
      setStatus("Passkey added. You can now sign in without a password on this device.");
      await refresh();
    } catch (e) {
      if (e instanceof Error && e.name === "NotAllowedError") setStatus("Passkey setup was cancelled.");
      else if (e instanceof Error && e.name === "InvalidStateError") setStatus("This device already has a passkey for your account.");
      else setStatus(e instanceof Error ? e.message : "The passkey could not be added.");
    } finally {
      setBusy(false);
    }
  }

  async function removePasskey(id: string) {
    if (!window.confirm("Remove this passkey? You will no longer be able to sign in with it.")) return;
    await api(`/api/v1/auth/webauthn/credentials/${id}`, {method: "DELETE"});
    await refresh();
  }

  return <section className="panel import-card">
    <span className="big-icon"><KeyRound/></span>
    <div>
      <h2>Passkeys</h2>
      <p>Sign in with your fingerprint, face, or device PIN instead of a password. Passkeys stay on your device and cannot be phished.</p>
      <div className="passkey-list">
        {passkeys.map(item => <div className="passkey-row" key={item.id}>
          <KeyRound size={16}/>
          <div>
            <strong>{item.label}</strong>
            <small>Added {new Date(item.created_at).toLocaleDateString()}{item.last_used_at ? ` · Last used ${new Date(item.last_used_at).toLocaleDateString()}` : ""}</small>
          </div>
          <button onClick={() => removePasskey(item.id)}>Remove</button>
        </div>)}
        {passkeys.length === 0 && <p className="muted" style={{fontSize: 12, margin: 0}}>No passkeys yet.</p>}
      </div>
      <form onSubmit={e => {e.preventDefault(); void addPasskey();}}>
        <button className="primary" disabled={busy}>{busy ? "Follow your browser's prompt…" : "Add a passkey"}</button>
      </form>
      {status && <div className="import-result"><p>{status}</p></div>}
    </div>
  </section>;
}

export default function Settings() {
  return <Shell>
    <div className="page-title"><div><p className="eyebrow">Household</p><h1>Settings</h1><p className="subtitle">Manage accounting preferences, sign-in security, and connected financial accounts.</p></div></div>
    <AccountingSettings/>
    <Passkeys/>
    <NotificationPreferences/>
    <div id="connections"><SimpleFinSettings/></div>
    <PrivacySettings/>
  </Shell>;
}
