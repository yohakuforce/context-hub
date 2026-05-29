"""Shared API response envelope schemas.

All responses use the consistent envelope from 02-api-spec.md:
  { "success": bool, "data": ..., "error": ... }
"""

from __future__ import annotations

from typing import Any, Generic, Optional, TypeVar

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

T = TypeVar("T")


class CamelModel(BaseModel):
    """Base for all wire-facing schemas.

    Serializes fields as camelCase (per 02-api-spec.md) while still accepting
    snake_case on input. The contract on the wire is camelCase; consumers
    (AI-Project-Manager, @yohakuforce/core) depend on this.
    """

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class ApiResponse(BaseModel, Generic[T]):
    """Standard API response envelope."""

    success: bool
    data: Optional[T] = None
    error: Optional["ApiError"] = None

    @classmethod
    def ok(cls, data: T) -> "ApiResponse[T]":
        return cls(success=True, data=data, error=None)

    @classmethod
    def fail(cls, code: str, message: str, details: dict[str, Any] | None = None) -> "ApiResponse[None]":
        return cls(
            success=False,
            data=None,
            error=ApiError(code=code, message=message, details=details or {}),
        )


class ApiError(BaseModel):
    code: str
    message: str
    details: dict[str, Any] = {}


class PaginatedMeta(BaseModel):
    total: int
    limit: int
    offset: int
