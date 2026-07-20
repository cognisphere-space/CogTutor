/**
 * Client side half of the sidebar brand mark (see
 * `deeptutor/integrations/external/router.py`'s `/brand/config`).
 *
 * Generic and opaque: `data_url` points at a deployment-owned document of
 * unit-sphere points, fetched directly from the browser (it may be
 * cross-origin — CORS is the deployment's concern, not this module's).
 * Nothing here interprets what the points represent.
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
    const points = raw
      .map((p: unknown) => {
        if (typeof p !== "object" || p === null) return null;
        const { x, y, z, weight } = p as Record<string, unknown>;
        if (typeof x !== "number" || typeof y !== "number" || typeof z !== "number") {
          return null;
        }
        return {
          x,
          y,
          z,
          weight: typeof weight === "number" ? weight : 0.5,
        } satisfies BrandPoint;
      })
      .filter((p: BrandPoint | null): p is BrandPoint => p !== null);
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
 * Combined, cached loader: config + points, fetched at most once per page
 * load. The sidebar mounts this on every navigation (it's the app shell),
 * so an uncached version would refetch both endpoints on every route change.
 */
let cachedBrandMark: Promise<BrandMark | null> | null = null;

export function loadExternalBrandMark(): Promise<BrandMark | null> {
  if (!cachedBrandMark) {
    cachedBrandMark = (async () => {
      const config = await fetchExternalBrandConfig();
      if (!config?.enabled || !config.dataUrl || !config.href) return null;
      const points = await fetchExternalBrandPoints(config.dataUrl);
      if (!points) return null;
      return { href: config.href, points };
    })();
  }
  return cachedBrandMark;
}
