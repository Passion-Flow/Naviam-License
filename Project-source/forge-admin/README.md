# forge-admin

Forge 厂商后台 —— React + TypeScript + Tailwind + shadcn/ui。

## 启动

```bash
pnpm install        # 或 npm install / yarn
pnpm dev            # http://localhost:13000
```

## 目录布局（features 细粒度）

每个独立操作 / 按钮 = 一个目录。

```
src/
├── main.tsx                       ← 入口（mount React app）
├── App.tsx                        ← 路由根 + ThemeProvider
├── routes/                        ← React Router data router 配置
│
├── features/                      ← 业务功能区，每个独立操作一个目录
│   ├── auth/
│   │   ├── login/                 ← 用户名/密码登录
│   │   ├── logout/
│   │   ├── sso/                   ← SSO 登录入口
│   │   └── reset_password/
│   ├── dashboard/                 ← 总览页
│   ├── customers/
│   │   ├── list/                  ← 客户列表（表格）
│   │   ├── detail/                ← 客户详情（含其名下 license）
│   │   ├── create/                ← 创建客户按钮 + 表单
│   │   ├── update/
│   │   └── delete/
│   ├── products/
│   │   ├── list/  detail/  create/  update/
│   ├── licenses/
│   │   ├── list/                  ← 全部 license 表格 + 筛选
│   │   ├── issue/                 ← 签发：选客户/产品/模式/算法/绑定/过期 → 生成 .forge
│   │   ├── detail/                ← payload 完整字段 + 心跳历史 + 审计
│   │   ├── revoke/                ← 吊销按钮 + 原因表单
│   │   ├── renew/                 ← 续期按钮
│   │   ├── download/              ← 下载 .forge 文件按钮
│   │   └── heartbeat_history/     ← 心跳时间线
│   ├── keys/
│   │   ├── list/  generate/  rotate/  revoke/  export_public/
│   ├── api_keys/
│   │   ├── list/  issue/  revoke/
│   ├── audit/
│   │   └── list/                  ← 审计日志（时间线 + 过滤）
│   └── settings/
│       ├── profile/               ← 当前 admin 的个人设置
│       ├── sso_config/            ← SSO 协议 + IdP 参数配置（可视化）
│       └── theme/                 ← 客户白标主题 / 品牌色配置
│
├── components/
│   ├── ui/                        ← shadcn/ui 拷贝过来的基础组件
│   └── layout/                    ← AppShell / Sidebar / Topbar / PageHeader
│
├── lib/
│   ├── api/                       ← TanStack Query hooks + fetch 封装
│   ├── auth/                      ← session / SSO 工具
│   ├── format/                    ← 时间 / 字节 / 货币 格式化
│   ├── i18n/                      ← 国际化（私有化本地化）
│   └── theme/                     ← Apple 风格 token + 主题切换工具
│
├── hooks/                         ← 跨 feature 的公共 hook
└── types/                         ← 全局类型
```

## 关键约束（继承全局规则）

1. **无硬编码**：API 地址、超时、限流阈值等全部走运行时注入 `window.__APP_CONFIG__`
2. **主题**：4 种模式（亮 / 暗 / 跟系统 / 客户改品牌色）；默认色板 #34C759 + 白/黑
3. **动效**：Apple 风格"轻柔渐隐"，200-300ms ease-out
4. **shadcn/ui 拷贝到 components/ui/**：不作为 npm 依赖
5. **TanStack Query 管服务端状态**；Context + useState 管客户端状态
6. **变更必启 dev server 验证**（与全局 agent-rules 一致）

## 与 forge-server 的边界

- 通过 forge-server 暴露的 `/api/v1/*` 通信
- API 地址在运行时由 `forge-deploy/docker/` 注入到 `window.__APP_CONFIG__.apiBaseUrl`
- **不**直接访问 Service（database / cache / object_storage 都由 forge-server 代理）
