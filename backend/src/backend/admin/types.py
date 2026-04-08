from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class AdminPrincipal:
    actor: str
    role: str
