"use client";
import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, CheckCircle2, XCircle } from "lucide-react";
import { request } from "@/lib/api";
import { formatBytes, formatNumber, humanize } from "@/lib/utils";
import { Main } from "@/components/shell";
import { ErrorState, LoadingBlock, MetaList, PageHeader, Panel, Section } from "@/components/page";
import { AiProviders, type AiSettings } from "@/components/admin/ai";

type SystemSettings = {
  version: string;
  environment: string;
  security: { session_ttl_hours: number; cookie_secure: boolean; cors_origins: string[]; encryption_key_configured: boolean; csrf: string; database_roles: Record<string, string> };
  storage: { backend: string; bucket: string | null; endpoint: string | null; signed_url_ttl_seconds: number; max_upload_bytes: number; public_base_url: string };
  ai: AiSettings & { keys_configured: Record<string, boolean>; max_images_per_asset: number };
  media: { tools: Record<string, boolean>; max_video_keyframes: number; max_document_pages_rendered: number };
  workers: { concurrency: number; poll_seconds: number; job_lock_timeout_seconds: number; queue: Record<string, number> };
  exports: { ttl_days: number };
  warnings: string[];
};

function YesNo({ ok, yes = "Yes", no = "No" }: { ok: boolean; yes?: string; no?: string }) {
  return ok ? (
    <span className="inline-flex items-center gap-1.5">
      <CheckCircle2 className="size-4 text-accent" /> {yes}
    </span>
  ) : (
    <span className="inline-flex items-center gap-1.5 text-muted">
      <XCircle className="size-4 text-faint" /> {no}
    </span>
  );
}

export default function SystemSettingsPage() {
  const q = useQuery({ queryKey: ["admin", "settings"], queryFn: () => request<SystemSettings>("/v1/platform/settings") });
  if (q.error) return <Main><ErrorState error={q.error} onRetry={() => q.refetch()} /></Main>;
  if (!q.data) return <Main><LoadingBlock rows={8} /></Main>;
  const s = q.data;
  return (
    <Main>
      <PageHeader
        title="System settings"
        description="Read-only view of this installation's configuration. Values come from environment variables (see .env.example); secrets are never shown."
        meta={
          <>
            <span>Version {s.version}</span>
            <span>{humanize(s.environment)} environment</span>
          </>
        }
      />
      {s.warnings.length ? (
        <Panel className="mb-8 border-warning/40 p-4">
          <p className="mb-2 flex items-center gap-2 font-medium">
            <AlertTriangle className="size-4 text-warning" /> Review before production use
          </p>
          <ul className="grid gap-1 pl-6 text-base text-ink-2">
            {s.warnings.map((w) => (
              <li key={w} className="list-disc">
                {w}
              </li>
            ))}
          </ul>
        </Panel>
      ) : null}
      <Section title="AI">
        <AiProviders ai={s.ai} />
        <MetaList
          className="mt-4"
          items={[
            ["Anthropic key", <YesNo key="a" ok={s.ai.keys_configured.anthropic} yes="Configured" no="Not configured" />],
            ["OpenAI key", <YesNo key="o" ok={s.ai.keys_configured.openai} yes="Configured" no="Not configured" />],
            ["Visual embedding service", <YesNo key="v" ok={s.ai.keys_configured.visual_embedding_service} yes="Configured" no="Not configured" />],
            ["Images sent per asset", formatNumber(s.ai.max_images_per_asset)],
          ]}
        />
      </Section>
      <div className="grid gap-x-10 md:grid-cols-2">
        <Section title="Security">
          <MetaList
            items={[
              ["Session length", `${s.security.session_ttl_hours} hours`],
              ["Secure cookies", <YesNo key="c" ok={s.security.cookie_secure} />],
              ["Secret encryption key", <YesNo key="e" ok={s.security.encryption_key_configured} yes="Dedicated key" no="Derived from secret key" />],
              ["CSRF protection", s.security.csrf],
              ["Tenant isolation", `Row Level Security ${s.security.database_roles.rls}`],
              ["Runtime database role", s.security.database_roles.app],
              ["Allowed origins", s.security.cors_origins.join(", ")],
            ]}
          />
        </Section>
        <Section title="Storage">
          <MetaList
            items={[
              ["Backend", s.storage.backend === "s3" ? "S3-compatible object storage" : "Local disk"],
              ["Bucket", s.storage.bucket],
              ["Endpoint", s.storage.endpoint],
              ["Signed link lifetime", `${Math.round(s.storage.signed_url_ttl_seconds / 60)} minutes`],
              ["Largest upload", formatBytes(s.storage.max_upload_bytes)],
              ["Public base URL", s.storage.public_base_url],
              ["Export retention", `${s.exports.ttl_days} days`],
            ]}
          />
        </Section>
        <Section title="Media processing">
          <MetaList
            items={[
              ...Object.entries(s.media.tools).map(([k, v]) => [k, <YesNo key={k} ok={v} yes="Available" no={k === "docling" ? "Not installed (optional)" : "Missing"} />] as [string, React.ReactNode]),
              ["Keyframes per video", formatNumber(s.media.max_video_keyframes)],
              ["Pages rendered per document", formatNumber(s.media.max_document_pages_rendered)],
            ]}
          />
        </Section>
        <Section title="Workers">
          <MetaList
            items={[
              ["Threads per worker", formatNumber(s.workers.concurrency)],
              ["Poll interval", `${s.workers.poll_seconds} s`],
              ["Stale lock timeout", `${Math.round(s.workers.job_lock_timeout_seconds / 60)} minutes`],
              ...Object.entries(s.workers.queue).map(([k, v]) => [`Jobs ${humanize(k).toLowerCase()}`, formatNumber(v)] as [string, React.ReactNode]),
            ]}
          />
        </Section>
      </div>
    </Main>
  );
}
