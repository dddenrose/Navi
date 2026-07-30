import {
  useState,
  useEffect,
  useRef,
  useCallback,
  type CSSProperties,
  type KeyboardEvent,
} from "react";
import { searchStocks, type StockSuggestion } from "@/lib/api";

interface TickerAutocompleteProps {
  /** 目前股票代碼輸入值（受控） */
  value: string;
  /** 使用者手動輸入代碼時觸發 */
  onChange: (ticker: string) => void;
  /** 從下拉選單選定（或 blur 完全命中）一檔股票時觸發，用於自動帶出名稱 */
  onSelect: (suggestion: StockSuggestion) => void;
  placeholder?: string;
  required?: boolean;
  className?: string;
  style?: CSSProperties;
  autoFocus?: boolean;
  id?: string;
}

/**
 * 股票代碼輸入框，附即時搜尋下拉（代碼或中文名皆可），
 * 選定後回傳 {code, name, ticker, market} 供呼叫端自動 mapping 名稱。
 * 資料來源：後端 GET /api/stock/search（searchStocks）。
 */
export default function TickerAutocomplete({
  value,
  onChange,
  onSelect,
  placeholder,
  required,
  className,
  style,
  autoFocus,
  id,
}: TickerAutocompleteProps) {
  const [suggestions, setSuggestions] = useState<StockSuggestion[]>([]);
  const [open, setOpen] = useState(false);
  const [highlight, setHighlight] = useState(-1);
  const wrapRef = useRef<HTMLDivElement>(null);
  // 剛用選單/自動命中選定的 ticker 文字，避免立刻又觸發一次搜尋把下拉彈回來
  const lastSelectedRef = useRef<string>("");

  // 點元件外部 → 關閉下拉
  useEffect(() => {
    function onDocMouseDown(e: MouseEvent) {
      if (wrapRef.current && !wrapRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", onDocMouseDown);
    return () => document.removeEventListener("mousedown", onDocMouseDown);
  }, []);

  // debounce 搜尋（250ms）；所有 setState 都在 timeout 回呼內（非同步），
  // 避免在 effect 同步階段更新狀態。
  useEffect(() => {
    const q = value.trim();
    if (q && q === lastSelectedRef.current) return; // 剛選定的值不重搜
    const t = setTimeout(async () => {
      if (!q) {
        setSuggestions([]);
        setHighlight(-1);
        setOpen(false);
        return;
      }
      const res = await searchStocks(q);
      setSuggestions(res);
      setHighlight(-1);
      setOpen(res.length > 0);
    }, q ? 250 : 0);
    return () => clearTimeout(t);
  }, [value]);

  const pick = useCallback(
    (s: StockSuggestion) => {
      lastSelectedRef.current = s.ticker;
      onSelect(s);
      setOpen(false);
      setSuggestions([]);
    },
    [onSelect],
  );

  const handleKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (!open || suggestions.length === 0) return;
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setHighlight((h) => (h + 1) % suggestions.length);
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setHighlight((h) => (h <= 0 ? suggestions.length - 1 : h - 1));
    } else if (e.key === "Enter") {
      if (highlight >= 0 && highlight < suggestions.length) {
        e.preventDefault(); // 阻止表單提交，改為選取
        pick(suggestions[highlight]);
      }
    } else if (e.key === "Escape") {
      setOpen(false);
    }
  };

  // blur 時若輸入值完全命中某筆（代碼/ticker/名稱），自動選定以帶出名稱
  const handleBlur = () => {
    const q = value.trim().toLowerCase();
    if (!q) return;
    const exact = suggestions.find(
      (s) =>
        s.ticker.toLowerCase() === q ||
        s.code.toLowerCase() === q ||
        s.name.toLowerCase() === q,
    );
    if (exact && exact.ticker !== lastSelectedRef.current) {
      pick(exact);
    }
  };

  return (
    <div ref={wrapRef} className="relative">
      <input
        id={id}
        value={value}
        onChange={(e) => {
          lastSelectedRef.current = "";
          onChange(e.target.value);
        }}
        onFocus={() => {
          if (suggestions.length > 0) setOpen(true);
        }}
        onBlur={handleBlur}
        onKeyDown={handleKeyDown}
        placeholder={placeholder}
        required={required}
        autoFocus={autoFocus}
        autoComplete="off"
        className={className}
        style={style}
        role="combobox"
        aria-expanded={open}
        aria-autocomplete="list"
      />
      {open && suggestions.length > 0 && (
        <ul
          className="absolute z-10 mt-1 max-h-60 w-full overflow-auto rounded-xl py-1 text-sm bg-surface border border-line shadow-[var(--shadow-pop)]"
          role="listbox"
        >
          {suggestions.map((s, i) => (
            <li
              key={s.ticker}
              role="option"
              aria-selected={i === highlight}
              onMouseDown={(e) => {
                e.preventDefault(); // 避免先觸發 input blur 導致點擊落空
                pick(s);
              }}
              onMouseEnter={() => setHighlight(i)}
              className="flex cursor-pointer items-center justify-between px-3 py-2"
              style={{
                background: i === highlight ? "var(--surface-2)" : "transparent",
              }}
            >
              <span className="truncate text-ink-strong">
                {s.ticker}
                <span className="ml-2 text-ink-secondary">{s.name}</span>
              </span>
              <span className="ml-2 shrink-0 text-xs text-ink-muted">
                {s.market}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
