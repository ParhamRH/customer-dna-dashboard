"use client";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { request } from "@/lib/api";
import { formatNumber, humanize, relativeTime } from "@/lib/utils";
import { Main } from "@/components/shell";
import { ErrorState, LoadingBlock, PageHeader, Panel, Section } from "@/components/page";
import { TBody, THead, Table } from "@/components/ui/misc";
import { Status, Tag } from "@/components/status";
import { CodeBlock } from "@/components/code-block";
import { AiProviders, type AiSettings } from "@/components/admin/ai";

type Inventory = {
  customers: {
    organization_id: string;
    organization_name: string;
    organization_slug: string;
    status: string;
    integrations: Record<string, Record<string, number>>;
    active_tokens: number;
    tokens_used_last_7_days: number;
    last_token_use_at: string | null;
  }[];
  ai: AiSettings;
  webhook_delivery_failures: number;
  mcp: { transports: string[]; stdio_command: string; http_command: string; auth: string; public_base_url: string };
};

export default function AdminIntegrations() {
  const q = useQuery({ queryKey: ["admin", "integrations"], queryFn: () => request<Inventory>("/v1/platform/integrations") });
  if (q.error) return <Main><ErrorState error={q.error} onRetry={() => q.refetch()} /></Main>;
  if (!q.data) return <Main><LoadingBlock rows={6} /></Main>;
  const d = q.data;
  const mcpConfig = JSON.stringify(
    {
      mcpServers: {
        "brand-dna": {
          command: "python",
          args: ["-m", "app.mcp"],
          cwd: "/path/to/brand-dna-platform/backend",
          env: { BDNA_MCP_TOKEN: "bdna_… (workspace API token)" },
        },
      },
    },
    null,
    2,
  );
  return (
    <Main wide>
      <PageHeader
        title="Integrations"
        description="How external AI applications, automations and agents reach customer libraries. Every connection is bound to exactly one customer."
      />
      <div className="grid gap-x-10 xl:grid-cols-2">
        <Section title="AI providers" description="Installation defaults. A customer can override a capability in its own integration settings.">
          <AiProviders ai={d.ai} />
        </Section>
        <Section title="MCP server" description="Read-only tools and resources for AI clients such as Claude Desktop or IDE agents.">
          <div className="grid gap-3 text-base">
            <p className="text-ink-2">{d.mcp.auth}</p>
            <CodeBlock code={mcpConfig} label="Claude Desktop configuration (stdio)" filename="claude_desktop_config.json" mime="application/json" maxHeight="16rem" />
            <CodeBlock code={d.mcp.http_command} label="Remote (Streamable HTTP) server" />
          </div>
        </Section>
      </div>
      <Section
        title="Connections per customer"
        description={
          d.webhook_delivery_failures
            ? `${d.webhook_delivery_failures} webhook deliveries failed — see AI processing for details.`
            : "Webhooks (for n8n and other automations), customer AI provider overrides and API/MCP tokens."
        }
      >
        <Panel>
          <Table>
            <THead>
              <tr>
                <th>Customer</th>
                <th>Status</th>
                <th>Integrations</th>
                <th className="text-right">Active tokens</th>
                <th className="text-right">Used this week</th>
                <th>Last API / MCP use</th>
              </tr>
            </THead>
            <TBody>
              {d.customers.map((c) => (
                <tr key={c.organization_id}>
                  <td>
                    <Link href={`/admin/customers/${c.organization_id}`} className="font-medium hover:underline">
                      {c.organization_name}
                    </Link>
                  </td>
                  <td>
                    <Status status={c.status} />
                  </td>
                  <td>
                    <div className="flex flex-wrap gap-1.5">
                      {Object.entries(c.integrations).length === 0 ? <span className="text-sm text-muted">None</span> : null}
                      {Object.entries(c.integrations).map(([kind, byStatus]) => (
                        <Tag key={kind} tone="outline">
                          {humanize(kind)} {formatNumber(Object.values(byStatus).reduce((a, b) => a + b, 0))}
                          {byStatus.disabled ? <span className="text-muted"> ({byStatus.disabled} off)</span> : null}
                        </Tag>
                      ))}
                    </div>
                  </td>
                  <td className="tabular text-right">{c.active_tokens}</td>
                  <td className="tabular text-right">{c.tokens_used_last_7_days}</td>
                  <td className="text-sm text-muted">{c.last_token_use_at ? relativeTime(c.last_token_use_at) : "never"}</td>
                </tr>
              ))}
            </TBody>
          </Table>
        </Panel>
      </Section>
    </Main>
  );
}
