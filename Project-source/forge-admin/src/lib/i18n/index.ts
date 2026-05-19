/**
 * Forge admin i18n — 极简实现，不引入 i18next 等额外依赖。
 *
 * 设计：
 * - 平铺 key（"nav.dashboard"）；不嵌套
 * - 命中策略：当前语言 → en（兜底）→ key 本身
 * - 切换语言写 localStorage，下次访问自动恢复
 * - 占位符语法：t("welcome", { name: "Alice" }) 把 `{name}` 替换
 *
 * 添加新 key：在 locales/en.ts 加，再补 zh-CN.ts。
 */
import * as React from "react";

import { en } from "./locales/en";
import { zhCN } from "./locales/zh-CN";

export type Locale = "en" | "zh-CN";

const DICTS: Record<Locale, Record<string, string>> = {
  en,
  "zh-CN": zhCN,
};

const STORAGE_KEY = "forge.locale";
const FALLBACK: Locale = "en";

function detectLocale(): Locale {
  if (typeof window === "undefined") return FALLBACK;
  const stored = window.localStorage.getItem(STORAGE_KEY) as Locale | null;
  if (stored && DICTS[stored]) return stored;
  const nav = (window.navigator.language || "").toLowerCase();
  if (nav.startsWith("zh")) return "zh-CN";
  return FALLBACK;
}

interface I18nContextValue {
  locale: Locale;
  setLocale: (l: Locale) => void;
  t: (key: string, vars?: Record<string, string | number>) => string;
}

const I18nContext = React.createContext<I18nContextValue | null>(null);

export function I18nProvider({ children }: { children: React.ReactNode }) {
  const [locale, setLocaleState] = React.useState<Locale>(() => detectLocale());

  const setLocale = React.useCallback((next: Locale) => {
    setLocaleState(next);
    if (typeof window !== "undefined") {
      window.localStorage.setItem(STORAGE_KEY, next);
      window.document.documentElement.setAttribute("lang", next);
    }
  }, []);

  const t = React.useCallback(
    (key: string, vars?: Record<string, string | number>): string => {
      const dict = DICTS[locale] || DICTS[FALLBACK];
      const raw = dict[key] ?? DICTS[FALLBACK][key] ?? key;
      if (!vars) return raw;
      return raw.replace(/\{(\w+)\}/g, (_, name) =>
        name in vars ? String(vars[name]) : `{${name}}`,
      );
    },
    [locale],
  );

  const value = React.useMemo<I18nContextValue>(
    () => ({ locale, setLocale, t }),
    [locale, setLocale, t],
  );

  return React.createElement(I18nContext.Provider, { value }, children);
}

export function useI18n(): I18nContextValue {
  const ctx = React.useContext(I18nContext);
  if (!ctx) {
    throw new Error("useI18n must be used inside <I18nProvider />");
  }
  return ctx;
}

export function useT(): I18nContextValue["t"] {
  return useI18n().t;
}

export const LOCALES: { value: Locale; label: string }[] = [
  { value: "zh-CN", label: "中文" },
  { value: "en", label: "English" },
];
