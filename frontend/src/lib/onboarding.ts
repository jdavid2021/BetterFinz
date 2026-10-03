export type OnboardingStatus = {
  dismissed?: boolean;
  complete?: boolean;
  account_complete?: boolean;
  income_complete?: boolean;
  plan_complete?: boolean;
};

export function shouldEnterSetup(path: string, status?: OnboardingStatus) {
  if (path !== "/today" || !status || status.dismissed) return false;
  const complete = status.complete ??
    Boolean(status.account_complete && status.income_complete && status.plan_complete);
  return !complete;
}
