"use client";

import { useEffect, useState } from "react";
import { loadExternalBrandMark, type BrandMark } from "@/lib/external-brand";

/**
 * `undefined` while the config/points fetch is in flight, `null` once
 * resolved but disabled/unavailable (no deployment config, or the fetch
 * failed) — callers should fall back to their default brand asset in both
 * the loading and disabled cases, and only swap in the live mark once it
 * resolves to a value.
 */
export function useExternalBrandMark(): BrandMark | null | undefined {
  const [mark, setMark] = useState<BrandMark | null | undefined>(undefined);

  useEffect(() => {
    let cancelled = false;
    loadExternalBrandMark().then((result) => {
      if (!cancelled) setMark(result);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  return mark;
}
