import * as React from "react";

import { cn } from "@/lib/cn";

type ToastTone = "info" | "success" | "error";

interface ToastEntry {
  id: number;
  tone: ToastTone;
  message: string;
}

interface ToastContextValue {
  show: (message: string, tone?: ToastTone) => void;
}

const ToastContext = React.createContext<ToastContextValue | null>(null);

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [items, setItems] = React.useState<ToastEntry[]>([]);
  const nextId = React.useRef(1);

  const show = React.useCallback((message: string, tone: ToastTone = "info") => {
    const id = nextId.current++;
    setItems((prev) => [...prev, { id, tone, message }]);
    window.setTimeout(() => {
      setItems((prev) => prev.filter((t) => t.id !== id));
    }, 4000);
  }, []);

  const ctx = React.useMemo(() => ({ show }), [show]);

  return (
    <ToastContext.Provider value={ctx}>
      {children}
      <div className="pointer-events-none fixed bottom-6 right-6 z-50 flex w-full max-w-sm flex-col gap-2">
        {items.map((t) => (
          <div
            key={t.id}
            role="status"
            className={cn(
              "pointer-events-auto rounded-xl border border-border bg-bg px-4 py-3 text-sm shadow-md transition-soft",
              t.tone === "success" && "border-primary/40 text-primary",
              t.tone === "error" && "border-red-500/40 text-red-600",
              t.tone === "info" && "text-fg/80",
            )}
          >
            {t.message}
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast(): ToastContextValue {
  const ctx = React.useContext(ToastContext);
  if (!ctx) throw new Error("useToast must be used inside <ToastProvider>");
  return ctx;
}
