import { useId } from "react";

/**
 * Navi 品牌標記：四芒羅盤星 + signature 四色漸層。
 * 全站 signature 漸層限用 3 處之一（另二為 Dashboard 問候名字、
 * Login 卡頂 hairline），因此漸層寫在 mark 本身而非外部 class。
 */
export default function NaviLogo({ size = 24 }: { size?: number }) {
  const gradientId = useId();

  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 48 48"
      role="img"
      aria-label="Navi"
    >
      <defs>
        <linearGradient id={gradientId} x1="0%" y1="100%" x2="100%" y2="0%">
          <stop offset="0%" stopColor="#3e7bfa" />
          <stop offset="32%" stopColor="#27c0e8" />
          <stop offset="66%" stopColor="#8f7bff" />
          <stop offset="100%" stopColor="#ff7a85" />
        </linearGradient>
      </defs>
      <path
        d="M24 5 L28.5 19.5 L43 24 L28.5 28.5 L24 43 L19.5 28.5 L5 24 L19.5 19.5 Z"
        fill={`url(#${gradientId})`}
      />
      <circle cx="24" cy="24" r="3.2" fill="var(--bg-surface)" />
    </svg>
  );
}
