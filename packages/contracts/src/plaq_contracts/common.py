"""Common helpers, ID generation, timestamp utilities, and base models."""

from __future__ import annotations

from datetime import datetime, timezone
import uuid
from typing import Any, Generic, List, Optional, TypeVar
from pydantic import BaseModel, ConfigDict, Field


def generate_id(prefix: Optional[str] = None) -> str:
    """Generate a random UUID4 string, optionally with a prefix."""
    raw = str(uuid.uuid4())
    return f"{prefix}_{raw}" if prefix else raw


def utc_now() -> datetime:
    """Return timezone-aware current UTC datetime."""
    return datetime.now(timezone.utc)


def utc_now_iso() -> str:
    """Return ISO-8601 string of current UTC datetime."""
    return utc_now().isoformat()


class PlaqBaseModel(BaseModel):
    """Base Pydantic v2 model for all Plaq-OS contracts with standard configuration."""

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        validate_assignment=True,
        use_enum_values=True,
    )


T = TypeVar("T")


class PaginationParams(PlaqBaseModel):
    """Standard pagination query parameters."""

    page: int = Field(default=1, ge=1, description="Page number (1-indexed)")
    page_size: int = Field(default=50, ge=1, le=1000, description="Items per page")


class PaginatedResponse(PlaqBaseModel, Generic[T]):
    """Standard paginated container response."""

    items: List[T] = Field(default_factory=list)
    total: int = Field(ge=0, description="Total count of items across all pages")
    page: int = Field(ge=1, description="Current page number")
    page_size: int = Field(ge=1, description="Current page size")
    total_pages: int = Field(ge=0, description="Total number of pages")
    has_more: bool = Field(description="Whether subsequent pages are available")


class SuccessResponse(PlaqBaseModel):
    """Standard success acknowledgement response."""

    success: bool = True
    message: Optional[str] = None
    data: Optional[Any] = None


class ErrorResponse(PlaqBaseModel):
    """Standard structured error response."""

    error: str = Field(..., description="High-level error classification")
    detail: Optional[str] = Field(default=None, description="Detailed error explanation")
    code: Optional[str] = Field(default=None, description="Machine-readable error code")
