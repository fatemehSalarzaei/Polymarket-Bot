from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


ErrorSeverity = Literal["info", "warning", "error", "critical"]


class ErrorResponse(BaseModel):
    code: str
    title: str
    message: str
    severity: ErrorSeverity = "error"
    source: str = "backend"
    possible_causes: list[str] = Field(default_factory=list)
    recovery_actions: list[str] = Field(default_factory=list)
    technical_detail: str | None = None
    timestamp: datetime
    request_id: str | None = None
