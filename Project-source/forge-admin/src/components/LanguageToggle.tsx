import { LOCALES, useI18n } from "@/lib/i18n";
import { cn } from "@/lib/cn";

/**
 * 与 ThemeToggle 同款分段切换器；en / zh-CN 两态。
 */
export function LanguageToggle() {
  const { locale, setLocale, t } = useI18n();

  return (
    <div
      role="radiogroup"
      aria-label={t("settings.language")}
      className="inline-flex rounded-lg border border-border bg-bg p-0.5"
    >
      {LOCALES.map((opt) => (
        <button
          key={opt.value}
          role="radio"
          aria-checked={locale === opt.value}
          aria-label={opt.label}
          title={opt.label}
          onClick={() => setLocale(opt.value)}
          className={cn(
            "rounded-md px-2.5 py-1 text-xs transition-soft",
            locale === opt.value
              ? "bg-primary text-primary-foreground"
              : "text-fg/70 hover:bg-muted",
          )}
          type="button"
        >
          {opt.label}
        </button>
      ))}
    </div>
  );
}
