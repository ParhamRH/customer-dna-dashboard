"use client";
import * as React from "react";
import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Download, Stamp } from "lucide-react";
import { toast } from "sonner";
import { useWorkspace } from "@/lib/workspace";
import { useBrandDetail, useConcepts, useMemberNames, usePalettes, useReviewSummary, useVersions, reviewTotal } from "@/lib/hooks";
import { errorMessage } from "@/lib/api";
import type { BrandVersion, WorkspaceOverview } from "@/lib/types";
import { DOMAIN_PATHS, RELEVANCE } from "@/lib/labels";
import { downloadText, formatBytes, formatDate, formatDateTime, formatNumber, humanize, pluralize } from "@/lib/utils";
import { Main } from "@/components/shell";
import { ErrorState, Figure, LoadingBlock, Panel, Section } from "@/components/page";
import { Button } from "@/components/ui/button";
import { Input, Textarea } from "@/components/ui/input";
import { Field } from "@/components/ui/label";
import { Dialog, DialogBody, DialogContent, DialogFooter, DialogHeader } from "@/components/ui/dialog";
import { TBody, THead, Table } from "@/components/ui/misc";
import { DnaStrip, stripFromPalettes } from "@/components/dna-strip";
import { StatusMark } from "@/components/status";
import { ActivityFeed } from "@/components/activity";
import { CopyValue } from "@/components/code-block";

function sum(o?: Record<string, number>) {
  return Object.values(o ?? {}).reduce((a, b) => a + b, 0);
}

function PublishDialog({ open, onOpenChange, next }: { open: boolean; onOpenChange: (o: boolean) => void; next: number }) {
  const ws = useWorkspace();
  const qc = useQueryClient();
  const [label, setLabel] = React.useState("");
  const [notes, setNotes] = React.useState("");
  const publish = useMutation({
    mutationFn: () => ws.req<BrandVersion>(`/v1/brands/${ws.brand.id}/versions`, { method: "POST", body: { label: label || undefined, notes: notes || undefined } }),
    onSuccess: (v) => {
      qc.invalidateQueries({ queryKey: ["ws", ws.orgSlug] });
      toast.success(`Published ${v.label}`);
      onOpenChange(false);
      setLabel("");
      setNotes("");
    },
    onError: () => {},
  });
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent size="sm">
        <DialogHeader title="Publish a brand version" description="Freezes every currently approved principle, guideline, concept, entry, palette, typeface and token into an immutable, checksummed snapshot. Context packages can be pinned to it." />
        <DialogBody className="grid gap-3">
          <Field label="Label" htmlFor="v-label">
            <Input id="v-label" placeholder={`v${next}`} value={label} onChange={(e) => setLabel(e.target.value)} />
          </Field>
          <Field label="Release notes" htmlFor="v-notes">
            <Textarea id="v-notes" rows={3} value={notes} onChange={(e) => setNotes(e.target.value)} />
          </Field>
          {publish.error ? <p className="text-sm text-danger">{errorMessage(publish.error)}</p> : null}
        </DialogBody>
        <DialogFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button variant="primary" disabled={publish.isPending} onClick={() => publish.mutate()}>
            <Stamp /> Publish version
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export default function BrandOverviewPage() {
  const ws = useWorkspace();
  const brand = useBrandDetail();
  const palettes = usePalettes();
  const concepts = useConcepts();
  const versions = useVersions();
  const review = useReviewSummary();
  const name = useMemberNames();
  const overview = useQuery({
    queryKey: ws.key("overview"),
    queryFn: () => ws.req<WorkspaceOverview>("/v1/workspace/overview"),
    enabled: ws.can("org.read"),
  });
  const [publishOpen, setPublishOpen] = React.useState(false);
  if (brand.error) return <Main><ErrorState error={brand.error} onRetry={() => brand.refetch()} /></Main>;
  if (!brand.data) return <Main><LoadingBlock rows={8} /></Main>;
  const b = brand.data;
  const o = b.overview;
  const pending = reviewTotal(review.data);
  const core = (concepts.data?.items ?? []).filter((c) => c.status === "approved").sort((a, z) => RELEVANCE.findIndex((r) => r.key === a.brand_relevance) - RELEVANCE.findIndex((r) => r.key === z.brand_relevance));

  async function downloadSnapshot(v: BrandVersion) {
    try {
      const full = await ws.req<BrandVersion>(`/v1/brand-versions/${v.id}`);
      downloadText(`${ws.brand.slug}-${v.label.replace(/\s+/g, "-")}.json`, JSON.stringify(full.snapshot, null, 2), "application/json");
    } catch (e) {
      toast.error(errorMessage(e));
    }
  }

  return (
    <Main wide>
      <header className="mb-8">
        <p className="text-sm text-muted">{ws.org.name}</p>
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div className="max-w-3xl">
            <h1 className="text-4xl font-semibold tracking-[-0.02em]">{b.name}</h1>
            {b.tagline ? <p className="official-text mt-2 text-xl text-ink-2">{b.tagline}</p> : null}
          </div>
          <div className="flex items-center gap-2">
            {o.current_version ? (
              <span className="text-sm text-muted">
                Published <span className="font-medium text-ink">{o.current_version.label}</span> · {formatDate(o.current_version.published_at)}
              </span>
            ) : (
              <span className="text-sm text-muted">No published version yet</span>
            )}
            {ws.can("brand.publish") ? (
              <Button onClick={() => setPublishOpen(true)}>
                <Stamp /> Publish version
              </Button>
            ) : null}
          </div>
        </div>
        <DnaStrip colors={stripFromPalettes(palettes.data?.items)} height={20} interactive className="mt-6 rounded-[3px]" label={b.name} />
        {b.description ? <p className="mt-4 max-w-3xl text-md text-ink-2">{b.description}</p> : null}
      </header>

      <Panel className="mb-10 grid grid-cols-2 gap-6 p-5 md:grid-cols-3 xl:grid-cols-6">
        <Figure label="Approved principles" value={formatNumber(o.principles.approved ?? 0)} hint={`${sum(o.principles) - (o.principles.approved ?? 0)} in progress`} />
        <Figure label="Aesthetic concepts" value={formatNumber(o.aesthetic_concepts.approved ?? 0)} hint="approved" />
        <Figure label="Approved assets" value={formatNumber(o.assets.approved ?? 0)} hint={`of ${formatNumber(sum(o.assets))} in the library`} />
        <Figure label="Colors" value={formatNumber(o.color_tokens)} hint={`${o.typography_systems.approved ?? 0} typefaces approved`} />
        <Figure
          label="Awaiting review"
          value={<Link href={`${ws.base}/review`} className={pending ? "text-ai hover:underline" : ""}>{formatNumber(pending)}</Link>}
          hint="AI interpretations and suggestions"
        />
        <Figure label="Projects" value={formatNumber(o.projects)} hint={overview.data ? formatBytes(overview.data.storage_bytes) + " stored" : undefined} />
      </Panel>

      <div className="grid gap-x-12 xl:grid-cols-[3fr_2fr]">
        <Section title="Knowledge domains" description="Approved knowledge per domain: entries, plus palettes and typefaces, concepts, principles and projects.">
          <Panel>
            <Table>
              <THead>
                <tr>
                  <th>Domain</th>
                  <th className="text-right">Approved</th>
                  <th className="text-right">In progress</th>
                  <th className="w-[40%]">Coverage</th>
                </tr>
              </THead>
              <TBody>
                {o.domains
                  .filter((d) => DOMAIN_PATHS[d.key] !== undefined)
                  .map((d) => {
                    // structured records outside knowledge entries also document a domain
                    const extra: Record<string, number>[] =
                      d.key === "visual_identity"
                        ? [{ approved: (palettes.data?.items ?? []).filter((p) => p.status === "approved").length, draft: (palettes.data?.items ?? []).filter((p) => p.status !== "approved").length }, o.typography_systems]
                        : d.key === "aesthetic_language"
                          ? [o.aesthetic_concepts]
                          : d.key === "principles_guidelines"
                            ? [o.principles, o.guidelines]
                            : d.key === "projects_applications"
                              ? [{ approved: o.projects }]
                              : [];
                    const approved = (d.entries.approved ?? 0) + extra.reduce((s, x) => s + (x.approved ?? 0), 0);
                    const total = sum(d.entries) + extra.reduce((s, x) => s + sum(x) - (x.archived ?? 0) - (x.rejected ?? 0), 0);
                    return (
                      <tr key={d.key}>
                        <td>
                          <Link href={`${ws.base}${DOMAIN_PATHS[d.key]}`} className="hover:underline">
                            {d.name}
                          </Link>
                        </td>
                        <td className="tabular text-right">{approved}</td>
                        <td className="tabular text-right text-muted">{total - approved}</td>
                        <td>
                          <div className="flex gap-0.5" aria-label={`${approved} approved, ${total - approved} in progress`}>
                            {Array.from({ length: approved }).map((_, i) => (
                              <span key={`a${i}`} className="h-2.5 w-2 rounded-[1px] bg-accent" />
                            ))}
                            {Array.from({ length: total - approved }).map((_, i) => (
                              <span key={`p${i}`} className="h-2.5 w-2 rounded-[1px] border border-dashed border-ink-2/50" />
                            ))}
                            {total === 0 ? <span className="text-sm text-faint">nothing yet</span> : null}
                          </div>
                        </td>
                      </tr>
                    );
                  })}
              </TBody>
            </Table>
          </Panel>
        </Section>
        <Section
          title="Aesthetic signature"
          description="Approved concepts, from core to avoid."
          actions={
            <Link href={`${ws.base}/aesthetics`} className="text-sm text-accent hover:underline">
              Explore
            </Link>
          }
        >
          {core.length ? (
            <ul className="grid gap-2">
              {core.map((c) => (
                <li key={c.id} className="grid grid-cols-[6.5rem_1fr] items-baseline gap-3">
                  <span className={`text-sm ${c.brand_relevance === "avoid" ? "text-danger" : "text-muted"}`}>{humanize(c.brand_relevance)}</span>
                  <Link href={`${ws.base}/aesthetics?concept=${c.id}`} className={`hover:underline ${c.brand_relevance === "avoid" ? "line-through decoration-danger/60" : ""}`}>
                    {c.name}
                  </Link>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-muted">No approved concepts yet.</p>
          )}
        </Section>
      </div>

      <div className="grid gap-x-12 xl:grid-cols-[3fr_2fr]">
        <Section title="Brand versions" description="Immutable snapshots of the approved knowledge. Exports and context packages record the version they used.">
          {versions.data?.items.length ? (
            <Panel>
              <Table>
                <THead>
                  <tr>
                    <th>Version</th>
                    <th>Published</th>
                    <th>Contents</th>
                    <th>Checksum</th>
                    <th className="w-0" />
                  </tr>
                </THead>
                <TBody>
                  {versions.data.items.map((v) => (
                    <tr key={v.id} className="align-top">
                      <td>
                        <span className="inline-flex items-center gap-1.5">
                          <StatusMark status={v.status} /> {v.label}
                        </span>
                        {v.notes ? <div className="text-sm text-muted">{v.notes}</div> : null}
                      </td>
                      <td className="text-sm">
                        {formatDateTime(v.published_at)}
                        <div className="text-muted">{name(v.published_by)}</div>
                      </td>
                      <td className="text-sm text-muted">
                        {pluralize(v.counts.principles ?? 0, "principle")}, {pluralize(v.counts.aesthetic_concepts ?? 0, "concept")}, {pluralize(v.counts.knowledge_entries ?? 0, "entry", "entries")}
                      </td>
                      <td>
                        <CopyValue value={v.snapshot_checksum} display={v.snapshot_checksum.slice(0, 12) + "…"} />
                      </td>
                      <td>
                        <Button size="sm" variant="ghost" onClick={() => downloadSnapshot(v)}>
                          <Download /> JSON
                        </Button>
                      </td>
                    </tr>
                  ))}
                </TBody>
              </Table>
            </Panel>
          ) : (
            <p className="text-muted">No version has been published. Publish once the core knowledge is approved.</p>
          )}
        </Section>
        <Section title="Recent activity">
          {overview.data ? <ActivityFeed items={overview.data.recent_activity.slice(0, 10).map((a, i) => ({ ...a, id: i }))} showCustomer={false} /> : ws.can("org.read") ? <LoadingBlock rows={4} /> : null}
        </Section>
      </div>
      <PublishDialog open={publishOpen} onOpenChange={setPublishOpen} next={(versions.data?.items[0]?.version_number ?? 0) + 1} />
    </Main>
  );
}
