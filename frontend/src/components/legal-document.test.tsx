import {render, screen} from "@testing-library/react";
import {describe, expect, it} from "vitest";
import {LegalDocument} from "./legal-document";

describe("public legal templates",()=>{
  it("includes GDPR and US privacy rights plus retention",()=>{
    render(<LegalDocument kind="privacy"/>);
    expect(screen.getByText("Privacy Notice")).toBeInTheDocument();
    expect(screen.getByText(/access, correction, portability, deletion/)).toBeInTheDocument();
    expect(screen.getByText(/opt out of sale, sharing/)).toBeInTheDocument();
    expect(screen.getByText(/anonymized deletion tombstone/)).toBeInTheDocument();
  });

  it("states the service never autonomously moves money",()=>{
    render(<LegalDocument kind="terms"/>);
    expect(screen.getByText(/does not hold or autonomously move money/)).toBeInTheDocument();
  });
});
