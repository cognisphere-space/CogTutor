/**
 * Client side half of the external viewer embed (see
 * `deeptutor/integrations/external/router.py`'s `/viewer/*` endpoints).
 *
 * The viewer is a generic, opaque iframe: this module only fetches its
 * config and bootstraps it with a `context_id`. It never inspects what the
 * iframe renders or sends it anything beyond that one bootstrap message —
 * there is no "navigate the viewer" channel. The only thing the viewer can
 * do back is post a `selection_changed` message, which
 * `SessionViewerPanel.tsx` forwards to `/context/payload` verbatim.
 */

import { apiFetch, apiUrl } from "@/lib/api";

export const VIEWER_PROTOCOL_VERSION = "1";

export interface ExternalViewerConfig {
  enabled: boolean;
  url: string;
  title: string;
  allowedOrigin: string;
  sandbox: string;
}

/** Fetches the deployment's viewer config. Disabled unless a deployment sets it. */
export async function fetchExternalViewerConfig(): Promise<ExternalViewerConfig | null> {
  try {
    const res = await apiFetch(apiUrl("/api/v1/external/viewer/config"), {
      skipAuthRedirect: true,
    });
    if (!res.ok) return null;
    const data = await res.json();
    return {
      enabled: Boolean(data.enabled),
      url: String(data.url ?? ""),
      title: String(data.title ?? ""),
      allowedOrigin: String(data.allowed_origin ?? ""),
      sandbox: String(data.sandbox ?? ""),
    };
  } catch {
    return null;
  }
}

/**
 * Fetches this browser's own `context_id`, if it went through a handoff.
 * The only endpoint that hands the id to frontend JS — needed to bootstrap
 * the cross-origin viewer iframe via `postMessage`, which can't happen
 * without the value passing through JS once.
 */
export async function fetchExternalViewerContextId(): Promise<string | null> {
  try {
    const res = await apiFetch(apiUrl("/api/v1/external/viewer/handle"), {
      skipAuthRedirect: true,
    });
    if (!res.ok) return null;
    const data = await res.json();
    return typeof data.context_id === "string" ? data.context_id : null;
  } catch {
    return null;
  }
}

/** Only the latest selection matters, so a burst collapses to its last frame. */
const SELECTION_PUSH_DEBOUNCE_MS = 200;

let selectionPushTimer: ReturnType<typeof setTimeout> | null = null;
let pendingSelection: Record<string, unknown> | null = null;

function postSelection(payload: Record<string, unknown>): void {
  apiFetch(apiUrl("/api/v1/external/context/payload"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ payload }),
    skipAuthRedirect: true,
  }).catch(() => {
    // Nothing to recover to — best-effort push, chat is unaffected.
  });
}

/**
 * Forwards the viewer's opaque `selection_changed` payload to this session's
 * stored context. Best-effort: a failure here just means the next turn's
 * prompt (if configured to use context) sees stale state, not a break.
 *
 * Debounced because the viewer decides how often it speaks: dragging through
 * a graph can emit a message per frame, and the endpoint it lands on rewrites
 * a database row each time. Only the last one is the current selection, so
 * intermediate ones are dropped rather than queued.
 *
 * A non-object payload is dropped outright — the endpoint requires an object
 * and would 422, and `.catch` here swallows that into silence.
 */
export function pushExternalViewerSelection(payload: unknown): void {
  const isPlainObject =
    typeof payload === "object" && payload !== null && !Array.isArray(payload);
  if (!isPlainObject) return;

  pendingSelection = payload as Record<string, unknown>;
  if (selectionPushTimer !== null) clearTimeout(selectionPushTimer);
  selectionPushTimer = setTimeout(() => {
    selectionPushTimer = null;
    const next = pendingSelection;
    pendingSelection = null;
    if (next) postSelection(next);
  }, SELECTION_PUSH_DEBOUNCE_MS);
}
