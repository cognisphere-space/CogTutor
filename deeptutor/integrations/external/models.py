"""Wire contracts for the external integration surface.

These shapes are owned by DeepTutor and must stay meaningful for *any* host
product: no field here may encode what a particular embedder's data means.
``ExternalContext.payload`` is deliberately an opaque object — DeepTutor
stores it, may hand it to a prompt when configured to, and echoes back only
its ``context_id``.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


PROTOCOL_VERSION = "1"


class ExternalIdentity(BaseModel):
    """A host-provided identity, normalized to a shape DeepTutor owns.

    ``issuer`` + ``subject`` is the stable key for the local user mapping,
    mirroring OIDC ``iss``/``sub`` without requiring OIDC.
    """

    protocol_version: str = PROTOCOL_VERSION
    issuer: str
    subject: str
    display_name: str | None = None
    scopes: list[str] = Field(default_factory=list)
    expires_at: datetime | None = None

    @property
    def user_key(self) -> str:
        return f"{self.issuer}:{self.subject}"


class ExternalContext(BaseModel):
    """Opaque context handed over by the host product at session start."""

    protocol_version: str = PROTOCOL_VERSION
    context_id: str
    context_type: str
    payload: dict[str, Any] = Field(default_factory=dict)


class ExternalUserRef(BaseModel):
    issuer: str
    subject: str


class ConversationEvent(BaseModel):
    """A conversation *fact* — not an interpretation of one.

    DeepTutor states what happened (a turn completed, in this session, under
    this capability). Whatever that means for the host product's domain is the
    host's business, derived on its side from ``external_context_id``.
    """

    protocol_version: str = PROTOCOL_VERSION
    event_id: str
    event_type: str
    user_ref: ExternalUserRef | None = None
    session_id: str
    turn_id: str | None = None
    external_context_id: str | None = None
    capability: str | None = None
    message_refs: list[str] = Field(default_factory=list)
    success: bool = True
    occurred_at: datetime


class HandoffExchangeResult(BaseModel):
    """What a code exchange with the external identity provider returns."""

    identity: ExternalIdentity
    context: ExternalContext | None = None
