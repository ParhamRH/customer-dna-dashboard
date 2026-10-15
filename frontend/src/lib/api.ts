/**
 * Thin client for the Brand DNA REST API (same-origin `/v1/*`).
 *
 * * Authentication is the HttpOnly session cookie set by POST /v1/auth/login.
 * * Every state-changing request carries `X-BDNA-CSRF: 1` (the API rejects cookie-authenticated
 *   writes without it, so a cross-site form post cannot act on the user's behalf).
 * * Workspace-scoped calls send `X-Organization-Id`; the API resolves membership and the
 *   database enforces tenant isolation with Row Level Security. The UI never filters tenants.
 */

export type ErrorBody = { error?: { code?: string; message?: string; details?: unknown } };

export class ApiError extends Error {
  status: number;
  code: string;
  details: unknown;
  constructor(status: number, code: string, message: string, details?: unknown) {
    super(message);
    this.status = status;
    this.code = code;
    this.details = details;
  }
  /** Human-readable message, including field-level validation problems. */
  get description(): string {
    if (this.code === "validation_failed" && Array.isArray(this.details)) {
      const parts = (this.details as { loc?: (string | number)[]; msg?: string }[])
        .map((d) => (typeof d === "string" ? d : `${(d.loc ?? []).filter((x) => x !== "body").join(".")}: ${d.msg ?? ""}`))
        .slice(0, 4);
      return parts.length ? `${this.message} — ${parts.join("; ")}` : this.message;
    }
    if (this.details && typeof this.details === "object" && "required" in (this.details as object)) {
      const req = (this.details as { required: string[] }).required;
      return `${this.message}: ${req.join(", ")}`;
    }
    return this.message;
  }
}

export type RequestOptions = {
  method?: "GET" | "POST" | "PATCH" | "PUT" | "DELETE";
  body?: unknown;
  form?: FormData;
  org?: string | null;
  params?: Record<string, string | number | boolean | null | undefined | (string | number)[]>;
  signal?: AbortSignal;
  raw?: boolean;
};

let onUnauthorized: (() => void) | null = null;
export function setUnauthorizedHandler(fn: () => void) {
  onUnauthorized = fn;
}

export function buildUrl(path: string, params?: RequestOptions["params"]): string {
  const qs = new URLSearchParams();
  for (const [k, v] of Object.entries(params ?? {})) {
    if (v === undefined || v === null || v === "") continue;
    if (Array.isArray(v)) v.forEach((x) => qs.append(k, String(x)));
    else qs.set(k, String(v));
  }
  const q = qs.toString();
  return q ? `${path}?${q}` : path;
}

export async function request<T = unknown>(path: string, opts: RequestOptions = {}): Promise<T> {
  const method = opts.method ?? (opts.body !== undefined || opts.form ? "POST" : "GET");
  const headers: Record<string, string> = { Accept: "application/json" };
  if (method !== "GET") headers["X-BDNA-CSRF"] = "1";
  if (opts.org) headers["X-Organization-Id"] = opts.org;
  let body: BodyInit | undefined;
  if (opts.form) body = opts.form;
  else if (opts.body !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(opts.body);
  }
  const res = await fetch(buildUrl(path, opts.params), {
    method,
    headers,
    body,
    credentials: "same-origin",
    signal: opts.signal,
    cache: "no-store",
  });
  if (res.status === 401 && onUnauthorized && !path.startsWith("/v1/auth/login")) onUnauthorized();
  if (!res.ok) {
    let parsed: ErrorBody = {};
    try {
      parsed = await res.json();
    } catch {
      /* non-JSON error */
    }
    throw new ApiError(
      res.status,
      parsed.error?.code ?? `http_${res.status}`,
      parsed.error?.message ?? res.statusText ?? "Request failed",
      parsed.error?.details,
    );
  }
  if (opts.raw) return res as unknown as T;
  if (res.status === 204) return undefined as T;
  const ct = res.headers.get("content-type") ?? "";
  return (ct.includes("application/json") ? res.json() : res.text()) as Promise<T>;
}

/** Multipart upload with progress (fetch has no upload progress events). */
export function upload<T = unknown>(
  path: string,
  form: FormData,
  { org, onProgress, signal }: { org?: string | null; onProgress?: (fraction: number) => void; signal?: AbortSignal } = {},
): Promise<T> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", path);
    xhr.withCredentials = true;
    xhr.setRequestHeader("X-BDNA-CSRF", "1");
    xhr.setRequestHeader("Accept", "application/json");
    if (org) xhr.setRequestHeader("X-Organization-Id", org);
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable && onProgress) onProgress(e.loaded / e.total);
    };
    xhr.onload = () => {
      let data: unknown = null;
      try {
        data = JSON.parse(xhr.responseText);
      } catch {
        /* ignore */
      }
      if (xhr.status >= 200 && xhr.status < 300) resolve(data as T);
      else {
        const e = (data as ErrorBody)?.error;
        if (xhr.status === 401 && onUnauthorized) onUnauthorized();
        reject(new ApiError(xhr.status, e?.code ?? `http_${xhr.status}`, e?.message ?? "Upload failed", e?.details));
      }
    };
    xhr.onerror = () => reject(new ApiError(0, "network_error", "Network error — the upload did not reach the server"));
    xhr.onabort = () => reject(new ApiError(0, "aborted", "Upload cancelled"));
    signal?.addEventListener("abort", () => xhr.abort());
    xhr.send(form);
  });
}

/** Fetch an authenticated text/binary endpoint and save it as a file. */
export async function downloadFrom(path: string, filename: string, org?: string | null, params?: RequestOptions["params"]) {
  const res = await request<Response>(path, { org, params, raw: true });
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 2000);
}

export function errorMessage(e: unknown): string {
  if (e instanceof ApiError) return e.description;
  if (e instanceof Error) return e.message;
  return "Something went wrong";
}
