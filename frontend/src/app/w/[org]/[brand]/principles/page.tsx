"use client";
import * as React from "react";
import { Plus } from "lucide-react";
import { useWorkspace } from "@/lib/workspace";
import { useGuidelines, usePrinciples, useRegistry } from "@/lib/hooks";
import { CLASSIFICATIONS } from "@/lib/labels";
import { Main } from "@/components/shell";
import { EmptyState, ErrorState, LoadingBlock, PageHeader, Section } from "@/components/page";
import { Button } from "@/components/ui/button";
import { Input, NativeSelect } from "@/components/ui/input";
import { Segmented } from "@/components/ui/tabs";
import { KnowledgeSheet } from "@/components/knowledge/item-sheet";
import { GuidelineRow, PrincipleRow, useSheetFromUrl } from "@/components/knowledge/domain-page";

type Scope = "current" | "approved" | "pending" | "all";

export default function PrinciplesPage() {
  const ws = useWorkspace();
  const principles = usePrinciples();
  const guidelines = useGuidelines();
  const registry = useRegistry();
  const [target, setTarget] = useSheetFromUrl();
  const [scope, setScope] = React.useState<Scope>("current");
  const [domain, setDomain] = React.useState("");
  const [q, setQ] = React.useState("");
  const canWrite = ws.can("knowledge.write");
  const match = (s: string, title: string, text: string | null, d: string | null) => {
    if (domain && d !== domain) return false;
    if (q && !`${title} ${text ?? ""}`.toLowerCase().includes(q.toLowerCase())) return false;
    if (scope === "approved") return s === "approved";
    if (scope === "pending") return s === "draft" || s === "in_review";
    if (scope === "current") return !["archived", "rejected"].includes(s);
    return true;
  };
  if (principles.error) return <Main><ErrorState error={principles.error} /></Main>;
  const ps = (principles.data?.items ?? []).filter((p) => match(p.status, p.title, p.statement, p.domain_key));
  const gs = (guidelines.data?.items ?? []).filter((g) => match(g.status, g.title, g.summary, g.domain_key));
  const domainName = (k: string | null) => registry.data?.domains.find((d) => d.key === k)?.name ?? "Brand-wide";
  return (
    <Main>
      <PageHeader
        title="Principles & guidelines"
        description="The rules the brand lives by. Only approved principles reach context packages, exports and AI clients — every one of them approved by a person."
        actions={
          canWrite ? (
            <>
              <Button onClick={() => setTarget({ collection: "guidelines", create: true })}>
                <Plus /> Guideline
              </Button>
              <Button variant="primary" onClick={() => setTarget({ collection: "principles", create: true })}>
                <Plus /> Principle
              </Button>
            </>
          ) : undefined
        }
      />
      <div className="mb-6 flex flex-wrap items-center gap-3">
        <Segmented<Scope>
          label="Show"
          value={scope}
          onChange={setScope}
          options={[
            { value: "current", label: "Current" },
            { value: "approved", label: "Official only" },
            { value: "pending", label: "Drafts & in review" },
            { value: "all", label: "Everything" },
          ]}
        />
        <NativeSelect aria-label="Domain" className="w-56" value={domain} onChange={(e) => setDomain(e.target.value)}>
          <option value="">All domains</option>
          {registry.data?.domains.map((d) => (
            <option key={d.key} value={d.key}>
              {d.name}
            </option>
          ))}
        </NativeSelect>
        <Input className="w-56" placeholder="Search text" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Search principles" />
      </div>
      {!principles.data ? (
        <LoadingBlock rows={6} />
      ) : ps.length === 0 ? (
        <EmptyState title="No principles match">Principles are short, classified rules — mandatory, preferred, prohibited and so on.</EmptyState>
      ) : (
        CLASSIFICATIONS.map((c) => {
          const inClass = ps.filter((p) => p.classification === c.key);
          if (!inClass.length) return null;
          return (
            <Section key={c.key} title={`${c.label} (${inClass.length})`} description={c.hint}>
              <ul>
                {inClass.map((p) => (
                  <PrincipleRow key={p.id} p={p} domainLabel={domainName(p.domain_key)} onOpen={() => setTarget({ collection: "principles", id: p.id })} />
                ))}
              </ul>
            </Section>
          );
        })
      )}
      <Section title={`Guidelines (${gs.length})`} description="Longer how-to documents that support the principles.">
        {gs.length ? (
          <ul>
            {gs.map((g) => (
              <GuidelineRow key={g.id} g={g} onOpen={() => setTarget({ collection: "guidelines", id: g.id })} />
            ))}
          </ul>
        ) : (
          <p className="text-muted">No guidelines match.</p>
        )}
      </Section>
      <KnowledgeSheet target={target} onClose={() => setTarget(null)} />
    </Main>
  );
}
