import { expect, test } from "@playwright/test";
import { AURORA, api, expectNoConsoleErrors, login, user } from "./helpers";

test.beforeEach(async ({ page }) => {
  await login(page, user("creative.director"));
});

test("natural-language search finds the slow cinematic film", async ({ page }) => {
  await expectNoConsoleErrors(page, async () => {
    await page.goto(`${AURORA}/search?q=${encodeURIComponent("Find videos with slow cinematic camera movements")}`);
    const results = page.getByRole("list").filter({ has: page.getByRole("link", { name: "Morning ritual film" }) });
    await expect(results).toBeVisible();
    await expect(page.getByText(/Understood as/)).toBeVisible();
  });
});

test("a video's scenes and camera movements are measured", async ({ page }) => {
  const assets = await (await api(page.request, "GET", "/v1/assets?q=Morning%20ritual%20film", { org: "aurora-atelier" })).json();
  const film = assets.items.find((a: { title: string }) => a.title === "Morning ritual film");
  await page.goto(`${AURORA}/assets/${film.id}`);
  await expect(page.getByRole("heading", { name: "Morning ritual film" })).toBeVisible();
  await expect(page.getByText(/slow pan right/i).first()).toBeVisible();
  await expect(page.getByText(/static/i).first()).toBeVisible();
});

test("the context generator produces a sourced brief for a project", async ({ page }) => {
  const ws = await (await api(page.request, "GET", "/v1/workspace", { org: "aurora-atelier" })).json();
  const projects = await (await api(page.request, "GET", `/v1/brands/${ws.brands[0].id}/projects`, { org: "aurora-atelier" })).json();
  await page.goto(`${AURORA}/context?project=${projects.items[0].id}`);
  await page.getByRole("button", { name: "Next", exact: true }).click();
  await page.getByRole("button", { name: "Preview what is included" }).click();
  await expect(page.getByText("Every source, with its version")).toBeVisible();
  await page.getByRole("button", { name: "Generate package" }).click();
  await expect(page.getByRole("heading", { name: "Mandatory constraints" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Sources" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Copy as Markdown" })).toBeVisible();
});

test("collections: create, add assets, remove the collection", async ({ page }) => {
  const name = `E2E set ${Date.now()}`;
  await page.goto(`${AURORA}/collections`);
  await page.getByRole("button", { name: "New collection" }).click();
  await page.fill("#col-name", name);
  await page.getByRole("button", { name: "Create collection" }).click();
  await page.waitForURL(/\/collections\/[0-9a-f-]{36}$/);
  await page.getByRole("button", { name: "Add assets" }).first().click();
  const picks = page.getByRole("dialog").locator("button[aria-pressed]");
  await picks.nth(0).click();
  await picks.nth(1).click();
  await page.getByRole("button", { name: "Add to collection" }).click();
  await expect(page.getByText("2 assets", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "More actions" }).click();
  await page.getByRole("menuitem", { name: "Delete collection" }).click();
  await page.getByRole("button", { name: "Delete collection" }).click();
  await page.waitForURL(/\/collections$/);
  await expect(page.getByText(name)).toHaveCount(0);
});

test("the knowledge graph renders and finds a concept", async ({ page }) => {
  await expectNoConsoleErrors(page, async () => {
    await page.goto(`${AURORA}/graph`);
    await expect(page.getByRole("img", { name: /Knowledge graph with/ })).toBeVisible();
    await page.getByLabel("Find a node").fill("Organic");
    await page.getByRole("button", { name: "Find", exact: true }).click();
    await expect(page.getByRole("heading", { name: "Organic geometry" })).toBeVisible();
    await page.getByRole("radio", { name: "List" }).click();
    const table = page.getByRole("table");
    await expect(table).toContainText("Relationship");
    await expect(table).toContainText("exemplifies");
  });
});

test("a selective export completes, passes the tenant purity check and downloads", async ({ page }) => {
  await page.goto(`${AURORA}/exports`);
  await expect(page.getByRole("heading", { name: "Exports & imports" })).toBeVisible();
  const ws = await (await api(page.request, "GET", "/v1/workspace", { org: "aurora-atelier" })).json();
  const r = await api(page.request, "POST", "/v1/exports", {
    org: "aurora-atelier",
    data: { mode: "selective", selection: { brand_id: ws.brands[0].id, domains: ["visual_identity"] }, include_originals: false },
  });
  expect(r.status()).toBe(202);
  const exp = await r.json();
  await expect
    .poll(async () => (await (await api(page.request, "GET", `/v1/exports/${exp.id}`, { org: "aurora-atelier" })).json()).status, { timeout: 45_000 })
    .toBe("completed");
  const done = await (await api(page.request, "GET", `/v1/exports/${exp.id}`, { org: "aurora-atelier" })).json();
  expect(done.manifest.tenant_purity_check.passed).toBe(true);
  expect(done.manifest.customer_slug).toBe("aurora-atelier");
  expect(done.download_available).toBe(true);
  const link = await (await api(page.request, "GET", `/v1/exports/${exp.id}/download`, { org: "aurora-atelier" })).json();
  const zip = await page.request.get(link.url);
  expect(zip.ok()).toBeTruthy();
  expect((await zip.body()).subarray(0, 2).toString()).toBe("PK");
});
