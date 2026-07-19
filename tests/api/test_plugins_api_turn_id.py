"""Regression test for turn identity on the non-partner capability path.

``/capabilities/{name}/execute-stream`` without a partner id runs the turn
through ``ChatOrchestrator``. That path once built ``UnifiedContext`` with no
metadata, so ``_publish_completion`` emitted an empty ``turn_id`` and every
downstream ``ConversationEvent`` lost both ``turn_id`` and ``message_refs``.
This test pins the whole chain: request -> context metadata -> published
event -> ``build_conversation_event``.
"""

from __future__ import annotations

import importlib
import re
from typing import Any

import pytest

try:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
except Exception:  # pragma: no cover
    FastAPI = None
    TestClient = None

pytestmark = pytest.mark.skipif(
    FastAPI is None or TestClient is None, reason="fastapi not installed"
)

# Same shape ``sqlite_store._create_turn_sync`` / ``pocketbase_store.create_turn``
# produce, so a turn id minted here is recognisable as one of ours.
TURN_ID_PATTERN = re.compile(r"^turn_\d{13}_[0-9a-f]{10}$")

PROBE_CAPABILITY = "turn_id_probe"


def _install_probe_capability(monkeypatch) -> list[Any]:
    """Register a no-op capability and capture the context it receives."""
    from deeptutor.core.capability_protocol import BaseCapability, CapabilityManifest
    from deeptutor.runtime.registry.capability_registry import get_capability_registry

    seen_contexts: list[Any] = []

    class ProbeCapability(BaseCapability):
        manifest = CapabilityManifest(
            name=PROBE_CAPABILITY,
            description="Test capability that records its context and returns.",
        )

        async def run(self, context, stream) -> None:
            seen_contexts.append(context)

    registry = get_capability_registry()
    monkeypatch.setitem(registry._capabilities, PROBE_CAPABILITY, ProbeCapability())
    return seen_contexts


def _capture_published_events(monkeypatch) -> list[Any]:
    """Replace the orchestrator's EventBus so completions are captured inline."""
    orchestrator_mod = importlib.import_module("deeptutor.runtime.orchestrator")
    published: list[Any] = []

    class FakeBus:
        async def publish(self, event) -> None:
            published.append(event)

    monkeypatch.setattr(orchestrator_mod, "get_event_bus", lambda: FakeBus())
    return published


def _client() -> Any:
    plugins_router_mod = importlib.import_module("deeptutor.api.routers.plugins_api")
    app = FastAPI()
    app.include_router(plugins_router_mod.router, prefix="/api/v1/plugins")
    return TestClient(app)


def test_orchestrator_path_stamps_a_turn_id_on_the_context(monkeypatch):
    seen_contexts = _install_probe_capability(monkeypatch)
    published = _capture_published_events(monkeypatch)

    # No ``bot_id``: this must take the orchestrator branch, not the partner one.
    response = _client().post(
        f"/api/v1/plugins/capabilities/{PROBE_CAPABILITY}/execute-stream",
        json={"content": "hi"},
    )

    assert response.status_code == 200
    assert "event: error" not in response.text

    assert len(seen_contexts) == 1
    turn_id = seen_contexts[0].metadata.get("turn_id")
    assert isinstance(turn_id, str) and TURN_ID_PATTERN.match(turn_id), turn_id

    assert len(published) == 1
    assert published[0].metadata["turn_id"] == turn_id
    assert published[0].task_id == turn_id


def test_published_completion_yields_a_referenceable_conversation_event(monkeypatch):
    """The audit side reads ``message_refs[0]``; it must not be empty."""
    _install_probe_capability(monkeypatch)
    published = _capture_published_events(monkeypatch)

    subscriber = importlib.import_module("deeptutor.integrations.external.subscriber")

    class NoContextStore:
        def resolve_context_for_session(self, *args, **kwargs):
            return None

    monkeypatch.setattr(subscriber, "get_external_store", lambda: NoContextStore())

    response = _client().post(
        f"/api/v1/plugins/capabilities/{PROBE_CAPABILITY}/execute-stream",
        json={"content": "hi"},
    )
    assert response.status_code == 200
    assert len(published) == 1

    conversation_event = subscriber.build_conversation_event(published[0])

    assert conversation_event.turn_id is not None
    assert TURN_ID_PATTERN.match(conversation_event.turn_id)
    assert conversation_event.message_refs == [conversation_event.turn_id]


def test_request_session_id_reaches_the_conversation_event(monkeypatch):
    """``session_id`` is what binds a turn to a handed-off external context."""
    seen_contexts = _install_probe_capability(monkeypatch)
    published = _capture_published_events(monkeypatch)

    subscriber = importlib.import_module("deeptutor.integrations.external.subscriber")
    resolved_for: list[str] = []

    class RecordingStore:
        def resolve_context_for_session(self, session_id, *args, **kwargs):
            resolved_for.append(session_id)
            return None

    monkeypatch.setattr(subscriber, "get_external_store", lambda: RecordingStore())

    response = _client().post(
        f"/api/v1/plugins/capabilities/{PROBE_CAPABILITY}/execute-stream",
        json={"content": "hi", "session_id": "sess-abc"},
    )
    assert response.status_code == 200

    assert seen_contexts[0].session_id == "sess-abc"
    assert published[0].metadata["session_id"] == "sess-abc"

    conversation_event = subscriber.build_conversation_event(published[0])
    assert conversation_event.session_id == "sess-abc"
    assert resolved_for == ["sess-abc"]


def test_absent_session_id_still_gets_one(monkeypatch):
    """Omitting it must keep the previous behaviour, not emit an empty id."""
    seen_contexts = _install_probe_capability(monkeypatch)
    _capture_published_events(monkeypatch)

    response = _client().post(
        f"/api/v1/plugins/capabilities/{PROBE_CAPABILITY}/execute-stream",
        json={"content": "hi"},
    )
    assert response.status_code == 200
    assert seen_contexts[0].session_id
