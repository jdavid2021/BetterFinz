import Image from "next/image";
import Link from "next/link";

export function AuthCard({
  eyebrow,
  title,
  description,
  children,
}: {
  eyebrow: string;
  title: string;
  description: string;
  children: React.ReactNode;
}) {
  return (
    <main className="auth-page">
      <section className="form-card auth-card">
        <Link className="auth-brand" href="/" aria-label="FinLeash sign in">
          <Image
            src="/brand/finleash-primary-lockup-transparent.png"
            alt="FinLeash"
            width={1249}
            height={750}
            className="brand-logo"
            priority
          />
        </Link>
        <p className="eyebrow">{eyebrow}</p>
        <h1>{title}</h1>
        <p className="muted">{description}</p>
        {children}
      </section>
    </main>
  );
}
