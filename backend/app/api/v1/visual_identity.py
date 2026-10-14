"""Visual identity & design language data: palettes, color tokens, typography, design tokens,
plus machine-readable exports (W3C DTCG JSON, CSS custom properties, Tailwind theme)."""
from __future__ import annotations

import json
import re
import uuid
from typing import Any

from fastapi import APIRouter, Query
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.common import row_to_dict
from app.api.deps import TenantDep
from app.api.errors import Conflict, NotFound, ValidationFailed
from app.api.v1.brands import get_brand_or_404
from app.knowledge import colors as colormath
from app.models import ColorToken, DesignToken, Palette, TypographySystem

router = APIRouter(tags=["visual identity"])
STATUS_RX = "^(draft|in_review|approved|deprecated|rejected|archived)$"


# --- Payload helpers (also used by domain view / context / MCP) -------------------------------
def palettes_payload(db: Session, brand_id: uuid.UUID, approved_only: bool = False) -> list[dict[str, Any]]:
    q = select(Palette).where(Palette.brand_id == brand_id)
    if approved_only:
        q = q.where(Palette.status == "approved")
    out = []
    for p in db.scalars(q.order_by(Palette.sort_order, Palette.name)):
        d = row_to_dict(p)
        d["colors"] = [row_to_dict(c) for c in db.scalars(select(ColorToken).where(ColorToken.palette_id == p.id).order_by(ColorToken.sort_order))]
        out.append(d)
    return out


def typography_payload(db: Session, brand_id: uuid.UUID, approved_only: bool = False) -> list[dict[str, Any]]:
    q = select(TypographySystem).where(TypographySystem.brand_id == brand_id)
    if approved_only:
        q = q.where(TypographySystem.status == "approved")
    return [row_to_dict(t) for t in db.scalars(q.order_by(TypographySystem.sort_order))]


# --- Palettes & colors --------------------------------------------------------------------------
class PaletteIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    role: str = Field(pattern="^(primary|secondary|accent|neutral|semantic|extended)$")
    description: str | None = None
    status: str = Field("draft", pattern=STATUS_RX)
    sort_order: int = 0


class ColorIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    hex: str
    token_key: str | None = Field(None, max_length=160)
    pantone: str | None = None
    cmyk: dict[str, float] | None = Field(None, description="Manual CMYK (overrides the approximate conversion)")
    semantic_role: str | None = None
    usage: str | None = None
    sort_order: int = 0


def _palette(tenant, palette_id: uuid.UUID) -> Palette:  # noqa: ANN001
    p = tenant.db.scalar(select(Palette).where(Palette.id == palette_id))
    if p is None:
        raise NotFound("Palette not found")
    tenant.check_brand(p.brand_id)
    return p


def _require_status_perm(tenant, status: str | None) -> None:  # noqa: ANN001
    if status == "approved":
        tenant.require("knowledge.approve")


@router.get("/brands/{brand_id}/palettes")
def list_palettes(brand_id: uuid.UUID, tenant: TenantDep) -> dict:
    tenant.require("knowledge.read")
    get_brand_or_404(tenant, brand_id)
    pals = palettes_payload(tenant.db, brand_id)
    flat = [{"name": c["name"], "hex": c["hex"]} for p in pals for c in p["colors"]]
    return {"items": pals, "accessibility": colormath.contrast_matrix(flat)[:200]}


@router.get("/palettes", summary="List palettes (brand_id query param)")
def flat_palettes(brand_id: uuid.UUID, tenant: TenantDep) -> dict:
    return list_palettes(brand_id, tenant)


@router.post("/brands/{brand_id}/palettes", status_code=201)
def create_palette(brand_id: uuid.UUID, body: PaletteIn, tenant: TenantDep) -> dict:
    tenant.require("knowledge.write")
    _require_status_perm(tenant, body.status)
    get_brand_or_404(tenant, brand_id)
    p = Palette(organization_id=tenant.org_id, brand_id=brand_id, **body.model_dump())
    tenant.db.add(p)
    tenant.db.flush()
    tenant.audit("palette.created", "palette", p.id, {"name": p.name})
    return {**row_to_dict(p), "colors": []}


@router.patch("/palettes/{palette_id}")
def update_palette(palette_id: uuid.UUID, body: dict[str, Any], tenant: TenantDep) -> dict:
    tenant.require("knowledge.write")
    p = _palette(tenant, palette_id)
    data = PaletteIn.model_validate({**row_to_dict(p), **body}).model_dump()
    _require_status_perm(tenant, body.get("status"))
    for k in body:
        if k in data:
            setattr(p, k, data[k])
    tenant.audit("palette.updated", "palette", p.id, {"fields": sorted(body)})
    tenant.db.flush()
    return next(x for x in palettes_payload(tenant.db, p.brand_id) if x["id"] == str(p.id))


@router.delete("/palettes/{palette_id}", status_code=204)
def delete_palette(palette_id: uuid.UUID, tenant: TenantDep) -> None:
    tenant.require("knowledge.write")
    p = _palette(tenant, palette_id)
    if p.status == "approved":
        raise ValidationFailed("Approved palettes cannot be deleted; archive them instead")
    tenant.db.delete(p)


def _color_fields(body: ColorIn, palette: Palette) -> dict[str, Any]:
    try:
        info = colormath.describe(body.hex)
    except ValueError as e:
        raise ValidationFailed(str(e)) from e
    key = body.token_key or f"color.{palette.role}.{re.sub(r'[^a-z0-9]+', '-', body.name.lower()).strip('-')}"
    return {
        "name": body.name, "hex": info["hex"], "token_key": key, "rgb": info["rgb"], "hsl": info["hsl"], "oklch": info["oklch"],
        "cmyk": {**body.cmyk, "approximate": False} if body.cmyk else info["cmyk"], "cmyk_is_manual": bool(body.cmyk),
        "pantone": body.pantone, "semantic_role": body.semantic_role, "usage": body.usage, "sort_order": body.sort_order,
    }


@router.post("/palettes/{palette_id}/colors", status_code=201)
def add_color(palette_id: uuid.UUID, body: ColorIn, tenant: TenantDep) -> dict:
    tenant.require("knowledge.write")
    p = _palette(tenant, palette_id)
    fields = _color_fields(body, p)
    if tenant.db.scalar(select(ColorToken.id).where(ColorToken.brand_id == p.brand_id, ColorToken.token_key == fields["token_key"])):
        raise Conflict(f"Token key {fields['token_key']} already exists")
    c = ColorToken(organization_id=tenant.org_id, brand_id=p.brand_id, palette_id=p.id, **fields)
    tenant.db.add(c)
    tenant.db.flush()
    tenant.audit("color.created", "color_token", c.id, {"hex": c.hex})
    return row_to_dict(c)


@router.patch("/colors/{color_id}")
def update_color(color_id: uuid.UUID, body: dict[str, Any], tenant: TenantDep) -> dict:
    tenant.require("knowledge.write")
    c = tenant.db.scalar(select(ColorToken).where(ColorToken.id == color_id))
    if c is None:
        raise NotFound("Color not found")
    tenant.check_brand(c.brand_id)
    p = _palette(tenant, c.palette_id)
    current = {"name": c.name, "hex": c.hex, "token_key": c.token_key, "pantone": c.pantone, "semantic_role": c.semantic_role,
               "usage": c.usage, "sort_order": c.sort_order, "cmyk": {k: v for k, v in c.cmyk.items() if k != "approximate"} if c.cmyk_is_manual else None}
    fields = _color_fields(ColorIn.model_validate({**current, **body}), p)
    for k, v in fields.items():
        setattr(c, k, v)
    return row_to_dict(c)


@router.delete("/colors/{color_id}", status_code=204)
def delete_color(color_id: uuid.UUID, tenant: TenantDep) -> None:
    tenant.require("knowledge.write")
    c = tenant.db.scalar(select(ColorToken).where(ColorToken.id == color_id))
    if c is None:
        raise NotFound("Color not found")
    tenant.check_brand(c.brand_id)
    tenant.db.delete(c)


@router.get("/colors/convert")
def convert_color(hex: str, tenant: TenantDep, against: list[str] | None = Query(None)) -> dict:
    tenant.require("knowledge.read")
    try:
        out = colormath.describe(hex)
        out["contrast"] = [{"against": colormath.normalize_hex(a), "ratio": (r := colormath.contrast_ratio(hex, a)), **colormath.wcag(r)} for a in against or []]
    except ValueError as e:
        raise ValidationFailed(str(e)) from e
    return out


# --- Typography --------------------------------------------------------------------------------
class TypeLevel(BaseModel):
    level: str
    size_px: float = Field(gt=0, le=400)
    line_height: float = Field(gt=0, le=4)
    weight: int = Field(400, ge=100, le=1000)
    letter_spacing_em: float = 0
    text_transform: str | None = None
    usage: str | None = None


class TypographyIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    role: str = Field(pattern="^(primary|secondary|display|body|mono|accent)$")
    family: str = Field(min_length=1, max_length=200)
    fallback_stack: str = "sans-serif"
    source: str | None = None
    source_url: str | None = None
    license: str | None = None
    weights: list[int] = Field(default_factory=lambda: [400, 700])
    supports_italic: bool = False
    hierarchy: list[TypeLevel] = Field(default_factory=list)
    usage: str | None = None
    status: str = Field("draft", pattern=STATUS_RX)
    sort_order: int = 0


@router.get("/brands/{brand_id}/typography")
def list_typography(brand_id: uuid.UUID, tenant: TenantDep) -> dict:
    tenant.require("knowledge.read")
    get_brand_or_404(tenant, brand_id)
    return {"items": typography_payload(tenant.db, brand_id)}


@router.get("/typography", summary="List typography systems (brand_id query param)")
def flat_typography(brand_id: uuid.UUID, tenant: TenantDep) -> dict:
    return list_typography(brand_id, tenant)


@router.post("/brands/{brand_id}/typography", status_code=201)
def create_typography(brand_id: uuid.UUID, body: TypographyIn, tenant: TenantDep) -> dict:
    tenant.require("knowledge.write")
    _require_status_perm(tenant, body.status)
    get_brand_or_404(tenant, brand_id)
    t = TypographySystem(organization_id=tenant.org_id, brand_id=brand_id, **body.model_dump(mode="json"))
    tenant.db.add(t)
    tenant.db.flush()
    tenant.audit("typography.created", "typography_system", t.id, {"family": t.family})
    return row_to_dict(t)


@router.patch("/typography/{type_id}")
def update_typography(type_id: uuid.UUID, body: dict[str, Any], tenant: TenantDep) -> dict:
    tenant.require("knowledge.write")
    t = tenant.db.scalar(select(TypographySystem).where(TypographySystem.id == type_id))
    if t is None:
        raise NotFound("Typography system not found")
    tenant.check_brand(t.brand_id)
    _require_status_perm(tenant, body.get("status"))
    data = TypographyIn.model_validate({**row_to_dict(t), **body}).model_dump(mode="json")
    for k in body:
        if k in data:
            setattr(t, k, data[k])
    return row_to_dict(t)


@router.delete("/typography/{type_id}", status_code=204)
def delete_typography(type_id: uuid.UUID, tenant: TenantDep) -> None:
    tenant.require("knowledge.write")
    t = tenant.db.scalar(select(TypographySystem).where(TypographySystem.id == type_id))
    if t is None:
        raise NotFound("Typography system not found")
    tenant.check_brand(t.brand_id)
    tenant.db.delete(t)


# --- Design tokens -------------------------------------------------------------------------------
TOKEN_TYPES = ("color", "dimension", "fontFamily", "fontWeight", "duration", "cubicBezier", "number", "shadow", "border",
               "typography", "gradient", "strokeStyle", "transition")


class TokenIn(BaseModel):
    path: str = Field(pattern=r"^[a-zA-Z0-9_-]+(\.[a-zA-Z0-9_-]+)*$", max_length=200)
    token_type: str
    value: Any
    description: str | None = None
    category: str = Field(min_length=1, max_length=64)
    domain_key: str = Field("design_language", pattern="^(visual_identity|design_language)$")
    status: str = Field("draft", pattern=STATUS_RX)
    sort_order: int = 0


@router.get("/brands/{brand_id}/design-tokens")
def list_tokens(brand_id: uuid.UUID, tenant: TenantDep, category: str | None = None) -> dict:
    tenant.require("knowledge.read")
    get_brand_or_404(tenant, brand_id)
    q = select(DesignToken).where(DesignToken.brand_id == brand_id)
    if category:
        q = q.where(DesignToken.category == category)
    return {"items": [row_to_dict(t) for t in tenant.db.scalars(q.order_by(DesignToken.category, DesignToken.sort_order, DesignToken.path))]}


@router.post("/brands/{brand_id}/design-tokens", status_code=201)
def create_token(brand_id: uuid.UUID, body: TokenIn, tenant: TenantDep) -> dict:
    tenant.require("knowledge.write")
    _require_status_perm(tenant, body.status)
    get_brand_or_404(tenant, brand_id)
    if body.token_type not in TOKEN_TYPES:
        raise ValidationFailed("Unknown token type", details={"allowed": TOKEN_TYPES})
    if tenant.db.scalar(select(DesignToken.id).where(DesignToken.brand_id == brand_id, DesignToken.path == body.path)):
        raise Conflict(f"Token {body.path} already exists")
    t = DesignToken(organization_id=tenant.org_id, brand_id=brand_id, **body.model_dump())
    tenant.db.add(t)
    tenant.db.flush()
    return row_to_dict(t)


@router.patch("/design-tokens/{token_id}")
def update_token(token_id: uuid.UUID, body: dict[str, Any], tenant: TenantDep) -> dict:
    tenant.require("knowledge.write")
    t = tenant.db.scalar(select(DesignToken).where(DesignToken.id == token_id))
    if t is None:
        raise NotFound("Token not found")
    tenant.check_brand(t.brand_id)
    _require_status_perm(tenant, body.get("status"))
    data = TokenIn.model_validate({**row_to_dict(t), **body}).model_dump()
    for k in body:
        if k in data:
            setattr(t, k, data[k])
    return row_to_dict(t)


@router.delete("/design-tokens/{token_id}", status_code=204)
def delete_token(token_id: uuid.UUID, tenant: TenantDep) -> None:
    tenant.require("knowledge.write")
    t = tenant.db.scalar(select(DesignToken).where(DesignToken.id == token_id))
    if t is None:
        raise NotFound("Token not found")
    tenant.check_brand(t.brand_id)
    tenant.db.delete(t)


def _num(x: Any) -> str:
    return str(int(x)) if isinstance(x, float) and x.is_integer() else str(x)


def collect_tokens(db: Session, brand_id: uuid.UUID, approved_only: bool) -> list[dict[str, Any]]:
    """All tokens (design tokens + palette colors + typography) as flat DTCG-style records."""
    out: list[dict[str, Any]] = []
    for p in palettes_payload(db, brand_id, approved_only):
        for c in p["colors"]:
            out.append({"path": c["token_key"], "type": "color", "value": c["hex"],
                        "description": c.get("usage") or c["name"], "extensions": {"oklch": c["oklch"]["css"], "cmyk": c["cmyk"]}})
    for t in typography_payload(db, brand_id, approved_only):
        slug = re.sub(r"[^a-z0-9]+", "-", t["role"].lower())
        out.append({"path": f"font.family.{slug}", "type": "fontFamily", "value": [t["family"], *[f.strip() for f in t["fallback_stack"].split(",")]],
                    "description": t["name"]})
        for lvl in t["hierarchy"]:
            lv = re.sub(r"[^a-z0-9]+", "-", str(lvl["level"]).lower())
            out.append({"path": f"typography.{lv}", "type": "typography", "value": {
                "fontFamily": f"{{font.family.{slug}}}", "fontSize": f"{_num(lvl['size_px'])}px", "lineHeight": lvl["line_height"],
                "fontWeight": lvl["weight"], "letterSpacing": f"{_num(lvl.get('letter_spacing_em', 0))}em"}, "description": lvl.get("usage")})
    q = select(DesignToken).where(DesignToken.brand_id == brand_id)
    if approved_only:
        q = q.where(DesignToken.status == "approved")
    for t in db.scalars(q.order_by(DesignToken.path)):
        out.append({"path": t.path, "type": t.token_type, "value": t.value, "description": t.description})
    return out


def to_dtcg(tokens: list[dict[str, Any]]) -> dict[str, Any]:
    root: dict[str, Any] = {}
    for t in tokens:
        node = root
        parts = t["path"].split(".")
        for part in parts[:-1]:
            node = node.setdefault(part, {})
        leaf = {"$type": t["type"], "$value": t["value"]}
        if t.get("description"):
            leaf["$description"] = t["description"]
        if t.get("extensions"):
            leaf["$extensions"] = {"com.branddna": t["extensions"]}
        node[parts[-1]] = leaf
    return root


def _css_value(v: Any) -> str | None:
    if isinstance(v, list):
        return ", ".join(f'"{x}"' if " " in str(x) and not str(x).startswith('"') else str(x) for x in v)
    if isinstance(v, dict) and "duration" in v:
        return str(v["duration"])
    if isinstance(v, int | float | str):
        return str(v)
    if isinstance(v, list | tuple) and len(v) == 4:
        return f"cubic-bezier({', '.join(map(str, v))})"
    return None


def to_css(tokens: list[dict[str, Any]], selector: str = ":root") -> str:
    lines = ["/* Generated by Brand DNA platform — do not edit by hand */", f"{selector} {{"]
    for t in tokens:
        name = "--" + t["path"].replace(".", "-")
        if t["type"] == "typography":
            for k, v in t["value"].items():
                if k == "fontFamily":
                    v = f"var(--{v.strip('{}').replace('.', '-')})"
                lines.append(f"  {name}-{re.sub(r'([A-Z])', r'-\1', k).lower()}: {v};")
            continue
        if t["type"] == "cubicBezier" and isinstance(t["value"], list):
            lines.append(f"  {name}: cubic-bezier({', '.join(map(str, t['value']))});")
            continue
        v = _css_value(t["value"])
        if v is not None:
            lines.append(f"  {name}: {v};")
    lines.append("}")
    return "\n".join(lines) + "\n"


def to_tailwind(tokens: list[dict[str, Any]]) -> dict[str, Any]:
    theme: dict[str, Any] = {"colors": {}, "fontFamily": {}, "spacing": {}, "borderRadius": {}, "fontSize": {}, "transitionDuration": {}}
    for t in tokens:
        parts = t["path"].split(".")
        if t["type"] == "color":
            node = theme["colors"]
            for p in parts[1:-1]:
                node = node.setdefault(p, {})
            node[parts[-1]] = t["value"]
        elif t["type"] == "fontFamily":
            theme["fontFamily"][parts[-1]] = t["value"]
        elif t["type"] == "dimension" and parts[0] in ("spacing", "space"):
            theme["spacing"][parts[-1]] = t["value"]
        elif t["type"] == "dimension" and parts[0] in ("radius", "radii", "borderRadius"):
            theme["borderRadius"][parts[-1]] = t["value"]
        elif t["type"] == "typography":
            theme["fontSize"][parts[-1]] = [t["value"]["fontSize"], {"lineHeight": str(t["value"]["lineHeight"]), "fontWeight": str(t["value"]["fontWeight"])}]
        elif t["type"] == "duration":
            theme["transitionDuration"][parts[-1]] = t["value"]
    return {"theme": {"extend": {k: v for k, v in theme.items() if v}}}


@router.get("/brands/{brand_id}/design-tokens/export")
def export_tokens(
    brand_id: uuid.UUID,
    tenant: TenantDep,
    format: str = Query("dtcg", pattern="^(dtcg|css|tailwind|flat)$"),
    include_drafts: bool = False,
):
    """Developer / design-tool exports. Default: approved tokens only."""
    tenant.require("knowledge.read")
    get_brand_or_404(tenant, brand_id)
    tokens = collect_tokens(tenant.db, brand_id, approved_only=not include_drafts)
    if format == "css":
        return PlainTextResponse(to_css(tokens), media_type="text/css")
    if format == "tailwind":
        return PlainTextResponse("/** @type {import('tailwindcss').Config} */\nmodule.exports = " + json.dumps(to_tailwind(tokens), indent=2) + ";\n",
                                 media_type="application/javascript")
    if format == "flat":
        return {"tokens": tokens}
    return to_dtcg(tokens)
