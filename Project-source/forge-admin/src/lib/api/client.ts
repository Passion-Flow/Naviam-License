/**
 * API 客户端 —— 从 window.__APP_CONFIG__ 取 base URL，禁止硬编码。
 *
 * 业务模块 import 本文件而不是直接用 fetch；统一处理：
 * - 鉴权 Cookie
 * - request_id 注入
 * - 错误结构归一化
 * - 重试 / 超时（项目按需添加）
 *
 * 运行时配置流（HARD RULE: 无硬编码）：
 * 1. index.html 写 `<<APP_API_BASE_URL>>` 等占位符
 * 2. 生产：forge-admin 容器 entrypoint sed 替换占位符为真实 env 值
 * 3. dev：占位符不会被替换，`resolveConfig()` 检测到 `<<` 前缀 → vite 代理默认值
 */

declare global {
  interface Window {
    __APP_CONFIG__: {
      apiBaseUrl: string;
      // 占位符态是 `<<APP_SSO_ENABLED>>` 字符串；替换后是 "true" / "false"
      ssoEnabled: string;
      brandPrimaryHsl: string;
    };
  }
}

function isPlaceholder(value: string | undefined): boolean {
  return !value || value.startsWith("<<");
}

/**
 * 把 window.__APP_CONFIG__ 规整为业务可用的类型。
 * 占位符还在 → 走 dev 默认（仅在 npm run dev 出现；生产 entrypoint 必替换）。
 */
export interface AppConfig {
  apiBaseUrl: string;
  ssoEnabled: boolean;
  brandPrimaryHsl: string;
}

export function resolveConfig(): AppConfig {
  const raw = window.__APP_CONFIG__;
  return {
    apiBaseUrl: isPlaceholder(raw?.apiBaseUrl) ? "/api/v1" : raw.apiBaseUrl,
    ssoEnabled: !isPlaceholder(raw?.ssoEnabled) && raw.ssoEnabled === "true",
    brandPrimaryHsl: isPlaceholder(raw?.brandPrimaryHsl)
      ? "142 70% 49%"
      : raw.brandPrimaryHsl,
  };
}

function generateRequestId(): string {
  // 简易 UUIDv4，避免引入 uuid 依赖
  return crypto.randomUUID();
}

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly code: string | null,
    public readonly requestId: string | null,
    message: string,
  ) {
    super(message);
  }
}

export async function apiFetch<T = unknown>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const base = resolveConfig().apiBaseUrl;
  const headers = new Headers(init.headers);
  headers.set("Accept", "application/json");
  if (!headers.has("X-Request-Id")) {
    headers.set("X-Request-Id", generateRequestId());
  }
  if (init.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  const response = await fetch(`${base}${path}`, {
    ...init,
    headers,
    credentials: "include", // session cookie
  });

  const requestId = response.headers.get("X-Request-Id");

  if (!response.ok) {
    let code: string | null = null;
    let message = response.statusText;
    try {
      const body = await response.json();
      code = body.code ?? null;
      message = body.message ?? body.detail ?? message;
    } catch {
      // 非 JSON 错误体
    }
    throw new ApiError(response.status, code, requestId, message);
  }

  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}
