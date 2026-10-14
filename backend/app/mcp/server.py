"""Read-only MCP server exposing one customer's brand knowledge to external AI clients.

Authentication: a platform API token (``bdna_…``), created in the workspace (Integrations →
API tokens). Over Streamable HTTP it is sent as ``Authorization: Bearer``; over stdio it is read
from ``BDNA_MCP_TOKEN``. The token fixes the organization (and optionally one brand); every tool
runs on the RLS-enforced database role scoped to that organization, with the token's permissions.
There is no unfiltered or cross-tenant access path.
"""
from __future__ import annotations

import json
import os
import uuid
from contextlib import contextmanager
from typing import Any

from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.auth.provider import AccessToken
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from sqlalchemy import or_, select

from app.api.deps import Identity, _resolve_api_token
from app.api.errors import ApiError
from app.db.session import TenantContext, tenant_session
from app.models import AestheticConcept, Asset, AuditLog, Brand, BrandVersion, KnowledgeEntry
from app.security.credentials import is_api_token
from app.security.permissions import permissions_for_role

INSTRUCTIONS = """Brand DNA & Creative Intelligence tools for ONE customer's brand library (read-only).
Official knowledge = human-approved principles, guidelines, concepts and entries; treat 'mandatory' and
'prohibited' principles as hard constraints. Asset interpretations marked 'pending' are unreviewed AI
output — never present them as brand rules. Cite source ids (e.g. principle:<id>) when you rely on them.
Typical flow: get_brand_identity → get_design_guidelines / get_visual_identity → search_brand_assets →
generate_brand_context for a complete task brief."""


class McpAccessError(ToolError):
    pass


class BdnaTokenVerifier:
    """Verifies platform API tokens for the Streamable HTTP transport."""

    async def verify_token(self, token: str) -> AccessToken | None:
        if not is_api_token(token):
            return None
        try:
            ident = _resolve_api_token(token)
        except ApiError:
            return None
        return AccessToken(token=token, client_id=str(ident.token_id), scopes=["brand.read"], subject=str(ident.token_org_id))


class _Principal:
    def __init__(self, ident: Identity):
        self.ident = ident
        self.org_id: uuid.UUID = ident.token_org_id  # type: ignore[assignment]
        perms = permissions_for_role(ident.token_role_key or "viewer")
        if ident.token_scopes:
            perms = perms & frozenset(ident.token_scopes)
        self.permissions = perms
        self.brand_restriction = ident.token_brand_id

    def require(self, *perms: str) -> None:
        missing = [p for p in perms if p not in self.permissions]
        if missing:
            raise McpAccessError(f"token lacks permission(s): {', '.join(missing)}")


def build_server(default_token: str | None = None, http_auth: bool = False, public_url: str | None = None) -> MCPServer:
    kwargs: dict[str, Any] = {}
    if http_auth:
        from mcp.server.auth.settings import AuthSettings

        base = (public_url or "http://localhost:8001").rstrip("/")
        kwargs = {
            "auth": AuthSettings(issuer_url=base, resource_server_url=f"{base}/mcp", validate_token_resource=False),
            "token_verifier": BdnaTokenVerifier(),
        }
    server = MCPServer(name="brand-dna", title="Brand DNA & Creative Intelligence", instructions=INSTRUCTIONS,
                       version="0.1.0", **kwargs)
    env_token = default_token or os.environ.get("BDNA_MCP_TOKEN")

    def principal() -> _Principal:
        at = get_access_token()
        raw = at.token if at else env_token
        if not raw:
            raise McpAccessError("No API token. Set BDNA_MCP_TOKEN (stdio) or send Authorization: Bearer (HTTP).")
        try:
            return _Principal(_resolve_api_token(raw))
        except ApiError as e:
            raise McpAccessError(e.message) from e

    @contextmanager
    def tenant(tool: str, args: dict[str, Any]):
        p = principal()
        with tenant_session(TenantContext(org_id=p.org_id, user_id=p.ident.user_id)) as db:
            db.add(AuditLog(organization_id=p.org_id, actor_user_id=p.ident.user_id, actor_type="api_token",
                            actor_label=f"mcp:{p.ident.token_name}", action="mcp.tool_called", entity_type="mcp_tool",
                            entity_id=tool, details={k: str(v)[:200] for k, v in args.items() if v is not None}))
            yield p, db

    def resolve_brand(p: _Principal, db, brand_id: str | None) -> Brand:  # noqa: ANN001
        if p.brand_restriction:
            if brand_id and uuid.UUID(brand_id) != p.brand_restriction:
                raise McpAccessError("this token is restricted to a different brand")
            brand_id = str(p.brand_restriction)
        if brand_id:
            b = db.scalar(select(Brand).where(Brand.id == uuid.UUID(brand_id)))
            if b is None:
                raise McpAccessError("brand not found")
            return b
        brands = db.scalars(select(Brand).where(Brand.status == "active")).all()
        if len(brands) == 1:
            return brands[0]
        raise McpAccessError("several brands available — pass brand_id: " + ", ".join(f"{b.name}={b.id}" for b in brands))

    # ------------------------------------------------------------------------------------------
    @server.tool(description="List the brands this token can access.")
    def list_brands() -> dict:
        with tenant("list_brands", {}) as (p, db):
            p.require("brand.read")
            q = select(Brand)
            if p.brand_restriction:
                q = q.where(Brand.id == p.brand_restriction)
            return {"brands": [{"id": str(b.id), "name": b.name, "slug": b.slug, "tagline": b.tagline} for b in db.scalars(q)]}

    @server.tool(description="Core brand identity: foundation (mission, vision, positioning, values…), core aesthetic concepts and the published version.")
    def get_brand_identity(brand_id: str | None = None) -> dict:
        from app.services import knowledge as ks

        with tenant("get_brand_identity", {"brand_id": brand_id}) as (p, db):
            p.require("knowledge.read")
            b = resolve_brand(p, db, brand_id)
            v = db.scalar(select(BrandVersion).where(BrandVersion.id == b.current_version_id)) if b.current_version_id else None
            entries = [e for e in ks.official_items(db, "knowledge_entry", b.id) if e["domain_key"] == "brand_foundation"]
            concepts = [c for c in ks.official_items(db, "aesthetic_concept", b.id) if c.get("brand_relevance") in ("core", "supporting")]
            return {
                "brand": {"id": str(b.id), "name": b.name, "tagline": b.tagline, "description": b.description},
                "published_version": {"number": v.version_number, "label": v.label, "published_at": v.published_at.isoformat()} if v else None,
                "foundation": [{"source": f"knowledge_entry:{e['id']}", "type": e["entry_type"], "title": e["title"],
                                "summary": e.get("summary"), "body": e.get("body"), "structured": e.get("structured")} for e in entries],
                "core_concepts": [{"source": f"aesthetic_concept:{c['id']}", "name": c["name"], "definition": c["definition"],
                                   "relevance": c["brand_relevance"]} for c in concepts],
            }

    @server.tool(description="Visual identity: approved palettes (HEX/RGB/HSL/OKLCH/CMYK), typography, logo assets, visual-identity rules and design tokens.")
    def get_visual_identity(brand_id: str | None = None) -> dict:
        from app.api.v1.visual_identity import collect_tokens, palettes_payload, to_dtcg, typography_payload
        from app.services import knowledge as ks
        from app.services.assets import load_summaries

        with tenant("get_visual_identity", {"brand_id": brand_id}) as (p, db):
            p.require("knowledge.read")
            b = resolve_brand(p, db, brand_id)
            logos = db.scalars(select(Asset).where(Asset.brand_id == b.id, Asset.deleted_at.is_(None),
                                                   or_(Asset.asset_type == "logo", Asset.category == "logo"))).all()
            return {
                "palettes": palettes_payload(db, b.id, approved_only=True),
                "typography": typography_payload(db, b.id, approved_only=True),
                "rules": [e for e in ks.official_items(db, "knowledge_entry", b.id) if e["domain_key"] == "visual_identity"],
                "principles": [x for x in ks.official_items(db, "principle", b.id) if x.get("domain_key") == "visual_identity"],
                "logos": load_summaries(db, list(logos), p.org_id) if "assets.read" in p.permissions else [],
                "design_tokens": to_dtcg(collect_tokens(db, b.id, approved_only=True)),
            }

    @server.tool(description="Official creative principles (grouped by classification) and guidelines; optionally filter by domain or project type.")
    def get_design_guidelines(brand_id: str | None = None, domain: str | None = None, project_type: str | None = None) -> dict:
        from app.services import knowledge as ks

        with tenant("get_design_guidelines", {"brand_id": brand_id, "domain": domain, "project_type": project_type}) as (p, db):
            p.require("knowledge.read")
            b = resolve_brand(p, db, brand_id)

            def keep(scope_types: list[str], dk: str | None) -> bool:
                return (not domain or dk == domain) and (not project_type or not scope_types or project_type in scope_types)

            principles = [x for x in ks.official_items(db, "principle", b.id) if keep((x.get("scope") or {}).get("project_types", []), x.get("domain_key"))]
            grouped: dict[str, list[dict]] = {}
            for x in sorted(principles, key=lambda x: (x.get("priority", 50), x["code"])):
                grouped.setdefault(x["classification"], []).append(
                    {"source": f"principle:{x['id']}", "code": x["code"], "title": x["title"], "statement": x["statement"],
                     "rationale": x.get("rationale"), "examples": x.get("examples"), "official_version": x.get("official_version")})
            guidelines = [{"source": f"guideline:{g['id']}", "title": g["title"], "domain": g["domain_key"], "summary": g.get("summary"),
                           "body": g.get("body"), "applies_to": g.get("applies_to")}
                          for g in ks.official_items(db, "guideline", b.id) if keep((g.get("applies_to") or {}).get("project_types", []), g["domain_key"])]
            design = [e for e in ks.official_items(db, "knowledge_entry", b.id) if e["domain_key"] == "design_language" and (not domain or domain == "design_language")]
            return {"principles": grouped, "guidelines": guidelines, "design_language": design}

    @server.tool(description="Brand language: tone of voice, vocabulary, preferred/restricted expressions, writing examples and language principles.")
    def get_brand_language(brand_id: str | None = None) -> dict:
        from app.services import knowledge as ks

        with tenant("get_brand_language", {"brand_id": brand_id}) as (p, db):
            p.require("knowledge.read")
            b = resolve_brand(p, db, brand_id)
            return {
                "entries": [e for e in ks.official_items(db, "knowledge_entry", b.id) if e["domain_key"] == "brand_language"],
                "principles": [x for x in ks.official_items(db, "principle", b.id) if x.get("domain_key") == "brand_language"],
            }

    @server.tool(description="Natural-language hybrid search over the brand's assets (e.g. 'videos with slow cinematic camera movement'). approved_only limits to official references.")
    def search_brand_assets(query: str, brand_id: str | None = None, asset_types: list[str] | None = None,
                            approved_only: bool = False, limit: int = 10) -> dict:
        from app.search.engine import SearchRequest, search

        with tenant("search_brand_assets", {"query": query, "brand_id": brand_id}) as (p, db):
            p.require("search.use", "assets.read")
            b = resolve_brand(p, db, brand_id)
            res = search(db, p.org_id, SearchRequest(query=query, brand_id=b.id, entity_types=["asset"], asset_types=asset_types or [],
                                                      scope="official" if approved_only else "all", limit=max(1, min(limit, 50))))
            return {"interpreted": res["interpreted"], "results": [
                {"asset_id": i["id"], "title": i["title"], "knowledge_status": i["knowledge_status"], "score": i["score"],
                 "asset_type": (i.get("asset") or {}).get("asset_type"), "summary": i["snippet"],
                 "dominant_colors": (i.get("asset") or {}).get("dominant_colors"),
                 "preview_url": (i.get("asset") or {}).get("preview_url"), "matched_segments": i.get("matched_segments")}
                for i in res["items"]]}

    @server.tool(description="Search or list the brand's aesthetic ontology (official concepts with definitions, synonyms, related and opposing concepts).")
    def search_aesthetic_concepts(query: str | None = None, brand_id: str | None = None) -> dict:
        from app.search.engine import SearchRequest, search
        from app.services import knowledge as ks

        with tenant("search_aesthetic_concepts", {"query": query, "brand_id": brand_id}) as (p, db):
            p.require("knowledge.read")
            b = resolve_brand(p, db, brand_id)
            if query:
                res = search(db, p.org_id, SearchRequest(query=query, brand_id=b.id, entity_types=["aesthetic_concept"], scope="official", limit=20))
                ids = [uuid.UUID(i["id"]) for i in res["items"]]
            else:
                ids = [uuid.UUID(c["id"]) for c in ks.official_items(db, "aesthetic_concept", b.id)]
            out = []
            for cid in ids:
                c = db.scalar(select(AestheticConcept).where(AestheticConcept.id == cid))
                d = ks.concept_detail(db, c, p.org_id)
                out.append({"source": f"aesthetic_concept:{c.id}", "name": c.name, "definition": c.definition, "synonyms": c.synonyms,
                            "attributes": c.attributes, "relevance": c.brand_relevance, "status": c.status,
                            "related": [r["other_label"] for r in d["related_concepts"]],
                            "opposing": [r["other_label"] for r in d["opposing_concepts"]],
                            "example_asset_ids": [a["id"] for a in d["example_assets"]]})
            return {"concepts": out}

    @server.tool(description="Full details of one asset: technical metadata, accepted/pending AI interpretation, tags, segments (scenes/pages), relationships.")
    def get_asset_details(asset_id: str) -> dict:
        from app.services.assets import asset_detail

        with tenant("get_asset_details", {"asset_id": asset_id}) as (p, db):
            p.require("assets.read")
            a = db.scalar(select(Asset).where(Asset.id == uuid.UUID(asset_id), Asset.deleted_at.is_(None)))
            if a is None or (p.brand_restriction and a.brand_id != p.brand_restriction):
                raise McpAccessError("asset not found")
            d = asset_detail(db, a, p.org_id)
            for x in d["analyses"]:
                x["note"] = "official interpretation" if x["status"] == "approved" else "UNREVIEWED AI interpretation"
            d.pop("derivatives", None)
            return d

    @server.tool(description="Assets related to an asset (visual or semantic similarity), or to a concept/principle via the knowledge graph.")
    def find_related_assets(asset_id: str | None = None, concept_id: str | None = None, principle_id: str | None = None,
                            modality: str = "visual", limit: int = 10) -> dict:
        from app.search.engine import related_entities, similar_to_asset

        with tenant("find_related_assets", {"asset_id": asset_id, "concept_id": concept_id, "principle_id": principle_id}) as (p, db):
            p.require("assets.read", "search.use")
            if asset_id:
                a = db.scalar(select(Asset).where(Asset.id == uuid.UUID(asset_id)))
                if a is None or (p.brand_restriction and a.brand_id != p.brand_restriction):
                    raise McpAccessError("asset not found")
                items = similar_to_asset(db, p.org_id, a, "text" if modality == "text" else "visual", max(1, min(limit, 50)))
                return {"mode": f"{modality} similarity", "results": [{"asset_id": i["id"], "title": i["title"], "score": i["score"],
                                                                       "knowledge_status": i.get("knowledge_status")} for i in items]}
            etype, eid = ("aesthetic_concept", concept_id) if concept_id else ("principle", principle_id)
            if not eid:
                raise McpAccessError("pass asset_id, concept_id or principle_id")
            rel = related_entities(db, etype, uuid.UUID(eid), depth=2)
            return {"mode": "knowledge graph", "results": [r for r in rel if r["entity_type"] == "asset"][:limit]}

    @server.tool(description="Approved colour palettes with all colour spaces and a WCAG contrast matrix.")
    def get_color_palette(brand_id: str | None = None) -> dict:
        from app.api.v1.visual_identity import palettes_payload
        from app.knowledge.colors import contrast_matrix

        with tenant("get_color_palette", {"brand_id": brand_id}) as (p, db):
            p.require("knowledge.read")
            b = resolve_brand(p, db, brand_id)
            pals = palettes_payload(db, b.id, approved_only=True)
            flat = [{"name": c["name"], "hex": c["hex"]} for x in pals for c in x["colors"]]
            return {"palettes": pals, "accessibility": contrast_matrix(flat)[:60]}

    @server.tool(description="Approved typography systems with hierarchy, and the typographic design tokens.")
    def get_typography_system(brand_id: str | None = None) -> dict:
        from app.api.v1.visual_identity import collect_tokens, typography_payload

        with tenant("get_typography_system", {"brand_id": brand_id}) as (p, db):
            p.require("knowledge.read")
            b = resolve_brand(p, db, brand_id)
            toks = [t for t in collect_tokens(db, b.id, approved_only=True) if t["type"] in ("fontFamily", "typography", "fontWeight")]
            return {"typography": typography_payload(db, b.id, approved_only=True), "tokens": toks}

    @server.tool(description="Generate a task-specific brand context package (not saved). task_type: website_design, website_development, "
                             "social_media, brand_campaign, graphic_design, product_design, image_generation, video_generation, presentation, "
                             "copywriting, other. mode: compact|standard|comprehensive. format: markdown|json.")
    def generate_brand_context(task_type: str, brand_id: str | None = None, mode: str = "standard", creative_direction: str | None = None,
                               output_medium: str | None = None, concept_ids: list[str] | None = None, project_id: str | None = None,
                               format: str = "markdown") -> dict:
        from app.ai.prompts import get_prompt
        from app.context.generator import ContextRequest, build_package
        from app.context.templates import TEMPLATES

        with tenant("generate_brand_context", {"task_type": task_type, "brand_id": brand_id, "mode": mode}) as (p, db):
            p.require("knowledge.read", "assets.read")
            b = resolve_brand(p, db, brand_id)
            tpl = get_prompt(db, "context_task_preamble")
            pre = tpl.render(task_label=TEMPLATES.get(task_type, TEMPLATES["other"])["label"], output_medium=output_medium or "unspecified medium")
            try:
                out = build_package(db, p.org_id, ContextRequest(
                    brand_id=b.id, task_type=task_type, mode=mode, creative_direction=creative_direction, output_medium=output_medium,
                    concept_ids=[uuid.UUID(c) for c in concept_ids or []], project_id=uuid.UUID(project_id) if project_id else None),
                    pre, {"key": tpl.key, "version": tpl.version})
            except ApiError as e:
                raise McpAccessError(f"{e.message} {json.dumps(e.details) if e.details else ''}") from e
            body = out["markdown"] if format == "markdown" else out["content"]
            return {"checksum": out["checksum"], "token_estimate": out["token_estimate"], "format": format, "context": body,
                    "sources": out["sources"]}

    # --- Resources ---------------------------------------------------------------------------
    @server.resource("brand://{brand_id}/identity", mime_type="application/json", description="Brand identity (official)")
    def identity_resource(brand_id: str) -> str:
        return json.dumps(get_brand_identity(brand_id), default=str)

    @server.resource("brand://{brand_id}/guidelines", mime_type="application/json", description="Official principles and guidelines")
    def guidelines_resource(brand_id: str) -> str:
        return json.dumps(get_design_guidelines(brand_id), default=str)

    @server.resource("brand://{brand_id}/visual-identity", mime_type="application/json", description="Palettes, typography, tokens")
    def visual_resource(brand_id: str) -> str:
        return json.dumps(get_visual_identity(brand_id), default=str)

    @server.resource("brand://{brand_id}/language", mime_type="application/json", description="Brand language")
    def language_resource(brand_id: str) -> str:
        return json.dumps(get_brand_language(brand_id), default=str)

    @server.resource("brand://{brand_id}/tokens.css", mime_type="text/css", description="Approved design tokens as CSS custom properties")
    def tokens_resource(brand_id: str) -> str:
        from app.api.v1.visual_identity import collect_tokens, to_css

        with tenant("tokens.css", {"brand_id": brand_id}) as (p, db):
            p.require("knowledge.read")
            b = resolve_brand(p, db, brand_id)
            return to_css(collect_tokens(db, b.id, approved_only=True))

    _ = KnowledgeEntry
    return server
