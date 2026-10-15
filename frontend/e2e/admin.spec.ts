import { expect, test } from "@playwright/test";
import { ADMIN_EMAIL, ADMIN_PASSWORD, api, login } from "./helpers";

test("onboarding a customer creates an isolated workspace with its administrator", async ({ page }) => {
  const stamp = Date.now().toString(36);
  const name = `E2E Customer ${stamp}`;
  await login(page, ADMIN_EMAIL, ADMIN_PASSWORD);
  await page.goto("/admin/customers");
  await page.getByRole("button", { name: /new customer/i }).click();
  await page.fill("#nc-name", name);
  await page.fill("#nc-slug", `e2e-${stamp}`);
  await page.fill("#nc-ae", `owner@e2e-${stamp}.example`);
  const created = page.waitForResponse((r) => new URL(r.url()).pathname === "/v1/organizations" && r.request().method() === "POST");
  await page.getByRole("button", { name: "Create customer" }).click();
  const org = await (await created).json();
  await expect(page.getByText(`Temporary password for owner@e2e-${stamp}.example`)).toBeVisible();

  // the new workspace starts empty — nothing from other customers is visible to it
  const counts = await (await api(page.request, "GET", "/v1/assets", { org: org.organization_id })).json();
  expect(counts.total).toBe(0);

  // clean up: request deletion with no grace period; the worker purges it
  const del = await api(page.request, "POST", `/v1/organizations/${org.organization_id}/request-deletion`, {
    data: { confirm_slug: `e2e-${stamp}`, grace_days: 0 },
  });
  expect(del.ok()).toBeTruthy();
});
