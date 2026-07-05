"""Router — GET/PUT/POST/DELETE /config/*: RSS feeds and operational parameters.

Exposes backend.runtime_settings as a REST API so the frontend Settings tab can
read and mutate the RSS feed list and the 15 operational thresholds without
redeploying. No authentication — the app has no user system.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend import runtime_settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/config", tags=["config"])


# Pydantic schemas
class RSSFeedPredefined(BaseModel):
    url: str
    name: str
    enabled: bool


class RSSFeedsResponse(BaseModel):
    predefined: list[RSSFeedPredefined]
    custom: list[str]


class RSSCustomFeedRequest(BaseModel):
    url: str = Field(..., description="http(s) URL of the RSS/Atom feed to add")


class ParameterInfo(BaseModel):
    key: str
    label: str
    group: str
    unit: str
    value: float
    default: float
    min: float
    max: float
    step: float


class ParametersResponse(BaseModel):
    parameters: list[ParameterInfo]


def _rss_feeds_response() -> RSSFeedsResponse:
    data = runtime_settings.get_rss_feeds()
    return RSSFeedsResponse(**data)


def _parameters_response() -> ParametersResponse:
    return ParametersResponse(parameters=runtime_settings.get_parameters())


# RSS feed endpoints
@router.get("/rss-feeds", response_model=RSSFeedsResponse)
async def get_rss_feeds() -> RSSFeedsResponse:
    """Returns the 8 predefined feeds (with enabled flags) and any custom feeds."""
    return _rss_feeds_response()


@router.put("/rss-feeds/predefined", response_model=RSSFeedsResponse)
async def update_predefined_feeds(flags: dict[str, bool]) -> RSSFeedsResponse:
    """Updates the enabled flag of the 8 predefined feeds. Body: {url: enabled, ...} for all 8."""
    try:
        runtime_settings.set_predefined_enabled(flags)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return _rss_feeds_response()


@router.post("/rss-feeds/custom", response_model=RSSFeedsResponse)
async def add_custom_feed(req: RSSCustomFeedRequest) -> RSSFeedsResponse:
    """Adds a custom RSS feed URL."""
    try:
        runtime_settings.add_custom_feed(req.url)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return _rss_feeds_response()


@router.delete("/rss-feeds/custom/{index}", response_model=RSSFeedsResponse)
async def delete_custom_feed(index: int) -> RSSFeedsResponse:
    """Removes a custom feed by its position in the custom feeds list."""
    try:
        runtime_settings.remove_custom_feed(index)
    except IndexError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return _rss_feeds_response()


@router.post("/rss-feeds/reset", response_model=RSSFeedsResponse)
async def reset_rss_feeds() -> RSSFeedsResponse:
    """Re-enables all 8 predefined feeds and clears custom feeds."""
    runtime_settings.reset_rss_feeds()
    return _rss_feeds_response()


# Operational parameter endpoints
@router.get("/parameters", response_model=ParametersResponse)
async def get_parameters() -> ParametersResponse:
    """Returns all 15 operational parameters with current/default/min/max/step."""
    return _parameters_response()


@router.put("/parameters", response_model=ParametersResponse)
async def update_parameters(updates: dict[str, float]) -> ParametersResponse:
    """Partially updates parameters. Body: {key: value, ...}. Rejects values off the min/step grid."""
    try:
        runtime_settings.set_parameters(updates)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return _parameters_response()


@router.post("/parameters/reset", response_model=ParametersResponse)
async def reset_parameters() -> ParametersResponse:
    """Resets all parameters to their default values."""
    runtime_settings.reset_parameters()
    return _parameters_response()
