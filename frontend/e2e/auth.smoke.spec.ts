import { expect, test } from "@playwright/test";

test("production auth entry points are reachable", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Sign in to your plan" })).toBeVisible();
  await expect(page.getByText("Local demo credentials")).toHaveCount(0);

  await page.getByRole("link", { name: "Create an account" }).click();
  await expect(page.getByRole("heading", { name: "Create your FinLeash account" })).toBeVisible();

  await page.goto("/forgot-password");
  await expect(page.getByRole("heading", { name: "Reset your password" })).toBeVisible();

  await page.goto("/reset-password?token=reset-token");
  await expect(page.getByRole("heading", { name: "Choose a new password" })).toBeVisible();
});

test("signup waits for verification and supports resend", async ({ page }) => {
  await page.route("**/api/v1/auth/signup", (route) => route.fulfill({ status: 202, contentType: "application/json", body: JSON.stringify({ message: "sent" }) }));
  await page.route("**/api/v1/auth/resend-verification", (route) => route.fulfill({ status: 202, contentType: "application/json", body: JSON.stringify({ message: "sent" }) }));
  await page.goto("/signup");
  await page.getByLabel("Full name").fill("Taylor Example");
  await page.getByLabel("Email address").fill("taylor@example.com");
  await page.getByLabel("Password", { exact: true }).fill("a-secure-passphrase");
  await page.getByLabel("Confirm password").fill("a-secure-passphrase");
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page.getByRole("heading", { name: "Check your email" })).toBeVisible();
  await page.getByRole("button", { name: "Resend verification email" }).click();
  await expect(page.getByText("A new verification email has been requested.")).toBeVisible();
});

test("email verification posts the token and opens setup", async ({ page }) => {
  let verificationBody = "";
  await page.route("**/api/v1/auth/verify-email", async (route) => {
    verificationBody = route.request().postData() || "";
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ verified: true }) });
  });
  await page.route("**/api/v1/onboarding/status", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ account_complete: false, income_complete: false, plan_complete: false, complete: false, dismissed: false }) }));
  await page.route("**/api/v1/accounts", (route) => route.fulfill({ status: 200, contentType: "application/json", body: "[]" }));
  await page.route("**/api/v1/income", (route) => route.fulfill({ status: 200, contentType: "application/json", body: "[]" }));
  await page.route("**/api/v1/bills", (route) => route.fulfill({ status: 200, contentType: "application/json", body: "[]" }));
  await page.goto("/verify-email?token=verify-token");
  await expect(page).toHaveURL(/\/setup$/);
  expect(verificationBody).toBe(JSON.stringify({ token: "verify-token" }));
});

test("verified signup and password recovery complete end to end", async ({ page }) => {
  const email = `launch-${Date.now()}@example.com`;
  const firstPassword = "launch-ready-password";
  const secondPassword = "updated-launch-password";

  await page.goto("/signup");
  await page.getByLabel("Full name").fill("Launch Test");
  await page.getByLabel("Email address").fill(email);
  await page.getByLabel("Password", { exact: true }).fill(firstPassword);
  await page.getByLabel("Confirm password").fill(firstPassword);
  await page.getByRole("button", { name: "Create account" }).click();
  await page.getByRole("link", { name: "Open development verification link" }).click();
  await expect(page.getByRole("heading", { name: "Build your first payment plan" })).toBeVisible();

  await page.goto("/forgot-password");
  await page.getByLabel("Email address").fill(email);
  await page.getByRole("button", { name: "Send reset link" }).click();
  await page.getByRole("link", { name: "Open development reset link" }).click();
  await page.getByLabel("New password", { exact: true }).fill(secondPassword);
  await page.getByLabel("Confirm new password").fill(secondPassword);
  await page.getByRole("button", { name: "Update password" }).click();
  await page.getByRole("link", { name: "Continue to sign in" }).click();
  await page.getByLabel("Email address").last().fill(email);
  await page.getByLabel("Password", { exact: true }).fill(secondPassword);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Build your first payment plan" })).toBeVisible();
});
