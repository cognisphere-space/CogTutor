/**
 * Client side half of the sidebar brand mark (see
 * `deeptutor/integrations/external/router.py`'s `/brand/config`).
 *
 * `data_url` points at a deployment-owned document of unit-sphere points,
 * fetched directly from the browser (may be cross-origin — CORS is the
 * deployment's concern). Cap + validate points so a bad document cannot
 * pin the main thread.
 */

import { apiFetch, apiUrl } from "@/lib/api";

export interface ExternalBrandConfig {
  enabled: boolean;
  href: string;
  dataUrl: string;
}

export interface BrandPoint {
  x: number;
  y: number;
  z: number;
  weight: number;
}

/** Hard cap — sidebar mark is decorative; denser clouds buy nothing. */
export const BRAND_MARK_MAX_POINTS = 512;

/** Fetches the deployment's brand mark config. Disabled unless a deployment sets it. */
export async function fetchExternalBrandConfig(): Promise<ExternalBrandConfig | null> {
  try {
    const res = await apiFetch(apiUrl("/api/v1/external/brand/config"), {
      skipAuthRedirect: true,
    });
    if (!res.ok) return null;
    const data = await res.json();
    return {
      enabled: Boolean(data.enabled),
      href: String(data.href ?? ""),
      dataUrl: String(data.data_url ?? ""),
    };
  } catch {
    return null;
  }
}

function clamp01(n: number): number {
  if (!Number.isFinite(n)) return 0.5;
  if (n < 0) return 0;
  if (n > 1) return 1;
  return n;
}

/**
 * Only same-app paths and http(s) absolute URLs. Rejects javascript:/data:
 * and other schemes that would be unsafe in a logo <a href>.
 */
export function sanitizeBrandHref(href: string): string | null {
  const raw = href.trim();
  if (!raw) return null;
  if (raw.startsWith("/") && !raw.startsWith("//")) return raw;
  try {
    const u = new URL(raw);
    if (u.protocol === "http:" || u.protocol === "https:") return u.toString();
  } catch {
    return null;
  }
  return null;
}

/** Fetches the point cloud itself, straight from `dataUrl` (not proxied). */
export async function fetchExternalBrandPoints(
  dataUrl: string,
): Promise<BrandPoint[] | null> {
  try {
    const res = await fetch(dataUrl);
    if (!res.ok) return null;
    const data = await res.json();
    const raw = Array.isArray(data?.points) ? data.points : null;
    if (!raw) return null;
    const points: BrandPoint[] = [];
    for (const p of raw) {
      if (points.length >= BRAND_MARK_MAX_POINTS) break;
      if (typeof p !== "object" || p === null) continue;
      const { x, y, z, weight } = p as Record<string, unknown>;
      if (
        typeof x !== "number" ||
        typeof y !== "number" ||
        typeof z !== "number" ||
        !Number.isFinite(x) ||
        !Number.isFinite(y) ||
        !Number.isFinite(z)
      ) {
        continue;
      }
      points.push({
        x,
        y,
        z,
        weight: typeof weight === "number" ? clamp01(weight) : 0.5,
      });
    }
    return points.length > 0 ? points : null;
  } catch {
    return null;
  }
}

export interface BrandMark {
  href: string;
  points: BrandPoint[];
}

/**
 * Combined loader: config + points. Successful marks are cached for the page
 * lifetime (sidebar remounts often). Failed loads leave the cache empty so a
 * later attempt can retry (e.g. viewer host briefly down at first paint).
 */
let cachedBrandMark: Promise<BrandMark | null> | null = null;

export function loadExternalBrandMark(): Promise<BrandMark | null> {
  if (!cachedBrandMark) {
    const pending = (async (): Promise<BrandMark | null> => {
      const config = await fetchExternalBrandConfig();
      if (!config?.enabled || !config.dataUrl || !config.href) return null;
      const href = sanitizeBrandHref(config.href);
      if (!href) return null;
      const points = await fetchExternalBrandPoints(config.dataUrl);
      if (!points) return null;
      return { href, points };
    })();
    cachedBrandMark = pending;
    void pending.then((result) => {
      if (!result) cachedBrandMark = null;
    });
  }
  return cachedBrandMark;
}
