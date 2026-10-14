"""Task templates for the Creative Context Generator."""
from __future__ import annotations

from typing import Any

ALL = ["brand_foundation", "visual_identity", "art_direction", "aesthetic_language", "design_language", "brand_language"]

TEMPLATES: dict[str, dict[str, Any]] = {
    "website_design": {
        "label": "Website design",
        "domains": ["brand_foundation", "visual_identity", "design_language", "art_direction", "aesthetic_language", "brand_language"],
        "project_types": ["website_design", "digital_application"],
        "include_tokens": True,
        "instructions": [
            "Design responsive page layouts that express the brand's aesthetic concepts through composition, not decoration.",
            "Use only the approved palette and typography; map them to the design tokens provided.",
            "Respect the layout, grid, spacing and motion rules of the design language.",
            "Meet WCAG 2.2 AA contrast for all text (see the accessibility notes).",
            "Use the reference assets for art direction of imagery; never reproduce them literally.",
        ],
        "deliverable_checklist": ["Desktop + mobile layouts", "Component inventory", "Imagery direction per section", "Token mapping"],
    },
    "website_development": {
        "label": "Website development",
        "domains": ["visual_identity", "design_language", "brand_language"],
        "project_types": ["website_development", "website_design", "digital_application"],
        "include_tokens": True,
        "include_css": True,
        "instructions": [
            "Implement UI strictly with the CSS custom properties / design tokens provided — no hard-coded colours or font stacks.",
            "Follow the interaction, animation, scroll and responsive behaviour rules.",
            "Use semantic HTML and meet WCAG 2.2 AA.",
            "Copy in components must follow the brand language rules (tone, restricted expressions).",
        ],
        "deliverable_checklist": ["Token usage", "Responsive breakpoints", "Motion durations / easings from tokens", "Accessibility"],
    },
    "social_media": {
        "label": "Social media",
        "domains": ["brand_foundation", "art_direction", "visual_identity", "aesthetic_language", "brand_language"],
        "project_types": ["social_media", "advertising", "branding_campaign"],
        "instructions": [
            "Create platform-native posts that stay unmistakably on-brand at thumbnail size.",
            "Imagery follows the art direction; copy follows tone of voice and restricted expressions.",
            "Prefer the core aesthetic concepts; avoid every prohibited direction.",
        ],
        "deliverable_checklist": ["Format & aspect ratio", "Visual", "Caption", "Alt text"],
    },
    "brand_campaign": {
        "label": "Brand campaign",
        "domains": ALL,
        "project_types": ["branding_campaign", "advertising"],
        "instructions": [
            "Develop a campaign idea rooted in the brand story, promise and positioning.",
            "Express it through the aesthetic concepts and art direction; keep every execution within the mandatory rules.",
        ],
        "deliverable_checklist": ["Campaign idea", "Key visual direction", "Headline system", "Channel executions"],
    },
    "graphic_design": {
        "label": "Graphic design",
        "domains": ["visual_identity", "aesthetic_language", "design_language", "art_direction"],
        "project_types": ["graphic_design", "packaging", "advertising"],
        "include_tokens": True,
        "instructions": [
            "Compose with the brand grid, palette and typographic hierarchy.",
            "Logo usage must follow clear-space and minimum-size rules.",
        ],
        "deliverable_checklist": ["Layout grid", "Type hierarchy", "Colour usage", "Logo placement"],
    },
    "product_design": {
        "label": "Product design",
        "domains": ["brand_foundation", "aesthetic_language", "art_direction", "visual_identity"],
        "project_types": ["product_design", "packaging"],
        "instructions": [
            "Translate the aesthetic concepts into form, material and finish decisions.",
            "Material and texture choices should follow the art direction's material notes.",
        ],
        "deliverable_checklist": ["Form language", "Materials & finishes", "CMF palette"],
    },
    "image_generation": {
        "label": "Image generation",
        "domains": ["art_direction", "aesthetic_language", "visual_identity"],
        "project_types": ["image_generation", "social_media", "advertising"],
        "prompt_ready": True,
        "instructions": [
            "Generate imagery that matches the art direction: lighting, composition, materials, atmosphere.",
            "Use the positive descriptors; never include anything from the negative descriptors.",
            "Colour grading should sit within the approved palette's hues.",
        ],
        "deliverable_checklist": ["Prompt", "Negative prompt", "Aspect ratio", "Reference images"],
    },
    "video_generation": {
        "label": "Video generation",
        "domains": ["art_direction", "aesthetic_language", "visual_identity", "brand_language"],
        "project_types": ["video_production", "social_media"],
        "prompt_ready": True,
        "include_motion": True,
        "instructions": [
            "Match camera movement, pacing and shot length to the motion references.",
            "Lighting, palette and atmosphere follow the art direction; avoid prohibited directions.",
        ],
        "deliverable_checklist": ["Shot list", "Camera movement per shot", "Pacing", "Grade"],
    },
    "presentation": {
        "label": "Presentation",
        "domains": ["brand_foundation", "visual_identity", "design_language", "brand_language"],
        "project_types": ["presentation"],
        "include_tokens": True,
        "instructions": [
            "Slides use the brand typography hierarchy, palette and grid; one idea per slide.",
            "Headlines follow the brand voice.",
        ],
        "deliverable_checklist": ["Title slide", "Section dividers", "Content layouts", "Data slides"],
    },
    "copywriting": {
        "label": "Marketing copywriting",
        "domains": ["brand_foundation", "brand_language"],
        "project_types": ["copywriting", "advertising", "social_media", "branding_campaign"],
        "instructions": [
            "Write in the brand voice; apply tone traits (is / is not) literally.",
            "Never use restricted expressions; prefer the brand vocabulary.",
            "Adapt register to the audience segment named in the brief.",
        ],
        "deliverable_checklist": ["Headline options", "Body copy", "CTA", "Self-check against restricted expressions"],
    },
    "other": {
        "label": "Other creative task",
        "domains": ALL,
        "project_types": [],
        "instructions": ["Apply the brand knowledge below to the task described in the brief."],
        "deliverable_checklist": [],
    },
}

MODE_LIMITS = {
    "compact": {"refs": 3, "concepts": 5, "principles": 12, "guidelines": 3, "entries": 6, "body_chars": 300},
    "standard": {"refs": 6, "concepts": 10, "principles": 40, "guidelines": 10, "entries": 24, "body_chars": 1200},
    "comprehensive": {"refs": 16, "concepts": 50, "principles": 200, "guidelines": 60, "entries": 200, "body_chars": 20000},
}
