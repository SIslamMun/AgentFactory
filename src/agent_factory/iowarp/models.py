"""Pydantic models for JSON-RPC messages exchanged with the ZeroMQ bridge."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Request / Response envelope
# ---------------------------------------------------------------------------

class BridgeRequest(BaseModel):
    """JSON-RPC-style request sent to the bridge."""

    method: str
    params: dict[str, Any] = Field(default_factory=dict)
    id: int | None = None


class BridgeResponse(BaseModel):
    """JSON-RPC-style response received from the bridge."""

    result: Any | None = None
    error: str | None = None
    id: int | None = None

    @property
    def ok(self) -> bool:
        return self.error is None


# ---------------------------------------------------------------------------
# Typed param / result models for each RPC method
# ---------------------------------------------------------------------------

class BundleParams(BaseModel):
    """Parameters for context_bundle."""

    src: str | list[str]
    dst: str
    format: str = "arrow"


class BundleResult(BaseModel):
    status: str
    tag: str
    stub: bool = False


class QueryParams(BaseModel):
    """Parameters for context_query."""

    tag_pattern: str = "*"
    blob_pattern: str = "*"


class QueryResultModel(BaseModel):
    matches: list[dict[str, Any]] = Field(default_factory=list)
    stub: bool = False


class RetrieveParams(BaseModel):
    """Parameters for context_retrieve."""

    tag: str
    blob_name: str


class RetrieveResultModel(BaseModel):
    data: Any | None = None
    encoding: str | None = None
    stub: bool = False


class DestroyParams(BaseModel):
    """Parameters for context_destroy."""

    tags: str | list[str]


class DestroyResult(BaseModel):
    status: str
    destroyed: list[str] = Field(default_factory=list)
    stub: bool = False
