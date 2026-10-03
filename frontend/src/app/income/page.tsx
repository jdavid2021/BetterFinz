"use client";
import { FormEvent, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, CircleDollarSign, Pencil, Plus, Trash2, X } from "lucide-react";
import { Shell } from "@/components/shell";
import { Money } from "@/components/status";
import { Account, api } from "@/lib/api";

type IncomeItem = {
  id: string;
  name: string;
  date: string;
  amount: string;
  reliability: string;
  account_id: string;
  status: string;
  frequency: string;
  series_id: string | null;
};
type IncomeCandidate = {
  id: string;
  name: string;
  account_id: string;
  account_name: string;
  amount: string;
  next_date: string;
  reliability: string;
  occurrences: number;
  frequency_days: number | null;
  last_received: string;
  last_amount: string;
};
type IncomeGroup = {
  key: string;
  next: IncomeItem;
  upcoming: number;
};
const confidenceLabel = (value: string) =>
  value === "guaranteed"
    ? "Guaranteed"
    : value === "high_confidence"
      ? "High confidence"
      : "Uncertain";
const frequencyLabels: Record<string, string> = {
  one_time: "One-time",
  weekly: "Weekly",
  biweekly: "Every 2 weeks",
  semi_monthly: "Twice a month",
  monthly: "Monthly",
};
const guessFrequency = (days: number | null) =>
  days == null ? "one_time" : days <= 9 ? "weekly" : days <= 17 ? "biweekly" : days <= 40 ? "monthly" : "one_time";

function groupIncome(items: IncomeItem[], todayIso: string): IncomeGroup[] {
  const map = new Map<string, IncomeItem[]>();
  for (const item of items) {
    const key = item.series_id || item.id;
    map.set(key, [...(map.get(key) || []), item]);
  }
  return [...map.entries()]
    .map(([key, list]) => {
      const sorted = [...list].sort((a, b) => a.date.localeCompare(b.date));
      const next = sorted.find((i) => i.date >= todayIso) || sorted[sorted.length - 1];
      return { key, next, upcoming: sorted.filter((i) => i.date >= todayIso).length };
    })
    .sort((a, b) => a.next.date.localeCompare(b.next.date));
}

export default function Income() {
  const [adding, setAdding] = useState(false),
    [editing, setEditing] = useState<IncomeItem | null>(null),
    [deleting, setDeleting] = useState<IncomeGroup | null>(null),
    [picked, setPicked] = useState<IncomeCandidate | null>(null),
    [errorMessage, setErrorMessage] = useState("");
  const queryClient = useQueryClient();
  const todayIso = new Date().toLocaleDateString("en-CA");
  const { data: income = [], isLoading } = useQuery({
    queryKey: ["income"],
    queryFn: () => api<IncomeItem[]>("/api/v1/income"),
  });
  const { data: candidates = [] } = useQuery({
    queryKey: ["income-candidates"],
    queryFn: () => api<IncomeCandidate[]>("/api/v1/income/candidates"),
  });
  const { data: accounts = [] } = useQuery({
    queryKey: ["accounts"],
    queryFn: () => api<Account[]>("/api/v1/accounts"),
  });
  const groups = groupIncome(income, todayIso);
  const depositAccounts = accounts.filter((a) =>
    ["checking", "savings", "money_market", "cash_management"].includes(a.kind),
  );
  function refresh() {
    queryClient.invalidateQueries({ queryKey: ["income"] });
    queryClient.invalidateQueries({ queryKey: ["income-candidates"] });
    queryClient.invalidateQueries({ queryKey: ["today"] });
  }
  function closeModal() {
    setAdding(false);
    setEditing(null);
    setPicked(null);
    setErrorMessage("");
  }
  const save = useMutation({
    mutationFn: ({ id, payload }: { id: string | null; payload: Record<string, string> }) =>
      api<IncomeItem>(id ? `/api/v1/income/${id}` : "/api/v1/income", {
        method: id ? "PUT" : "POST",
        body: JSON.stringify(payload),
      }),
    onSuccess: () => {
      refresh();
      closeModal();
    },
    onError: (error) =>
      setErrorMessage(
        error instanceof Error ? error.message : "Income could not be saved.",
      ),
  });
  const remove = useMutation({
    mutationFn: ({ id, scope }: { id: string; scope: "one" | "all" }) =>
      api<void>(`/api/v1/income/${id}?scope=${scope}`, { method: "DELETE" }),
    onSuccess: () => {
      refresh();
      setDeleting(null);
    },
  });
  function open() {
    setPicked(null);
    setEditing(null);
    setErrorMessage("");
    setAdding(true);
  }
  function openEdit(item: IncomeItem) {
    setPicked(null);
    setErrorMessage("");
    setEditing(item);
    setAdding(true);
  }
  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setErrorMessage("");
    const form = new FormData(event.currentTarget);
    save.mutate({
      id: editing?.id || null,
      payload: {
        name: String(form.get("name")),
        account_id: String(form.get("account_id")),
        amount: String(form.get("amount")),
        expected_date: String(form.get("expected_date")),
        reliability: String(form.get("reliability")),
        frequency: String(form.get("frequency")),
      },
    });
  }
  const accountName = (id: string) =>
    accounts.find((a) => a.id === id)?.name || "Deposit account";
  const deletingRecurring = deleting ? deleting.upcoming > 1 || !!deleting.next.series_id : false;
  return (
    <Shell>
      <div className="page-title">
        <div>
          <p className="eyebrow">Money expected</p>
          <h1>Income</h1>
          <p className="subtitle">
            Confirm income before FinLeash uses it to recommend debt payments.
          </p>
        </div>
        <button className="primary" onClick={open}>
          <Plus />
          Add income
        </button>
      </div>
      <section className="panel income-panel">
        <div className="panel-head">
          <div>
            <h2>Confirmed income</h2>
            <p>Only income you approve is included in payment planning.</p>
          </div>
        </div>
        {isLoading ? (
          <div className="empty compact">
            <p>Loading income…</p>
          </div>
        ) : groups.length === 0 ? (
          <div className="empty">
            <CircleDollarSign />
            <h2>No income confirmed yet</h2>
            <p>
              FinLeash found {candidates.length} possible income source
              {candidates.length === 1 ? "" : "s"} in your checking history.
            </p>
            <button className="primary" onClick={open}>
              <Plus />
              Review and add income
            </button>
          </div>
        ) : (
          groups.map((group) => (
            <div className="income-row manage" key={group.key}>
              <span className={`reliability ${group.next.reliability}`} />
              <div>
                <strong>{group.next.name}</strong>
                <p>
                  {confidenceLabel(group.next.reliability)} ·{" "}
                  {accountName(group.next.account_id)}
                </p>
              </div>
              <div>
                <strong className="income-frequency">
                  {frequencyLabels[group.next.frequency] || "One-time"}
                </strong>
                {group.upcoming > 1 && (
                  <p>{group.upcoming} upcoming deposits</p>
                )}
              </div>
              <span>
                {new Date(group.next.date + "T12:00").toLocaleDateString("en-US", {
                  month: "long",
                  day: "numeric",
                  year: "numeric",
                })}
              </span>
              <strong>
                +<Money value={group.next.amount} />
              </strong>
              <div className="income-actions">
                <button
                  className="icon-button"
                  aria-label={`Edit ${group.next.name}`}
                  title="Edit income"
                  onClick={() => openEdit(group.next)}
                >
                  <Pencil size={15} />
                </button>
                <button
                  className="icon-button danger-icon"
                  aria-label={`Delete ${group.next.name}`}
                  title="Delete income"
                  onClick={() => setDeleting(group)}
                >
                  <Trash2 size={15} />
                </button>
              </div>
            </div>
          ))
        )}
      </section>
      {adding && (
        <div className="modal-backdrop">
          <form
            className="modal income-modal"
            key={editing?.id || picked?.id || "manual"}
            onSubmit={submit}
          >
            <div className="modal-head">
              <div>
                <p className="eyebrow">Expected deposit</p>
                <h2>{editing ? "Edit income" : "Add income"}</h2>
                <p>
                  {editing
                    ? "Changes apply to this and all future deposits."
                    : "Choose a detected source or enter income manually."}
                </p>
              </div>
              <button
                type="button"
                className="icon-button"
                aria-label="Close"
                onClick={closeModal}
              >
                <X />
              </button>
            </div>
            {!editing && candidates.length > 0 && (
              <div className="income-picker">
                <div className="income-picker-head">
                  <strong>Detected from checking transactions</strong>
                  <span>Select one to review</span>
                </div>
                {candidates.map((candidate) => (
                  <button
                    type="button"
                    className={
                      picked?.id === candidate.id
                        ? "income-picker-option selected"
                        : "income-picker-option"
                    }
                    key={candidate.id}
                    onClick={() => setPicked(candidate)}
                  >
                    <span className={`reliability ${candidate.reliability}`} />
                    <div>
                      <strong>{candidate.name}</strong>
                      <small>
                        {candidate.account_name} · {candidate.occurrences}{" "}
                        deposit{candidate.occurrences === 1 ? "" : "s"}
                        {candidate.frequency_days
                          ? ` · every ${candidate.frequency_days} days`
                          : ""}
                      </small>
                    </div>
                    <div>
                      <small>Typical amount</small>
                      <strong>
                        <Money value={candidate.amount} />
                      </strong>
                    </div>
                    <span
                      className={`confidence-badge ${candidate.reliability}`}
                    >
                      {confidenceLabel(candidate.reliability)}
                    </span>
                    {picked?.id === candidate.id && (
                      <Check className="picked-check" />
                    )}
                  </button>
                ))}
              </div>
            )}
            {!editing && (
              <div className="income-form-divider">
                <span>
                  {picked ? "Review selected income" : "Or add manually"}
                </span>
              </div>
            )}
            <label>
              Income source
              <input
                name="name"
                required
                maxLength={100}
                placeholder="Employer paycheck, Social Security…"
                defaultValue={editing?.name || picked?.name || ""}
                autoFocus={!picked && !editing}
              />
            </label>
            <div className="form-grid">
              <label>
                Expected amount
                <input
                  name="amount"
                  type="number"
                  min="0.01"
                  step="0.01"
                  required
                  placeholder="0.00"
                  defaultValue={editing?.amount || picked?.amount || ""}
                />
              </label>
              <label>
                Next expected deposit
                <input
                  name="expected_date"
                  type="date"
                  required
                  defaultValue={
                    editing?.date ||
                    picked?.next_date ||
                    new Date().toISOString().slice(0, 10)
                  }
                />
              </label>
            </div>
            <div className="form-grid">
              <label>
                How often
                <select
                  name="frequency"
                  defaultValue={
                    editing?.frequency ||
                    (picked ? guessFrequency(picked.frequency_days) : "one_time")
                  }
                >
                  <option value="one_time">One-time deposit</option>
                  <option value="weekly">Weekly</option>
                  <option value="biweekly">Every 2 weeks</option>
                  <option value="semi_monthly">Twice a month</option>
                  <option value="monthly">Monthly</option>
                </select>
              </label>
              <label>
                Income confidence
                <select
                  name="reliability"
                  defaultValue={
                    editing?.reliability || picked?.reliability || "high_confidence"
                  }
                >
                  <option value="guaranteed">Guaranteed</option>
                  <option value="high_confidence">High confidence</option>
                  <option value="uncertain">Uncertain or variable</option>
                </select>
              </label>
            </div>
            <label>
              Deposit account
              <select
                name="account_id"
                required
                defaultValue={editing?.account_id || picked?.account_id || ""}
              >
                <option value="" disabled>
                  Choose checking or savings account
                </option>
                {depositAccounts.map((a) => (
                  <option value={a.id} key={a.id}>
                    {a.name}
                    {a.institution_name ? ` · ${a.institution_name}` : ""}
                  </option>
                ))}
              </select>
            </label>
            <p className="field-help">
              Recurring income schedules deposits for the next 12 months. Only
              guaranteed and high-confidence income supports payment
              recommendations.
            </p>
            {depositAccounts.length === 0 && (
              <div className="error-box">
                Add a checking, savings, or money market account before adding
                income.
              </div>
            )}
            {errorMessage && (
              <div className="error-box" role="alert">
                {errorMessage}
              </div>
            )}
            <button
              className="primary wide"
              disabled={save.isPending || depositAccounts.length === 0}
            >
              {save.isPending
                ? "Saving…"
                : editing
                  ? "Save changes"
                  : picked
                    ? "Save selected income"
                    : "Save income"}
            </button>
          </form>
        </div>
      )}
      {deleting && (
        <div className="modal-backdrop">
          <div className="modal confirm-modal">
            <div className="delete-icon">
              <Trash2 />
            </div>
            <h2>Delete {deleting.next.name}?</h2>
            <p>
              {deletingRecurring
                ? `This income repeats ${(frequencyLabels[deleting.next.frequency] || "").toLowerCase()}. You can remove just the ${new Date(deleting.next.date + "T12:00").toLocaleDateString("en-US", { month: "long", day: "numeric" })} deposit or the entire income with all its scheduled deposits.`
                : "This removes the expected deposit from your forecast. Posted bank transactions are not affected."}
            </p>
            {remove.isError && (
              <div className="error-box" role="alert">
                {remove.error instanceof Error
                  ? remove.error.message
                  : "Income could not be deleted."}
              </div>
            )}
            <div className="wizard-actions">
              <button
                type="button"
                className="secondary"
                onClick={() => setDeleting(null)}
                disabled={remove.isPending}
              >
                Keep income
              </button>
              {deletingRecurring && (
                <button
                  type="button"
                  className="secondary"
                  disabled={remove.isPending}
                  onClick={() =>
                    remove.mutate({ id: deleting.next.id, scope: "one" })
                  }
                >
                  This deposit only
                </button>
              )}
              <button
                type="button"
                className="danger-button"
                disabled={remove.isPending}
                onClick={() =>
                  remove.mutate({ id: deleting.next.id, scope: "all" })
                }
              >
                {remove.isPending
                  ? "Deleting…"
                  : deletingRecurring
                    ? "Delete entire income"
                    : "Delete income"}
              </button>
            </div>
          </div>
        </div>
      )}
    </Shell>
  );
}
