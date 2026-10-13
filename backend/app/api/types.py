"""Reusable validated field types."""
from __future__ import annotations

import re
from typing import Annotated

from pydantic import AfterValidator

_EMAIL = re.compile(r"^[^@\s]{1,64}@[^@\s]+\.[^@\s]{2,}$")


def _email(v: str) -> str:
    v = v.strip()
    if len(v) > 320 or not _EMAIL.match(v):
        raise ValueError("invalid email address")
    return v.lower()


# Syntactic validation only (no DNS / special-use TLD checks) so customer domains of any kind work.
Email = Annotated[str, AfterValidator(_email)]
