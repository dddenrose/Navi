import { Component, type ReactNode, type ErrorInfo } from "react";
import { TriangleAlert } from "lucide-react";

interface Props {
  children: ReactNode;
  fallback?: ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

export default class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false, error: null };

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("[ErrorBoundary]", error, info.componentStack);
  }

  render() {
    if (this.state.hasError) {
      if (this.props.fallback) return this.props.fallback;

      return (
        <div className="flex flex-col items-center justify-center min-h-[50vh] px-6 text-center">
          <div
            className="w-14 h-14 rounded-2xl flex items-center justify-center mb-5 text-warn"
            style={{
              background: "color-mix(in srgb, var(--warn) 12%, transparent)",
              border:
                "1px solid color-mix(in srgb, var(--warn) 24%, transparent)",
            }}
          >
            <TriangleAlert size={28} strokeWidth={1.5} aria-hidden="true" />
          </div>
          <h2 className="text-base font-semibold text-ink mb-2">
            發生錯誤
          </h2>
          <p className="text-sm text-ink-muted mb-6 max-w-xs leading-relaxed">
            {this.state.error?.message ?? "頁面載入時發生未預期的錯誤"}
          </p>
          <button
            onClick={() => this.setState({ hasError: false, error: null })}
            className="btn btn-primary"
          >
            重試
          </button>
        </div>
      );
    }

    return this.props.children;
  }
}
