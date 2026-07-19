"""Turn EventBus completions into generic ``ConversationEvent`` facts.

What this module is allowed to say is deliberately narrow: a turn completed,
in this session, under this capability, associated with this external context
id. It never inspects ``ExternalContext.payload`` and never classifies the
turn — interpretation belongs to whoever receives the event.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from deeptutor.events.event_bus import Event, EventType, get_event_bus
from deeptutor.integrations.external.config import get_external_config
from deeptutor.integrations.external.models import ConversationEvent
from deeptutor.integrations.external.sink import enqueue_conversation_event
from deeptutor.integrations.external.store import get_external_store

logger = logging.getLogger(__name__)

_SUBSCRIBED = False


def _auth_enabled() -> bool:
    try:
        from deeptutor.services.config import get_runtime_settings

        return bool(getattr(get_runtime_settings(), "auth_enabled", False))
    except Exception:
        return False


def _current_user_key() -> str | None:
    """The key contexts are scoped by, matching what the handoff stored.

    ``save_context`` records ``ExternalIdentity.user_key``, and the handoff
    provisions the local account under that same name, so ``username`` — not
    ``id`` — is the field that lines up on both sides.
    """
    try:
        from deeptutor.multi_user.context import get_current_user_or_none

        user = get_current_user_or_none()
    except Exception:
        return None
    if user is None:
        return None
    return str(getattr(user, "username", "") or "") or None


def _current_user_ref() -> dict[str, str] | None:
    try:
        from deeptutor.multi_user.context import get_current_user_or_none

        user = get_current_user_or_none()
    except Exception:
        return None
    if user is None:
        return None
    subject = str(getattr(user, "id", "") or "")
    if not subject:
        return None
    return {"issuer": "local", "subject": subject}


def build_conversation_event(event: Event) -> ConversationEvent:
    metadata = event.metadata if isinstance(event.metadata, dict) else {}
    session_id = str(metadata.get("session_id") or event.task_id or "")
    turn_id = str(metadata.get("turn_id") or "") or None

    context = None
    if session_id:
        config = get_external_config()
        try:
            context = get_external_store().resolve_context_for_session(
                session_id,
                user_key=_current_user_key(),
                # On a multi-user instance an unattributable turn must not
                # claim a context at all — see claim_unbound_context.
                require_user_key=_auth_enabled(),
                ttl_seconds=config.handoff_context_ttl_seconds,
            )
        except Exception:
            logger.warning("External context lookup failed", exc_info=True)

    occurred = event.timestamp
    if not isinstance(occurred, datetime):
        occurred = datetime.now(timezone.utc)
    if occurred.tzinfo is None:
        occurred = occurred.replace(tzinfo=timezone.utc)

    user_ref = _current_user_ref()

    return ConversationEvent(
        event_id=str(event.event_id or uuid.uuid4()),
        event_type="turn.completed" if event.success else "turn.failed",
        user_ref=user_ref,
        session_id=session_id or "session-unknown",
        turn_id=turn_id,
        external_context_id=context.context_id if context else None,
        capability=str(metadata.get("capability") or "") or None,
        message_refs=[turn_id] if turn_id else [],
        success=bool(event.success),
        occurred_at=occurred,
    )


async def publish_conversation_event(event: Event) -> None:
    if not get_external_config().event_sink_enabled:
        return
    try:
        conversation_event = build_conversation_event(event)
    except Exception:
        logger.warning("Failed to build conversation event", exc_info=True)
        return
    enqueue_conversation_event(conversation_event.model_dump(mode="json"))


def register_conversation_event_publisher() -> None:
    global _SUBSCRIBED
    if _SUBSCRIBED:
        return
    get_event_bus().subscribe(EventType.CAPABILITY_COMPLETE, publish_conversation_event)
    _SUBSCRIBED = True
    logger.info(
        "Conversation event publisher registered (sink=%s)",
        get_external_config().event_sink_url or "disabled",
    )


def unregister_conversation_event_publisher() -> None:
    global _SUBSCRIBED
    if not _SUBSCRIBED:
        return
    try:
        get_event_bus().unsubscribe(
            EventType.CAPABILITY_COMPLETE, publish_conversation_event
        )
    except Exception:
        logger.debug("Conversation event publisher unregister failed", exc_info=True)
    _SUBSCRIBED = False
