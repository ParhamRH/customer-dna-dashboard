"""Tenant isolation (Row Level Security), grants, integrity triggers, vector indexes, reference data.

Revision ID: 0002
Revises: 0001
"""
from __future__ import annotations

import os

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

APP = os.environ.get("BDNA_DB_APP_ROLE", "bdna_app")
SYSTEM = os.environ.get("BDNA_DB_SYSTEM_ROLE", "bdna_system")

# Every table whose rows belong to exactly one organization (organization_id NOT NULL).
TENANT_TABLES = [
    "organization_users",
    "api_tokens",
    "brands",
    "brand_versions",
    "knowledge_entries",
    "principles",
    "guidelines",
    "aesthetic_concepts",
    "palettes",
    "color_tokens",
    "typography_systems",
    "design_tokens",
    "knowledge_revisions",
    "assets",
    "asset_derivatives",
    "asset_segments",
    "asset_analyses",
    "asset_tags",
    "collections",
    "collection_assets",
    "external_references",
    "projects",
    "relationships",
    "embeddings",
    "processing_jobs",
    "ai_suggestions",
    "reviews",
    "context_packages",
    "export_jobs",
    "import_jobs",
    "integrations",
]
# Append-only / immutable tenant tables: the runtime role may not UPDATE or DELETE.
APPEND_ONLY = {"knowledge_revisions", "reviews"}
REFERENCE_TABLES = ["roles", "permissions", "role_permissions", "knowledge_domains"]

GRAPH_ENTITY_TABLES = {
    "asset": "assets",
    "asset_segment": "asset_segments",
    "principle": "principles",
    "guideline": "guidelines",
    "aesthetic_concept": "aesthetic_concepts",
    "knowledge_entry": "knowledge_entries",
    "project": "projects",
    "collection": "collections",
    "palette": "palettes",
    "color_token": "color_tokens",
    "typography_system": "typography_systems",
    "design_token": "design_tokens",
    "external_reference": "external_references",
}

PERMISSIONS = {
    "platform.admin": "Full platform administration across all customers",
    "org.read": "View the customer profile",
    "org.manage": "Edit customer profile and settings",
    "users.read": "View workspace members",
    "users.manage": "Invite, change roles of and remove workspace members",
    "brand.read": "View brands",
    "brand.manage": "Create and edit brands",
    "brand.publish": "Publish immutable brand versions",
    "knowledge.read": "Read brand knowledge (all domains)",
    "knowledge.write": "Create and edit draft brand knowledge",
    "knowledge.approve": "Approve official principles, guidelines and knowledge entries",
    "concepts.manage": "Create and edit aesthetic ontology concepts",
    "assets.read": "Browse assets, previews and metadata",
    "assets.write": "Upload and edit assets",
    "assets.delete": "Delete assets (retention workflow)",
    "assets.download_original": "Download original files",
    "collections.manage": "Create and edit collections and moodboards",
    "projects.manage": "Create and edit projects",
    "review.read": "View the AI review queue",
    "review.decide": "Approve or reject AI analyses and suggestions",
    "search.use": "Use search",
    "context.generate": "Generate and save context packages",
    "export.create": "Create customer exports",
    "export.download": "Download customer exports",
    "import.run": "Import a library export into this workspace",
    "integrations.manage": "Manage integrations and webhooks",
    "api_tokens.manage": "Create and revoke API / MCP tokens",
    "audit.read": "Read the audit log",
    "jobs.read": "View processing jobs",
    "jobs.manage": "Retry or cancel processing jobs",
}

_ALL_ORG = [k for k in PERMISSIONS if k != "platform.admin"]
ROLES = {
    "platform_super_admin": ("Platform Super Administrator", "platform", 100, list(PERMISSIONS)),
    "customer_admin": ("Customer Administrator", "organization", 90, _ALL_ORG),
    "creative_director": (
        "Creative Director",
        "organization",
        80,
        [
            "org.read", "users.read", "brand.read", "brand.manage", "brand.publish",
            "knowledge.read", "knowledge.write", "knowledge.approve", "concepts.manage",
            "assets.read", "assets.write", "assets.delete", "assets.download_original",
            "collections.manage", "projects.manage", "review.read", "review.decide",
            "search.use", "context.generate", "export.create", "export.download",
            "audit.read", "jobs.read", "jobs.manage",
        ],
    ),
    "editor": (
        "Editor",
        "organization",
        60,
        [
            "org.read", "users.read", "brand.read", "knowledge.read", "knowledge.write",
            "assets.read", "assets.write", "assets.download_original", "collections.manage",
            "projects.manage", "review.read", "search.use", "context.generate", "jobs.read",
        ],
    ),
    "reviewer": (
        "Reviewer",
        "organization",
        50,
        [
            "org.read", "users.read", "brand.read", "knowledge.read", "assets.read",
            "assets.download_original", "review.read", "review.decide", "search.use",
            "context.generate", "jobs.read",
        ],
    ),
    "viewer": ("Viewer", "organization", 10, ["org.read", "brand.read", "knowledge.read", "assets.read", "search.use"]),
}

DOMAINS = [
    ("brand_foundation", 1, "Brand Foundation", "Philosophy, mission, vision, story, positioning, personality, values, audience."),
    ("visual_identity", 2, "Visual Identity", "Logos, color palettes, typography, iconography, graphic elements, grids, accessibility."),
    ("art_direction", 3, "Art Direction", "Photography, lighting, composition, materials, atmosphere, motion and image treatment."),
    ("aesthetic_language", 4, "Aesthetic Language & Ontology", "Controlled vocabulary of aesthetic concepts."),
    ("design_language", 5, "Design Language", "Layout, grids, spacing, hierarchy, components, interaction and motion."),
    ("brand_language", 6, "Brand Language", "Tone of voice, vocabulary, writing style, storytelling and copy rules."),
    ("creative_assets", 7, "Creative Asset Repository", "Images, video, 3D, documents, references and moodboards."),
    ("principles_guidelines", 8, "Creative Principles & Guidelines", "Classified principles and official guidelines."),
    ("projects_applications", 9, "Projects & Applications", "Customer projects and their task-specific context."),
    ("ai_knowledge", 10, "AI Knowledge & Operations", "Analyses, embeddings, prompts, context packages and review history."),
]

VECTOR_DIMENSIONS = [256, 384, 512, 768, 1024, 1536]


def _q(s: str) -> str:
    return s.replace("'", "''")


def upgrade() -> None:
    # --- request-context helpers (fail closed: unset -> NULL -> no rows match) ------------
    op.execute(
        """
        CREATE OR REPLACE FUNCTION bdna_current_org() RETURNS uuid LANGUAGE sql STABLE PARALLEL SAFE
          AS $$ SELECT NULLIF(current_setting('app.org_id', true), '')::uuid $$;
        CREATE OR REPLACE FUNCTION bdna_current_user() RETURNS uuid LANGUAGE sql STABLE PARALLEL SAFE
          AS $$ SELECT NULLIF(current_setting('app.user_id', true), '')::uuid $$;
        """
    )

    # --- Row Level Security on tenant tables ---------------------------------------------
    for t in TENANT_TABLES:
        op.execute(f"ALTER TABLE {t} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {t} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY tenant_isolation ON {t} FOR ALL TO {APP} "
            f"USING (organization_id = bdna_current_org()) "
            f"WITH CHECK (organization_id = bdna_current_org())"
        )

    # organizations: a tenant session sees and may update only its own organization row.
    op.execute("ALTER TABLE organizations ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE organizations FORCE ROW LEVEL SECURITY")
    op.execute(f"CREATE POLICY org_self_select ON organizations FOR SELECT TO {APP} USING (id = bdna_current_org())")
    op.execute(
        f"CREATE POLICY org_self_update ON organizations FOR UPDATE TO {APP} "
        f"USING (id = bdna_current_org()) WITH CHECK (id = bdna_current_org())"
    )

    # users: yourself, or members of the organization in context.
    op.execute("ALTER TABLE users ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE users FORCE ROW LEVEL SECURITY")
    op.execute(
        f"""CREATE POLICY users_visible ON users FOR SELECT TO {APP} USING (
              id = bdna_current_user()
              OR EXISTS (SELECT 1 FROM organization_users ou
                         WHERE ou.user_id = users.id AND ou.organization_id = bdna_current_org()))"""
    )
    op.execute(
        f"CREATE POLICY users_self_update ON users FOR UPDATE TO {APP} "
        f"USING (id = bdna_current_user()) WITH CHECK (id = bdna_current_user())"
    )

    # auth sessions: only your own.
    op.execute("ALTER TABLE auth_sessions ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE auth_sessions FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY sessions_own ON auth_sessions FOR ALL TO {APP} "
        f"USING (user_id = bdna_current_user()) WITH CHECK (user_id = bdna_current_user())"
    )

    # audit log: tenant-scoped reads and inserts only.
    op.execute("ALTER TABLE audit_logs ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE audit_logs FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY audit_select ON audit_logs FOR SELECT TO {APP} USING (organization_id = bdna_current_org())"
    )
    op.execute(
        f"CREATE POLICY audit_insert ON audit_logs FOR INSERT TO {APP} WITH CHECK (organization_id = bdna_current_org())"
    )

    # prompt templates: platform defaults (NULL org) are readable by everyone; overrides are private.
    op.execute("ALTER TABLE prompt_templates ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE prompt_templates FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY prompts_select ON prompt_templates FOR SELECT TO {APP} "
        f"USING (organization_id IS NULL OR organization_id = bdna_current_org())"
    )
    op.execute(
        f"CREATE POLICY prompts_write ON prompt_templates FOR ALL TO {APP} "
        f"USING (organization_id = bdna_current_org()) WITH CHECK (organization_id = bdna_current_org())"
    )

    # --- Grants --------------------------------------------------------------------------
    op.execute(f"GRANT USAGE ON SCHEMA public TO {APP}, {SYSTEM}")
    for t in TENANT_TABLES:
        if t in APPEND_ONLY:
            op.execute(f"GRANT SELECT, INSERT ON {t} TO {APP}")
        elif t == "brand_versions":
            op.execute(f"GRANT SELECT, INSERT ON {t} TO {APP}")
            op.execute(f"GRANT UPDATE (status) ON {t} TO {APP}")
        else:
            op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {t} TO {APP}")
    op.execute(f"GRANT SELECT, UPDATE ON organizations TO {APP}")
    op.execute(f"GRANT SELECT ON users TO {APP}")
    op.execute(f"GRANT UPDATE (full_name, password_hash, updated_at) ON users TO {APP}")
    op.execute(f"GRANT SELECT ON auth_sessions TO {APP}")
    op.execute(f"GRANT UPDATE (last_seen_at, revoked_at) ON auth_sessions TO {APP}")
    op.execute(f"GRANT SELECT, INSERT ON audit_logs TO {APP}")
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON prompt_templates TO {APP}")
    for t in REFERENCE_TABLES:
        op.execute(f"GRANT SELECT ON {t} TO {APP}")
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {SYSTEM}")
    op.execute(f"GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {APP}, {SYSTEM}")
    op.execute(f"GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO {APP}, {SYSTEM}")

    # --- Integrity triggers --------------------------------------------------------------
    # 1) Original asset files are immutable once registered.
    op.execute(
        """
        CREATE OR REPLACE FUNCTION bdna_assets_immutable_original() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          IF OLD.storage_uri IS NOT NULL AND (
               NEW.storage_uri IS DISTINCT FROM OLD.storage_uri
            OR NEW.checksum IS DISTINCT FROM OLD.checksum
            OR NEW.file_size IS DISTINCT FROM OLD.file_size
            OR NEW.mime_type IS DISTINCT FROM OLD.mime_type
            OR NEW.original_filename IS DISTINCT FROM OLD.original_filename) THEN
            RAISE EXCEPTION 'original asset file metadata is immutable (asset %)', OLD.id
              USING ERRCODE = 'check_violation';
          END IF;
          IF NEW.organization_id IS DISTINCT FROM OLD.organization_id THEN
            RAISE EXCEPTION 'assets cannot change organization' USING ERRCODE = 'check_violation';
          END IF;
          RETURN NEW;
        END $$;
        CREATE TRIGGER trg_assets_immutable_original BEFORE UPDATE ON assets
          FOR EACH ROW EXECUTE FUNCTION bdna_assets_immutable_original();
        """
    )

    # 2) Relationship endpoints must exist in the same organization (and be visible under RLS).
    cases = "\n".join(
        f"      WHEN '{etype}' THEN EXECUTE 'SELECT organization_id FROM {table} WHERE id = $1' INTO o USING eid;"
        for etype, table in GRAPH_ENTITY_TABLES.items()
    )
    op.execute(
        f"""
        CREATE OR REPLACE FUNCTION bdna_entity_org(etype text, eid uuid) RETURNS uuid LANGUAGE plpgsql STABLE AS $$
        DECLARE o uuid;
        BEGIN
          CASE etype
{cases}
            ELSE RAISE EXCEPTION 'unknown graph entity type %', etype USING ERRCODE = 'check_violation';
          END CASE;
          RETURN o;
        END $$;

        CREATE OR REPLACE FUNCTION bdna_relationship_check() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          IF bdna_entity_org(NEW.source_type, NEW.source_id) IS DISTINCT FROM NEW.organization_id THEN
            RAISE EXCEPTION 'relationship source %:% not found in organization', NEW.source_type, NEW.source_id
              USING ERRCODE = 'foreign_key_violation';
          END IF;
          IF bdna_entity_org(NEW.target_type, NEW.target_id) IS DISTINCT FROM NEW.organization_id THEN
            RAISE EXCEPTION 'relationship target %:% not found in organization', NEW.target_type, NEW.target_id
              USING ERRCODE = 'foreign_key_violation';
          END IF;
          IF NEW.source_type = NEW.target_type AND NEW.source_id = NEW.target_id THEN
            RAISE EXCEPTION 'relationship cannot point to itself' USING ERRCODE = 'check_violation';
          END IF;
          RETURN NEW;
        END $$;
        CREATE TRIGGER trg_relationships_check BEFORE INSERT OR UPDATE ON relationships
          FOR EACH ROW EXECUTE FUNCTION bdna_relationship_check();

        -- Embeddings must also point at an entity of the same organization.
        CREATE OR REPLACE FUNCTION bdna_embedding_check() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          IF bdna_entity_org(NEW.entity_type, NEW.entity_id) IS DISTINCT FROM NEW.organization_id THEN
            RAISE EXCEPTION 'embedding entity %:% not found in organization', NEW.entity_type, NEW.entity_id
              USING ERRCODE = 'foreign_key_violation';
          END IF;
          IF vector_dims(NEW.embedding) <> NEW.dimensions THEN
            RAISE EXCEPTION 'embedding dimension mismatch' USING ERRCODE = 'check_violation';
          END IF;
          RETURN NEW;
        END $$;
        CREATE TRIGGER trg_embeddings_check BEFORE INSERT OR UPDATE ON embeddings
          FOR EACH ROW EXECUTE FUNCTION bdna_embedding_check();

        -- When a graph entity is deleted, remove its edges and vectors (polymorphic, no FK).
        CREATE OR REPLACE FUNCTION bdna_cleanup_entity_refs() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          DELETE FROM relationships
           WHERE (source_type = TG_ARGV[0] AND source_id = OLD.id)
              OR (target_type = TG_ARGV[0] AND target_id = OLD.id);
          DELETE FROM embeddings WHERE entity_type = TG_ARGV[0] AND entity_id = OLD.id;
          RETURN OLD;
        END $$;
        """
    )
    for etype, table in GRAPH_ENTITY_TABLES.items():
        op.execute(
            f"CREATE TRIGGER trg_{table}_cleanup_refs AFTER DELETE ON {table} "
            f"FOR EACH ROW EXECUTE FUNCTION bdna_cleanup_entity_refs('{etype}')"
        )

    # --- Vector indexes: one partial HNSW expression index per supported dimension --------
    for d in VECTOR_DIMENSIONS:
        op.execute(
            f"CREATE INDEX ix_embeddings_hnsw_{d} ON embeddings "
            f"USING hnsw ((embedding::vector({d})) vector_cosine_ops) WHERE dimensions = {d}"
        )
    # Fuzzy/exact title search
    op.execute("CREATE INDEX ix_assets_title_trgm ON assets USING gin (title gin_trgm_ops)")

    # --- Reference data ------------------------------------------------------------------
    for key, desc in PERMISSIONS.items():
        op.execute(f"INSERT INTO permissions (key, description) VALUES ('{key}', '{_q(desc)}')")
    for key, (name, scope, rank, perms) in ROLES.items():
        op.execute(
            f"INSERT INTO roles (key, name, description, scope, rank) "
            f"VALUES ('{key}', '{_q(name)}', '', '{scope}', {rank})"
        )
        for p in perms:
            op.execute(f"INSERT INTO role_permissions (role_key, permission_key) VALUES ('{key}', '{p}')")
    for key, num, name, desc in DOMAINS:
        op.execute(
            f"INSERT INTO knowledge_domains (key, number, name, description) "
            f"VALUES ('{key}', {num}, '{_q(name)}', '{_q(desc)}')"
        )


def downgrade() -> None:
    op.execute("DELETE FROM role_permissions; DELETE FROM roles; DELETE FROM permissions; DELETE FROM knowledge_domains;")
    op.execute("DROP INDEX IF EXISTS ix_assets_title_trgm")
    for d in VECTOR_DIMENSIONS:
        op.execute(f"DROP INDEX IF EXISTS ix_embeddings_hnsw_{d}")
    for etype, table in GRAPH_ENTITY_TABLES.items():
        op.execute(f"DROP TRIGGER IF EXISTS trg_{table}_cleanup_refs ON {table}")
    op.execute(
        """
        DROP TRIGGER IF EXISTS trg_embeddings_check ON embeddings;
        DROP TRIGGER IF EXISTS trg_relationships_check ON relationships;
        DROP TRIGGER IF EXISTS trg_assets_immutable_original ON assets;
        DROP FUNCTION IF EXISTS bdna_cleanup_entity_refs();
        DROP FUNCTION IF EXISTS bdna_embedding_check();
        DROP FUNCTION IF EXISTS bdna_relationship_check();
        DROP FUNCTION IF EXISTS bdna_entity_org(text, uuid);
        DROP FUNCTION IF EXISTS bdna_assets_immutable_original();
        """
    )
    for t in TENANT_TABLES:
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {t}")
        op.execute(f"ALTER TABLE {t} DISABLE ROW LEVEL SECURITY")
    for t, pols in {
        "organizations": ["org_self_select", "org_self_update"],
        "users": ["users_visible", "users_self_update"],
        "auth_sessions": ["sessions_own"],
        "audit_logs": ["audit_select", "audit_insert"],
        "prompt_templates": ["prompts_select", "prompts_write"],
    }.items():
        for p in pols:
            op.execute(f"DROP POLICY IF EXISTS {p} ON {t}")
        op.execute(f"ALTER TABLE {t} DISABLE ROW LEVEL SECURITY")
    op.execute("DROP FUNCTION IF EXISTS bdna_current_org(); DROP FUNCTION IF EXISTS bdna_current_user();")
