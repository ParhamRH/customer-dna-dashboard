"""Idempotent reference-data sync run at API/worker start-up."""
from __future__ import annotations

import logging

log = logging.getLogger("bdna.bootstrap")


def ensure_reference_data() -> None:
    """Sync code-defined reference data (knowledge entry types, default prompt templates)."""
    try:
        from app.knowledge.registry import sync_domain_entry_types

        sync_domain_entry_types()
    except ImportError:  # registry not present yet in early phases
        pass
    try:
        from app.ai.prompts import ensure_default_prompts

        ensure_default_prompts()
    except ImportError:
        pass
