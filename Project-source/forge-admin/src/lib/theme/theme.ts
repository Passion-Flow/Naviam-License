/**
 * 主题切换工具 — 支持 4 模式（亮 / 暗 / 跟系统 / 客户改品牌色）。
 * 主题选择持久化到 localStorage，避免 FOUC。
 */

export type ThemeMode = "light" | "dark" | "system";

const STORAGE_KEY = "forge-theme";

export function applyTheme(mode: ThemeMode): void {
  const root = document.documentElement;
  const resolved =
    mode === "system"
      ? window.matchMedia("(prefers-color-scheme: dark)").matches
        ? "dark"
        : "light"
      : mode;
  root.setAttribute("data-theme", resolved);
}

export function loadStoredTheme(): ThemeMode {
  const stored = localStorage.getItem(STORAGE_KEY);
  if (stored === "light" || stored === "dark" || stored === "system") return stored;
  return "system";
}

export function setTheme(mode: ThemeMode): void {
  localStorage.setItem(STORAGE_KEY, mode);
  applyTheme(mode);
}

export function applyBrandPrimary(hsl: string): void {
  // 客户白标改主色：覆盖 --color-primary
  document.documentElement.style.setProperty("--color-primary", hsl);
}
