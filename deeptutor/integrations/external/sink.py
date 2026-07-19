"""Generic HTTP event sink with a persistent outbox.

Delivery is at-least-once: an event is written to the outbox first, then a
background worker drains it with exponential backoff. A receiver that is down,
slow, or broken never propagates back into the chat loop — the conversation
does not depend on anything downstream of it.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import httpx

from deeptutor.integrations.external.config import get_external_config
from deeptutor.integrations.external.store import get_external_store

logger = logging.getLogger(__name__)

_POLL_INTERVAL_SECONDS = 2.0
_MAX_BACKOFF_SECONDS = 300.0


def sign_body(body: bytes, secret: str) -> str:
    digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def _backoff_seconds(attempts: int) -> float:
    return min(_MAX_BACKOFF_SECONDS, 2.0 ** min(attempts, 10))


def enqueue_conversation_event(body: dict[str, Any]) -> bool:
    """Persist an event for delivery. Safe to call from any context."""
    event_id = str(body.get("event_id") or "")
    if not event_id:
        logger.warning("Refusing to enqueue an event without event_id")
        return False
    try:
        return get_external_store().enqueue_event(event_id, body)
    except Exception:
        logger.warning("Failed to enqueue conversation event", exc_info=True)
        return False


def serialize_body(body: dict[str, Any]) -> bytes:
    """Render an event to the exact bytes that get signed and sent.

    One function so the signature covers what the receiver actually parses.
    ``sort_keys`` and a fixed separator make that byte string reproducible:
    signing one serialization and transmitting another differs only by dict
    ordering, which is invisible until the day it is not.
    """
    return json.dumps(
        body, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


async def _deliver_one(
    client: "httpx.AsyncClient", event_id: str, body: dict[str, Any], attempts: int
) -> None:
    config = get_external_config()
    store = get_external_store()

    if attempts >= config.event_sink_max_attempts:
        store.mark_dead_lettered(event_id, "max attempts exceeded")
        logger.error("Event sink gave up on event_id=%s after %s attempts", event_id, attempts)
        return

    raw = serialize_body(body)
    headers = {
        "Content-Type": "application/json",
        "X-Event-Id": event_id,
    }
    if config.event_sink_secret:
        headers["X-Event-Signature"] = sign_body(raw, config.event_sink_secret)

    try:
        response = await client.post(
            config.event_sink_url,
            content=raw,
            headers=headers,
            timeout=config.event_sink_timeout_seconds,
        )
        if response.status_code < 300:
            store.mark_delivered(event_id)
            logger.debug("Delivered conversation event %s", event_id)
            return
        store.mark_failed(
            event_id,
            f"HTTP {response.status_code}",
            _backoff_seconds(attempts),
        )
        logger.warning(
            "Event sink HTTP %s for event_id=%s", response.status_code, event_id
        )
    except Exception as exc:
        store.mark_failed(event_id, str(exc), _backoff_seconds(attempts))
        logger.warning("Event sink delivery failed for event_id=%s: %s", event_id, exc)


class EventSinkWorker:
    def __init__(self) -> None:
        self._task: asyncio.Task | None = None
        self._running = False

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._loop())
        logger.info("External event sink worker started")

    async def stop(self) -> None:
        self._running = False
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass
            self._task = None
        logger.info("External event sink worker stopped")

    async def _loop(self) -> None:
        import httpx

        # One client for the worker's lifetime: a fresh AsyncClient per event
        # threw away the connection pool, so every delivery paid a new TCP and
        # TLS handshake.
        async with httpx.AsyncClient() as client:
            while self._running:
                try:
                    config = get_external_config()
                    if config.event_sink_enabled:
                        for event_id, body, attempts in get_external_store().due_events():
                            await _deliver_one(client, event_id, body, attempts)
                except asyncio.CancelledError:
                    raise
                except Exception:
                    logger.warning("Event sink worker iteration failed", exc_info=True)
                await asyncio.sleep(_POLL_INTERVAL_SECONDS)


_WORKER: EventSinkWorker | None = None


def get_event_sink_worker() -> EventSinkWorker:
    global _WORKER
    if _WORKER is None:
        _WORKER = EventSinkWorker()
    return _WORKER
