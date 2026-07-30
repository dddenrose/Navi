import { useEffect, useRef, useState } from "react";
import { useReducedMotion } from "./useReducedMotion";

interface UseCountUpOptions {
  /** 動畫時長（ms），預設 700ms（全站 count-up 動效正典）。 */
  duration?: number;
  /** 數值 → 顯示字串的格式化函式，預設四捨五入 + zh-TW 千分位。 */
  format?: (value: number) => string;
}

function easeOutCubic(p: number): number {
  return 1 - Math.pow(1 - p, 3);
}

const defaultFormat = (value: number): string =>
  Math.round(value).toLocaleString("zh-TW");

/**
 * 數字進場 count-up：rAF 驅動、700ms easeOutCubic。
 * - target 變更時從目前顯示值滑到新值（不會從頭重跑）。
 * - reduced-motion 時直接回傳 format(target)，不進場動畫。
 * - unmount / 依賴變更時取消未完成的 rAF。
 */
export function useCountUp(
  target: number,
  opts: UseCountUpOptions = {},
): string {
  const { duration = 700, format = defaultFormat } = opts;
  const reducedMotion = useReducedMotion();
  const [display, setDisplay] = useState(() => (reducedMotion ? target : 0));
  const valueRef = useRef(display);
  const rafRef = useRef<number | null>(null);

  useEffect(() => {
    if (rafRef.current != null) {
      cancelAnimationFrame(rafRef.current);
      rafRef.current = null;
    }

    if (reducedMotion) {
      // 不在 effect 內同步 setState（觸發連鎖 render，react-hooks/set-state-in-effect
      // 會擋下）；改為只同步 ref，實際顯示值在下方 return 時直接繞過 state 衍生。
      valueRef.current = target;
      return;
    }

    const from = valueRef.current;
    const delta = target - from;
    if (delta === 0) return;

    const start = performance.now();

    const tick = (now: number) => {
      const p = Math.min((now - start) / duration, 1);
      const value = from + delta * easeOutCubic(p);
      valueRef.current = value;
      setDisplay(value);
      rafRef.current = p < 1 ? requestAnimationFrame(tick) : null;
    };

    rafRef.current = requestAnimationFrame(tick);

    return () => {
      if (rafRef.current != null) {
        cancelAnimationFrame(rafRef.current);
        rafRef.current = null;
      }
    };
  }, [target, duration, reducedMotion]);

  return format(reducedMotion ? target : display);
}
