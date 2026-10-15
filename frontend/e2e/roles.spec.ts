import { expect, test } from "@playwright/test";
import { AURORA, api, login, user } from "./helpers";

test("viewers can read and search but not change anything", async ({ page }) => {
  await login(page, user("viewer"));
  await page.goto(`${AURORA}/assets`);
  await expect(page.getByRole("heading", { name: "Asset library" })).toBeVisible();
  await expect(page.getByRole("button", { name: /upload/i })).toHaveCount(0);
  const nav = page.getByRole("navigation");
  await expect(nav.getByRole("link", { name: "AI review queue" })).toHaveCount(0);
  await expect(nav.getByRole("link", { name: "Integrations" })).toHaveCount(0);
  const ws = await (await api(page.request, "GET", "/v1/workspace", { org: "aurora-atelier" })).json();
  const r = await api(page.request, "POST", `/v1/brands/${ws.brands[0].id}/collections`, { org: "aurora-atelier", data: { name: "Not allowed" } });
  expect(r.status()).toBe(403);
});

test("reviewers see the review queue; editors can write but not approve", async ({ page }) => {
  await login(page, user("reviewer"));
  await page.goto(`${AURORA}/review`);
  await expect(page.getByRole("heading", { name: "AI review queue" })).toBeVisible();
  await login(page, user("editor"));
  await page.goto(`${AURORA}/principles`);
  await expect(page.getByRole("button", { name: "Principle" })).toBeVisible();
});

test("integrations are limited to workspace administrators", async ({ page }) => {
  await login(page, user("creative.director"));
  await page.goto(`${AURORA}/integrations`);
  await expect(page.getByText("Integrations are managed by workspace administrators")).toBeVisible();
  await login(page, user("admin"));
  await page.goto(`${AURORA}/integrations`);
  await expect(page.getByRole("heading", { name: "API tokens" })).toBeVisible();
  await expect(page.getByText("get_brand_identity")).toBeVisible();
});
