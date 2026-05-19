import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { logoutRequest, meRequest } from "@/lib/api/auth";
import { ApiError } from "@/lib/api/client";
import type { AdminUser } from "@/types/api";

const SESSION_QUERY_KEY = ["auth", "me"] as const;

/**
 * 拉一次当前会话。401 视为"未登录"，不算错误 —— 上层据此跳登录。
 */
export function useSession() {
  return useQuery<AdminUser | null, Error>({
    queryKey: SESSION_QUERY_KEY,
    queryFn: async () => {
      try {
        return await meRequest();
      } catch (err) {
        if (err instanceof ApiError && err.status === 401) {
          return null;
        }
        throw err;
      }
    },
    retry: false,
    staleTime: 60_000,
  });
}

export function useLogout() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: logoutRequest,
    onSuccess: () => {
      queryClient.setQueryData(SESSION_QUERY_KEY, null);
      queryClient.removeQueries();
    },
  });
}

export const sessionQueryKey = SESSION_QUERY_KEY;
