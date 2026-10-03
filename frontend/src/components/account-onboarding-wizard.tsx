"use client";

import { ChangeEvent, useState } from "react";
import {
  ArrowLeft,
  ArrowRight,
  Check,
  FileSearch,
  Landmark,
  PencilLine,
  Upload,
  X,
} from "lucide-react";
import { useMutation } from "@tanstack/react-query";
import { Money } from "@/components/status";
import { api } from "@/lib/api";

type Fields = {
  name: string;
  institution_name: string;
  kind: string;
  mask: string;
  balance: string;
  available_balance: string;
  investment_balance: string;
  original_balance: string;
  balance_as_of_date: string | null;
  statement_date: string | null;
  due_date: string | null;
  minimum_payment: string | null;
  interest_rate: string | null;
  interest_paid: string | null;
  payments_and_credits: string | null;
};
type Preview = {
  detected_format: string;
  filename: string;
  transaction_count: number;
  fields: Fields;
  confidence: Record<string, string>;
  duplicate_account: {
    id: string;
    name: string;
    institution_name: string | null;
  } | null;
  institution_suggestion: {
    id: string;
    name: string;
    login_url: string;
    domains: string[];
    confidence: string;
    source: string;
    verified: boolean;
  } | null;
  diagnostics: string[];
};
type Props = {
  onClose: () => void;
  onManual: () => void;
  onComplete: () => void;
};
const liabilityKinds = [
  "credit_card",
  "mortgage",
  "auto_loan",
  "buy_now_pay_later",
  "loan",
  "other",
];
const label = (kind: string) =>
  kind === "buy_now_pay_later"
    ? "Buy now, pay later"
    : kind.replaceAll("_", " ");
const dateText = (value: string | null) =>
  value ? new Date(value + "T12:00:00").toLocaleDateString() : "Not detected";

export function AccountOnboardingWizard({
  onClose,
  onManual,
  onComplete,
}: Props) {
  const [step, setStep] = useState(0),
    [file, setFile] = useState<File | null>(null),
    [preview, setPreview] = useState<Preview | null>(null),
    [draft, setDraft] = useState<Fields | null>(null),
    [reserve, setReserve] = useState("0"),
    [bankUrl, setBankUrl] = useState(""),
    [useSuggestedInstitution, setUseSuggestedInstitution] = useState(false),
    [useExisting, setUseExisting] = useState(true),
    [error, setError] = useState("");
  const analyze = useMutation({
    mutationFn: (selected: File) => {
      const body = new FormData();
      body.append("file", selected);
      return api<Preview>("/api/v1/accounts/statement-preview", {
        method: "POST",
        body,
      });
    },
    onSuccess: (value) => {
      setPreview(value);
      setDraft(value.fields);
      setBankUrl("");
      setUseSuggestedInstitution(false);
      setUseExisting(Boolean(value.duplicate_account));
      setError("");
      setStep(2);
    },
    onError: (e) => setError(e.message),
  });
  const create = useMutation({
    mutationFn: () => {
      if (!file || !draft) throw new Error("Choose a statement first.");
      const body = new FormData();
      Object.entries({
        name: draft.name,
        kind: draft.kind,
        mask: draft.mask,
        balance: draft.balance,
        available_balance: draft.available_balance,
        investment_balance: draft.investment_balance,
        original_balance: draft.original_balance,
        reserve,
        institution_name: draft.institution_name,
        bank_login_url: bankUrl,
        institution_id: useSuggestedInstitution
          ? preview?.institution_suggestion?.id || ""
          : "",
        existing_account_id: useExisting
          ? preview?.duplicate_account?.id || ""
          : "",
      }).forEach(([key, value]) => {
        if (value !== "") body.append(key, value);
      });
      body.append("file", file);
      return api("/api/v1/accounts/from-statement", { method: "POST", body });
    },
    onSuccess: onComplete,
    onError: (e) => setError(e.message),
  });
  function choose(event: ChangeEvent<HTMLInputElement>) {
    const selected = event.target.files?.[0];
    if (!selected) return;
    setFile(selected);
    setError("");
    analyze.mutate(selected);
  }
  function update(key: keyof Fields, value: string) {
    setDraft((current) => (current ? { ...current, [key]: value } : current));
  }
  const progress = Math.max(step, 1);
  return (
    <div className="modal-backdrop">
      <section
        className="modal onboarding-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="onboarding-title"
      >
        <div className="modal-head">
          <div>
            <p className="eyebrow">Add account · Step {progress} of 5</p>
            <h2 id="onboarding-title">
              {step === 0
                ? "How would you like to begin?"
                : step === 1
                  ? "Upload your latest statement"
                  : step === 2
                    ? "Confirm the account"
                    : step === 3
                      ? "Review the financial details"
                      : "Review and create"}
            </h2>
          </div>
          <button
            type="button"
            className="icon-button"
            aria-label="Close"
            onClick={onClose}
          >
            <X />
          </button>
        </div>
        <div className="wizard-progress">
          {[1, 2, 3, 4, 5].map((number) => (
            <span className={number <= progress ? "active" : ""} key={number} />
          ))}
        </div>
        {step === 0 && (
          <div className="onboarding-choices">
            <button onClick={() => setStep(1)}>
              <span>
                <Upload />
              </span>
              <div>
                <strong>Upload a statement</strong>
                <p>
                  Recommended · detect the institution, account type, balance,
                  transactions, and payment details.
                </p>
              </div>
              <ArrowRight />
            </button>
            <button
              onClick={() => {
                onClose();
                onManual();
              }}
            >
              <span>
                <PencilLine />
              </span>
              <div>
                <strong>Enter manually</strong>
                <p>Create the account using the existing form.</p>
              </div>
              <ArrowRight />
            </button>
          </div>
        )}
        {step === 1 && (
          <div className="wizard-upload">
            <FileSearch />
            <h3>Choose a statement or transaction export</h3>
            <p>PDF, QFX, QBO, OFX, QBX, or CSV · maximum 20 MB</p>
            <label className="file-input">
              <Upload />
              Choose file
              <input
                type="file"
                accept=".pdf,.csv,.ofx,.qfx,.qbo,.qbx"
                onChange={choose}
              />
            </label>
            {analyze.isPending && (
              <p className="wizard-working">
                Analyzing account identity, balances, and statement details…
              </p>
            )}
          </div>
        )}
        {step === 2 && draft && preview && (
          <div className="wizard-body">
            {preview.duplicate_account && (
              <div className="duplicate-account">
                <Landmark />
                <div>
                  <strong>
                    This appears to match {preview.duplicate_account.name}
                  </strong>
                  <p>
                    Import into the existing account to avoid creating a
                    duplicate.
                  </p>
                </div>
                <label>
                  <input
                    type="checkbox"
                    checked={useExisting}
                    onChange={(e) => setUseExisting(e.target.checked)}
                  />{" "}
                  Use existing
                </label>
              </div>
            )}
            <label>
              Account name
              <input
                value={draft.name}
                onChange={(e) => update("name", e.target.value)}
                required
              />
            </label>
            <div className="form-grid">
              <label>
                Institution
                <input
                  value={draft.institution_name}
                  onChange={(e) => {
                    update("institution_name", e.target.value);
                    if (e.target.value !== preview.institution_suggestion?.name)
                      setUseSuggestedInstitution(false);
                  }}
                />
                <small
                  className={`confidence ${preview.confidence.institution_name}`}
                >
                  {preview.confidence.institution_name} confidence
                </small>
              </label>
              <label>
                Account type
                <select
                  value={draft.kind}
                  onChange={(e) => update("kind", e.target.value)}
                >
                  {[
                    "checking",
                    "savings",
                    "credit_card",
                    "money_market",
                    "cash_management",
                    "mortgage",
                    "auto_loan",
                    "buy_now_pay_later",
                    "loan",
                    "investment",
                    "other",
                  ].map((kind) => (
                    <option value={kind} key={kind}>
                      {label(kind)}
                    </option>
                  ))}
                </select>
                <small className={`confidence ${preview.confidence.kind}`}>
                  {preview.confidence.kind} confidence
                </small>
              </label>
            </div>
            <label>
              Last 2–4 account characters
              <input
                minLength={2}
                maxLength={4}
                pattern="[A-Za-z0-9]{2,4}"
                value={draft.mask}
                onChange={(e) => update("mask", e.target.value)}
                required
              />
              <small className={`confidence ${preview.confidence.mask}`}>
                {preview.confidence.mask} confidence
              </small>
            </label>
            <div className="wizard-detected">
              <span>{preview.detected_format.toUpperCase()}</span>
              <span>{preview.transaction_count} transactions detected</span>
              <span>Statement date {dateText(draft.statement_date)}</span>
            </div>
          </div>
        )}
        {step === 3 && draft && preview && (
          <div className="wizard-body">
            <div className="form-grid">
              <label>
                {draft.kind === "cash_management"
                  ? "Total account value"
                  : liabilityKinds.includes(draft.kind)
                  ? "Statement / outstanding balance"
                  : "Closing balance"}
                <input
                  type="number"
                  min="0"
                  step="0.01"
                  value={draft.balance}
                  onChange={(e) => update("balance", e.target.value)}
                  required
                />
                <small className={`confidence ${preview.confidence.balance}`}>
                  {preview.confidence.balance} confidence
                </small>
              </label>
              {draft.kind === "cash_management" ? (
                <><label>Spendable cash<input type="number" min="0" step="0.01" value={draft.available_balance} onChange={(e)=>update("available_balance",e.target.value)}/></label><label>Investment holdings<input type="number" min="0" step="0.01" value={draft.investment_balance} onChange={(e)=>update("investment_balance",e.target.value)}/></label></>
              ) : draft.kind === "credit_card" ? (
                <label>
                  Available credit
                  <input
                    type="number"
                    min="0"
                    step="0.01"
                    value={draft.available_balance}
                    onChange={(e) =>
                      update("available_balance", e.target.value)
                    }
                  />
                </label>
              ) : draft.kind === "mortgage" ? (
                <label>
                  Original mortgage
                  <input
                    type="number"
                    min="0"
                    step="0.01"
                    value={draft.original_balance}
                    onChange={(e) => update("original_balance", e.target.value)}
                  />
                </label>
              ) : (
                !liabilityKinds.includes(draft.kind) && (
                  <label>
                    Available balance
                    <input
                      type="number"
                      min="0"
                      step="0.01"
                      value={draft.available_balance}
                      onChange={(e) =>
                        update("available_balance", e.target.value)
                      }
                    />
                  </label>
                )
              )}
            </div>
            {liabilityKinds.includes(draft.kind) && (
              <div className="detected-financial-grid">
                <div>
                  <span>Due date</span>
                  <strong>{dateText(draft.due_date)}</strong>
                </div>
                <div>
                  <span>Minimum payment</span>
                  <strong>
                    {draft.minimum_payment ? (
                      <Money value={draft.minimum_payment} />
                    ) : (
                      "Not detected"
                    )}
                  </strong>
                </div>
                <div>
                  <span>Interest rate</span>
                  <strong>
                    {draft.interest_rate
                      ? `${draft.interest_rate}%`
                      : "Not detected"}
                  </strong>
                </div>
                <div>
                  <span>Interest charged</span>
                  <strong>
                    {draft.interest_paid ? (
                      <Money value={draft.interest_paid} />
                    ) : (
                      "Not detected"
                    )}
                  </strong>
                </div>
              </div>
            )}
            <label>
              Bank login website <span>optional</span>
              <input
                type="url"
                placeholder="https://www.example.com/"
                value={bankUrl}
                onChange={(e) => {
                  setBankUrl(e.target.value);
                  if (e.target.value !== preview.institution_suggestion?.login_url)
                    setUseSuggestedInstitution(false);
                }}
              />
            </label>
            {preview.institution_suggestion && (
              <div className="duplicate-account">
                <Landmark />
                <div>
                  <strong>Verified institution match</strong>
                  <p>
                    {preview.institution_suggestion.name} · {preview.institution_suggestion.domains[0]}
                    {" · "}{preview.institution_suggestion.source}
                  </p>
                </div>
                <label>
                  <input
                    type="checkbox"
                    checked={useSuggestedInstitution}
                    onChange={(e) => {
                      setUseSuggestedInstitution(e.target.checked);
                      if (e.target.checked) {
                        update("institution_name", preview.institution_suggestion!.name);
                        setBankUrl(preview.institution_suggestion!.login_url);
                      }
                    }}
                  />{" "}
                  Confirm
                </label>
              </div>
            )}
            {["checking", "savings", "money_market", "cash_management"].includes(draft.kind) && (
              <label>
                Protected reserve <span>your planning preference</span>
                <input
                  type="number"
                  min="0"
                  step="0.01"
                  value={reserve}
                  onChange={(e) => setReserve(e.target.value)}
                />
              </label>
            )}
          </div>
        )}
        {step === 4 && draft && preview && (
          <div className="wizard-review">
            <div className="review-account">
              <Landmark />
              <div>
                <strong>
                  {useExisting && preview.duplicate_account
                    ? preview.duplicate_account.name
                    : draft.name}
                </strong>
                <p>
                  {draft.institution_name || "Institution not provided"} ·{" "}
                  {label(draft.kind)} · •••• {draft.mask}
                </p>
              </div>
            </div>
            <ul>
              <li>
                <Check />{" "}
                {useExisting && preview.duplicate_account
                  ? "Import into the matching existing account"
                  : "Create one account"}
              </li>
              <li>
                <Check /> Set balance to <Money value={draft.balance} /> as of{" "}
                {dateText(draft.balance_as_of_date)}
              </li>
              <li>
                <Check /> Import {preview.transaction_count} detected
                transactions and skip duplicates
              </li>
              <li>
                <Check /> Save the statement and payment details in 12-month
                history
              </li>
              <li>
                <Check /> Record this upload as {preview.filename}
              </li>
              <li>
                <Check />{" "}
                {useSuggestedInstitution && preview.institution_suggestion
                  ? `Use verified website ${preview.institution_suggestion.domains[0]}`
                  : bankUrl
                    ? "Use the manually entered bank website"
                    : "No bank website saved"}
              </li>
            </ul>
            <p className="review-note">
              FinLeash will not store bank credentials or move money.
            </p>
          </div>
        )}
        {error && (
          <div className="error-box" role="alert">
            {error}
          </div>
        )}
        {step > 0 && (
          <div className="wizard-actions">
            <button
              className="secondary"
              onClick={() => {
                setError("");
                setStep((value) => Math.max(0, value - 1));
              }}
            >
              <ArrowLeft />
              Back
            </button>
            {step === 2 && (
              <button
                className="primary"
                disabled={!draft?.name || !draft.mask}
                onClick={() => setStep(3)}
              >
                Review balances
                <ArrowRight />
              </button>
            )}
            {step === 3 && (
              <button className="primary" onClick={() => setStep(4)}>
                Final review
                <ArrowRight />
              </button>
            )}
            {step === 4 && (
              <button
                className="primary"
                disabled={create.isPending}
                onClick={() => create.mutate()}
              >
                {create.isPending
                  ? "Creating and importing…"
                  : "Create account and import"}
              </button>
            )}
          </div>
        )}
      </section>
    </div>
  );
}
