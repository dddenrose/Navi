import { useEffect, useRef } from "react";
import { useReducedMotion } from "@/lib/useReducedMotion";

interface ParticleFieldProps {
  /** 粒子密度倍率，預設 1（桌機基準 ~55 顆／行動裝置（<768px）~30 顆）。 */
  density?: number;
  /** 是否啟用滑鼠聚合互動；預設 false（純 ambient 背景漂移）。 */
  interactive?: boolean;
  className?: string;
}

interface Dot {
  x: number;
  y: number;
  /** ambient 漂移的錨點（home position），聚合後靠這個緩慢歸位。 */
  hx: number;
  hy: number;
  vx: number;
  vy: number;
  r: number;
  color: string;
  alpha: number;
  phase: number;
}

const COLORS = ["#3e7bfa", "#27c0e8", "#8f7bff", "#ff7a85"];
const MOBILE_BREAKPOINT = 768;
const DESKTOP_COUNT = 55;
const MOBILE_COUNT = 30;
const AGGREGATE_RADIUS = 140;
const AGGREGATE_LERP = 0.04;
const HOMING_LERP = 0.01;
const DRIFT_RANGE = 0.3; // → vx/vy 落在 ±0.15px/frame

function createDots(width: number, height: number, count: number): Dot[] {
  return Array.from({ length: count }, () => {
    const x = Math.random() * width;
    const y = Math.random() * height;
    return {
      x,
      y,
      hx: x,
      hy: y,
      vx: (Math.random() - 0.5) * DRIFT_RANGE,
      vy: (Math.random() - 0.5) * DRIFT_RANGE,
      r: 1 + Math.random() * 1.5,
      color: COLORS[(Math.random() * COLORS.length) | 0],
      alpha: 0.25 + Math.random() * 0.25,
      phase: Math.random() * Math.PI * 2,
    };
  });
}

/**
 * 2D canvas 粒子背景：ambient 漫游 + 選擇性滑鼠聚合。
 * 不畫粒子連線（神經網路連線圖是 AI 陳腔濫調，見設計研究結論）。
 */
export default function ParticleField({
  density = 1,
  interactive = false,
  className,
}: ParticleFieldProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const reducedMotion = useReducedMotion();

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const context = canvas.getContext("2d");
    if (!context) return;
    // TS narrowing above doesn't propagate into nested function declarations
    // below (known limitation), so rebind as explicitly non-null locals.
    const canvasEl: HTMLCanvasElement = canvas;
    const ctx: CanvasRenderingContext2D = context;

    let width = 0;
    let height = 0;
    let dots: Dot[] = [];
    let rafId: number | null = null;
    let pointer: { x: number; y: number } | null = null;

    function resize() {
      const rect = canvasEl.getBoundingClientRect();
      width = rect.width;
      height = rect.height;
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      canvasEl.width = Math.round(width * dpr);
      canvasEl.height = Math.round(height * dpr);
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      if (width === 0 || height === 0) {
        // Layout not settled yet — seeding now would pile every dot at the
        // origin. Bail and let the ResizeObserver (or the in-frame guard
        // below) reseed once the canvas has a real size.
        dots = [];
        return;
      }
      const base = width < MOBILE_BREAKPOINT ? MOBILE_COUNT : DESKTOP_COUNT;
      const count = Math.max(0, Math.round(base * density));
      dots = createDots(width, height, count);
    }

    function drawFrame(t: number) {
      ctx.clearRect(0, 0, width, height);
      for (const d of dots) {
        if (pointer) {
          const dx = pointer.x - d.x;
          const dy = pointer.y - d.y;
          if (dx * dx + dy * dy < AGGREGATE_RADIUS * AGGREGATE_RADIUS) {
            d.x += dx * AGGREGATE_LERP;
            d.y += dy * AGGREGATE_LERP;
          } else {
            d.x += (d.hx - d.x) * HOMING_LERP + d.vx;
            d.y += (d.hy - d.y) * HOMING_LERP + d.vy;
          }
        } else {
          d.x += d.vx;
          d.y += d.vy;
        }
        if (d.x < -8) d.x = width + 8;
        if (d.x > width + 8) d.x = -8;
        if (d.y < -8) d.y = height + 8;
        if (d.y > height + 8) d.y = -8;

        const twinkle = 0.7 + 0.3 * Math.sin(t / 1400 + d.phase);
        ctx.globalAlpha = d.alpha * twinkle;
        ctx.fillStyle = d.color;
        ctx.beginPath();
        ctx.arc(d.x, d.y, d.r, 0, Math.PI * 2);
        ctx.fill();

        ctx.globalAlpha = d.alpha * twinkle * 0.28;
        ctx.beginPath();
        ctx.arc(d.x, d.y, d.r * 3.2, 0, Math.PI * 2);
        ctx.fill();
      }
      ctx.globalAlpha = 1;
    }

    function frame(t: number) {
      if (width === 0 || height === 0) resize();
      drawFrame(t);
      rafId = requestAnimationFrame(frame);
    }

    function handlePointerMove(e: PointerEvent) {
      const rect = canvasEl.getBoundingClientRect();
      pointer = { x: e.clientX - rect.left, y: e.clientY - rect.top };
    }
    function handlePointerLeave() {
      pointer = null;
    }
    function handleVisibilityChange() {
      if (document.hidden) {
        if (rafId != null) cancelAnimationFrame(rafId);
        rafId = null;
      } else if (rafId == null) {
        rafId = requestAnimationFrame(frame);
      }
    }

    resize();
    const observer = new ResizeObserver(() => {
      resize();
      if (reducedMotion) drawFrame(0);
    });
    observer.observe(canvasEl);

    if (reducedMotion) {
      drawFrame(0);
    } else {
      if (interactive) {
        canvasEl.addEventListener("pointermove", handlePointerMove);
        canvasEl.addEventListener("pointerleave", handlePointerLeave);
      }
      document.addEventListener("visibilitychange", handleVisibilityChange);
      rafId = requestAnimationFrame(frame);
    }

    return () => {
      observer.disconnect();
      if (rafId != null) cancelAnimationFrame(rafId);
      canvasEl.removeEventListener("pointermove", handlePointerMove);
      canvasEl.removeEventListener("pointerleave", handlePointerLeave);
      document.removeEventListener("visibilitychange", handleVisibilityChange);
    };
  }, [density, interactive, reducedMotion]);

  return (
    <canvas
      ref={canvasRef}
      aria-hidden="true"
      className={className}
      style={{
        display: "block",
        // canvas is a replaced element: `absolute inset-0` alone won't
        // stretch it (intrinsic 300x150 wins), so fill the box explicitly.
        width: "100%",
        height: "100%",
        pointerEvents: interactive ? "auto" : "none",
      }}
    />
  );
}
