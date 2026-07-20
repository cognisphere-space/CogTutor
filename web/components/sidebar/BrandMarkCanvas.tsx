"use client";

/**
 * Decorative, non-interactive point-cloud renderer for the sidebar brand
 * mark (see `hooks/useExternalBrandMark.ts` and
 * `deeptutor/integrations/external/router.py`'s `/brand/config`).
 *
 * Both variants draw the same thing — a dark sphere disc, a soft outer
 * atmosphere glow, a rim highlight, and bright points rotating on the
 * surface — just at different sizes: "icon" for the collapsed rail's logo
 * slot, "square" for the expanded header.
 *
 * Pure canvas + rAF, no dependency beyond the point data — this runs
 * continuously for as long as the sidebar is mounted (effectively the whole
 * app), so it deliberately stays cheap: a couple of radial gradients and a
 * few dozen small dots per frame, no offscreen buffers, no libraries.
 */

import { useEffect, useRef } from "react";
import type { BrandPoint } from "@/lib/external-brand";

interface BrandMarkCanvasProps {
  variant: "icon" | "square";
  points: BrandPoint[];
  className?: string;
}

const SIZE: Record<BrandMarkCanvasProps["variant"], number> = {
  icon: 28,
  square: 48,
};
// Icon dots read cluttered at the same absolute size as the square variant's
// — the icon packs the same point count into a much smaller sphere.
const DOT_SCALE: Record<BrandMarkCanvasProps["variant"], number> = {
  icon: 0.55,
  square: 1,
};
const ROTATE_RAD_PER_SEC = 0.22;
const DOT_COLOR = "180, 210, 255";
const SPHERE_DARK_CENTER = "rgba(24, 32, 56, 0.95)";
const SPHERE_DARK_EDGE = "rgba(6, 9, 18, 0.98)";
const HALO_COLOR = "88, 122, 210";
const RIM_COLOR = "190, 212, 255";

export function BrandMarkCanvas({ variant, points, className }: BrandMarkCanvasProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || points.length === 0) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const size = SIZE[variant];
    const dotScale = DOT_SCALE[variant];
    const dpr = typeof window !== "undefined" ? window.devicePixelRatio || 1 : 1;
    canvas.width = size * dpr;
    canvas.height = size * dpr;
    canvas.style.width = `${size}px`;
    canvas.style.height = `${size}px`;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

    let raf = 0;
    let cancelled = false;
    const start = performance.now();
    const cx = size / 2;
    const cy = size / 2;
    // Leaves headroom for the atmosphere halo to bleed past the sphere edge
    // without the gradient's visible portion getting clipped by the canvas.
    const radius = size * 0.4;
    const haloRadius = radius * 1.45;

    function draw(now: number) {
      const t = (now - start) / 1000;
      const angle = t * ROTATE_RAD_PER_SEC;
      const cosA = Math.cos(angle);
      const sinA = Math.sin(angle);
      const lightX = cx - radius * 0.35;
      const lightY = cy - radius * 0.35;

      ctx!.clearRect(0, 0, size, size);

      // Outer atmosphere glow, drawn first so the sphere body sits on top of
      // it and only the halo's bleed past the rim stays visible.
      const halo = ctx!.createRadialGradient(cx, cy, radius * 0.8, cx, cy, haloRadius);
      halo.addColorStop(0, `rgba(${HALO_COLOR}, 0.22)`);
      halo.addColorStop(0.65, `rgba(${HALO_COLOR}, 0.08)`);
      halo.addColorStop(1, `rgba(${HALO_COLOR}, 0)`);
      ctx!.beginPath();
      ctx!.arc(cx, cy, haloRadius, 0, Math.PI * 2);
      ctx!.fillStyle = halo;
      ctx!.fill();

      // Dark sphere body, lit slightly off-center for a bit of volume.
      const body = ctx!.createRadialGradient(lightX, lightY, radius * 0.1, cx, cy, radius);
      body.addColorStop(0, SPHERE_DARK_CENTER);
      body.addColorStop(1, SPHERE_DARK_EDGE);
      ctx!.beginPath();
      ctx!.arc(cx, cy, radius, 0, Math.PI * 2);
      ctx!.fillStyle = body;
      ctx!.fill();

      // Rim highlight along the lit edge — a thin brighter arc, not a full
      // stroke, so the sphere reads as lit from the same corner as the body
      // gradient rather than outlined all the way round.
      ctx!.beginPath();
      ctx!.arc(cx, cy, radius - 0.4, (-3 * Math.PI) / 4, -Math.PI / 4);
      ctx!.strokeStyle = `rgba(${RIM_COLOR}, 0.4)`;
      ctx!.lineWidth = 1;
      ctx!.stroke();

      const rotated = points
        .map((p) => ({
          x: p.x * cosA - p.z * sinA,
          y: p.y,
          z: p.x * sinA + p.z * cosA,
          weight: p.weight,
        }))
        .sort((a, b) => a.z - b.z);

      for (const p of rotated) {
        const depth = (p.z + 1) / 2; // 0..1, far..near
        const px = cx + p.x * radius;
        const py = cy - p.y * radius;
        const twinkle = 0.85 + 0.15 * Math.sin(t * 1.8 + p.x * 11 + p.y * 7);
        const dotSize = (0.5 + depth * 0.9 + p.weight * 0.45) * twinkle * dotScale;
        const alpha = (0.35 + depth * 0.55) * twinkle;
        ctx!.beginPath();
        ctx!.arc(px, py, dotSize, 0, Math.PI * 2);
        ctx!.fillStyle = `rgba(${DOT_COLOR}, ${alpha.toFixed(3)})`;
        ctx!.fill();
      }

      if (!cancelled) raf = requestAnimationFrame(draw);
    }

    raf = requestAnimationFrame(draw);
    return () => {
      cancelled = true;
      cancelAnimationFrame(raf);
    };
  }, [variant, points]);

  if (points.length === 0) return null;

  return <canvas ref={canvasRef} className={className} aria-hidden="true" />;
}
