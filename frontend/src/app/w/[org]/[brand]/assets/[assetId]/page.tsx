"use client";
import * as React from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Check, Download, ExternalLink, FolderPlus, Pencil, Play, Plus, RotateCw, Trash2, Undo2, X } from "lucide-react";
import { toast } from "sonner";
import { useWorkspace } from "@/lib/workspace";
import { useCollections, useMemberNames } from "@/lib/hooks";
import { errorMessage } from "@/lib/api";
import type { AssetDetail, Json, SearchItem } from "@/lib/types";
import { ASSET_TYPE_LABELS, REFERENCE_ROLE_LABELS } from "@/lib/labels";
import { cn, formatBytes, formatDateTime, formatDuration, humanize } from "@/lib/utils";
import { Main } from "@/components/shell";
import { ErrorState, LoadingBlock, MetaList, Section } from "@/components/page";
import { Button } from "@/components/ui/button";
import { Input, NativeSelect, Textarea } from "@/components/ui/input";
import { Field } from "@/components/ui/label";
import { Segmented } from "@/components/ui/tabs";
import { Dialog, DialogBody, DialogContent, DialogFooter, DialogHeader } from "@/components/ui/dialog";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { AssetThumb } from "@/components/asset-thumb";
import { AiTag, Status, Tag } from "@/components/status";
import { CodeBlock, CopyValue } from "@/components/code-block";
import { useConfirm } from "@/components/confirm";
import { AnalysisBlock, PaletteBar } from "@/components/assets/analysis";
import { RelationshipsTab } from "@/components/knowledge/item-tabs";

function Preview({ a }: { a: AssetDetail }) {
  const ws = useWorkspace();
  const [videoUrl, setVideoUrl] = React.useState<string | null>(null);
  const pages = a.derivatives.filter((d) => d.kind === "page_render");
  const preview = a.derivatives.find((d) => d.kind === "preview") ?? a.derivatives.find((d) => d.kind === "poster");
  if (a.asset_type === "external_reference") {
    const ref = a.references[0];
    return (
      <div className="grid gap-2 rounded-lg border border-dashed border-line-strong p-6">
        <p className="text-sm text-muted">External reference — not stored in the library</p>
        {a.source_url ? (
          <a href={a.source_url} target="_blank" rel="noreferrer noopener" className="inline-flex items-center gap-1.5 break-all text-accent hover:underline">
            {a.source_url} <ExternalLink className="size-3.5 shrink-0" />
          </a>
        ) : null}
        {ref ? <p className="text-sm">{[ref.source_name, ref.creator, ref.license].filter(Boolean).join(" · ")}</p> : null}
      </div>
    );
  }
  if (a.asset_type === "video" || a.asset_type === "animation") {
    return (
      <div className="grid gap-2">
        <div className="relative overflow-hidden rounded-lg bg-ink">
          {videoUrl ? (
            <video src={videoUrl} controls autoPlay poster={preview?.url} className="aspect-video w-full" />
          ) : (
            <>
              {preview ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img src={preview.url} alt={a.title} className="aspect-video w-full object-contain" />
              ) : (
                <div className="aspect-video" />
              )}
              {ws.can("assets.download_original") && a.original_download_available ? (
                <button
                  onClick={async () => {
                    try {
                      const d = await ws.req<{ url: string }>(`/v1/assets/${a.id}/download`);
                      setVideoUrl(d.url);
                    } catch (e) {
                      toast.error(errorMessage(e));
                    }
                  }}
                  className="absolute inset-0 m-auto flex size-16 items-center justify-center rounded-full bg-surface/90 text-ink shadow-pop hover:bg-surface"
                  aria-label="Play original video"
                >
                  <Play className="size-7" />
                </button>
              ) : null}
            </>
          )}
        </div>
        {a.duration_seconds ? <p className="text-sm text-muted">{formatDuration(a.duration_seconds)} · playing streams the original file</p> : null}
      </div>
    );
  }
  if (pages.length) {
    return (
      <div className="grid gap-3">
        <div className="flex gap-3 overflow-x-auto pb-2">
          {pages.map((p) => (
            <a key={p.id} href={p.url} target="_blank" rel="noreferrer" className="shrink-0">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src={p.url} alt={`Page ${p.page_number}`} className="h-96 rounded border border-line bg-white shadow-sm" />
              <span className="mt-1 block text-center text-xs text-muted">Page {p.page_number}</span>
            </a>
          ))}
        </div>
      </div>
    );
  }
  return (
    <div className={cn("overflow-hidden rounded-lg border border-line", a.asset_type === "logo" ? "bg-[repeating-conic-gradient(var(--sunken)_0_25%,var(--surface)_0_50%)] bg-[length:20px_20px] p-8" : "bg-sunken")}>
      <AssetThumb asset={a} size="preview" fit="contain" className="max-h-[70vh] min-h-64 w-full bg-transparent" />
    </div>
  );
}

function Scenes({ a }: { a: AssetDetail }) {
  const deriv = new Map(a.derivatives.map((d) => [d.id, d]));
  const scenes = a.segments.filter((s) => s.segment_type === "scene");
  const pages = a.segments.filter((s) => s.segment_type !== "scene");
  if (!scenes.length && !pages.length) return null;
  return (
    <Section title={scenes.length ? `Scenes (${scenes.length})` : `Pages and sections (${pages.length})`} description={scenes.length ? "Detected with PySceneDetect; camera movement estimated from optical flow." : "Extracted text per page, kept with its page number."}>
      <ol className="grid gap-3">
        {scenes.map((s) => {
          const kf = s.keyframe_derivative_id ? deriv.get(s.keyframe_derivative_id) : undefined;
          const motion = (s.meta?.motion ?? {}) as Json;
          return (
            <li key={s.id} className="grid grid-cols-[10rem_1fr] gap-4">
              {kf ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img src={kf.url} alt={`Keyframe of scene ${s.index + 1}`} className="aspect-video w-40 rounded object-cover" />
              ) : (
                <div className="aspect-video w-40 rounded bg-sunken" />
              )}
              <div className="text-sm">
                <p className="font-medium">
                  Scene {s.index + 1} <span className="tabular font-normal text-muted">{formatDuration((s.start_ms ?? 0) / 1000)} – {formatDuration((s.end_ms ?? 0) / 1000)}</span>
                </p>
                {motion.camera_movement ? <p className="text-ink-2">Camera: {String(motion.camera_movement)}{motion.speed ? `, ${String(motion.speed)}` : ""}</p> : null}
                {s.text_excerpt ? <p className="mt-1 text-muted">{s.text_excerpt}</p> : null}
              </div>
            </li>
          );
        })}
        {pages.map((s) => (
          <li key={s.id} className="text-sm">
            <p className="font-medium">{s.title ?? `Page ${s.page_number}`}</p>
            <p className="line-clamp-3 text-muted">{s.text_excerpt}</p>
          </li>
        ))}
      </ol>
    </Section>
  );
}

function TechnicalMeta({ m, a }: { m: Json; a: AssetDetail }) {
  const motion = (m.motion ?? {}) as Json;
  const palette = m.palette as { hex: string; name?: string; proportion?: number }[] | undefined;
  const items: [React.ReactNode, React.ReactNode][] = [
    ["Dimensions", m.width ? `${m.width} × ${m.height} px` : null],
    ["Orientation", m.orientation as string],
    ["Color", [m.color_profile, m.color_space, m.mode].filter(Boolean).join(" · ")],
    ["Duration", m.duration_seconds ? formatDuration(m.duration_seconds as number) : null],
    ["Frame rate", m.frame_rate ? `${m.frame_rate} fps` : null],
    ["Codec", m.video_codec as string],
    ["Scenes", m.scene_count as number],
    ["Pace", motion.pace as string],
    ["Camera", motion.overall_camera_movement as string],
    ["Average shot", motion.average_shot_length_s ? `${motion.average_shot_length_s} s` : null],
    ["Audio", m.audio ? "yes" : m.has_video ? "none" : null],
    ["Pages", m.page_count as number],
    ["Words", m.word_count as number],
    ["Document title", m.title as string],
    ["Author", m.author as string],
    ["Format", (m.format ?? m.file_format) as string],
    ["Vertices", m.vertex_count as number],
    ["Faces", m.face_count as number],
    ["Bounding box", Array.isArray(m.extents) ? (m.extents as number[]).map((x) => Number(x).toFixed(2)).join(" × ") : null],
    ["Materials", Array.isArray(m.materials) ? (m.materials as string[]).length || "none" : null],
    ["MIME type", a.mime_type],
    ["File size", formatBytes(a.file_size)],
  ];
  return (
    <div className="grid gap-3">
      {palette?.length ? <PaletteBar colors={palette} /> : null}
      <MetaList items={items} className="text-sm" />
    </div>
  );
}

function EditDialog({ a, open, onOpenChange }: { a: AssetDetail; open: boolean; onOpenChange: (o: boolean) => void }) {
  const ws = useWorkspace();
  const qc = useQueryClient();
  const lic = (a.license ?? {}) as Json;
  const [f, setF] = React.useState({
    title: a.title,
    description: a.description ?? "",
    asset_type: a.asset_type,
    category: a.category ?? "",
    subcategory: a.subcategory ?? "",
    folder_path: a.folder_path,
    reference_role: a.reference_role,
    brand_relevance: a.brand_relevance,
    source_url: a.source_url ?? "",
    license: String(lic.license ?? ""),
    holder: String(lic.holder ?? ""),
    expires: String(lic.expires ?? ""),
    usage: String(lic.usage ?? ""),
    curated: JSON.stringify(a.curated_metadata ?? {}, null, 2),
  });
  const [err, setErr] = React.useState<string | null>(null);
  const save = useMutation({
    mutationFn: () => {
      let curated: Json;
      try {
        curated = JSON.parse(f.curated || "{}");
      } catch {
        throw new Error("Custom metadata must be valid JSON");
      }
      const license = Object.fromEntries(Object.entries({ license: f.license, holder: f.holder, expires: f.expires, usage: f.usage }).filter(([, v]) => v));
      return ws.req(`/v1/assets/${a.id}`, {
        method: "PATCH",
        body: {
          title: f.title,
          description: f.description || null,
          asset_type: f.asset_type,
          category: f.category || null,
          subcategory: f.subcategory || null,
          folder_path: f.folder_path || "/",
          reference_role: f.reference_role,
          brand_relevance: f.brand_relevance,
          source_url: f.source_url || null,
          license,
          curated_metadata: curated,
        },
      });
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ws.key("assets") });
      toast.success("Asset details saved");
      onOpenChange(false);
    },
    onError: (e) => setErr(errorMessage(e)),
  });
  const set = (k: keyof typeof f) => (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) => setF({ ...f, [k]: e.target.value });
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent size="lg">
        <DialogHeader title="Edit asset details" description="The original file is never modified — only its catalogue record." />
        <DialogBody className="grid gap-3 sm:grid-cols-2">
          <Field label="Title" htmlFor="a-title" className="sm:col-span-2">
            <Input id="a-title" value={f.title} onChange={set("title")} />
          </Field>
          <Field label="Description" htmlFor="a-desc" className="sm:col-span-2">
            <Textarea id="a-desc" rows={3} value={f.description} onChange={set("description")} />
          </Field>
          <Field label="Type" htmlFor="a-type">
            <NativeSelect id="a-type" value={f.asset_type} onChange={set("asset_type")}>
              {Object.entries(ASSET_TYPE_LABELS).map(([k, v]) => (
                <option key={k} value={k}>
                  {v}
                </option>
              ))}
            </NativeSelect>
          </Field>
          <Field label="Reference role" htmlFor="a-role">
            <NativeSelect id="a-role" value={f.reference_role} onChange={set("reference_role")}>
              {Object.entries(REFERENCE_ROLE_LABELS).map(([k, v]) => (
                <option key={k} value={k}>
                  {v}
                </option>
              ))}
            </NativeSelect>
          </Field>
          <Field label="Category" htmlFor="a-cat">
            <Input id="a-cat" value={f.category} onChange={set("category")} />
          </Field>
          <Field label="Subcategory" htmlFor="a-sub">
            <Input id="a-sub" value={f.subcategory} onChange={set("subcategory")} />
          </Field>
          <Field label="Folder" htmlFor="a-folder">
            <Input id="a-folder" className="font-mono text-sm" value={f.folder_path} onChange={set("folder_path")} />
          </Field>
          <Field label="Brand relevance" htmlFor="a-rel">
            <NativeSelect id="a-rel" value={f.brand_relevance} onChange={set("brand_relevance")}>
              {["core", "supporting", "peripheral", "off_brand", "unassessed"].map((k) => (
                <option key={k} value={k}>
                  {humanize(k)}
                </option>
              ))}
            </NativeSelect>
          </Field>
          <Field label="Source URL" htmlFor="a-src" className="sm:col-span-2">
            <Input id="a-src" value={f.source_url} onChange={set("source_url")} />
          </Field>
          <fieldset className="grid gap-3 rounded-md border border-line p-3 sm:col-span-2 sm:grid-cols-2">
            <legend className="px-1 text-sm font-medium text-muted">License and rights</legend>
            <Field label="License" htmlFor="a-lic">
              <Input id="a-lic" placeholder="Owned, licensed, CC BY 4.0…" value={f.license} onChange={set("license")} />
            </Field>
            <Field label="Rights holder" htmlFor="a-holder">
              <Input id="a-holder" value={f.holder} onChange={set("holder")} />
            </Field>
            <Field label="Expires" htmlFor="a-exp">
              <Input id="a-exp" type="date" value={f.expires} onChange={set("expires")} />
            </Field>
            <Field label="Permitted use" htmlFor="a-use">
              <Input id="a-use" placeholder="e.g. web and social only" value={f.usage} onChange={set("usage")} />
            </Field>
          </fieldset>
          <Field label="Custom metadata (JSON)" htmlFor="a-cur" className="sm:col-span-2">
            <Textarea id="a-cur" rows={4} className="font-mono text-[12.5px]" value={f.curated} onChange={set("curated")} />
          </Field>
          {err ? <p className="text-sm text-danger sm:col-span-2">{err}</p> : null}
        </DialogBody>
        <DialogFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button variant="primary" disabled={!f.title || save.isPending} onClick={() => save.mutate()}>
            Save details
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function Tags({ a }: { a: AssetDetail }) {
  const ws = useWorkspace();
  const qc = useQueryClient();
  const [t, setT] = React.useState("");
  const can = ws.can("assets.write");
  const invalidate = () => qc.invalidateQueries({ queryKey: ws.key("assets") });
  const add = useMutation({
    mutationFn: () => ws.req(`/v1/assets/${a.id}/tags`, { method: "POST", body: { tags: t.split(",").map((x) => x.trim()).filter(Boolean) } }),
    onSuccess: () => {
      setT("");
      invalidate();
    },
  });
  const decide = useMutation({ mutationFn: ({ tag, d }: { tag: string; d: "accept" | "reject" }) => ws.req(`/v1/assets/${a.id}/tags/${encodeURIComponent(tag)}/${d}`, { method: "POST" }), onSuccess: invalidate });
  const remove = useMutation({ mutationFn: (tag: string) => ws.req(`/v1/assets/${a.id}/tags/${encodeURIComponent(tag)}`, { method: "DELETE" }), onSuccess: invalidate });
  const approved = a.tag_details.filter((x) => x.status === "approved");
  const suggested = a.tag_details.filter((x) => x.status === "suggested");
  return (
    <div className="grid gap-3">
      <div className="flex flex-wrap gap-1.5">
        {approved.map((x) => (
          <Tag key={x.tag} className="pr-0.5">
            {x.tag}
            {x.source === "ai" ? <span className="text-faint" title="Suggested by AI, accepted by a person">·ai</span> : null}
            {can ? (
              <button aria-label={`Remove tag ${x.tag}`} className="rounded p-0.5 hover:bg-line" onClick={() => remove.mutate(x.tag)}>
                <X className="size-3" />
              </button>
            ) : null}
          </Tag>
        ))}
        {!approved.length ? <span className="text-sm text-muted">No tags yet.</span> : null}
      </div>
      {suggested.length ? (
        <div>
          <p className="mb-1 text-xs text-muted">Suggested by AI — not applied until accepted</p>
          <div className="flex flex-wrap gap-1.5">
            {suggested.map((x) => (
              <Tag key={x.tag} tone="ai" className="pr-0.5">
                {x.tag}
                {can ? (
                  <>
                    <button aria-label={`Accept tag ${x.tag}`} className="rounded p-0.5 hover:bg-ai/15" onClick={() => decide.mutate({ tag: x.tag, d: "accept" })}>
                      <Check className="size-3" />
                    </button>
                    <button aria-label={`Reject tag ${x.tag}`} className="rounded p-0.5 hover:bg-ai/15" onClick={() => decide.mutate({ tag: x.tag, d: "reject" })}>
                      <X className="size-3" />
                    </button>
                  </>
                ) : null}
              </Tag>
            ))}
          </div>
        </div>
      ) : null}
      {can ? (
        <form
          className="flex gap-1.5"
          onSubmit={(e) => {
            e.preventDefault();
            if (t.trim()) add.mutate();
          }}
        >
          <Input className="h-7 text-sm" placeholder="Add tags, comma separated" value={t} onChange={(e) => setT(e.target.value)} aria-label="Add tags" />
          <Button size="sm" type="submit" disabled={!t.trim()}>
            <Plus /> Add
          </Button>
        </form>
      ) : null}
    </div>
  );
}

function Similar({ a }: { a: AssetDetail }) {
  const ws = useWorkspace();
  const visualOk = ["image", "photograph", "illustration", "graphic_design", "logo", "render_3d", "sketch", "video", "animation", "moodboard"].includes(a.asset_type);
  const [mode, setMode] = React.useState<"visual" | "text">(visualOk ? "visual" : "text");
  const q = useQuery({
    queryKey: ws.key("assets", "similar", a.id, mode),
    queryFn: () => ws.req<{ items: SearchItem[] }>(`/v1/assets/${a.id}/similar`, { params: { modality: mode, limit: 10 } }),
    enabled: ws.can("search.use"),
  });
  if (!ws.can("search.use")) return null;
  return (
    <Section
      title="Similar assets"
      description={mode === "visual" ? "Closest first, by visual similarity of the image content." : "Closest first, by meaning of descriptions, tags and accepted interpretations."}
      actions={visualOk ? <Segmented label="Similarity" value={mode} onChange={setMode} options={[{ value: "visual", label: "Looks like" }, { value: "text", label: "Means like" }]} /> : undefined}
    >
      {!q.data ? (
        <LoadingBlock rows={2} />
      ) : q.data.items.length === 0 ? (
        <p className="text-sm text-muted">Nothing similar yet — the index fills as assets are processed.</p>
      ) : (
        <div className="grid grid-cols-3 gap-3 sm:grid-cols-5 xl:grid-cols-10">
          {q.data.items.filter((x) => x.asset).map((x) => (
            <Link key={x.id} href={`${ws.base}/assets/${x.id}`} className="group">
              <AssetThumb asset={x.asset!} className="aspect-square rounded" />
              <span className="mt-1 block truncate text-xs text-muted group-hover:text-ink">{x.title}</span>
            </Link>
          ))}
        </div>
      )}
    </Section>
  );
}

export default function AssetPage() {
  const { assetId } = useParams<{ assetId: string }>();
  const ws = useWorkspace();
  const router = useRouter();
  const qc = useQueryClient();
  const confirm = useConfirm();
  const name = useMemberNames();
  const collections = useCollections();
  const [editOpen, setEditOpen] = React.useState(false);
  const q = useQuery({
    queryKey: ws.key("assets", "detail", assetId),
    queryFn: () => ws.req<AssetDetail>(`/v1/assets/${assetId}`),
    refetchInterval: (query) => (["pending", "processing"].includes(query.state.data?.processing_status ?? "") ? 2500 : false),
  });
  const invalidate = () => qc.invalidateQueries({ queryKey: ws.key("assets") });
  const approval = useMutation({
    mutationFn: (status: string) => ws.req(`/v1/assets/${assetId}/approval`, { method: "POST", body: { status } }),
    onSuccess: (_d, s) => {
      invalidate();
      toast.success(`Asset ${s}`);
    },
  });
  const reprocess = useMutation({
    mutationFn: () => ws.req(`/v1/assets/${assetId}/reprocess`, { method: "POST", body: { media: true, ai: true, embed: true } }),
    onSuccess: () => {
      invalidate();
      toast.success("Reprocessing queued");
    },
  });
  const del = useMutation({
    mutationFn: () => ws.req<{ purge_at: string }>(`/v1/assets/${assetId}`, { method: "DELETE" }),
    onSuccess: () => {
      invalidate();
      toast.success("Asset deleted. It can be restored for 30 days.");
      router.push(`${ws.base}/assets`);
    },
  });
  const restore = useMutation({ mutationFn: () => ws.req(`/v1/assets/${assetId}/restore`, { method: "POST" }), onSuccess: invalidate });
  const decide = useMutation({
    mutationFn: ({ id, decision }: { id: string; decision: "approve" | "reject" }) =>
      ws.req(`/v1/review/analyses/${id}`, { method: "POST", body: { decision, accept_suggested_tags: decision === "approve" } }),
    onSuccess: (_d, v) => {
      invalidate();
      qc.invalidateQueries({ queryKey: ws.key("review") });
      toast.success(v.decision === "approve" ? "Interpretation accepted" : "Interpretation rejected");
    },
  });
  const addToCollection = useMutation({
    mutationFn: (cid: string) => ws.req(`/v1/collections/${cid}/assets`, { method: "POST", body: { asset_ids: [assetId] } }),
    onSuccess: () => {
      invalidate();
      qc.invalidateQueries({ queryKey: ws.key("collections") });
      toast.success("Added to collection");
    },
  });

  if (q.error) return <Main><ErrorState error={q.error} onRetry={() => q.refetch()} /></Main>;
  if (!q.data) return <Main><LoadingBlock rows={10} /></Main>;
  const a = q.data;
  const processing = ["pending", "processing"].includes(a.processing_status);

  return (
    <Main wide>
      <Link href={`${ws.base}/assets`} className="mb-3 inline-flex items-center gap-1 text-sm text-muted hover:text-ink">
        <ArrowLeft className="size-3.5" /> Asset library
      </Link>
      <header className="mb-6 flex flex-wrap items-end justify-between gap-4">
        <div className="min-w-0">
          <h1 className="text-2xl font-semibold">{a.title}</h1>
          <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-muted">
            <span>{ASSET_TYPE_LABELS[a.asset_type]}</span>
            <Status status={a.approval_status} />
            <Status status={a.reference_role === "official" ? "official" : a.reference_role} label={REFERENCE_ROLE_LABELS[a.reference_role]} />
            {processing ? <Status status="running" label="Processing…" /> : null}
            {a.processing_status === "failed" ? <span className="text-danger">Processing failed</span> : null}
            {a.deleted_at ? <span className="text-danger">Deleted {formatDateTime(a.deleted_at)}</span> : null}
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          {a.deleted_at ? (
            ws.can("assets.delete") ? (
              <Button onClick={() => restore.mutate()}>
                <Undo2 /> Restore
              </Button>
            ) : null
          ) : (
            <>
              {ws.can("review.decide") && a.approval_status !== "approved" ? (
                <Button variant="primary" onClick={() => approval.mutate("approved")}>
                  <Check /> Approve
                </Button>
              ) : null}
              {ws.can("review.decide") && a.approval_status !== "rejected" ? (
                <Button onClick={() => approval.mutate(a.approval_status === "approved" ? "archived" : "rejected")}>{a.approval_status === "approved" ? "Archive" : "Reject"}</Button>
              ) : null}
              {ws.can("assets.download_original") && a.original_download_available ? (
                <Button
                  onClick={async () => {
                    try {
                      const d = await ws.req<{ url: string }>(`/v1/assets/${a.id}/download`);
                      window.location.href = d.url;
                    } catch (e) {
                      toast.error(errorMessage(e));
                    }
                  }}
                >
                  <Download /> Original
                </Button>
              ) : null}
              {ws.can("collections.manage") && collections.data?.items.length ? (
                <Popover>
                  <PopoverTrigger asChild>
                    <Button>
                      <FolderPlus /> Collection
                    </Button>
                  </PopoverTrigger>
                  <PopoverContent align="end" className="grid max-h-72 w-60 gap-1 overflow-y-auto p-1.5">
                    {collections.data.items.map((c) => (
                      <Button key={c.id} size="sm" variant="ghost" className="justify-start" disabled={a.collections.some((x) => x.id === c.id)} onClick={() => addToCollection.mutate(c.id)}>
                        {c.name}
                      </Button>
                    ))}
                  </PopoverContent>
                </Popover>
              ) : null}
              {ws.can("assets.write") ? (
                <>
                  <Button onClick={() => setEditOpen(true)}>
                    <Pencil /> Edit
                  </Button>
                  <Button variant="ghost" onClick={() => reprocess.mutate()} title="Regenerate previews, analysis and embeddings">
                    <RotateCw /> Reprocess
                  </Button>
                </>
              ) : null}
              {ws.can("assets.delete") ? (
                <Button
                  variant="ghost"
                  aria-label="Delete asset"
                  onClick={async () => {
                    if (await confirm({ title: `Delete “${a.title}”?`, description: "The asset is hidden immediately and permanently purged after 30 days unless restored.", confirmLabel: "Delete asset", destructive: true }))
                      del.mutate();
                  }}
                >
                  <Trash2 />
                </Button>
              ) : null}
            </>
          )}
        </div>
      </header>

      <div className="grid gap-10 xl:grid-cols-[minmax(0,1fr)_22rem]">
        <div className="min-w-0">
          <Preview a={a} />
          {a.description ? <p className="mt-4 max-w-3xl text-md text-ink-2">{a.description}</p> : null}
          {a.processing_error ? <p className="mt-3 rounded-md bg-danger-soft px-3 py-2 text-sm text-danger">{a.processing_error}</p> : null}

          <Section
            className="mt-10"
            title="AI interpretation"
            description="What a model read into this asset. It is never official brand knowledge; a reviewer accepts or rejects it, and accepting only links it to the asset."
          >
            {a.analyses.length === 0 ? (
              <p className="text-sm text-muted">{processing ? "Analysis is running…" : "No analysis yet. Use Reprocess to run it."}</p>
            ) : (
              <div className="grid gap-4">
                {a.analyses.map((x) => (
                  <AnalysisBlock
                    key={x.id}
                    a={x}
                    className={x.status === "superseded" || x.status === "rejected" ? "opacity-70" : ""}
                    actions={
                      ws.can("review.decide") && x.status === "pending_review" ? (
                        <div className="flex gap-1.5">
                          <Button size="sm" variant="primary" onClick={() => decide.mutate({ id: x.id, decision: "approve" })}>
                            Accept
                          </Button>
                          <Button size="sm" onClick={() => decide.mutate({ id: x.id, decision: "reject" })}>
                            Reject
                          </Button>
                        </div>
                      ) : x.reviewed_at ? (
                        <span className="text-sm text-muted">
                          {x.status === "approved" ? "Accepted" : "Decided"} by {name(x.reviewed_by)}
                        </span>
                      ) : null
                    }
                  />
                ))}
                {a.pending_suggestions ? (
                  <Link href={`${ws.base}/review?tab=suggestions&asset=${a.id}`} className="inline-flex items-center gap-1 text-sm text-ai hover:underline">
                    <AiTag label={`${a.pending_suggestions} suggestion(s) from this asset await review`} />
                  </Link>
                ) : null}
              </div>
            )}
          </Section>
          <Scenes a={a} />
          <Section title="Relationships" description="Concepts and principles this asset exemplifies (or violates), and projects that use it.">
            <RelationshipsTab entityType="asset" entityId={a.id} relationships={a.relationships} canEdit={ws.can("knowledge.write")} />
          </Section>
          <Similar a={a} />
        </div>

        <aside className="grid content-start gap-8">
          <Section title="Tags" className="mb-0">
            <Tags a={a} />
          </Section>
          <Section title="Technical metadata" description="Measured from the file." className="mb-0">
            <TechnicalMeta m={a.media_metadata} a={a} />
            <details className="mt-3">
              <summary className="cursor-pointer text-sm text-accent">All measured values (JSON)</summary>
              <CodeBlock className="mt-2" code={JSON.stringify(a.media_metadata, null, 2)} maxHeight="20rem" />
            </details>
          </Section>
          <Section title="Catalogue" className="mb-0">
            <MetaList
              className="text-sm"
              items={[
                ["Category", [a.category, a.subcategory].filter(Boolean).join(" / ")],
                ["Folder", <span key="f" className="font-mono text-[12px]">{a.folder_path}</span>],
                ["Brand relevance", humanize(a.brand_relevance)],
                ["Collections", a.collections.length ? a.collections.map((c) => <Link key={c.id} href={`${ws.base}/collections/${c.id}`} className="mr-2 text-accent hover:underline">{c.name}</Link>) : "None"],
                ["Approved", a.approved_at ? `${formatDateTime(a.approved_at)} by ${name(a.approved_by)}` : null],
                ...Object.entries(a.curated_metadata ?? {}).map(([k, v]) => [humanize(k), typeof v === "object" ? JSON.stringify(v) : String(v)] as [string, string]),
              ]}
            />
          </Section>
          <Section title="Provenance and rights" className="mb-0">
            <MetaList
              className="text-sm"
              items={[
                ["Source", humanize(a.source_type)],
                ["Source URL", a.source_url ? <a key="u" href={a.source_url} target="_blank" rel="noreferrer noopener" className="break-all text-accent hover:underline">{a.source_url}</a> : null],
                ["License", (a.license?.license as string) ?? "Not recorded"],
                ["Rights holder", a.license?.holder as string],
                ["Expires", a.license?.expires as string],
                ["Permitted use", a.license?.usage as string],
                ...a.references.flatMap((r) => [
                  ["Reference", [r.source_name, r.creator].filter(Boolean).join(" · ") || r.title] as [string, string],
                  ["Accessed", formatDateTime(r.accessed_at)] as [string, string],
                ]),
                ["Original file", a.original_filename],
                ["SHA-256", a.checksum ? <CopyValue key="c" value={a.checksum} display={a.checksum.slice(0, 16) + "…"} /> : null],
                ["Schema", `v${a.schema_version}`],
                ["Added", formatDateTime(a.created_at)],
                ["Asset ID", <CopyValue key="i" value={a.id} display={a.id.slice(0, 8)} />],
              ]}
            />
          </Section>
        </aside>
      </div>
      <EditDialog key={a.updated_at} a={a} open={editOpen} onOpenChange={setEditOpen} />
    </Main>
  );
}
