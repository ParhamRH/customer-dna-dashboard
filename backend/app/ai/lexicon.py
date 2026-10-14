"""Small aesthetic lexicon used ONLY by the development adapters.

It lets the offline embedding model place "biomorphic", "curvilinear" and "organic" near each
other, and lets the heuristic vision adapter phrase measurements in art-direction vocabulary.
Production providers (real embedding / vision models) do not use it.
"""
from __future__ import annotations

import re

FAMILIES: dict[str, list[str]] = {
    "organic": ["organic", "biomorphic", "curved", "curvilinear", "flowing", "fluid", "natural", "undulating",
                "rounded", "botanical", "wave", "soft-edged", "sinuous", "nature"],
    "geometric": ["geometric", "geometry", "angular", "rectilinear", "orthogonal", "modular", "linear", "precise",
                  "grid", "structured", "symmetrical", "symmetry"],
    "minimal": ["minimal", "minimalist", "minimalism", "sparse", "clean", "reduced", "restrained", "quiet",
                "whitespace", "negative space", "uncluttered", "simple", "calm", "essential"],
    "sculptural": ["sculptural", "sculpture", "volumetric", "monolithic", "carved", "plastic form", "mass", "object"],
    "architectural": ["architectural", "architecture", "structural", "building", "facade", "column", "spatial",
                      "space", "interior", "construction"],
    "material": ["material", "materiality", "tactile", "texture", "textured", "grain", "stone", "wood", "metal",
                 "linen", "ceramic", "raw", "matte", "surface", "concrete", "paper", "fabric"],
    "cinematic": ["cinematic", "filmic", "film", "moody", "dramatic", "atmospheric", "chiaroscuro", "anamorphic",
                  "widescreen", "narrative", "storytelling"],
    "brutalist": ["brutalist", "brutalism", "monumental", "heavy", "blocky", "harsh", "raw concrete"],
    "editorial": ["editorial", "magazine", "typographic", "typography", "layout", "serif", "print", "publication"],
    "industrial": ["industrial", "machined", "steel", "engineered", "utilitarian", "factory", "mechanical", "technical"],
    "elegant": ["elegant", "elegance", "refined", "luxurious", "luxury", "sophisticated", "graceful", "premium", "poised"],
    "bright": ["bright", "airy", "luminous", "high-key", "sunlit", "light-filled", "daylight", "radiant"],
    "dark": ["dark", "low-key", "shadow", "shadows", "nocturnal", "night", "deep", "dim"],
    "muted": ["muted", "desaturated", "subdued", "pastel", "earthy", "neutral", "tonal", "understated", "soft palette"],
    "vibrant": ["vibrant", "saturated", "bold", "vivid", "punchy", "colorful", "colourful", "energetic color"],
    "warm": ["warm", "golden", "amber", "terracotta", "sunset", "ochre", "honey"],
    "cool": ["cool", "blue", "icy", "cold", "steel blue", "teal", "nordic"],
    "slow_motion": ["slow", "contemplative", "lingering", "long take", "gentle", "drift", "drifting", "unhurried"],
    "fast_motion": ["fast", "rapid", "kinetic", "dynamic", "rapid-cut", "frenetic", "quick"],
    "experimental_type": ["experimental typography", "expressive type", "distorted type", "kinetic type", "variable font"],
    "playful": ["playful", "whimsical", "fun", "joyful", "quirky", "humorous"],
    "human": ["human", "people", "portrait", "candid", "authentic", "documentary", "lifestyle"],
    "contrast_high": ["high contrast", "contrasty", "dramatic lighting", "hard light", "graphic"],
    "contrast_low": ["low contrast", "soft light", "diffused", "hazy", "gentle light", "flat light"],
}

_WORD_TO_FAMILY: dict[str, list[str]] = {}
for fam, words in FAMILIES.items():
    for w in words:
        _WORD_TO_FAMILY.setdefault(w, []).append(fam)
_PHRASES = sorted((w for w in _WORD_TO_FAMILY if " " in w or "-" in w), key=len, reverse=True)
_TOKEN = re.compile(r"[a-z0-9]+(?:[-'][a-z0-9]+)?")


def tokens(text: str) -> list[str]:
    return _TOKEN.findall(text.lower())


def families_in(text: str) -> dict[str, int]:
    low = text.lower()
    found: dict[str, int] = {}
    for ph in _PHRASES:
        if ph in low:
            for fam in _WORD_TO_FAMILY[ph]:
                found[fam] = found.get(fam, 0) + 1
    for t in tokens(low):
        for fam in _WORD_TO_FAMILY.get(t, []):
            found[fam] = found.get(fam, 0) + 1
        # crude stemming for -s / -ly / -ness forms
        for suffix in ("s", "ly", "ness", "ity"):
            if t.endswith(suffix) and t[: -len(suffix)] in _WORD_TO_FAMILY:
                for fam in _WORD_TO_FAMILY[t[: -len(suffix)]]:
                    found[fam] = found.get(fam, 0) + 1
    return found
