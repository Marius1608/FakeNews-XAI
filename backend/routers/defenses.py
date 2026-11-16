"""Router — GET/PUT /defenses: status and demo toggle of the security defences (report ch. 5).

Reading is always allowed. Changing the switches over the API is a demo feature and is
refused unless DEMO_MODE=true is set in the environment: the API has no authentication,
so a public deployment must not let anyone turn the defences off.
"""

from __future__ import annotations

import os
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend import defense_config

router = APIRouter(tags=["defenses"])


class DefensesUpdate(BaseModel):
    cross_pipeline: Optional[bool] = None
    prompt_hardening: Optional[bool] = None
    trust_tiers: Optional[bool] = None
    title_isolation: Optional[bool] = None
    api_hardening: Optional[bool] = None


def _demo_mode() -> bool:
    return os.getenv("DEMO_MODE", "false").strip().lower() in {"1", "true", "yes", "on"}


@router.get("/defenses")
async def get_defenses() -> dict:
    return {"defenses": defense_config.snapshot(), "toggle_enabled": _demo_mode()}


@router.put("/defenses")
async def put_defenses(req: DefensesUpdate) -> dict:
    if not _demo_mode():
        raise HTTPException(status_code=403, detail="Changing defences over the API requires DEMO_MODE=true.")
    updates = {k: v for k, v in req.model_dump().items() if v is not None}
    if updates:
        defense_config.set_flags(**updates)
    return {"defenses": defense_config.snapshot(), "toggle_enabled": True}
