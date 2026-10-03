import { describe, expect, it } from "vitest";
import { loginSchema, signupSchema } from "./auth-validation";

describe("auth validation", () => {
  it("accepts a production login without demo defaults", () => {
    expect(loginSchema.safeParse({ email: "person@example.com", password: "long-enough" }).success).toBe(true);
  });

  it("requires a stronger matching password for signup", () => {
    expect(signupSchema.safeParse({
      name: "Taylor",
      email: "person@example.com",
      password: "a-secure-passphrase",
      confirmPassword: "different-passphrase",
    }).success).toBe(false);
    expect(signupSchema.safeParse({
      name: "Taylor",
      email: "person@example.com",
      password: "a-secure-passphrase",
      confirmPassword: "a-secure-passphrase",
    }).success).toBe(true);
  });
});
