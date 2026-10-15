import { expect, test } from "@playwright/test";
import { AURORA, api, login, user } from "./helpers";

test("a new principle stays a draft until a creative director approves it", async ({ page }) => {
  const title = `E2E principle ${Date.now()}`;
  await login(page, user("editor"));
  await page.goto(`${AURORA}/principles`);
  await page.getByRole("button", { name: "Principle" }).click();
  await page.fill("#p-title", title);
  await page.fill("#p-stmt", "Every end-to-end test leaves the library as it found it.");
  const created = page.waitForResponse((r) => /\/knowledge\/principles$/.test(new URL(r.url()).pathname) && r.request().method() === "POST");
  await page.getByRole("button", { name: "Create draft" }).click();
  const principle = await (await created).json();
  expect(principle.status).toBe("draft");
  // the editor has no approval controls
  await page.goto(`${AURORA}/principles?item=principles:${principle.id}`);
  await expect(page.getByRole("dialog").getByText(title)).toBeVisible();
  await expect(page.getByRole("button", { name: "Approve as official" })).toHaveCount(0);
  // and the API refuses an approval from the editor
  const refused = await api(page.request, "POST", `/v1/knowledge/principles/${principle.id}/approve`, { org: "aurora-atelier" });
  expect(refused.status()).toBe(403);

  await login(page, user("creative.director"));
  await page.goto(`${AURORA}/principles?item=principles:${principle.id}`);
  await page.getByRole("button", { name: "Approve as official" }).click();
  await page.getByRole("button", { name: "Confirm: approve as official" }).click();
  await expect(page.getByText("Approved — now official brand knowledge")).toBeVisible();
  const after = await (await api(page.request, "GET", `/v1/knowledge/principles/${principle.id}`, { org: "aurora-atelier" })).json();
  expect(after.status).toBe("approved");

  // clean up: archive (history is kept)
  const archived = await api(page.request, "POST", `/v1/knowledge/principles/${principle.id}/archive`, { org: "aurora-atelier" });
  expect(archived.ok()).toBeTruthy();
});
