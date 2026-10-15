import { expect, test } from "@playwright/test";
import { ADMIN_EMAIL, ADMIN_PASSWORD, AURORA, api, login, user } from "./helpers";

test.describe("authentication", () => {
  test("signed-out visitors are sent to the sign-in page", async ({ page }) => {
    await page.goto("/admin/customers");
    await expect(page).toHaveURL(/\/login\?next=%2Fadmin%2Fcustomers/);
  });

  test("a wrong password is refused without saying which part was wrong", async ({ page }) => {
    await page.goto("/login");
    await page.fill("#email", user("viewer"));
    await page.fill("#password", "not-the-password");
    await page.getByRole("button", { name: /sign in/i }).click();
    await expect(page.getByText("Invalid email or password")).toBeVisible();
    await expect(page).toHaveURL(/\/login/);
  });

  test("platform administrators land in the console and see every customer", async ({ page }) => {
    await login(page, ADMIN_EMAIL, ADMIN_PASSWORD);
    await expect(page).toHaveURL(/\/admin/);
    await page.goto("/admin/customers");
    for (const name of ["Aurora Atelier", "Northwind Mobility", "Kiln & Thread"]) {
      await expect(page.getByRole("link", { name, exact: true }).first()).toBeVisible();
    }
  });

  test("customer members land in their workspace and cannot open the console", async ({ page }) => {
    await login(page, user("admin"));
    await expect(page).toHaveURL(new RegExp(`${AURORA}`));
    await page.goto("/admin");
    await expect(page).toHaveURL(/\/w\/aurora-atelier/);
    const r = await api(page.request, "GET", "/v1/platform/overview");
    expect(r.status()).toBe(403);
  });
});

test.describe("tenant isolation", () => {
  test("another customer's workspace does not open, by URL or by API", async ({ page }) => {
    await login(page, user("admin"));
    await page.goto("/w/northwind-mobility/northwind");
    await expect(page.getByRole("heading", { name: "Workspace not found" })).toBeVisible();
    await expect(page.getByText("Brand library")).toHaveCount(0);

    for (const path of ["/v1/workspace", "/v1/assets", "/v1/brands"]) {
      const r = await api(page.request, "GET", path, { org: "northwind-mobility" });
      expect(r.status(), path).toBe(404);
    }
  });

  test("everything the API returns belongs to the signed-in workspace", async ({ page }) => {
    await login(page, user("admin"));
    const ws = await (await api(page.request, "GET", "/v1/workspace", { org: "aurora-atelier" })).json();
    const assets = await (await api(page.request, "GET", "/v1/assets?limit=200", { org: "aurora-atelier" })).json();
    expect(assets.items.length).toBeGreaterThan(0);
    for (const a of assets.items) expect(a.organization_id).toBe(ws.organization.id);

    // Search never surfaces another customer's material, even when asked for it by name.
    const r = await api(page.request, "POST", "/v1/search", { org: "aurora-atelier", data: { query: "commuter bike city structure", limit: 30 } });
    const found = await r.json();
    for (const item of found.items) expect(item.asset?.organization_id ?? ws.organization.id).toBe(ws.organization.id);
    expect(found.items.map((i: { title: string }) => i.title)).not.toContain("City structure 1");
  });

  test("forging a write against another workspace fails", async ({ page }) => {
    await login(page, user("admin"));
    const northwind = await login(page, user("admin", "northwind-mobility")).then(async () =>
      (await api(page.request, "GET", "/v1/workspace", { org: "northwind-mobility" })).json(),
    );
    const brandId = northwind.brands[0].id;
    await login(page, user("admin"));
    const r = await api(page.request, "POST", `/v1/brands/${brandId}/collections`, { org: "aurora-atelier", data: { name: "Forged" } });
    expect(r.status()).toBe(404);
  });
});
