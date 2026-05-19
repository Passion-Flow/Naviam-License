import { useTheme } from "@/hooks/useTheme";
import { useT } from "@/lib/i18n";
import { cn } from "@/lib/cn";
import type { ThemeMode } from "@/lib/theme/theme";

/**
 * Three-mode segmented switch. Label comes from i18n so EN sees Light/System/Dark
 * and 中文 sees 亮色/默认/暗色 — no emoji, plain text per design intent.
 */
export function ThemeToggle() {
  const { mode, setMode } = useTheme();
  const t = useT();

  const options: { value: ThemeMode; label: string }[] = [
    { value: "light", label: t("theme.light") },
    { value: "system", label: t("theme.system") },
    { value: "dark", label: t("theme.dark") },
  ];

  return (
    <div
      role="radiogroup"
      aria-label={t("theme.aria")}
      className="inline-flex rounded-lg border border-border bg-bg p-0.5"
    >
      {options.map((opt) => (
        <button
          key={opt.value}
          role="radio"
          aria-checked={mode === opt.value}
          aria-label={opt.label}
          title={opt.label}
          onClick={() => setMode(opt.value)}
          className={cn(
            "rounded-md px-2.5 py-1 text-xs transition-soft",
            mode === opt.value
              ? "bg-primary text-white"
              : "text-fg/70 hover:bg-muted hover:text-fg",
          )}
          type="button"
        >
          {opt.label}
        </button>
      ))}
    </div>
  );
}
