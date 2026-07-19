"""Runtime configuration for the external integration surface.

Every key is generic. No host product name, URL, or default endpoint is
baked in here — an unconfigured deployment simply has the whole surface off.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


def _env(name: str) -> str:
    return os.environ.get(name, "").strip()


def _env_bool(name: str, default: bool = False) -> bool:
    raw = _env(name).lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    raw = _env(name)
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


@dataclass(frozen=True)
class ExternalIntegrationConfig:
    # Identity / context handoff
    handoff_exchange_url: str = ""
    handoff_exchange_token: str = ""
    handoff_redirect_path: str = "/"
    handoff_context_ttl_seconds: int = 86400

    # Conversation event sink
    event_sink_url: str = ""
    event_sink_secret: str = ""
    event_sink_timeout_seconds: int = 10
    event_sink_max_attempts: int = 8

    # Embedded viewer
    viewer_enabled: bool = False
    viewer_url: str = ""
    viewer_title: str = ""
    viewer_allowed_origin: str = ""
    viewer_sandbox: str = "allow-scripts allow-same-origin"

    @property
    def handoff_enabled(self) -> bool:
        return bool(self.handoff_exchange_url)

    @property
    def event_sink_enabled(self) -> bool:
        return bool(self.event_sink_url)


def get_external_config() -> ExternalIntegrationConfig:
    """Read config fresh each call so a restart is not needed to reconfigure."""
    return ExternalIntegrationConfig(
        handoff_exchange_url=_env("EXTERNAL_HANDOFF_EXCHANGE_URL").rstrip("/"),
        handoff_exchange_token=_env("EXTERNAL_HANDOFF_EXCHANGE_TOKEN"),
        handoff_redirect_path=_env("EXTERNAL_HANDOFF_REDIRECT_PATH") or "/",
        handoff_context_ttl_seconds=_env_int("EXTERNAL_HANDOFF_CONTEXT_TTL_SECONDS", 86400),
        event_sink_url=_env("EXTERNAL_EVENT_SINK_URL"),
        event_sink_secret=_env("EXTERNAL_EVENT_SINK_SECRET"),
        event_sink_timeout_seconds=_env_int("EXTERNAL_EVENT_SINK_TIMEOUT_SECONDS", 10),
        event_sink_max_attempts=_env_int("EXTERNAL_EVENT_SINK_MAX_ATTEMPTS", 8),
        viewer_enabled=_env_bool("EXTERNAL_VIEWER_ENABLED"),
        viewer_url=_env("EXTERNAL_VIEWER_URL"),
        viewer_title=_env("EXTERNAL_VIEWER_TITLE"),
        viewer_allowed_origin=_env("EXTERNAL_VIEWER_ALLOWED_ORIGIN"),
        viewer_sandbox=_env("EXTERNAL_VIEWER_SANDBOX")
        or "allow-scripts allow-same-origin",
    )
