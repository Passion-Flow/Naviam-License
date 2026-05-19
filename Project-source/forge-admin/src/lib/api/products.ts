import { apiFetch } from "@/lib/api/client";
import type {
  CreateProductBody,
  ProductListResponse,
  ProductResponse,
  UpdateProductBody,
} from "@/types/api";

export interface ProductListQuery {
  status?: "active" | "archived";
  limit?: number;
  offset?: number;
}

function qs(params: Record<string, string | number | undefined>): string {
  const entries = Object.entries(params).filter(([, v]) => v !== undefined && v !== "");
  if (entries.length === 0) return "";
  return "?" + new URLSearchParams(entries.map(([k, v]) => [k, String(v)])).toString();
}

export function listProducts(query: ProductListQuery = {}): Promise<ProductListResponse> {
  return apiFetch<ProductListResponse>(`/products${qs(query as Record<string, string | number | undefined>)}`);
}

export function getProduct(id: string): Promise<ProductResponse> {
  return apiFetch<ProductResponse>(`/products/${encodeURIComponent(id)}`);
}

export function createProduct(body: CreateProductBody): Promise<ProductResponse> {
  return apiFetch<ProductResponse>("/products", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function updateProduct(id: string, body: UpdateProductBody): Promise<ProductResponse> {
  return apiFetch<ProductResponse>(`/products/${encodeURIComponent(id)}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

/** Hard delete — drops the product and cascades to its licenses/heartbeats. */
export function hardDeleteProduct(id: string): Promise<{ product_id: string; cascaded: Record<string, number> }> {
  return apiFetch(`/products/${encodeURIComponent(id)}`, { method: "DELETE" });
}
