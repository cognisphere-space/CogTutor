"""HTTP surface for the external integration.

Endpoints are named for the *role* the other side plays (an external identity
provider, an external context, an embedded viewer), never for any particular
product that might fill that role.
"""

from __future__ import annotations

import json
import logging
import secrets
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from fastapi import APIRouter, Cookie, HTTPException, Query, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from deeptutor.integrations.external.config import get_external_config
from deeptutor.integrations.external.models import (
    PROTOCOL_VERSION,
    ExternalContext,
    ExternalIdentity,
)
from deeptutor.integrations.external.store import get_external_store

logger = logging.getLogger(__name__)

router = APIRouter()

_CONTEXT_COOKIE = "dt_external_context"
_PENDING_BIND_PARAM = "external_context_pending"


def _safe_redirect_path(path: str) -> str:
    """Confine ``handoff_redirect_path`` to a same-origin relative path.

    The value is deploy-time config (``EXTERNAL_HANDOFF_REDIRECT_PATH``), not
    request input, but it still ends up as the target of an unauthenticated
    302. A misconfigured absolute URL, protocol-relative ``//evil.com``, or
    bare ``evil.com`` would turn every handoff into an open redirect, so this
    fails closed to ``/`` rather than trusting the value as given.
    """
    if not path.startswith("/") or path.startswith("//"):
        logger.warning("Ignoring unsafe EXTERNAL_HANDOFF_REDIRECT_PATH %r", path)
        return "/"
    parts = urlsplit(path)
    if parts.scheme or parts.netloc:
        logger.warning("Ignoring unsafe EXTERNAL_HANDOFF_REDIRECT_PATH %r", path)
        return "/"
    return path


def _with_pending_bind_marker(path: str) -> str:
    """Append a non-secret marker so the landing page knows to call
    ``/context/bind`` once it has a session id, instead of falling back to
    the claim heuristic. The marker carries no id — the actual context stays
    behind the httponly cookie set alongside this redirect.
    """
    parts = urlsplit(path)
    query = parse_qsl(parts.query, keep_blank_values=True)
    query.append((_PENDING_BIND_PARAM, "1"))
    return urlunsplit(parts._replace(query=urlencode(query)))


async def _exchange_code(code: str) -> dict[str, Any]:
    """Redeem a one-time code with the configured identity provider.

    Server-to-server on purpose: the browser only ever carries a short-lived,
    single-use code, never a bearer token.
    """
    import httpx

    config = get_external_config()
    headers = {"Content-Type": "application/json"}
    if config.handoff_exchange_token:
        headers["Authorization"] = f"Bearer {config.handoff_exchange_token}"
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(
            config.handoff_exchange_url, json={"code": code}, headers=headers
        )
    if response.status_code >= 400:
        raise HTTPException(
            status_code=502,
            detail=f"Identity provider rejected the handoff code ({response.status_code})",
        )
    return response.json()


def _cookie_security() -> tuple[bool, str]:
    """Match the app's configured cookie security posture (see `auth.py`).

    Reused rather than reinvented: `cookie_secure` is already a generic
    runtime setting (`AUTH_COOKIE_SECURE` / `data/user/settings`), not
    specific to the login flow, and the two flags move together — Secure is
    required by browsers whenever SameSite=None is used to let frontend and
    backend sit on different origins. Defaults closed (Lax, not Secure) so a
    plain local HTTP deployment with no config at all still works, matching
    every other cookie this router sets.
    """
    try:
        from deeptutor.api.routers.auth import _SAMESITE, _SECURE

        return bool(_SECURE), str(_SAMESITE)
    except Exception:
        return False, "lax"


def _maybe_establish_local_session(
    response: Response, identity: ExternalIdentity
) -> None:
    """Map a federated identity onto a local session when auth is enabled.

    With auth disabled (the single-user default) there is no session to
    establish and this is a no-op.
    """
    try:
        from deeptutor.services.config import get_runtime_settings
    except Exception:
        return
    try:
        auth_enabled = bool(getattr(get_runtime_settings(), "auth_enabled", False))
    except Exception:
        auth_enabled = False
    if not auth_enabled:
        return

    from deeptutor.api.routers.auth import _COOKIE_NAME, _COOKIE_MAX_AGE
    from deeptutor.services.auth import add_user, create_token, get_user_info

    username = identity.user_key
    if get_user_info(username) is None:
        add_user(username, secrets.token_urlsafe(32), role="user")
    info = get_user_info(username) or {}
    token = create_token(username, info.get("role", "user"), info.get("user_id"))
    secure, samesite = _cookie_security()
    response.set_cookie(
        key=_COOKIE_NAME,
        value=token,
        httponly=True,
        samesite=samesite,
        secure=secure,
        max_age=_COOKIE_MAX_AGE,
    )


@router.get("/handoff/complete")
async def complete_handoff(code: str = Query(...)) -> Response:
    """Land here from the host product; leave with a session and no credentials in the URL."""
    config = get_external_config()
    if not config.handoff_enabled:
        raise HTTPException(status_code=404, detail="External handoff is not configured")

    result = await _exchange_code(code)

    try:
        identity = ExternalIdentity.model_validate(result["identity"])
    except Exception as exc:
        raise HTTPException(
            status_code=502, detail="Identity provider returned an unusable identity"
        ) from exc

    context_id: str | None = None
    raw_context = result.get("context")
    if raw_context:
        try:
            context = ExternalContext.model_validate(raw_context)
        except Exception as exc:
            raise HTTPException(
                status_code=502, detail="Identity provider returned an unusable context"
            ) from exc
        get_external_store().save_context(context, user_key=identity.user_key)
        context_id = context.context_id

    redirect_path = _safe_redirect_path(config.handoff_redirect_path)
    if context_id:
        redirect_path = _with_pending_bind_marker(redirect_path)
    response = RedirectResponse(url=redirect_path, status_code=302)
    _maybe_establish_local_session(response, identity)
    if context_id:
        # This cookie is the capability that authorizes /context/{id} and
        # /context/bind for this browser — see _authorize_context. It is not a
        # second delivery channel: the event path resolves a context by
        # session binding alone and never reads it. Holding it is a bearer
        # capability with no separate binding to a login session, so it
        # follows the same Secure/SameSite posture as the rest of the app's
        # cookies rather than a weaker one of its own.
        secure, samesite = _cookie_security()
        response.set_cookie(
            key=_CONTEXT_COOKIE,
            value=context_id,
            httponly=True,
            samesite=samesite,
            secure=secure,
            max_age=config.handoff_context_ttl_seconds,
        )
    logger.info(
        "External handoff completed (issuer=%s, context=%s)",
        identity.issuer,
        context_id or "none",
    )
    return response


class ContextBindRequest(BaseModel):
    # Optional: the browser holds the real context id only in the httponly
    # handoff cookie, never in JS-reachable storage, so the common caller
    # (the landing page reacting to the pending-bind marker) has no id to
    # send and relies on the cookie alone. A caller that already knows the
    # id (e.g. a future non-cookie integration) may still pass it explicitly.
    context_id: str | None = None
    session_id: str


def _authorize_context(context_id: str, cookie_context_id: str | None) -> None:
    """Only the browser that completed the handoff may read or bind a context.

    The handoff sets ``dt_external_context`` httponly on the redirect, so
    holding it is proof of having been through the exchange. Without this
    check, ``context_id`` is a bearer token that is also a path segment:
    anyone who guesses or scrapes one reads the stored payload, and — worse —
    binds someone else's context onto their own session.

    A context id is not a secret by construction, so it must not be the only
    thing standing between a caller and the payload.
    """
    if cookie_context_id and secrets.compare_digest(cookie_context_id, context_id):
        return
    # 404 rather than 403: an unauthorized caller learns nothing about whether
    # the id exists.
    raise HTTPException(status_code=404, detail="Unknown context_id")


@router.post("/context/bind")
async def bind_context(
    body: ContextBindRequest,
    dt_external_context: str | None = Cookie(default=None),
) -> dict[str, Any]:
    """Attach a stored context to a session id explicitly.

    Preferred over the store's first-turn claim whenever the frontend knows
    its session id: the claim is a heuristic, this is a statement of fact.

    ``context_id`` defaults to whatever the handoff cookie names, which is
    the only copy of it the browser ever holds. A caller with neither an
    explicit id nor a cookie has nothing to bind — that is not an error, it
    just means this browser never went through a handoff.
    """
    context_id = body.context_id or dt_external_context
    if not context_id:
        return {"ok": False, "context_id": None, "session_id": body.session_id}
    _authorize_context(context_id, dt_external_context)
    store = get_external_store()
    if store.get_context(context_id) is None:
        raise HTTPException(status_code=404, detail="Unknown context_id")
    bound = store.bind_context_to_session(context_id, body.session_id)
    return {"ok": bound, "context_id": context_id, "session_id": body.session_id}


class ContextPayloadUpdateRequest(BaseModel):
    # No context_id here either, for the same reason as ContextBindRequest:
    # the caller is the viewer-embed bridge reacting to a cross-origin
    # ``selection_changed`` postMessage, which never learns the id — only
    # the httponly cookie does.
    payload: dict[str, Any]


# The payload is opaque, so nothing about its *shape* can be validated. Its
# size can be: it is written whole into a SQLite cell on every selection
# change, and the sender is a cross-origin page we do not control. A viewer
# posting its entire node graph on each click would otherwise be free to grow
# one row without bound.
_MAX_CONTEXT_PAYLOAD_BYTES = 64 * 1024


def _payload_size_or_413(payload: dict[str, Any]) -> int:
    try:
        encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    except (TypeError, ValueError) as exc:
        # Pydantic guarantees a dict, not that everything inside it survives
        # JSON encoding. Answer 422 rather than let the store raise a 500.
        raise HTTPException(
            status_code=422, detail="Payload is not JSON-serialisable"
        ) from exc
    if len(encoded) > _MAX_CONTEXT_PAYLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"Payload exceeds {_MAX_CONTEXT_PAYLOAD_BYTES} bytes",
        )
    return len(encoded)


@router.post("/context/payload")
async def update_context_payload(
    body: ContextPayloadUpdateRequest,
    dt_external_context: str | None = Cookie(default=None),
) -> dict[str, Any]:
    """Overwrite the bound context's opaque payload — the viewer-embed tab's
    only way to "push" anything back into this session.

    ``payload`` is never interpreted here; it is whatever the embedded
    viewer's ``selection_changed`` message carried, stored verbatim so a
    later turn's prompt (if configured to use it) sees the update. This is
    deliberately the *only* direction the viewer embed can influence this
    session — there is no reverse channel that lets this session push a
    navigation command into the viewer.

    Size is the one property of an opaque payload worth checking; see
    ``_payload_size_or_413``. It runs before the cookie checks so a caller
    gets told the payload is too big rather than a quiet ``ok: false``.
    """
    _payload_size_or_413(body.payload)
    if not dt_external_context:
        # A browser that never went through a handoff has nothing to update.
        # Not an error (the viewer tab cannot know), but worth seeing when a
        # deployment's pushes are silently going nowhere.
        logger.debug("Ignoring context payload push: no handoff cookie")
        return {"ok": False, "context_id": None}
    store = get_external_store()
    if store.get_context(dt_external_context) is None:
        logger.debug("Ignoring context payload push: unknown context in cookie")
        return {"ok": False, "context_id": None}
    updated = store.update_context_payload(dt_external_context, body.payload)
    return {"ok": updated, "context_id": dt_external_context}


@router.get("/context/{context_id}")
async def read_context(
    context_id: str,
    dt_external_context: str | None = Cookie(default=None),
) -> ExternalContext:
    _authorize_context(context_id, dt_external_context)
    context = get_external_store().get_context(context_id)
    if context is None:
        raise HTTPException(status_code=404, detail="Unknown context_id")
    return context


@router.get("/viewer/config")
async def viewer_config() -> dict[str, Any]:
    """Config for the embedded viewer tab. Empty unless a deployment sets it."""
    config = get_external_config()
    return {
        "protocol_version": PROTOCOL_VERSION,
        "enabled": config.viewer_enabled and bool(config.viewer_url),
        "url": config.viewer_url,
        "title": config.viewer_title,
        "allowed_origin": config.viewer_allowed_origin,
        "sandbox": config.viewer_sandbox,
    }


@router.get("/viewer/handle")
async def viewer_handle(
    response: Response,
    dt_external_context: str | None = Cookie(default=None),
) -> dict[str, Any]:
    """The one deliberate exposure of ``context_id`` to frontend JS.

    The viewer tab embeds a cross-origin iframe and has to hand it a
    ``context_id`` via ``postMessage`` to bootstrap it — that hop
    fundamentally can't happen without the value passing through JS once, so
    the httponly-cookie-only design used elsewhere doesn't apply here. Still
    gated on holding the cookie: this only ever returns *this browser's own*
    id, never lets one be looked up by anyone else's guess.

    Explicitly uncacheable: the answer varies by a cookie no intermediary is
    required to key on, and one cached copy handed to a second browser would
    give away exactly the id this endpoint exists to keep per-browser.
    """
    response.headers["Cache-Control"] = "no-store"
    if not dt_external_context:
        return {"context_id": None}
    if get_external_store().get_context(dt_external_context) is None:
        return {"context_id": None}
    return {"context_id": dt_external_context}


@router.get("/events/status")
async def events_status() -> dict[str, Any]:
    """Outbox health — for operators, not for the host product's domain logic."""
    config = get_external_config()
    return {
        "sink_enabled": config.event_sink_enabled,
        "outbox": get_external_store().outbox_stats(),
    }
