"use client";

import Link from "next/link";
import { FormEvent, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowRight, Check, CircleDollarSign, CalendarDays, Landmark, X } from "lucide-react";
import { AccountOnboardingWizard } from "@/components/account-onboarding-wizard";
import { api, Account } from "@/lib/api";
import { onboardingRoutes } from "@/lib/frontend-routes";

type SetupStatus = {
  dismissed?: boolean;
  account_complete?: boolean;
  income_complete?: boolean;
  plan_complete?: boolean;
  complete?: boolean;
};
type IncomeItem = { id: string };
type Bill = { id: string };

export default function SetupPage() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [showAccountWizard, setShowAccountWizard] = useState(false);
  const [showIncomeForm, setShowIncomeForm] = useState(false);
  const [error, setError] = useState("");
  const {data: me} = useQuery({
    queryKey: ["me"],
    queryFn: () => api<{legal:{required:boolean}}>("/api/v1/auth/me"),
    retry: false,
  });
  const { data: status } = useQuery({
    queryKey: ["onboarding-status"],
    queryFn: () => api<SetupStatus>(onboardingRoutes.status),
    retry: false,
  });
  useEffect(() => {
    if (me?.legal.required) {
      router.replace("/legal-review");
      return;
    }
    if (status?.dismissed || status?.complete) router.replace("/today");
  }, [me, router, status]);
  const { data: accounts = [] } = useQuery({
    queryKey: ["accounts"],
    queryFn: () => api<Account[]>("/api/v1/accounts"),
  });
  const { data: income = [] } = useQuery({
    queryKey: ["income"],
    queryFn: () => api<IncomeItem[]>("/api/v1/income"),
  });
  const { data: bills = [] } = useQuery({
    queryKey: ["bills"],
    queryFn: () => api<Bill[]>("/api/v1/bills"),
  });
  const accountComplete = status?.account_complete ?? accounts.length > 0;
  const incomeComplete = status?.income_complete ?? income.length > 0;
  const planComplete = status?.plan_complete ?? bills.length > 0;
  const activeStep = !accountComplete ? 0 : !incomeComplete ? 1 : !planComplete ? 2 : 3;

  const dismiss = useMutation({
    mutationFn: () => api(onboardingRoutes.dismiss, { method: "POST" }),
    onSuccess: () => router.push("/today"),
    onError: (reason) => setError(reason instanceof Error ? reason.message : "Setup could not be dismissed."),
  });
  const saveIncome = useMutation({
    mutationFn: (body: Record<string, string>) =>
      api("/api/v1/income", { method: "POST", body: JSON.stringify(body) }),
    onSuccess: () => {
      setShowIncomeForm(false);
      setError("");
      queryClient.invalidateQueries({ queryKey: ["income"] });
      queryClient.invalidateQueries({ queryKey: ["onboarding-status"] });
    },
    onError: (reason) => setError(reason instanceof Error ? reason.message : "Income could not be saved."),
  });

  function submitIncome(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const values = new FormData(event.currentTarget);
    saveIncome.mutate({
      name: String(values.get("name")),
      account_id: String(values.get("account_id")),
      amount: String(values.get("amount")),
      expected_date: String(values.get("expected_date")),
      reliability: String(values.get("reliability")),
      frequency: String(values.get("frequency")),
    });
  }

  return (
    <main className="setup-page">
      <header className="setup-header">
        <Link href="/today" className="setup-wordmark">FinLeash</Link>
        <button className="text-button setup-dismiss" onClick={() => dismiss.mutate()} disabled={dismiss.isPending}>
          <X size={15} /> Finish later
        </button>
      </header>
      <section className="setup-card">
        <p className="eyebrow">Guided setup</p>
        <h1>Build your first payment plan</h1>
        <p className="subtitle">Add only what you need. You can change every detail later.</p>
        <div className="setup-progress" aria-label={`Setup step ${Math.min(activeStep + 1, 3)} of 3`}>
          {[0, 1, 2].map((step) => <span key={step} className={step <= activeStep ? "active" : ""} />)}
        </div>
        <div className="setup-steps">
          <SetupStep number={1} icon={<Landmark />} title="Add an account" description="Start with the checking account that pays your bills." complete={accountComplete} active={activeStep === 0}>
            <button className="primary" onClick={() => setShowAccountWizard(true)}>Add account <ArrowRight size={16} /></button>
          </SetupStep>
          <SetupStep number={2} icon={<CircleDollarSign />} title="Confirm income" description="Tell FinLeash which deposits are dependable enough to plan around." complete={incomeComplete} active={activeStep === 1}>
            <button className="primary" disabled={!accountComplete} onClick={() => setShowIncomeForm(true)}>Add income <ArrowRight size={16} /></button>
          </SetupStep>
          <SetupStep number={3} icon={<CalendarDays />} title="Create your plan" description="Add recurring bills and review when each payment can safely clear." complete={planComplete} active={activeStep === 2}>
            <Link className={incomeComplete ? "primary" : "primary disabled-link"} aria-disabled={!incomeComplete} href={incomeComplete ? "/monthly-plan?from=setup" : "#"}>Open Payment Plan <ArrowRight size={16} /></Link>
          </SetupStep>
        </div>
        {error && !showIncomeForm && <div className="error-box setup-error" role="alert">{error}</div>}
        {activeStep === 3 && (
          <div className="setup-complete">
            <Check />
            <div><strong>Your foundation is ready</strong><p>FinLeash can now show your payment coverage.</p></div>
            <button className="primary" onClick={() => dismiss.mutate()}>Go to Today</button>
          </div>
        )}
      </section>
      {showAccountWizard && <AccountOnboardingWizard onClose={() => setShowAccountWizard(false)} onManual={() => router.push("/accounts?add=manual")} onComplete={() => {
        setShowAccountWizard(false);
        queryClient.invalidateQueries({ queryKey: ["accounts"] });
        queryClient.invalidateQueries({ queryKey: ["onboarding-status"] });
      }} />}
      {showIncomeForm && (
        <div className="modal-backdrop">
          <form className="modal" onSubmit={submitIncome}>
            <div className="modal-head"><div><p className="eyebrow">Setup · Income</p><h2>Add expected income</h2><p>FinLeash uses the schedule provided by the API; no totals are calculated here.</p></div><button type="button" className="icon-button" aria-label="Close" onClick={() => setShowIncomeForm(false)}><X /></button></div>
            <label>Income source<input name="name" required maxLength={100} placeholder="Employer paycheck" /></label>
            <div className="form-grid"><label>Expected amount<input name="amount" type="number" min="0.01" step="0.01" required /></label><label>Next expected deposit<input name="expected_date" type="date" required defaultValue={new Date().toISOString().slice(0, 10)} /></label></div>
            <div className="form-grid"><label>How often<select name="frequency" defaultValue="biweekly"><option value="weekly">Weekly</option><option value="biweekly">Every 2 weeks</option><option value="semi_monthly">Twice a month</option><option value="monthly">Monthly</option><option value="one_time">One time</option></select></label><label>Confidence<select name="reliability" defaultValue="high_confidence"><option value="guaranteed">Guaranteed</option><option value="high_confidence">High confidence</option><option value="uncertain">Uncertain or variable</option></select></label></div>
            <label>Deposit account<select name="account_id" required defaultValue=""><option value="" disabled>Choose an account</option>{accounts.filter((account) => ["checking", "savings", "money_market", "cash_management"].includes(account.kind)).map((account) => <option value={account.id} key={account.id}>{account.name}</option>)}</select></label>
            {error && <div className="error-box" role="alert">{error}</div>}
            <button className="primary wide" disabled={saveIncome.isPending}>{saveIncome.isPending ? "Saving…" : "Save income"}</button>
          </form>
        </div>
      )}
    </main>
  );
}

function SetupStep({ number, icon, title, description, complete, active, children }: { number: number; icon: React.ReactNode; title: string; description: string; complete: boolean; active: boolean; children: React.ReactNode }) {
  return <article className={`setup-step${active ? " active" : ""}${complete ? " complete" : ""}`}><div className="setup-step-icon">{complete ? <Check /> : icon}</div><div><span>Step {number}</span><h2>{title}</h2><p>{description}</p></div><div className="setup-step-action">{complete ? <strong><Check size={15} /> Complete</strong> : children}</div></article>;
}
