import type { Config } from "tailwindcss";

/**
 * Forge Admin — Tailwind 配置
 *
 * 继承全局 UI 规则：
 * - 默认色板：iOS Green #34C759 + 白 / 黑
 * - 4 主题模式（亮 / 暗 / 系统 / 品牌色客户自定义）走 CSS 变量
 * - 动效：Apple 风格轻柔渐隐 200-300ms ease-out
 *
 * 设计 token 集中此处定义；业务代码禁止写死颜色 / 间距 / 字号。
 */
export default {
  darkMode: ["class", '[data-theme="dark"]'],
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        primary: "hsl(var(--color-primary) / <alpha-value>)",
        bg: "hsl(var(--color-bg) / <alpha-value>)",
        fg: "hsl(var(--color-fg) / <alpha-value>)",
        muted: "hsl(var(--color-muted) / <alpha-value>)",
        border: "hsl(var(--color-border) / <alpha-value>)",
      },
      transitionTimingFunction: {
        "apple-soft": "cubic-bezier(0.25, 0.1, 0.25, 1)",
      },
      transitionDuration: {
        soft: "240ms",
      },
    },
  },
  plugins: [],
} satisfies Config;
