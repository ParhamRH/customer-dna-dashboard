/* Types mirror the FastAPI responses (see backend/app/api/v1/*). Dates are ISO strings. */

export type UUID = string;
export type Json = Record<string, unknown>;

export type KnowledgeStatus = "draft" | "in_review" | "approved" | "deprecated" | "rejected" | "archived";
export type ApprovalStatus = "pending" | "approved" | "rejected" | "archived";
export type ReferenceRole = "official" | "inspiration" | "historical" | "external" | "work_in_progress";
export type Classification = "mandatory" | "preferred" | "optional" | "prohibited" | "context_dependent" | "experimental";
export type Relevance = "core" | "supporting" | "peripheral" | "neutral" | "avoid";

export type Membership = { organization_id: UUID; slug: string; name: string; status: string; role: string };

export type Me = {
  kind: "user" | "api_token";
  user?: { id: UUID; email: string; full_name: string; is_platform_admin: boolean };
  memberships?: Membership[];
};

export type Organization = {
  id: UUID;
  slug: string;
  name: string;
  legal_name: string | null;
  status: "active" | "archived" | "pending_deletion";
  contact_name: string | null;
  contact_email: string | null;
  website: string | null;
  industry: string | null;
  country: string | null;
  notes: string | null;
  settings: Json;
  storage_quota_bytes: number | null;
  retention_days_after_archive: number | null;
  archived_at: string | null;
  deletion_requested_at: string | null;
  created_at: string;
  updated_at: string;
};

export type CustomerRow = {
  id: UUID;
  slug: string;
  name: string;
  status: Organization["status"];
  industry: string | null;
  country: string | null;
  contact_email: string | null;
  created_at: string;
  archived_at: string | null;
  brand_count: number;
  member_count: number;
  asset_count: number;
  storage_bytes: number;
  storage_quota_bytes: number | null;
  pending_reviews: number;
  last_activity_at: string | null;
  palette: { hex: string; name: string; role: string }[];
};

export type PlatformOverview = {
  customers: { total: number; active?: number; archived?: number; pending_deletion?: number };
  assets: { total: number; by_type: Record<string, number>; uploaded_last_7_days: number };
  storage_bytes: number;
  pending_reviews: number;
  jobs: {
    by_status: Record<string, number>;
    by_type: { job_type: string; succeeded: number; failed: number; total: number }[];
    avg_duration_ms: number | null;
  };
  exports: Record<string, number>;
  activity_last_14_days: { day: string; count: number }[];
};

export type ActivityItem = {
  id: number;
  organization_id?: UUID | null;
  organization_name?: string | null;
  organization_slug?: string | null;
  actor: string | null;
  actor_type: string;
  action: string;
  entity_type: string | null;
  entity_id: string | null;
  details: Json;
  created_at: string;
  ip_address?: string | null;
};

export type Job = {
  id: UUID;
  organization_id: UUID;
  organization_name?: string;
  brand_id?: UUID | null;
  job_type: string;
  entity_type: string | null;
  entity_id: UUID | null;
  status: "queued" | "running" | "succeeded" | "failed" | "dead" | "cancelled";
  attempts: number;
  max_attempts: number;
  progress: number;
  error: string | null;
  result?: Json;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  run_after?: string;
};

export type Page<T> = { items: T[]; total: number; limit: number; offset: number };

export type Brand = {
  id: UUID;
  organization_id: UUID;
  slug: string;
  name: string;
  tagline: string | null;
  description: string | null;
  status: "active" | "archived";
  primary_language: string;
  current_version_id: UUID | null;
  settings: Json;
  created_at: string;
  updated_at: string;
};

export type BrandOverview = {
  current_version: { id: UUID; version_number: number; label: string; published_at: string } | null;
  domains: { key: string; number: number; name: string; entries: Record<string, number> }[];
  principles: Record<string, number>;
  guidelines: Record<string, number>;
  aesthetic_concepts: Record<string, number>;
  typography_systems: Record<string, number>;
  design_tokens: Record<string, number>;
  color_tokens: number;
  assets: Record<string, number>;
  projects: number;
};

export type Workspace = {
  organization: Organization | { id: UUID; name: string; slug: string };
  role: string;
  permissions: string[];
  brands: Brand[];
};

export type WorkspaceOverview = {
  counts: Record<string, number>;
  assets_by_type: Record<string, number>;
  assets_by_status: Record<string, number>;
  storage_bytes: number;
  recent_activity: ActivityItem[];
};

export type Governed = {
  id: UUID;
  brand_id: UUID;
  organization_id: UUID;
  status: KnowledgeStatus;
  version: number;
  origin: "human" | "ai_suggestion" | "import";
  source_suggestion_id: UUID | null;
  created_by: UUID | null;
  updated_by: UUID | null;
  approved_by: UUID | null;
  approved_at: string | null;
  created_at: string;
  updated_at: string;
  official_version?: number | null;
  has_official_version?: boolean;
  can_approve?: boolean;
  relationships?: Relationship[];
};

export type KnowledgeEntry = Governed & {
  domain_key: string;
  entry_type: string;
  title: string;
  summary: string | null;
  body: string;
  structured: Json;
  tags: string[];
  sort_order: number;
};

export type Principle = Governed & {
  code: string;
  title: string;
  statement: string;
  rationale: string | null;
  classification: Classification;
  domain_key: string | null;
  scope: { project_types?: string[]; media?: string[]; [k: string]: unknown };
  examples: { do?: string[]; dont?: string[]; notes?: string };
  priority: number;
};

export type Guideline = Governed & {
  domain_key: string;
  slug: string;
  title: string;
  summary: string | null;
  body: string;
  applies_to: { project_types?: string[]; [k: string]: unknown };
};

export type Concept = Governed & {
  slug: string;
  name: string;
  definition: string;
  attributes: unknown[];
  synonyms: string[];
  brand_relevance: Relevance;
  relevance_score: number | null;
  related_concepts?: Relationship[];
  opposing_concepts?: Relationship[];
  broader_concepts?: Relationship[];
  narrower_concepts?: Relationship[];
  example_assets?: AssetSummary[];
  suggested_example_count?: number;
};

export type Relationship = {
  id: UUID;
  relation_type: string;
  direction: "outgoing" | "incoming";
  other_type: string;
  other_id: UUID;
  other_label: string | null;
  other_status: string | null;
  status: "approved" | "suggested" | "rejected";
  origin: string;
  weight: number;
  confidence: number | null;
  note: string | null;
};

export type FieldSpec = { key: string; label: string; kind: "text" | "list" | "records" | "object"; fields?: string[] };
export type EntryType = { key: string; label: string; fields: FieldSpec[] };
export type DomainInfo = { key: string; number: number; name: string; description: string };

export type Registry = { domains: DomainInfo[]; entry_types: Record<string, EntryType[]> };

export type ColorToken = {
  id: UUID;
  palette_id: UUID;
  name: string;
  token_key: string;
  hex: string;
  rgb: { r: number; g: number; b: number; css?: string };
  hsl: { h: number; s: number; l: number; css?: string };
  oklch: { l: number; c: number; h: number; css: string };
  cmyk: { c: number; m: number; y: number; k: number; approximate?: boolean };
  cmyk_is_manual: boolean;
  pantone: string | null;
  semantic_role: string | null;
  usage: string | null;
  sort_order: number;
};

export type Palette = {
  id: UUID;
  brand_id: UUID;
  name: string;
  role: "primary" | "secondary" | "accent" | "neutral" | "semantic" | "extended";
  description: string | null;
  status: KnowledgeStatus;
  sort_order: number;
  colors: ColorToken[];
};

export type TypeLevel = {
  level: string;
  size_px: number;
  line_height: number;
  weight: number;
  letter_spacing_em?: number;
  text_transform?: string | null;
  usage?: string | null;
};

export type Typography = {
  id: UUID;
  brand_id: UUID;
  name: string;
  role: "primary" | "secondary" | "display" | "body" | "mono" | "accent";
  family: string;
  fallback_stack: string;
  source: string | null;
  source_url: string | null;
  license: string | null;
  weights: number[];
  supports_italic: boolean;
  hierarchy: TypeLevel[];
  usage: string | null;
  status: KnowledgeStatus;
  sort_order: number;
};

export type DesignToken = {
  id: UUID;
  brand_id: UUID;
  path: string;
  token_type: string;
  value: unknown;
  description: string | null;
  category: string;
  domain_key: "visual_identity" | "design_language";
  status: KnowledgeStatus;
  sort_order: number;
};

export type DomainView = {
  domain: DomainInfo;
  entry_types: EntryType[];
  entries: KnowledgeEntry[];
  principles: Principle[];
  guidelines: Guideline[];
  palettes?: Palette[];
  typography?: Typography[];
  logos?: AssetSummary[];
  concepts?: Concept[];
};

export type AssetSummary = {
  id: UUID;
  organization_id: UUID;
  brand_id: UUID;
  title: string;
  description: string | null;
  asset_type: string;
  category: string | null;
  subcategory: string | null;
  folder_path: string;
  mime_type: string | null;
  file_size: number | null;
  original_filename: string | null;
  approval_status: ApprovalStatus;
  reference_role: ReferenceRole;
  brand_relevance: string;
  processing_status: string;
  source_type: string;
  source_url: string | null;
  tags: string[];
  thumbnail_url: string | null;
  preview_url: string | null;
  width: number | null;
  height: number | null;
  duration_seconds: number | null;
  dominant_colors: string[];
  created_at: string;
  updated_at: string;
  collection_note?: string | null;
};

export type Derivative = {
  id: UUID;
  kind: string;
  mime_type: string;
  width: number | null;
  height: number | null;
  file_size: number | null;
  page_number: number | null;
  timestamp_ms: number | null;
  segment_index: number | null;
  url: string;
};

export type Segment = {
  id: UUID;
  segment_type: "scene" | "page" | "section";
  index: number;
  start_ms: number | null;
  end_ms: number | null;
  page_number: number | null;
  title: string | null;
  text_excerpt: string;
  keyframe_derivative_id: UUID | null;
  meta: Json;
};

export type ConceptMatch = { name: string; evidence?: string; confidence?: number };

export type Interpretation = {
  summary?: string;
  atmosphere?: string[];
  visual_style?: string[];
  suggested_tags?: string[];
  brand_relevance?: { assessment?: string; rationale?: string | null };
  aesthetic_concepts?: ConceptMatch[];
  potential_applications?: string[];
  photography_characteristics?: string[];
  [k: string]: unknown;
};

export type Analysis = {
  id: UUID;
  asset_id?: UUID;
  brand_id?: UUID;
  analysis_type: string;
  provider: string;
  model: string;
  prompt_key: string | null;
  prompt_version: number | null;
  schema_version: number;
  status: "pending_review" | "approved" | "rejected" | "superseded";
  confidence: number | null;
  processing_ms: number | null;
  is_development_adapter: boolean;
  objective: Json;
  interpretive: Interpretation;
  validation_errors: unknown[];
  reviewed_by: UUID | null;
  reviewed_at: string | null;
  review_notes: string | null;
  created_at: string;
  asset?: AssetSummary | null;
};

export type AssetDetail = AssetSummary & {
  tag_details: { tag: string; source: "human" | "ai"; status: "approved" | "suggested" | "rejected"; confidence: number | null }[];
  checksum: string | null;
  schema_version: number;
  license: Json;
  media_metadata: Json;
  curated_metadata: Json;
  processing_error: string | null;
  approved_analysis_id: UUID | null;
  approved_by: UUID | null;
  approved_at: string | null;
  deleted_at: string | null;
  derivatives: Derivative[];
  segments: Segment[];
  analyses: Analysis[];
  collections: { id: UUID; name: string; slug: string }[];
  references: {
    id: UUID;
    title: string;
    url: string | null;
    source_name: string | null;
    creator: string | null;
    license: string | null;
    accessed_at: string | null;
    notes: string | null;
    provenance: Json;
  }[];
  relationships: Relationship[];
  original_download_available: boolean;
  pending_suggestions?: number;
};

export type AssetFacets = {
  asset_type: Record<string, number>;
  approval_status: Record<string, number>;
  reference_role: Record<string, number>;
  processing_status: Record<string, number>;
  tags: { tag: string; count: number }[];
};

export type Collection = {
  id: UUID;
  brand_id: UUID;
  slug: string;
  name: string;
  description: string | null;
  kind: "collection" | "moodboard" | "curated_set" | "project_board";
  cover_asset_id: UUID | null;
  asset_count: number;
  cover: AssetSummary | null;
  /** list view only: up to four assets, cover first */
  preview?: AssetSummary[];
  assets?: AssetSummary[];
  created_at: string;
  updated_at: string;
};

export type Suggestion = {
  id: UUID;
  brand_id: UUID;
  suggestion_type: string;
  title: string;
  payload: Json;
  rationale: string | null;
  confidence: number | null;
  source_asset_id: UUID | null;
  source_analysis_id: UUID | null;
  status: "pending" | "accepted" | "rejected" | "superseded";
  resolved_entity_type: string | null;
  resolved_entity_id: UUID | null;
  reviewed_by: UUID | null;
  reviewed_at: string | null;
  created_at: string;
  asset?: AssetSummary | null;
};

export type SearchItem = {
  entity_type: string;
  id: UUID;
  brand_id: UUID;
  title: string;
  snippet?: string;
  score: number;
  knowledge_status: "official" | "pending" | "inspiration" | "external" | "historical" | string;
  status: string | null;
  matched_segments?: { segment_type?: string; index?: number; similarity: number; start_ms?: number; page_number?: number; title?: string }[];
  asset?: AssetSummary;
  classification?: string;
  signals?: Record<string, { rank: number; score: number; fused: number }>;
};

export type SearchResult = {
  query: string;
  interpreted: {
    text: string;
    asset_types: string[];
    entity_types: string[];
    approved_only: boolean;
    attributes: string[];
    project_types: string[];
    matched_entities: { type: string; id: UUID; label: string }[];
  };
  embedding_model: string | null;
  signals_used: string[];
  total_candidates: number;
  items: SearchItem[];
};

export type GraphNode = {
  id: string;
  type: string;
  entity_id: UUID;
  label: string;
  status: string | null;
  thumbnail_url?: string | null;
  asset_type?: string;
  reference_role?: string;
};
export type GraphEdge = { id: UUID; source: string; target: string; relation_type: string; status: string; origin?: string; weight: number };

export type Project = {
  id: UUID;
  brand_id: UUID;
  slug: string;
  name: string;
  project_type: string;
  status: "planning" | "active" | "completed" | "archived";
  description: string | null;
  objectives: string | null;
  audience: string | null;
  deliverables: unknown[];
  selected_domains: string[];
  brief: Json;
  start_date: string | null;
  due_date: string | null;
  created_at: string;
  updated_at: string;
  relationships?: Relationship[];
  assets?: AssetSummary[];
  context_packages?: { id: UUID; title: string; task_type: string; mode: string; created_at: string }[];
};

export type ContextTemplate = {
  key: string;
  label: string;
  domains: string[];
  instructions: string[];
  deliverable_checklist: string[];
  prompt_ready: boolean;
  include_tokens: boolean;
};

export type ContextSource = { ref: string; type: string; id: UUID; version: number | null; status: string | null; label: string };

export type ContextPreview = {
  domains: string[];
  counts: Record<string, number>;
  sources: Record<string, ContextSource[]>;
  principles_by_classification: Record<string, number>;
  references: { id: UUID; title: string; selected_because: string; interpretation_status: string }[];
  prohibited_count: number;
  brand_version: number | null;
};

export type ContextPackage = {
  id: UUID;
  brand_id: UUID;
  project_id: UUID | null;
  brand_version_id: UUID | null;
  title: string;
  task_type: string;
  output_medium: string | null;
  mode: "compact" | "standard" | "comprehensive";
  request?: Json;
  content?: Json;
  content_markdown?: string;
  markdown?: string;
  sources?: ContextSource[];
  token_estimate: number;
  checksum: string;
  created_at: string;
};

export type ExportJob = {
  id: UUID;
  organization_id: UUID;
  brand_ids: UUID[];
  brand_names: string[];
  mode: "full" | "selective";
  options: Json;
  status: "queued" | "running" | "completed" | "failed" | "expired";
  job_id: UUID | null;
  storage_uri: string | null;
  file_count: number | null;
  size_bytes: number | null;
  archive_checksum: string | null;
  manifest: Json;
  error: string | null;
  created_at: string;
  completed_at: string | null;
  expires_at: string | null;
  download_available: boolean;
};

export type ImportJob = {
  id: UUID;
  status: "uploaded" | "validating" | "validated" | "invalid" | "committing" | "committed" | "failed" | "discarded";
  staging_uri: string;
  options: Json;
  source_manifest: Json;
  preview: Json;
  report: Json;
  job_id: UUID | null;
  created_at: string;
  updated_at: string;
};

export type Member = {
  id: UUID;
  user_id: UUID;
  email: string;
  full_name: string;
  role: string;
  status: "active" | "suspended";
  last_login_at: string | null;
  created_at: string;
  temporary_password?: string | null;
};

export type ApiTokenRow = {
  id: UUID;
  name: string;
  token_prefix: string;
  role: string;
  brand_id: UUID | null;
  scopes: string[];
  created_at: string;
  expires_at: string | null;
  last_used_at: string | null;
  revoked_at: string | null;
  token?: string;
};

export type Integration = {
  id: UUID;
  brand_id: UUID | null;
  kind: "webhook" | "mcp_client" | "ai_provider" | "rest_client";
  name: string;
  config: Json;
  status: "active" | "disabled";
  has_secret: boolean;
  last_event_at: string | null;
  created_at: string;
  updated_at: string;
};

export type AiProviderInfo = { provider: string; model: string | null; dimensions: number | null; development_adapter: boolean };
export type AiDescribe = Record<"vision" | "text" | "text_embedding" | "visual_embedding", AiProviderInfo>;

export type PromptTemplate = {
  id: UUID;
  organization_id: UUID | null;
  key: string;
  name: string;
  purpose: string;
  version: number;
  template: string;
  is_active: boolean;
  scope: string;
  created_at: string;
};

export type BrandVersion = {
  id: UUID;
  brand_id: UUID;
  version_number: number;
  label: string;
  status: "published" | "superseded";
  notes: string | null;
  snapshot_checksum: string;
  counts: Record<string, number>;
  published_by: UUID | null;
  published_at: string;
  snapshot?: Json;
};

export type Revision = {
  version: number;
  status_at_creation: string;
  change_note: string | null;
  data: Json;
  created_by: UUID | null;
  created_at: string;
  approved: boolean;
  approved_at: string | null;
  approved_by: UUID | null;
};

export type PlatformUser = {
  id: UUID;
  email: string;
  full_name: string;
  is_platform_admin: boolean;
  is_active: boolean;
  last_login_at: string | null;
  created_at: string;
  active_sessions: number;
  memberships: {
    membership_id: UUID;
    organization_id: UUID;
    organization_name: string;
    organization_slug: string;
    organization_status: string;
    role: string;
    status: string;
  }[];
  temporary_password?: string | null;
};

export type RoleInfo = { key: string; name: string; rank: number; permissions: string[] };

export type ContrastPair = {
  a: string;
  a_hex: string;
  b: string;
  b_hex: string;
  ratio: number;
  AA_normal: boolean;
  AA_large: boolean;
  AAA_normal: boolean;
  AAA_large: boolean;
};
