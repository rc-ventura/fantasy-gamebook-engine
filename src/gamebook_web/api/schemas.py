from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator


def _strip_control_chars(value: str | None) -> str | None:
    if value is None:
        return None
    return "".join(c for c in value if c == " " or (ord(c) > 0x20 and ord(c) != 0x7F))


class CreateGameRequest(BaseModel):
    name: str | None = Field(default=None, max_length=100)

    @field_validator("name")
    @classmethod
    def _sanitize_name(cls, v: str | None) -> str | None:
        return _strip_control_chars(v)


class GameResponse(BaseModel):
    status: str
    campaign_id: str
    name: str | None = None


class CreateCharacterRequest(BaseModel):
    name: str = Field(default="Hero", max_length=100)

    @field_validator("name")
    @classmethod
    def _sanitize_name(cls, v: str) -> str:
        return _strip_control_chars(v) or "Hero"


class TurnRequest(BaseModel):
    choice: str | int | None = Field(default=None, max_length=500)


class TurnResponse(BaseModel):
    scene: dict[str, Any]
    status: str
    character: dict[str, Any] | None = None
    world: dict[str, Any] | None = None


class SaveResponse(BaseModel):
    ok: bool
    slot: str | None


class GraveyardEntry(BaseModel):
    campaign_id: str
    status: str = "ended"
    name: str | None = None
    created_at: str | None = None
    ended_at: str | None = None
    ended_reason: str | None = None


