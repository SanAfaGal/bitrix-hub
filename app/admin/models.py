"""Payloads de los formularios del panel admin."""
from __future__ import annotations

from pydantic import BaseModel, Field


class TemplateUpdatePayload(BaseModel):
    content: str = Field(min_length=1)
