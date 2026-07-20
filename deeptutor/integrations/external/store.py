"""SQLite store for external contexts, session bindings, and the event outbox.

Separate from ``chat_history.db`` on purpose: the integration surface has its
own lifecycle and can be dropped wholesale without touching conversation data.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator

from deeptutor.integrations.external.models import ExternalContext
from deeptutor.services.path_service import get_path_service


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.isoformat()


class ExternalIntegrationStore:
    def __init__(self, database_path: str | Path) -> None:
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._initialize()

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.database_path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout = 5000")
        try:
            yield connection
        except BaseException:
            try:
                connection.rollback()
            except sqlite3.Error:
                pass
            raise
        else:
            connection.commit()
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self._connection() as connection:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS external_context (
                    context_id TEXT PRIMARY KEY,
                    context_type TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    protocol_version TEXT NOT NULL,
                    user_key TEXT,
                    session_id TEXT,
                    created_at TEXT NOT NULL,
                    bound_at TEXT
                );

                CREATE INDEX IF NOT EXISTS external_context_session
                ON external_context(session_id);

                CREATE INDEX IF NOT EXISTS external_context_created
                ON external_context(created_at);

                CREATE TABLE IF NOT EXISTS external_event_outbox (
                    event_id TEXT PRIMARY KEY,
                    body_json TEXT NOT NULL,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    next_attempt_at TEXT NOT NULL,
                    delivered_at TEXT,
                    dead_lettered_at TEXT,
                    last_error TEXT,
                    created_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS external_event_outbox_pending
                ON external_event_outbox(delivered_at, next_attempt_at);
                """
            )
            # Giving up used to be encoded as a next_attempt_at far in the
            # future, which reads as "retrying, eventually" in every query and
            # every dashboard. Dead-lettered is a state, so it gets a column.
            outbox_columns = {
                row["name"]
                for row in connection.execute("PRAGMA table_info(external_event_outbox)")
            }
            if "dead_lettered_at" not in outbox_columns:
                connection.execute(
                    "ALTER TABLE external_event_outbox ADD COLUMN dead_lettered_at TEXT"
                )

    # ---------------------------------------------------------------- context

    def save_context(
        self,
        context: ExternalContext,
        *,
        user_key: str | None = None,
    ) -> None:
        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO external_context (
                    context_id, context_type, payload_json, protocol_version,
                    user_key, session_id, created_at, bound_at
                ) VALUES (?, ?, ?, ?, ?, NULL, ?, NULL)
                ON CONFLICT(context_id) DO UPDATE SET
                    context_type = excluded.context_type,
                    payload_json = excluded.payload_json,
                    protocol_version = excluded.protocol_version,
                    user_key = COALESCE(excluded.user_key, external_context.user_key)
                """,
                (
                    context.context_id,
                    context.context_type,
                    json.dumps(context.payload, ensure_ascii=False),
                    context.protocol_version,
                    user_key,
                    _iso(_now()),
                ),
            )

    def get_context(self, context_id: str) -> ExternalContext | None:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT * FROM external_context WHERE context_id = ?",
                (context_id,),
            ).fetchone()
        return self._row_to_context(row) if row else None

    def bind_context_to_session(self, context_id: str, session_id: str) -> bool:
        """Bind once. A context already bound to a *different* session is left
        alone — otherwise a second ``/context/bind`` call (or a replayed one)
        could reattach someone else's context to a new session after the
        fact. Re-binding to the same session id is a harmless no-op refresh.
        """
        with self._connection() as connection:
            cursor = connection.execute(
                """
                UPDATE external_context
                SET session_id = ?, bound_at = ?
                WHERE context_id = ? AND (session_id IS NULL OR session_id = ?)
                """,
                (session_id, _iso(_now()), context_id, session_id),
            )
            return cursor.rowcount == 1

    def context_for_session(self, session_id: str) -> ExternalContext | None:
        with self._connection() as connection:
            row = connection.execute(
                """
                SELECT * FROM external_context
                WHERE session_id = ?
                ORDER BY bound_at DESC LIMIT 1
                """,
                (session_id,),
            ).fetchone()
        return self._row_to_context(row) if row else None

    def claim_unbound_context(
        self,
        session_id: str,
        *,
        user_key: str | None = None,
        require_user_key: bool = False,
        ttl_seconds: int = 86400,
    ) -> ExternalContext | None:
        """Attach the most recent still-unbound context to ``session_id``.

        A handoff hands over the context *before* the user has sent a first
        message, so there is no session id to bind to yet. The first turn of
        the next session claims it. Explicit binding via ``/context/bind`` is
        always preferred when the host frontend knows the session id; this
        fallback is what makes the plain "open the chat page and talk" flow
        work without one.

        Only unbound contexts inside the TTL are eligible, so a stale handoff
        never silently attaches itself to an unrelated conversation later.

        WARNING — "most recent unbound" is a guess, and it is wrong whenever
        more than one handoff is in flight. Two tabs handed off in quick
        succession, or two users on a shared instance, and the first turn to
        arrive takes the other's context: the conversation is then reported
        against a context its user never opened. ``user_key`` narrows this to
        within one account and is therefore required once auth is on; it does
        nothing for two tabs belonging to the same person. The real fix is for
        the frontend to call ``/context/bind`` with its session id, making this
        path unreachable. Do not extend this heuristic — replace it.
        """
        if require_user_key and not user_key:
            # Multi-user instance with no idea who is asking: claiming here
            # could only ever hand one person another person's context.
            return None

        cutoff = _iso(_now() - timedelta(seconds=ttl_seconds))
        with self._lock, self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            clauses = ["session_id IS NULL", "created_at >= ?"]
            params: list[Any] = [cutoff]
            if user_key:
                # Exact match only. ``user_key IS NULL`` used to qualify too,
                # which let an unattributed context cross accounts.
                clauses.append("user_key = ?")
                params.append(user_key)
            row = connection.execute(
                f"""
                SELECT * FROM external_context
                WHERE {' AND '.join(clauses)}
                ORDER BY created_at DESC LIMIT 1
                """,
                params,
            ).fetchone()
            if row is None:
                return None
            connection.execute(
                "UPDATE external_context SET session_id = ?, bound_at = ? WHERE context_id = ?",
                (session_id, _iso(_now()), row["context_id"]),
            )
        return self._row_to_context(row)

    def resolve_context_for_session(
        self,
        session_id: str,
        *,
        user_key: str | None = None,
        require_user_key: bool = False,
        ttl_seconds: int = 86400,
    ) -> ExternalContext | None:
        existing = self.context_for_session(session_id)
        if existing is not None:
            return existing
        return self.claim_unbound_context(
            session_id,
            user_key=user_key,
            require_user_key=require_user_key,
            ttl_seconds=ttl_seconds,
        )

    @staticmethod
    def _row_to_context(row: sqlite3.Row) -> ExternalContext:
        return ExternalContext(
            protocol_version=row["protocol_version"],
            context_id=row["context_id"],
            context_type=row["context_type"],
            payload=json.loads(row["payload_json"]),
        )

    # ----------------------------------------------------------------- outbox

    def enqueue_event(self, event_id: str, body: dict[str, Any]) -> bool:
        """Queue an event for delivery. Returns False if already queued."""
        now = _iso(_now())
        with self._connection() as connection:
            cursor = connection.execute(
                """
                INSERT OR IGNORE INTO external_event_outbox (
                    event_id, body_json, attempts, next_attempt_at, created_at
                ) VALUES (?, ?, 0, ?, ?)
                """,
                (event_id, json.dumps(body, ensure_ascii=False), now, now),
            )
            return cursor.rowcount == 1

    def due_events(self, limit: int = 20) -> list[tuple[str, dict[str, Any], int]]:
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT event_id, body_json, attempts FROM external_event_outbox
                WHERE delivered_at IS NULL
                  AND dead_lettered_at IS NULL
                  AND next_attempt_at <= ?
                ORDER BY created_at ASC LIMIT ?
                """,
                (_iso(_now()), limit),
            ).fetchall()
        return [(r["event_id"], json.loads(r["body_json"]), r["attempts"]) for r in rows]

    def mark_delivered(self, event_id: str) -> None:
        with self._connection() as connection:
            connection.execute(
                """
                UPDATE external_event_outbox
                SET delivered_at = ?, last_error = NULL
                WHERE event_id = ?
                """,
                (_iso(_now()), event_id),
            )

    def mark_failed(self, event_id: str, error: str, retry_after_seconds: float) -> None:
        with self._connection() as connection:
            connection.execute(
                """
                UPDATE external_event_outbox
                SET attempts = attempts + 1,
                    next_attempt_at = ?,
                    last_error = ?
                WHERE event_id = ?
                """,
                (
                    _iso(_now() + timedelta(seconds=retry_after_seconds)),
                    error[:500],
                    event_id,
                ),
            )

    def mark_dead_lettered(self, event_id: str, error: str) -> None:
        """Stop retrying, keep the row. Visible as its own state, not as a
        delivery scheduled implausibly far in the future."""
        with self._connection() as connection:
            connection.execute(
                """
                UPDATE external_event_outbox
                SET dead_lettered_at = ?, attempts = attempts + 1, last_error = ?
                WHERE event_id = ?
                """,
                (_iso(_now()), error[:500], event_id),
            )

    def outbox_stats(self) -> dict[str, int]:
        with self._connection() as connection:
            row = connection.execute(
                """
                SELECT
                    COUNT(*) AS total,
                    SUM(CASE WHEN delivered_at IS NOT NULL THEN 1 ELSE 0 END) AS delivered,
                    SUM(CASE WHEN delivered_at IS NULL AND dead_lettered_at IS NOT NULL
                        THEN 1 ELSE 0 END) AS dead_lettered
                FROM external_event_outbox
                """
            ).fetchone()
        total = int(row["total"] or 0)
        delivered = int(row["delivered"] or 0)
        dead_lettered = int(row["dead_lettered"] or 0)
        return {
            "total": total,
            "delivered": delivered,
            "dead_lettered": dead_lettered,
            "pending": total - delivered - dead_lettered,
        }


_STORE: ExternalIntegrationStore | None = None


def get_external_store() -> ExternalIntegrationStore:
    global _STORE
    if _STORE is None:
        path = get_path_service().get_user_root() / "external_integration.db"
        _STORE = ExternalIntegrationStore(path)
    return _STORE
