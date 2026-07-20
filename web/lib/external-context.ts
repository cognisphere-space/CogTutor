/**
 * Client side half of the external context handoff (see
 * `deeptutor/integrations/external/router.py`).
 *
 * `/handoff/complete` redirects here with `?external_context_pending=1` when
 * it stored a context for this browser. The actual context id lives only in
 * an httponly cookie — this module never sees it — so all it does is
 * remember "there is something to bind" across the redirect, then hand that
 * fact to whichever code learns the new session id first, once, and never
 * again after that.
 */

import { apiFetch, apiUrl } from "@/lib/api";

const PENDING_PARAM = "external_context_pending";
const PENDING_STORAGE_KEY = "dt_external_context_pending";

/**
 * Call once on app start. If the landing URL carries the marker, record it
 * for `bindPendingExternalContext` and strip it from the visible URL so it
 * doesn't linger in history or get shared in a copied link.
 */
export function capturePendingExternalContextMarker(): void {
  if (typeof window === "undefined") return;
  const url = new URL(window.location.href);
  if (url.searchParams.get(PENDING_PARAM) !== "1") return;

  try {
    window.sessionStorage.setItem(PENDING_STORAGE_KEY, "1");
  } catch {
    // sessionStorage may be unavailable (e.g. private browsing); nothing to
    // recover to, the claim heuristic fallback still runs server-side.
    return;
  }
  url.searchParams.delete(PENDING_PARAM);
  window.history.replaceState(null, "", url.pathname + url.search + url.hash);
}

/**
 * Call whenever a session id becomes known for the first time. No-ops
 * unless `capturePendingExternalContextMarker` saw the marker earlier in
 * this browsing session, and only ever fires once — the flag is cleared
 * before the request goes out, not after, so a slow or failed request
 * can't be retried into binding a second, unrelated session.
 *
 * Best-effort: this only upgrades the server's claim-heuristic fallback to
 * an explicit fact (see `claim_unbound_context` in the CogTutor store). A
 * failure here leaves that fallback in place rather than breaking chat.
 */
export function bindPendingExternalContext(sessionId: string): void {
  if (typeof window === "undefined" || !sessionId) return;
  try {
    if (window.sessionStorage.getItem(PENDING_STORAGE_KEY) !== "1") return;
    window.sessionStorage.removeItem(PENDING_STORAGE_KEY);
  } catch {
    // sessionStorage may be unavailable; nothing was captured, so nothing
    // to bind here either — the claim heuristic fallback still runs.
    return;
  }

  apiFetch(apiUrl("/api/v1/external/context/bind"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_id: sessionId }),
    skipAuthRedirect: true,
  }).catch(() => {
    // Nothing to recover to: the marker is already consumed and the
    // fallback claim heuristic still runs server-side on the first turn.
  });
}
