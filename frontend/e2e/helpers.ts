import { expect, type APIRequestContext, type Page } from "@playwright/test";

/** Fictional demo accounts created by `python -m app.cli seed-demo`. */
export const DEMO_PASSWORD = process.env.E2E_DEMO_PASSWORD ?? "demo-password-2026";
export const ADMIN_EMAIL = process.env.E2E_ADMIN_EMAIL ?? "admin@platform.local";
export const ADMIN_PASSWORD = process.env.E2E_ADMIN_PASSWORD ?? "admin-password-2026";

export const AURORA = "/w/aurora-atelier/aurora";
export const user = (role: "admin" | "creative.director" | "editor" | "reviewer" | "viewer", org = "aurora-atelier") => `${role}@${org}.example`;

export async function login(page: Page, email: string, password = DEMO_PASSWORD) {
  await page.context().clearCookies();
  await page.goto("/login");
  await page.fill("#email", email);
  await page.fill("#password", password);
  await page.getByRole("button", { name: /sign in/i }).click();
  await page.waitForURL((u) => !u.pathname.startsWith("/login"));
}

/** Same-origin API call with the page's session cookie (and the CSRF header for writes). */
export async function api(request: APIRequestContext, method: "GET" | "POST" | "PATCH" | "DELETE", path: string, opts: { org?: string; data?: unknown } = {}) {
  const headers: Record<string, string> = { "X-BDNA-CSRF": "1" };
  if (opts.org) headers["X-Organization-Id"] = opts.org;
  return request.fetch(path, { method, headers, data: opts.data as never });
}

export async function expectNoConsoleErrors(page: Page, run: () => Promise<void>) {
  const errors: string[] = [];
  const onConsole = (m: { type(): string; text(): string }) => {
    // Google Fonts specimens cannot load in sandboxed CI; everything else is a real error.
    if (m.type() === "error" && !/fonts\.(googleapis|gstatic)|ERR_TUNNEL|ERR_NAME_NOT_RESOLVED/.test(m.text())) errors.push(m.text());
  };
  page.on("console", onConsole);
  page.on("pageerror", (e) => errors.push(e.message));
  await run();
  page.off("console", onConsole);
  expect(errors, errors.join("\n")).toEqual([]);
}
