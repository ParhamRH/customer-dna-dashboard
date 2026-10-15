/* Vocabulary of the interface. Keep names identical across screens. */

export const ROLE_LABELS: Record<string, string> = {
  platform_super_admin: "Platform administrator",
  customer_admin: "Customer administrator",
  creative_director: "Creative director",
  editor: "Editor",
  reviewer: "Reviewer",
  viewer: "Viewer",
};

export const ROLE_SUMMARY: Record<string, string> = {
  customer_admin: "Everything in this workspace, including members, tokens and exports.",
  creative_director: "Shapes and approves brand knowledge, publishes versions, exports.",
  editor: "Uploads assets and drafts knowledge; cannot approve.",
  reviewer: "Decides on AI interpretations and suggestions.",
  viewer: "Reads the library and searches it. Cannot change anything.",
};

export const ORG_ROLES = ["customer_admin", "creative_director", "editor", "reviewer", "viewer"] as const;

export const KNOWLEDGE_STATUS_LABELS: Record<string, string> = {
  draft: "Draft",
  in_review: "In review",
  approved: "Approved",
  deprecated: "Deprecated",
  rejected: "Rejected",
  archived: "Archived",
  pending: "Pending",
  pending_review: "Awaiting review",
  superseded: "Superseded",
  accepted: "Accepted",
  suggested: "Suggested",
  published: "Published",
};

export const CLASSIFICATIONS = [
  { key: "mandatory", label: "Mandatory", hint: "Always applies. Breaking it is off-brand." },
  { key: "preferred", label: "Preferred", hint: "The default choice unless there is a reason not to." },
  { key: "optional", label: "Optional", hint: "Available when it helps the work." },
  { key: "prohibited", label: "Prohibited", hint: "Never do this." },
  { key: "context_dependent", label: "Context-dependent", hint: "Applies only in the stated scope." },
  { key: "experimental", label: "Experimental", hint: "Being tested; not yet a rule." },
] as const;

export const CLASSIFICATION_LABEL: Record<string, string> = Object.fromEntries(CLASSIFICATIONS.map((c) => [c.key, c.label]));

export const RELEVANCE = [
  { key: "core", label: "Core", hint: "Defines the brand" },
  { key: "supporting", label: "Supporting", hint: "Reinforces the core" },
  { key: "peripheral", label: "Peripheral", hint: "Occasional, situational" },
  { key: "neutral", label: "Neutral", hint: "Neither on nor off brand" },
  { key: "avoid", label: "Avoid", hint: "Works against the brand" },
] as const;

export const ASSET_TYPE_LABELS: Record<string, string> = {
  image: "Image",
  photograph: "Photograph",
  video: "Video",
  animation: "Animation",
  render_3d: "3D render",
  model_3d: "3D model",
  sketch: "Sketch",
  illustration: "Illustration",
  graphic_design: "Graphic design",
  logo: "Logo",
  document: "Document",
  presentation: "Presentation",
  text: "Text",
  external_reference: "External reference",
  moodboard: "Moodboard",
  audio: "Audio",
  other: "Other",
};

export const REFERENCE_ROLE_LABELS: Record<string, string> = {
  official: "Official",
  inspiration: "Inspiration",
  historical: "Historical",
  external: "External",
  work_in_progress: "Work in progress",
};

export const APPROVAL_LABELS: Record<string, string> = {
  pending: "Pending",
  approved: "Approved",
  rejected: "Rejected",
  archived: "Archived",
};

export const PROJECT_TYPE_LABELS: Record<string, string> = {
  website_design: "Website design",
  website_development: "Website development",
  branding_campaign: "Branding campaign",
  social_media: "Social media",
  product_design: "Product design",
  packaging: "Packaging",
  advertising: "Advertising",
  presentation: "Presentation",
  digital_application: "Digital application",
  video_production: "Video production",
  graphic_design: "Graphic design",
  image_generation: "Image generation",
  copywriting: "Copywriting",
  other: "Other",
};

export const RELATION_LABELS: Record<string, string> = {
  exemplifies: "exemplifies",
  violates: "violates",
  related_to: "related to",
  opposes: "opposes",
  broader_than: "broader than",
  applies_to: "applies to",
  uses: "uses",
  derived_from: "derived from",
  supports: "supports",
  references: "references",
  part_of: "part of",
};

export const ENTITY_LABELS: Record<string, string> = {
  asset: "Asset",
  asset_segment: "Segment",
  principle: "Principle",
  guideline: "Guideline",
  aesthetic_concept: "Aesthetic concept",
  knowledge_entry: "Knowledge entry",
  project: "Project",
  collection: "Collection",
  palette: "Palette",
  color_token: "Color",
  typography_system: "Typography",
  design_token: "Design token",
  external_reference: "External reference",
};

export const JOB_LABELS: Record<string, string> = {
  "asset.ingest": "Asset ingestion",
  "asset.embed": "Asset indexing",
  "knowledge.embed": "Knowledge indexing",
  "brand.reindex": "Brand re-index",
  "asset.purge": "Asset purge",
  "organization.purge": "Customer purge",
  "webhook.deliver": "Webhook delivery",
  "export.build": "Export build",
  "import.validate": "Import validation",
  "import.commit": "Import commit",
  noop: "Test job",
};

/** Workspace sections. Paths are relative to /w/[org]/[brand]. */
export type NavItem = { key: string; label: string; path: string; domain?: string; perm?: string };
export type NavGroup = { label: string; items: NavItem[] };

export const WORKSPACE_NAV: NavGroup[] = [
  {
    label: "Brand library",
    items: [
      { key: "overview", label: "Overview", path: "" },
      { key: "foundation", label: "Brand foundation", path: "/foundation", domain: "brand_foundation" },
      { key: "visual", label: "Visual identity", path: "/visual-identity", domain: "visual_identity" },
      { key: "art", label: "Art direction", path: "/art-direction", domain: "art_direction" },
      { key: "aesthetics", label: "Aesthetic explorer", path: "/aesthetics", domain: "aesthetic_language" },
      { key: "design", label: "Design language", path: "/design-language", domain: "design_language" },
      { key: "language", label: "Brand language", path: "/brand-language", domain: "brand_language" },
      { key: "principles", label: "Principles & guidelines", path: "/principles", domain: "principles_guidelines" },
      { key: "projects", label: "Projects", path: "/projects", domain: "projects_applications" },
    ],
  },
  {
    label: "Creative material",
    items: [
      { key: "assets", label: "Asset library", path: "/assets", perm: "assets.read" },
      { key: "collections", label: "Collections", path: "/collections", perm: "assets.read" },
      { key: "graph", label: "Knowledge graph", path: "/graph" },
    ],
  },
  {
    label: "Intelligence",
    items: [
      { key: "review", label: "AI review queue", path: "/review", perm: "review.read" },
      { key: "search", label: "Search", path: "/search", perm: "search.use" },
      { key: "context", label: "Context generator", path: "/context" },
    ],
  },
  {
    label: "Operations",
    items: [
      { key: "exports", label: "Exports & imports", path: "/exports", perm: "export.create" },
      { key: "integrations", label: "Integrations", path: "/integrations", perm: "integrations.manage" },
      { key: "settings", label: "Settings", path: "/settings" },
    ],
  },
];

export const DOMAIN_PATHS: Record<string, string> = Object.fromEntries(
  WORKSPACE_NAV.flatMap((g) => g.items).filter((i) => i.domain).map((i) => [i.domain!, i.path]),
);

export const ADMIN_NAV: NavItem[] = [
  { key: "overview", label: "Overview", path: "/admin" },
  { key: "customers", label: "Customers", path: "/admin/customers" },
  { key: "activity", label: "System activity", path: "/admin/activity" },
  { key: "processing", label: "AI processing", path: "/admin/processing" },
  { key: "exports", label: "Export management", path: "/admin/exports" },
  { key: "users", label: "Users & roles", path: "/admin/users" },
  { key: "integrations", label: "Integrations", path: "/admin/integrations" },
  { key: "settings", label: "System settings", path: "/admin/settings" },
];

export function actionLabel(action: string): string {
  const map: Record<string, string> = {
    "auth.login": "signed in",
    "auth.login_failed": "failed to sign in",
    "organization.created": "created the customer",
    "organization.updated": "updated the customer profile",
    "organization.archived": "archived the customer",
    "organization.reactivated": "reactivated the customer",
    "organization.deletion_requested": "requested deletion",
    "member.added": "added a member",
    "member.updated": "changed a member",
    "member.removed": "removed a member",
    "asset.uploaded": "uploaded an asset",
    "asset.updated": "edited an asset",
    "asset.approval_changed": "changed asset approval",
    "asset.deleted": "deleted an asset",
    "asset.restored": "restored an asset",
    "asset.original_downloaded": "downloaded an original",
    "analysis.approve": "approved an AI interpretation",
    "analysis.reject": "rejected an AI interpretation",
    "suggestion.accept": "accepted an AI suggestion",
    "suggestion.reject": "rejected an AI suggestion",
    "brand.version_published": "published a brand version",
    "context.generated": "generated a context package",
    "export.requested": "requested an export",
    "export.completed": "export finished",
    "export.downloaded": "downloaded an export",
    "export.expired": "export expired",
    "api_token.created": "created an API token",
    "api_token.revoked": "revoked an API token",
  };
  if (map[action]) return map[action];
  const [entity, verb] = action.split(".");
  if (verb) return `${verb.replace(/_/g, " ")} ${entity.replace(/_/g, " ")}`;
  return action.replace(/[._]/g, " ");
}
