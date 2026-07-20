"""Tests for the generic external integration surface.

Scope note: these cover the mechanics DeepTutor owns — code exchange, context
binding, the outbox, signing. They deliberately assert nothing about what a
context *means*; that is the host product's business and testing it here would
smuggle a consumer's domain into this repo.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone

import pytest

from deeptutor.integrations.external.models import (
    ConversationEvent,
    ExternalContext,
    ExternalIdentity,
)
from deeptutor.integrations.external.sink import serialize_body, sign_body
from deeptutor.integrations.external.store import ExternalIntegrationStore


@pytest.fixture
def store(tmp_path) -> ExternalIntegrationStore:
    return ExternalIntegrationStore(tmp_path / "external.db")


def make_context(context_id: str = "ctx-1", **payload) -> ExternalContext:
    return ExternalContext(
        context_id=context_id,
        context_type="host.context",
        payload=payload or {"opaque": True},
    )


# --------------------------------------------------------------------- context


def test_saved_context_round_trips(store: ExternalIntegrationStore) -> None:
    store.save_context(make_context(nested={"a": [1, 2]}), user_key="iss:sub")

    loaded = store.get_context("ctx-1")

    assert loaded is not None
    assert loaded.payload == {"nested": {"a": [1, 2]}}
    assert loaded.context_type == "host.context"


def test_explicit_bind_wins_over_claiming(store: ExternalIntegrationStore) -> None:
    store.save_context(make_context("ctx-a"))
    store.save_context(make_context("ctx-b"))

    store.bind_context_to_session("ctx-a", "session-1")

    resolved = store.resolve_context_for_session("session-1")
    assert resolved is not None
    # Not ctx-b, even though ctx-b is the more recent unbound context.
    assert resolved.context_id == "ctx-a"


def test_bind_does_not_steal_a_context_already_bound_elsewhere(
    store: ExternalIntegrationStore,
) -> None:
    store.save_context(make_context("ctx-a"))
    store.bind_context_to_session("ctx-a", "session-1")

    stolen = store.bind_context_to_session("ctx-a", "session-2")

    assert stolen is False
    resolved = store.context_for_session("session-1")
    assert resolved is not None
    assert resolved.context_id == "ctx-a"
    assert store.context_for_session("session-2") is None


def test_bind_to_the_same_session_twice_is_a_no_op_refresh(
    store: ExternalIntegrationStore,
) -> None:
    store.save_context(make_context("ctx-a"))
    store.bind_context_to_session("ctx-a", "session-1")

    again = store.bind_context_to_session("ctx-a", "session-1")

    assert again is True


def test_only_one_session_claims_a_context(store: ExternalIntegrationStore) -> None:
    """The claim is a race by construction; it must at least be an atomic one."""
    store.save_context(make_context("ctx-only"))

    first = store.claim_unbound_context("session-1")
    second = store.claim_unbound_context("session-2")

    assert first is not None and first.context_id == "ctx-only"
    assert second is None


def test_claim_ignores_contexts_older_than_the_ttl(
    store: ExternalIntegrationStore,
) -> None:
    store.save_context(make_context("ctx-stale"))
    stale = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()
    with store._connection() as connection:
        connection.execute(
            "UPDATE external_context SET created_at = ? WHERE context_id = ?",
            (stale, "ctx-stale"),
        )

    assert store.claim_unbound_context("session-1", ttl_seconds=3600) is None


def test_claim_does_not_cross_user_keys(store: ExternalIntegrationStore) -> None:
    store.save_context(make_context("ctx-alice"), user_key="iss:alice")

    assert store.claim_unbound_context("session-bob", user_key="iss:bob") is None
    assert store.claim_unbound_context("session-alice", user_key="iss:alice") is not None


def test_claim_refuses_when_user_is_required_but_unknown(
    store: ExternalIntegrationStore,
) -> None:
    """On a multi-user instance an unattributable turn claims nothing."""
    store.save_context(make_context("ctx-someone"), user_key="iss:alice")

    assert (
        store.claim_unbound_context(
            "session-anon", user_key=None, require_user_key=True
        )
        is None
    )


# ---------------------------------------------------------------------- outbox


def test_enqueue_is_idempotent_on_event_id(store: ExternalIntegrationStore) -> None:
    body = {"event_id": "evt-1", "session_id": "s"}

    assert store.enqueue_event("evt-1", body) is True
    assert store.enqueue_event("evt-1", body) is False

    assert len(store.due_events()) == 1


def test_failure_records_attempt_and_defers_retry(
    store: ExternalIntegrationStore,
) -> None:
    store.enqueue_event("evt-1", {"event_id": "evt-1"})

    store.mark_failed("evt-1", "HTTP 500", retry_after_seconds=600)

    # Deferred past the retry window, so it is not immediately due again.
    assert store.due_events() == []
    assert store.outbox_stats() == {
        "total": 1,
        "delivered": 0,
        "dead_lettered": 0,
        "pending": 1,
    }


def test_delivered_events_leave_the_queue(store: ExternalIntegrationStore) -> None:
    store.enqueue_event("evt-1", {"event_id": "evt-1"})

    store.mark_delivered("evt-1")

    assert store.due_events() == []
    assert store.outbox_stats()["delivered"] == 1
    assert store.outbox_stats()["pending"] == 0


def test_dead_lettered_events_are_a_distinct_state(
    store: ExternalIntegrationStore,
) -> None:
    """Giving up is not 'pending forever' and not 'delivered'."""
    store.enqueue_event("evt-1", {"event_id": "evt-1"})

    store.mark_dead_lettered("evt-1", "max attempts exceeded")

    assert store.due_events() == []
    stats = store.outbox_stats()
    assert stats["dead_lettered"] == 1
    assert stats["pending"] == 0
    assert stats["delivered"] == 0


def test_repeated_failure_ends_in_dead_letter_not_endless_retry(
    monkeypatch, store: ExternalIntegrationStore
) -> None:
    """Drive the real retry ladder: failures accumulate, then delivery stops."""
    from deeptutor.integrations.external import sink

    monkeypatch.setattr(sink, "get_external_store", lambda: store)
    monkeypatch.setenv("EXTERNAL_EVENT_SINK_URL", "https://host.invalid/events")
    monkeypatch.setenv("EXTERNAL_EVENT_SINK_MAX_ATTEMPTS", "3")

    class _AlwaysFails:
        async def post(self, *args, **kwargs):  # noqa: ANN002, ANN003
            raise ConnectionError("sink is down")

    store.enqueue_event("evt-1", {"event_id": "evt-1"})

    def force_due() -> tuple[str, dict, int]:
        with store._connection() as connection:
            connection.execute(
                "UPDATE external_event_outbox SET next_attempt_at = ? "
                "WHERE delivered_at IS NULL AND dead_lettered_at IS NULL",
                (datetime.now(timezone.utc).isoformat(),),
            )
        due = store.due_events()
        return due[0] if due else None

    # Three failures exhaust the configured budget...
    for _ in range(3):
        event_id, body, attempts = force_due()
        asyncio.run(sink._deliver_one(_AlwaysFails(), event_id, body, attempts))

    assert store.outbox_stats()["pending"] == 1

    # ...and the next pass retires it instead of retrying forever.
    event_id, body, attempts = force_due()
    assert attempts == 3
    asyncio.run(sink._deliver_one(_AlwaysFails(), event_id, body, attempts))

    stats = store.outbox_stats()
    assert stats["dead_lettered"] == 1
    assert stats["pending"] == 0
    assert force_due() is None


# --------------------------------------------------------------------- signing


def test_signature_is_stable_across_key_ordering() -> None:
    """The signed bytes must not depend on how the dict happened to be built."""
    a = {"event_id": "evt-1", "session_id": "s", "success": True}
    b = {"success": True, "session_id": "s", "event_id": "evt-1"}

    assert serialize_body(a) == serialize_body(b)
    assert sign_body(serialize_body(a), "secret") == sign_body(serialize_body(b), "secret")


def test_signature_verifies_the_way_a_receiver_would() -> None:
    """Mirror of the HMAC a receiver is expected to compute over the raw body.

    Reimplemented here rather than imported: the point is to pin the wire
    format, and a shared helper would let both sides drift together.
    """
    import hashlib
    import hmac

    body = {"event_id": "evt-1", "occurred_at": "2026-07-19T00:00:00+00:00"}
    raw = serialize_body(body)
    header = sign_body(raw, "shared-secret")

    assert header.startswith("sha256=")
    expected = hmac.new(b"shared-secret", raw, hashlib.sha256).hexdigest()
    assert header.split("=", 1)[1] == expected


def test_signature_rejects_a_tampered_body() -> None:
    raw = serialize_body({"event_id": "evt-1", "success": True})
    tampered = serialize_body({"event_id": "evt-1", "success": False})

    assert sign_body(raw, "s") != sign_body(tampered, "s")


def test_events_without_an_event_id_are_not_queued(monkeypatch, store) -> None:
    from deeptutor.integrations.external import sink

    monkeypatch.setattr(sink, "get_external_store", lambda: store)

    assert sink.enqueue_conversation_event({"session_id": "s"}) is False
    assert store.outbox_stats()["total"] == 0


# ---------------------------------------------------------------------- router


@pytest.fixture
def client(monkeypatch, tmp_path):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from deeptutor.integrations.external import router as router_module
    from deeptutor.integrations.external import store as store_module

    fresh = ExternalIntegrationStore(tmp_path / "router.db")
    monkeypatch.setattr(store_module, "get_external_store", lambda: fresh)
    monkeypatch.setattr(router_module, "get_external_store", lambda: fresh)

    monkeypatch.setenv("EXTERNAL_HANDOFF_EXCHANGE_URL", "https://host.invalid/exchange")
    # A real workspace route, not a placeholder: web/app/(workspace)/page.tsx
    # only forwards a fixed set of query params on its client-side redirect,
    # so asserting against a route that actually exists in the app is what
    # catches a marker silently getting dropped there.
    monkeypatch.setenv("EXTERNAL_HANDOFF_REDIRECT_PATH", "/home")

    app = FastAPI()
    app.include_router(router_module.router, prefix="/api/v1/external")
    return TestClient(app, follow_redirects=False), fresh


def _exchange_result() -> dict:
    identity = ExternalIdentity(issuer="host", subject="user-1")
    return {
        "identity": identity.model_dump(mode="json"),
        "context": make_context("ctx-handoff").model_dump(mode="json"),
    }


def test_handoff_stores_context_and_redirects(monkeypatch, client) -> None:
    test_client, store = client
    from deeptutor.integrations.external import router as router_module

    async def fake_exchange(code: str) -> dict:
        assert code == "one-time-code"
        return _exchange_result()

    monkeypatch.setattr(router_module, "_exchange_code", fake_exchange)

    response = test_client.get(
        "/api/v1/external/handoff/complete", params={"code": "one-time-code"}
    )

    assert response.status_code == 302
    # The marker carries no id — just tells the landing page to try binding
    # once it has a session id, instead of falling back to the claim heuristic.
    assert response.headers["location"] == "/home?external_context_pending=1"
    assert store.get_context("ctx-handoff") is not None
    assert response.cookies.get("dt_external_context") == "ctx-handoff"


def test_context_cookie_follows_the_app_cookie_security_setting(
    monkeypatch, client
) -> None:
    """The context cookie is a bearer capability with no login binding — it
    must not default to a weaker posture than the rest of the app's cookies
    just because this router forgot to ask.

    ``_cookie_security`` itself is a two-line lazy import of
    ``deeptutor.api.routers.auth``'s own computed flags (see that module for
    where ``cookie_secure`` is sourced); this test pins what the handoff
    endpoint *does* with whatever that returns, without dragging in the rest
    of the auth router (unrelated optional deps like python-multipart
    shouldn't gate a test about cookie flags).
    """
    test_client, _ = client
    from deeptutor.integrations.external import router as router_module

    async def fake_exchange(code: str) -> dict:
        return _exchange_result()

    monkeypatch.setattr(router_module, "_exchange_code", fake_exchange)
    monkeypatch.setattr(router_module, "_cookie_security", lambda: (True, "none"))

    response = test_client.get(
        "/api/v1/external/handoff/complete", params={"code": "one-time-code"}
    )

    set_cookie_headers = response.headers.get_list("set-cookie")
    context_cookie = next(h for h in set_cookie_headers if h.startswith("dt_external_context="))
    assert "Secure" in context_cookie
    assert "samesite=none" in context_cookie.lower()


def test_cookie_security_falls_back_to_lax_when_auth_module_is_unavailable(
    monkeypatch,
) -> None:
    """Any import failure (e.g. an optional dep missing in a minimal deploy)
    must fail closed to today's behavior, not raise out of the handoff."""
    import builtins

    from deeptutor.integrations.external import router as router_module

    real_import = builtins.__import__

    def blocked_import(name, *args, **kwargs):
        if name == "deeptutor.api.routers.auth":
            raise RuntimeError("simulated: optional dependency unavailable")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", blocked_import)

    assert router_module._cookie_security() == (False, "lax")


@pytest.mark.parametrize(
    "unsafe_path",
    [
        "https://evil.invalid/",
        "//evil.invalid",
        "//evil.invalid/path",
        "evil.invalid",
        "",
    ],
)
def test_safe_redirect_path_rejects_anything_not_same_origin(unsafe_path) -> None:
    from deeptutor.integrations.external import router as router_module

    assert router_module._safe_redirect_path(unsafe_path) == "/"


@pytest.mark.parametrize("safe_path", ["/", "/home", "/home?foo=bar"])
def test_safe_redirect_path_passes_through_relative_paths(safe_path) -> None:
    from deeptutor.integrations.external import router as router_module

    assert router_module._safe_redirect_path(safe_path) == safe_path


def test_handoff_redirect_rejects_a_misconfigured_absolute_url(
    monkeypatch, client
) -> None:
    """A deploy setting EXTERNAL_HANDOFF_REDIRECT_PATH to an absolute URL must
    not turn the handoff into an open redirect."""
    test_client, _ = client
    from deeptutor.integrations.external import router as router_module

    monkeypatch.setenv("EXTERNAL_HANDOFF_REDIRECT_PATH", "https://evil.invalid/")

    async def fake_exchange(code: str) -> dict:
        return _exchange_result()

    monkeypatch.setattr(router_module, "_exchange_code", fake_exchange)

    response = test_client.get(
        "/api/v1/external/handoff/complete", params={"code": "one-time-code"}
    )

    assert response.headers["location"] == "/?external_context_pending=1"


def test_handoff_redirect_has_no_marker_without_a_context(monkeypatch, client) -> None:
    test_client, _ = client
    from deeptutor.integrations.external import router as router_module

    async def fake_exchange(code: str) -> dict:
        identity = ExternalIdentity(issuer="host", subject="user-1")
        return {"identity": identity.model_dump(mode="json")}  # no context

    monkeypatch.setattr(router_module, "_exchange_code", fake_exchange)

    response = test_client.get(
        "/api/v1/external/handoff/complete", params={"code": "one-time-code"}
    )

    assert response.headers["location"] == "/home"


def test_handoff_surfaces_a_rejected_code_as_502(monkeypatch, client) -> None:
    test_client, _ = client
    from fastapi import HTTPException

    from deeptutor.integrations.external import router as router_module

    async def fake_exchange(code: str) -> dict:
        raise HTTPException(status_code=502, detail="Identity provider rejected")

    monkeypatch.setattr(router_module, "_exchange_code", fake_exchange)

    response = test_client.get(
        "/api/v1/external/handoff/complete", params={"code": "bad"}
    )

    assert response.status_code == 502


def test_handoff_rejects_an_unusable_identity(monkeypatch, client) -> None:
    test_client, _ = client
    from deeptutor.integrations.external import router as router_module

    async def fake_exchange(code: str) -> dict:
        return {"identity": {"issuer": "host"}}  # no subject

    monkeypatch.setattr(router_module, "_exchange_code", fake_exchange)

    response = test_client.get("/api/v1/external/handoff/complete", params={"code": "c"})

    assert response.status_code == 502


def test_handoff_is_404_when_unconfigured(monkeypatch, client) -> None:
    test_client, _ = client
    monkeypatch.delenv("EXTERNAL_HANDOFF_EXCHANGE_URL", raising=False)

    response = test_client.get("/api/v1/external/handoff/complete", params={"code": "c"})

    assert response.status_code == 404


def test_reading_a_context_requires_the_handoff_cookie(client) -> None:
    """A context_id is a path segment, not a credential."""
    test_client, store = client
    store.save_context(make_context("ctx-secret", private="payload"))

    unauthorized = test_client.get("/api/v1/external/context/ctx-secret")
    assert unauthorized.status_code == 404

    test_client.cookies.set("dt_external_context", "ctx-secret")
    authorized = test_client.get("/api/v1/external/context/ctx-secret")
    assert authorized.status_code == 200
    assert authorized.json()["payload"] == {"private": "payload"}


def test_cookie_for_one_context_does_not_unlock_another(client) -> None:
    test_client, store = client
    store.save_context(make_context("ctx-mine"))
    store.save_context(make_context("ctx-yours", secret="not yours"))

    test_client.cookies.set("dt_external_context", "ctx-mine")

    assert test_client.get("/api/v1/external/context/ctx-yours").status_code == 404


def test_binding_a_context_requires_the_handoff_cookie(client) -> None:
    test_client, store = client
    store.save_context(make_context("ctx-1"))

    body = {"context_id": "ctx-1", "session_id": "session-hijack"}
    assert test_client.post("/api/v1/external/context/bind", json=body).status_code == 404
    assert store.context_for_session("session-hijack") is None

    test_client.cookies.set("dt_external_context", "ctx-1")
    ok = test_client.post("/api/v1/external/context/bind", json=body)
    assert ok.status_code == 200
    assert store.context_for_session("session-hijack") is not None


def test_binding_without_a_context_id_uses_the_handoff_cookie(client) -> None:
    """The pending-bind landing page never learns the id (httponly cookie);
    it only ever sends session_id, so the cookie alone must be enough."""
    test_client, store = client
    store.save_context(make_context("ctx-cookie-only"))
    test_client.cookies.set("dt_external_context", "ctx-cookie-only")

    response = test_client.post(
        "/api/v1/external/context/bind", json={"session_id": "session-1"}
    )

    assert response.status_code == 200
    assert response.json() == {
        "ok": True,
        "context_id": "ctx-cookie-only",
        "session_id": "session-1",
    }
    assert store.context_for_session("session-1") is not None


def test_binding_without_a_context_id_or_cookie_is_a_no_op(client) -> None:
    """A browser that never went through a handoff has nothing to bind —
    that's the common case, not an error the generic landing-page call
    should surface."""
    test_client, store = client

    response = test_client.post(
        "/api/v1/external/context/bind", json={"session_id": "session-1"}
    )

    assert response.status_code == 200
    assert response.json() == {
        "ok": False,
        "context_id": None,
        "session_id": "session-1",
    }
    assert store.context_for_session("session-1") is None


# -------------------------------------------------------------------- contract


def test_conversation_event_carries_no_domain_fields() -> None:
    """The boundary in one assertion.

    If a field naming a planet, node, score, or confidence ever appears here,
    the consumer-agnostic split has been undone — this repo would again be
    stating what a conversation *means* to one particular host.
    """
    fields = set(ConversationEvent.model_fields)

    assert fields == {
        "protocol_version",
        "event_id",
        "event_type",
        "user_ref",
        "session_id",
        "turn_id",
        "external_context_id",
        "capability",
        "message_refs",
        "success",
        "occurred_at",
    }


def test_conversation_event_serializes_to_json_safe_values() -> None:
    event = ConversationEvent(
        event_id="evt-1",
        event_type="turn.completed",
        session_id="s-1",
        occurred_at=datetime.now(timezone.utc),
    )

    # Must survive the exact trip the outbox puts it through.
    restored = json.loads(serialize_body(event.model_dump(mode="json")))

    assert restored["event_id"] == "evt-1"
    assert restored["success"] is True
