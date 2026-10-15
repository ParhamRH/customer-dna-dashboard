import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatBytes(n: number | null | undefined, digits = 1): string {
  if (n == null) return "—";
  if (n < 1024) return `${n} B`;
  const units = ["KB", "MB", "GB", "TB"];
  let v = n / 1024;
  let i = 0;
  while (v >= 1024 && i < units.length - 1) {
    v /= 1024;
    i++;
  }
  return `${v.toFixed(v >= 100 ? 0 : digits)} ${units[i]}`;
}

export function formatNumber(n: number | null | undefined): string {
  if (n == null) return "—";
  return new Intl.NumberFormat("en").format(n);
}

const dateFmt = new Intl.DateTimeFormat("en", { day: "numeric", month: "short", year: "numeric" });
const dateTimeFmt = new Intl.DateTimeFormat("en", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });

export function formatDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  return dateFmt.format(new Date(iso));
}

export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  return dateTimeFmt.format(new Date(iso));
}

export function relativeTime(iso: string | null | undefined): string {
  if (!iso) return "never";
  const diff = (Date.now() - new Date(iso).getTime()) / 1000;
  if (diff < 45) return "just now";
  const steps: [number, string][] = [
    [60, "minute"],
    [3600, "hour"],
    [86400, "day"],
    [604800, "week"],
    [2629800, "month"],
    [31557600, "year"],
  ];
  let unit = "minute";
  let value = diff / 60;
  for (let i = steps.length - 1; i >= 0; i--) {
    if (Math.abs(diff) >= steps[i][0]) {
      unit = steps[i][1];
      value = diff / steps[i][0];
      break;
    }
  }
  const v = Math.round(value);
  return `${v} ${unit}${v === 1 ? "" : "s"} ago`;
}

export function formatDuration(seconds: number | null | undefined): string {
  if (seconds == null) return "—";
  const m = Math.floor(seconds / 60);
  const s = Math.round(seconds % 60);
  return m ? `${m}:${String(s).padStart(2, "0")}` : `${s}s`;
}

/** snake_case / dotted keys → readable sentence case ("brand_foundation" → "Brand foundation") */
export function humanize(key: string | null | undefined): string {
  if (!key) return "";
  const s = key.replace(/[._]/g, " ").replace(/\s+/g, " ").trim();
  return s.charAt(0).toUpperCase() + s.slice(1);
}

export function pluralize(n: number, one: string, many?: string): string {
  return `${formatNumber(n)} ${n === 1 ? one : many ?? one + "s"}`;
}

export function initials(name: string | null | undefined): string {
  if (!name) return "?";
  const parts = name.trim().split(/[\s@._-]+/).filter(Boolean);
  return (parts[0]?.[0] ?? "?").toUpperCase() + (parts[1]?.[0] ?? "").toUpperCase();
}

export function shortId(id: string | null | undefined): string {
  return id ? id.slice(0, 8) : "";
}

export function downloadText(filename: string, text: string, type = "text/plain") {
  const blob = new Blob([text], { type });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export async function copyText(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    return false;
  }
}

/** Readable text color (ink or white) for a background hex. */
export function onColor(hex: string): string {
  const h = hex.replace("#", "");
  const full = h.length === 3 ? h.split("").map((c) => c + c).join("") : h.slice(0, 6);
  const [r, g, b] = [0, 2, 4].map((i) => parseInt(full.slice(i, i + 2), 16) / 255);
  const lin = (c: number) => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4);
  const L = 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b);
  return L > 0.42 ? "#1e2329" : "#ffffff";
}
