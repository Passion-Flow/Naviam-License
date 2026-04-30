# apps/web - License Console (Next.js 14)

## 启动

```bash
cd apps/web
pnpm install
pnpm dev
```

默认 `http://127.0.0.1:3000`。

## 关键约束

- 仅 HttpOnly Cookie 鉴权；任何 token 不进入 `localStorage` / `sessionStorage`。
- 表单写操作必须带 CSRF Token（来自 cookie + `X-CSRFToken` header）。
- CSP 严格策略由 `next.config.js` 输出。
- 默认明 / 暗 / 跟随系统三档。
- 单文件组件不建目录；详见 `docs/design/04-目录设计.md`。

## 目录

```text
apps/web/
  package.json
  next.config.js
  tsconfig.json
  tailwind.config.ts
  postcss.config.js
  src/
    app/
      layout.tsx
      page.tsx
      (auth)/login/page.tsx
      (dashboard)/
        layout.tsx
        licenses/page.tsx
        customers/page.tsx
        products/page.tsx
        audit/page.tsx
        notifications/page.tsx
        settings/page.tsx
    components/
    lib/
    hooks/
    types/
    styles/
```
