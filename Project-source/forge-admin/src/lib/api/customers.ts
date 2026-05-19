import { apiFetch } from "@/lib/api/client";
import type {
  CreateCustomerBody,
  CustomerListResponse,
  CustomerResponse,
  UpdateCustomerBody,
} from "@/types/api";

export interface CustomerListQuery {
  status?: "active" | "archived";
  limit?: number;
  offset?: number;
}

function qs(params: Record<string, string | number | undefined>): string {
  const entries = Object.entries(params).filter(([, v]) => v !== undefined && v !== "");
  if (entries.length === 0) return "";
  return "?" + new URLSearchParams(entries.map(([k, v]) => [k, String(v)])).toString();
}

export function listCustomers(query: CustomerListQuery = {}): Promise<CustomerListResponse> {
  return apiFetch<CustomerListResponse>(`/customers${qs(query as Record<string, string | number | undefined>)}`);
}

export function getCustomer(id: string): Promise<CustomerResponse> {
  return apiFetch<CustomerResponse>(`/customers/${encodeURIComponent(id)}`);
}

export function createCustomer(body: CreateCustomerBody): Promise<CustomerResponse> {
  return apiFetch<CustomerResponse>("/customers", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function updateCustomer(id: string, body: UpdateCustomerBody): Promise<CustomerResponse> {
  return apiFetch<CustomerResponse>(`/customers/${encodeURIComponent(id)}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

export function archiveCustomer(id: string): Promise<CustomerResponse> {
  return apiFetch<CustomerResponse>(`/customers/${encodeURIComponent(id)}`, {
    method: "DELETE",
  });
}

export interface HardDeleteResult {
  customer_id?: string;
  product_id?: string;
  license_id?: string;
  key_id?: string;
  user_id?: string;
  cascaded?: Record<string, number>;
  deleted?: boolean;
}

/** Hard delete — drops the customer row and cascades to its licenses / api keys / heartbeats. */
export function hardDeleteCustomer(id: string): Promise<HardDeleteResult> {
  return apiFetch<HardDeleteResult>(`/customers/${encodeURIComponent(id)}/hard-delete`, {
    method: "POST",
  });
}
