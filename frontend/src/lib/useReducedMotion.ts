import { useEffect, useState } from "react";

const QUERY = "(prefers-reduced-motion: reduce)";

/** 使用者是否偏好減少動效（OS 層級設定）；SSR 安全，掛載後才讀取。 */
export function useReducedMotion(): boolean {
  const [reduced, setReduced] = useState(
    () => typeof window !== "undefined" && window.matchMedia(QUERY).matches,
  );

  useEffect(() => {
    const mql = window.matchMedia(QUERY);
    const onChange = () => setReduced(mql.matches);
    onChange();
    mql.addEventListener("change", onChange);
    return () => mql.removeEventListener("change", onChange);
  }, []);

  return reduced;
}
