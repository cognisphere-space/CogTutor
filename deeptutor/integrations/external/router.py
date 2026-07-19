"""HTTP surface for the external integration.

Endpoints are named for the *role* the other side plays (an external identity
provider, an external context, an embedded viewer), never for any particular
product that might fill that role.
"""

from __future__ import annotations

import logging
import secrets
from typing import Any

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
    response.set_cookie(
        key=_COOKIE_NAME,
        value=token,
        httponly=True,
        samesite="lax",
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

    response = RedirectResponse(url=config.handoff_redirect_path, status_code=302)
    _maybe_establish_local_session(response, identity)
    if context_id:
        # This cookie is the capability that authorizes /context/{id} and
        # /context/bind for this browser — see _authorize_context. It is not a
        # second delivery channel: the event path resolves a context by
        # session binding alone and never reads it.
        response.set_cookie(
            key=_CONTEXT_COOKIE,
            value=context_id,
            httponly=True,
            samesite="lax",
            max_age=config.handoff_context_ttl_seconds,
        )
    logger.info(
        "External handoff completed (issuer=%s, context=%s)",
        identity.issuer,
        context_id or "none",
    )
    return response


class ContextBindRequest(BaseModel):
    context_id: str
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
    """
    _authorize_context(body.context_id, dt_external_context)
    store = get_external_store()
    if store.get_context(body.context_id) is None:
        raise HTTPException(status_code=404, detail="Unknown context_id")
    bound = store.bind_context_to_session(body.context_id, body.session_id)
    return {"ok": bound, "context_id": body.context_id, "session_id": body.session_id}


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


@router.get("/events/status")
async def events_status() -> dict[str, Any]:
    """Outbox health — for operators, not for the host product's domain logic."""
    config = get_external_config()
    return {
        "sink_enabled": config.event_sink_enabled,
        "outbox": get_external_store().outbox_stats(),
    }
