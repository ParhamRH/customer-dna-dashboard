"use client";
import * as React from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { useWorkspace } from "@/lib/workspace";
import type { AiDescribe, Integration } from "@/lib/types";
import { Main } from "@/components/shell";
import { EmptyState, ErrorState, LoadingBlock, PageHeader, Section } from "@/components/page";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { TokensPanel } from "@/components/integrations/tokens";
import { McpPanel, type McpInfo } from "@/components/integrations/mcp";
import { WebhooksPanel } from "@/components/integrations/webhooks";
import { AiOverridesPanel } from "@/components/integrations/ai-overrides";
import { PromptsPanel } from "@/components/integrations/prompts";

type IntegrationsResponse = { items: Integration[]; event_types: string[]; ai: AiDescribe; mcp: McpInfo };
const TABS = ["access", "webhooks", "ai", "prompts"] as const;
type Tab = (typeof TABS)[number];

export default function IntegrationsPage() {
  const ws = useWorkspace();
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const tab = (TABS as readonly string[]).includes(params.get("tab") ?? "") ? (params.get("tab") as Tab) : "access";
  const setTab = (t: string) => router.replace(`${pathname}?tab=${t}`, { scroll: false });
  const [newToken, setNewToken] = React.useState(false);
  const allowed = ws.can("integrations.manage");
  const q = useQuery({
    queryKey: ws.key("integrations"),
    queryFn: () => ws.req<IntegrationsResponse>("/v1/integrations"),
    enabled: allowed,
  });
  if (!allowed)
    return (
      <Main>
        <EmptyState title="Integrations are managed by workspace administrators">Ask a customer administrator for an API token or webhook.</EmptyState>
      </Main>
    );
  const webhooks = q.data?.items.filter((i) => i.kind === "webhook") ?? [];
  const overrides = q.data?.items.filter((i) => i.kind === "ai_provider") ?? [];
  return (
    <Main>
      <PageHeader title="Integrations" description="Connect this workspace to automations and AI clients. Everything here is scoped to this workspace — nothing reaches another customer’s data." />
      {q.error ? <ErrorState error={q.error} /> : null}
      <Tabs value={tab} onValueChange={setTab}>
        <TabsList>
          <TabsTrigger value="access">API &amp; MCP</TabsTrigger>
          <TabsTrigger value="webhooks">Webhooks{webhooks.length ? ` · ${webhooks.length}` : ""}</TabsTrigger>
          <TabsTrigger value="ai">AI providers</TabsTrigger>
          <TabsTrigger value="prompts">Prompt templates</TabsTrigger>
        </TabsList>
        <TabsContent value="access">
          {ws.can("api_tokens.manage") ? (
            <Section title="API tokens">
              <TokensPanel mcpUrl={q.data?.mcp.http_url} open={newToken} setOpen={setNewToken} />
            </Section>
          ) : null}
          <Section title="MCP server">
            {q.data ? <McpPanel mcp={q.data.mcp} onCreateToken={ws.can("api_tokens.manage") ? () => setNewToken(true) : undefined} /> : <LoadingBlock rows={4} />}
          </Section>
        </TabsContent>
        <TabsContent value="webhooks">{q.data ? <WebhooksPanel items={webhooks} eventTypes={q.data.event_types} /> : <LoadingBlock rows={3} />}</TabsContent>
        <TabsContent value="ai">{q.data ? <AiOverridesPanel ai={q.data.ai} overrides={overrides} /> : <LoadingBlock rows={4} />}</TabsContent>
        <TabsContent value="prompts">
          <PromptsPanel canEdit={allowed} />
        </TabsContent>
      </Tabs>
    </Main>
  );
}
