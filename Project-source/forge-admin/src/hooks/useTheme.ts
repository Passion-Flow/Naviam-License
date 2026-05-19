import * as React from "react";

import { applyTheme, loadStoredTheme, setTheme, type ThemeMode } from "@/lib/theme/theme";

/**
 * React 视图层主题钩子：
 * - 持久化在 localStorage，由 `lib/theme/theme.ts` 实现
 * - mode === "system" 时跟随 prefers-color-scheme，订阅其变化即时切换
 * - SSR 安全：未挂载时返回 stored 值；不直接操作 window 之前先 useEffect
 */
export function useTheme(): {
  mode: ThemeMode;
  setMode: (next: ThemeMode) => void;
} {
  const [mode, setModeState] = React.useState<ThemeMode>(() => loadStoredTheme());

  // 当 mode === "system" 时跟随系统切换（不需要每次重新计算 stored）
  React.useEffect(() => {
    if (mode !== "system") return;
    const mql = window.matchMedia("(prefers-color-scheme: dark)");
    const handler = () => applyTheme("system");
    mql.addEventListener("change", handler);
    return () => mql.removeEventListener("change", handler);
  }, [mode]);

  const update = React.useCallback((next: ThemeMode) => {
    setTheme(next);
    setModeState(next);
  }, []);

  return { mode, setMode: update };
}
