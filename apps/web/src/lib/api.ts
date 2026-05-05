/**
 * 统一 API 客户端 (Phase 9)
 *
 * 设计目标：
 * - 单一调用入口 apiFetch()，所有页面禁止裸 fetch()
 * - 强制超时（默认 10s）：浏览器原生 fetch 没有超时，长时间挂起会让用户体验崩盘
 * - 401 → 自动跳转 /login（session 过期统一处理，不让每个页面写 if）
 * - CSRF token 自动注入（从 cookie 读 csrftoken header）
 * - credentials: 'include' 默认开（session cookie 必带）
 * - 错误形态收敛：返回 ApiError，message 取自后端 contracts/errors.py
 *
 * 配置：
 * - API_BASE 必须从 NEXT_PUBLIC_API_BASE_URL 注入；缺失时 dev 警告 + 用回环兜底，
 *   prod 直接抛错（buildtime 阻断 — 由调用方在初始化点捕获）
 */

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly detail: unknown;

  constructor(status: number, code: string, message: string, detail?: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.detail = detail;
  }
}

export class ApiTimeoutError extends ApiError {
  constructor(timeoutMs: number) {
    super(0, "timeout", `request timed out after ${timeoutMs}ms`);
    this.name = "ApiTimeoutError";
  }
}

export class ApiNetworkError extends ApiError {
  constructor(cause: unknown) {
    super(0, "network", "network error — backend unreachable", cause);
    this.name = "ApiNetworkError";
  }
}

// === API_BASE 解析与卡校验 ===

function resolveApiBase(): string {
  const fromEnv = process.env.NEXT_PUBLIC_API_BASE_URL;
  if (fromEnv && fromEnv.length > 0) {
    return fromEnv.replace(/\/$/, "");
  }

  // 生产构建必须配置 NEXT_PUBLIC_API_BASE_URL；缺失就崩，避免误用回环
  if (process.env.NODE_ENV === "production") {
    throw new Error(
      "NEXT_PUBLIC_API_BASE_URL is required in production builds; " +
        "set it at build time (next build) — runtime injection is not supported by Next.js public envs.",
    );
  }

  // dev：兜底回环 + 显式 console.warn 让开发者知道
  if (typeof window !== "undefined") {
    // 浏览器侧才 warn（避免 SSR 重复打印）
    // eslint-disable-next-line no-console
    console.warn(
      "[apiFetch] NEXT_PUBLIC_API_BASE_URL not set, falling back to http://127.0.0.1:8081/v1",
    );
  }
  return "http://127.0.0.1:8081/v1";
}

export const API_BASE = resolveApiBase();

// === CSRF token ===

function getCsrfToken(): string {
  if (typeof document === "undefined") return "";
  const m = document.cookie.match(/csrftoken=([^;]+)/);
  return m?.[1] ? decodeURIComponent(m[1]) : "";
}

// === 主入口 ===

export interface ApiFetchOptions extends Omit<RequestInit, "body" | "headers"> {
  /** JSON-serializable body；与 raw body 二选一 */
  json?: unknown;
  /** 自定义 headers（与默认合并） */
  headers?: Record<string, string>;
  /** 超时毫秒，默认 10000 */
  timeoutMs?: number;
  /** 收到 401 时是否自动跳 /login（默认 true） */
  redirectOnUnauthorized?: boolean;
}

export async function apiFetch<T = unknown>(
  path: string,
  opts: ApiFetchOptions = {},
): Promise<T> {
  const {
    json,
    headers = {},
    timeoutMs = 10000,
    redirectOnUnauthorized = true,
    method = json !== undefined ? "POST" : "GET",
    ...rest
  } = opts;

  const url = path.startsWith("http")
    ? path
    : `${API_BASE}${path.startsWith("/") ? path : `/${path}`}`;

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);

  const finalHeaders: Record<string, string> = {
    "Content-Type": "application/json",
    ...headers,
  };

  // 写操作必带 CSRF
  if (
    method !== "GET" &&
    method !== "HEAD" &&
    method !== "OPTIONS"
  ) {
    const csrf = getCsrfToken();
    if (csrf) finalHeaders["X-CSRFToken"] = csrf;
  }

  let res: Response;
  try {
    res = await fetch(url, {
      method,
      credentials: "include",
      headers: finalHeaders,
      body: json !== undefined ? JSON.stringify(json) : undefined,
      signal: controller.signal,
      ...rest,
    });
  } catch (err: unknown) {
    clearTimeout(timer);
    if (err instanceof DOMException && err.name === "AbortError") {
      throw new ApiTimeoutError(timeoutMs);
    }
    throw new ApiNetworkError(err);
  }
  clearTimeout(timer);

  if (res.status === 401 && redirectOnUnauthorized) {
    if (typeof window !== "undefined" && !window.location.pathname.startsWith("/login")) {
      window.location.href = "/login";
    }
    // 仍然抛错，调用方可以 catch 取消后续动作
    throw new ApiError(401, "unauthorized", "session expired or not logged in");
  }

  // 204 / 空响应
  if (res.status === 204 || res.headers.get("content-length") === "0") {
    return undefined as T;
  }

  const ct = res.headers.get("content-type") || "";
  let data: unknown = undefined;
  if (ct.includes("application/json")) {
    try {
      data = await res.json();
    } catch {
      data = undefined;
    }
  } else {
    data = await res.text().catch(() => undefined);
  }

  if (!res.ok) {
    // 后端 contracts/errors.py 约定 {code, message, hint?} 结构
    const body = (data ?? {}) as { code?: string; message?: string; detail?: string };
    throw new ApiError(
      res.status,
      body.code ?? `http_${res.status}`,
      body.message ?? body.detail ?? `request failed (${res.status})`,
      data,
    );
  }

  return data as T;
}

// === 便捷别名 ===

export const apiGet = <T = unknown>(path: string, opts?: ApiFetchOptions) =>
  apiFetch<T>(path, { ...opts, method: "GET" });

export const apiPost = <T = unknown>(
  path: string,
  json?: unknown,
  opts?: ApiFetchOptions,
) => apiFetch<T>(path, { ...opts, method: "POST", json });

export const apiPatch = <T = unknown>(
  path: string,
  json?: unknown,
  opts?: ApiFetchOptions,
) => apiFetch<T>(path, { ...opts, method: "PATCH", json });

export const apiPut = <T = unknown>(
  path: string,
  json?: unknown,
  opts?: ApiFetchOptions,
) => apiFetch<T>(path, { ...opts, method: "PUT", json });

export const apiDelete = <T = unknown>(path: string, opts?: ApiFetchOptions) =>
  apiFetch<T>(path, { ...opts, method: "DELETE" });

// === Dashboard 兼容 API：扁平命名空间 ===
//
// 所有 list 端点 DRF 默认走 PageNumberPagination，返回 {count,next,previous,results}。
// 我们对 dashboard 隐藏分页：api.list<T>() 直接返回 results 数组；如果后端没分页直接返回数组，
// 也透明兼容（runtime 检测）。后续要分页时，单独提供 api.listPaged()。
type Paginated<T> = {
  count?: number;
  next?: string | null;
  previous?: string | null;
  results: T[];
};

function isPaginated<T>(x: unknown): x is Paginated<T> {
  return (
    typeof x === "object" &&
    x !== null &&
    Array.isArray((x as Paginated<T>).results)
  );
}

export const api = {
  /** GET 一个资源；返回原始 JSON 反序列化对象。 */
  get: apiGet,

  /** POST 一个资源；body 自动 JSON.stringify。 */
  post: apiPost,

  /** PATCH 部分字段。 */
  patch: apiPatch,

  /** PUT 替换。 */
  put: apiPut,

  /** DELETE；后端通常 204，返回 undefined。 */
  delete: apiDelete,

  /**
   * GET 一个 list 端点；自动剥掉 DRF 分页壳。
   * 行为：
   *   - 后端返回 {count, results} → 返回 results
   *   - 后端直接返回 [...] → 原样返回
   *   - 其他形态 → 抛错
   */
  async list<T = unknown>(path: string, opts?: ApiFetchOptions): Promise<T[]> {
    const data = await apiFetch<unknown>(path, { ...opts, method: "GET" });
    if (Array.isArray(data)) return data as T[];
    if (isPaginated<T>(data)) return data.results;
    throw new ApiError(
      0,
      "shape_mismatch",
      `expected array or {results:[...]} from ${path}, got ${typeof data}`,
      data,
    );
  },

  /** 同 list，但返回完整分页元信息。 */
  async listPaged<T = unknown>(
    path: string,
    opts?: ApiFetchOptions,
  ): Promise<Paginated<T>> {
    const data = await apiFetch<unknown>(path, { ...opts, method: "GET" });
    if (isPaginated<T>(data)) return data;
    if (Array.isArray(data)) {
      return { results: data as T[], count: data.length };
    }
    throw new ApiError(
      0,
      "shape_mismatch",
      `expected paginated response from ${path}`,
      data,
    );
  },
};

// === 类型再导出（dashboard 直接 import 用） ===
//
// 所有 contract 类型在 @/types/contracts 内单一来源；这里仅做 re-export 方便 import。
// 几个 dashboard-only 的请求 / 响应 wrapper 类型在这里直接定义（避免 contracts.ts 膨胀）。
export type {
  Uuid,
  IsoDateTime,
  Pagination,
  User,
  Customer,
  Product,
  License,
  LicenseStatus,
} from "@/types/contracts";

import type { Customer, Product, License, Uuid, IsoDateTime } from "@/types/contracts";

export interface CreateCustomerRequest {
  display_name: string;
  legal_name?: string | null;
  contact_name?: string | null;
  contact_email?: string | null;
  contact_phone?: string | null;
  region?: string | null;
  notes?: string | null;
}

export interface CreateProductRequest {
  code: string;
  display_name: string;
  description?: string | null;
}

export interface IssueLicenseRequest {
  product_id: Uuid;
  customer_id: Uuid;
  cloud_id_text: string;
  expires_at: IsoDateTime;
  not_before?: IsoDateTime | null;
  grace_seconds?: number;
  notes?: string;
}

export interface IssueLicenseResponse {
  license: License;
  /** base64url(CBOR(envelope))，可直接保存为 *.lic */
  license_file: string;
  /** base32 分组人类可读串 */
  activation_code: string;
}

export interface RenewLicenseResponse {
  license: License;
  license_file: string;
  activation_code: string;
}

export interface AuditEvent {
  id: number;
  ts: IsoDateTime;
  actor_id?: Uuid | null;
  actor_name?: string | null;
  actor_kind: string;
  actor_ip?: string | null;
  action: string;
  target_kind?: string | null;
  target_id?: string | null;
  request_id?: string | null;
  signature_kid: string;
  payload: Record<string, unknown>;
}

export interface Notification {
  id: Uuid;
  category: string;
  level: string;
  title: string;
  body: string;
  link?: string | null;
  read_at?: IsoDateTime | null;
  created_at: IsoDateTime;
}

export interface LoginAttempt {
  id: number;
  ip: string;
  ua?: string | null;
  result: string;
  created_at: IsoDateTime;
}
