"""Payloads de los formularios del panel admin."""
from __future__ import annotations

from pydantic import BaseModel, Field


class LoginPayload(BaseModel):
    username: str = Field(min_length=1)
    password: str = Field(min_length=1)


class TemplateUpdatePayload(BaseModel):
    content: str = Field(min_length=1)
