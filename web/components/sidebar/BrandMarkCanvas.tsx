"use client";

/**
 * Decorative point-cloud renderer for the sidebar brand mark (see
 * `hooks/useExternalBrandMark.ts` and `/brand/config`).
 *
 * Dark sphere + atmosphere glow + rim + rotating surface points.
 * Cheap canvas + rAF; pauses when the tab is hidden; freezes to one frame
 * when prefers-reduced-motion is set.
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
    const radius = size * 0.4;
    const haloRadius = radius * 1.45;

    const reduceMotion =
      typeof window !== "undefined" &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    function paint(now: number) {
      const t = reduceMotion ? 0 : (now - start) / 1000;
      const angle = t * ROTATE_RAD_PER_SEC;
      const cosA = Math.cos(angle);
      const sinA = Math.sin(angle);
      const lightX = cx - radius * 0.35;
      const lightY = cy - radius * 0.35;

      ctx!.clearRect(0, 0, size, size);

      const halo = ctx!.createRadialGradient(cx, cy, radius * 0.8, cx, cy, haloRadius);
      halo.addColorStop(0, `rgba(${HALO_COLOR}, 0.22)`);
      halo.addColorStop(0.65, `rgba(${HALO_COLOR}, 0.08)`);
      halo.addColorStop(1, `rgba(${HALO_COLOR}, 0)`);
      ctx!.beginPath();
      ctx!.arc(cx, cy, haloRadius, 0, Math.PI * 2);
      ctx!.fillStyle = halo;
      ctx!.fill();

      const body = ctx!.createRadialGradient(lightX, lightY, radius * 0.1, cx, cy, radius);
      body.addColorStop(0, SPHERE_DARK_CENTER);
      body.addColorStop(1, SPHERE_DARK_EDGE);
      ctx!.beginPath();
      ctx!.arc(cx, cy, radius, 0, Math.PI * 2);
      ctx!.fillStyle = body;
      ctx!.fill();

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
        const depth = (p.z + 1) / 2;
        const px = cx + p.x * radius;
        const py = cy - p.y * radius;
        const twinkle = reduceMotion
          ? 1
          : 0.85 + 0.15 * Math.sin(t * 1.8 + p.x * 11 + p.y * 7);
        const dotSize = (0.5 + depth * 0.9 + p.weight * 0.45) * twinkle * dotScale;
        const alpha = (0.35 + depth * 0.55) * twinkle;
        ctx!.beginPath();
        ctx!.arc(px, py, dotSize, 0, Math.PI * 2);
        ctx!.fillStyle = `rgba(${DOT_COLOR}, ${alpha.toFixed(3)})`;
        ctx!.fill();
      }
    }

    function tick(now: number) {
      paint(now);
      if (!cancelled && !reduceMotion) raf = requestAnimationFrame(tick);
    }

    function onVisibility() {
      if (cancelled || reduceMotion) return;
      if (document.visibilityState === "hidden") {
        cancelAnimationFrame(raf);
        raf = 0;
      } else if (raf === 0) {
        raf = requestAnimationFrame(tick);
      }
    }

    if (reduceMotion) {
      paint(performance.now());
    } else {
      raf = requestAnimationFrame(tick);
      document.addEventListener("visibilitychange", onVisibility);
    }

    return () => {
      cancelled = true;
      cancelAnimationFrame(raf);
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, [variant, points]);

  if (points.length === 0) return null;

  return <canvas ref={canvasRef} className={className} aria-hidden="true" />;
}
