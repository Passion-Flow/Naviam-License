import { apiFetch } from "@/lib/api/client";
import type { AdminUser } from "@/types/api";

export interface LoginBody {
  username: string;
  password: string;
}

export interface LoginResponse extends AdminUser {}

export function loginRequest(body: LoginBody): Promise<LoginResponse> {
  return apiFetch<LoginResponse>("/auth/login", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function logoutRequest(): Promise<void> {
  return apiFetch<void>("/auth/logout", { method: "POST" });
}

export function meRequest(): Promise<AdminUser> {
  return apiFetch<AdminUser>("/auth/me");
}

export interface ChangePasswordBody {
  current_password: string;
  new_password: string;
}

export function changePasswordRequest(body: ChangePasswordBody): Promise<void> {
  return apiFetch<void>("/auth/change-password", {
    method: "POST",
    body: JSON.stringify(body),
  });
}
