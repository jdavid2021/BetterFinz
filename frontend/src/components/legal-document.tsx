import Link from "next/link";

const operator = process.env.LEGAL_OPERATOR_NAME || "FinLeash";
const contact = process.env.LEGAL_CONTACT_EMAIL || "privacy@example.com";
const governingLaw =
  process.env.LEGAL_GOVERNING_LAW ||
  "the laws of the operator's registered jurisdiction";
const effectiveDate = process.env.LEGAL_EFFECTIVE_DATE || "2026-08-23";
const retentionDays = process.env.LEGAL_RETENTION_DAYS || "30";
const deletionGraceDays = process.env.DELETION_GRACE_DAYS || "30";

export function LegalDocument({kind}:{kind:"privacy"|"terms"}) {
  if (kind === "terms") return <main className="legal-page">
    <article className="panel">
      <p className="eyebrow">Legal</p>
      <h1>Terms of Service</h1>
      <p>Effective {effectiveDate}</p>
      <h2>Agreement and eligibility</h2>
      <p>These Terms govern your use of {operator}. You must be legally able to enter this agreement and provide accurate account information.</p>
      <h2>Planning service only</h2>
      <p>{operator} provides informational financial planning tools. It is not a bank, fiduciary, financial adviser, tax adviser, or payment processor. It does not hold or autonomously move money. Confirm all amounts, dates, and payment instructions with your financial institutions.</p>
      <h2>Your responsibilities</h2>
      <p>You are responsible for safeguarding access, using the service lawfully, maintaining accurate data, and independently deciding whether to act on projections. Do not upload data you lack authority to use.</p>
      <h2>Third-party services</h2>
      <p>Optional providers such as bank-data connections operate under their own terms. Availability and accuracy can change, and {operator} is not responsible for a third party&apos;s systems.</p>
      <h2>Intellectual property and acceptable use</h2>
      <p>You retain rights in your data. You may not disrupt, reverse engineer, abuse, or use the service to violate law or another person&apos;s rights.</p>
      <h2>Disclaimers and liability</h2>
      <p>The service is provided on an “as is” and “as available” basis to the extent permitted by law. Financial projections may be incomplete or delayed. Mandatory consumer rights are not excluded. To the extent permitted by law, indirect and consequential damages are excluded.</p>
      <h2>Termination and changes</h2>
      <p>You may stop using the service and request deletion. We may suspend abusive or unlawful use. Material revisions require acceptance of a new version before continued authenticated use.</p>
      <h2>Governing law and contact</h2>
      <p>These Terms are governed by {governingLaw}, without overriding mandatory rights that apply where you live. Questions: <a href={`mailto:${contact}`}>{contact}</a>.</p>
      <p><Link href="/privacy">Read the Privacy Notice</Link></p>
    </article>
  </main>;

  return <main className="legal-page">
    <article className="panel">
      <p className="eyebrow">Legal</p>
      <h1>Privacy Notice</h1>
      <p>Effective {effectiveDate}</p>
      <h2>Who controls your data</h2>
      <p>{operator} is the operator responsible for the processing described here. Contact <a href={`mailto:${contact}`}>{contact}</a> for privacy requests.</p>
      <h2>Data we process</h2>
      <p>We process account identity and security data, household settings, financial records you enter or connect, support communications, and limited security and audit events. We do not store bank passwords and do not sell personal information.</p>
      <h2>Purposes and legal bases</h2>
      <p>We process data to provide the service and fulfill our contract, secure accounts and prevent abuse based on legitimate interests, comply with law, and handle optional features with consent where required. You may withdraw consent without affecting earlier lawful processing.</p>
      <h2>Sharing and international transfers</h2>
      <p>Data may be handled by contracted hosting, email, authentication, and connection providers only as needed to operate the service, or disclosed where legally required. Where data crosses borders, we use an applicable transfer mechanism and safeguards.</p>
      <h2>Retention and deletion</h2>
      <p>We retain active-account data while needed to provide the service and limited operational records for the configured period of {retentionDays} days unless law requires otherwise. Confirmed deletion has a {deletionGraceDays}-day grace period, then household records are purged in dependency-safe order. An anonymized deletion tombstone is retained to evidence completion. Legal or security obligations may require limited exceptions.</p>
      <h2>Your choices and rights</h2>
      <p>Depending on your location, you may request access, correction, portability, deletion, restriction, objection, or withdrawal of consent; opt out of sale, sharing, or targeted advertising where applicable; and appeal or complain to a regulator. We may verify your identity before acting. The service provides a ZIP export and deletion controls in Settings.</p>
      <h2>US state disclosures</h2>
      <p>We do not sell personal information or share it for cross-context behavioral advertising. Authorized agents may submit requests, subject to authority and identity verification. We do not discriminate for exercising applicable privacy rights.</p>
      <h2>Security, children, and changes</h2>
      <p>We use administrative and technical safeguards, but no system is risk-free. The service is not directed to children under 13 or a higher local minimum age. Material notice revisions require a new version acceptance.</p>
      <p><Link href="/terms">Read the Terms of Service</Link></p>
    </article>
  </main>;
}
