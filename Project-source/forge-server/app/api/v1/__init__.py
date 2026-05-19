"""API v1 — 路由聚合点。

每个资源 / 每个独立操作（按 button）单独一个子目录（auth/login、licenses/issue ...），
本文件把它们拼起来挂到统一前缀 `/api/v1`。
"""
from __future__ import annotations

from fastapi import APIRouter

from app.api.v1.admin.users.create import router as admin_user_create_router
from app.api.v1.admin.users.deactivate import router as admin_user_deactivate_router
from app.api.v1.admin.users.list import router as admin_user_list_router
from app.api.v1.admin.users.reactivate import router as admin_user_reactivate_router
from app.api.v1.admin.users.reset_password import router as admin_user_reset_password_router
from app.api.v1.admin.users.delete import router as admin_user_delete_router
from app.api.v1.api_keys.delete import router as api_key_delete_router
from app.api.v1.api_keys.issue import router as api_key_issue_router
from app.api.v1.api_keys.list import router as api_key_list_router
from app.api.v1.api_keys.revoke import router as api_key_revoke_router
from app.api.v1.audit import router as audit_router
from app.api.v1.auth import router as auth_router
from app.api.v1.customers.create import router as customer_create_router
from app.api.v1.customers.delete import router as customer_delete_router
from app.api.v1.customers.detail import router as customer_detail_router
from app.api.v1.customers.hard_delete import router as customer_hard_delete_router
from app.api.v1.customers.list import router as customer_list_router
from app.api.v1.customers.update import router as customer_update_router
from app.api.v1.health import router as health_router
from app.api.v1.heartbeats.detail import router as heartbeats_detail_router
from app.api.v1.heartbeats.list import router as heartbeats_list_router
from app.api.v1.heartbeats.summary import router as heartbeats_summary_router
from app.api.v1.keys.delete import router as key_delete_router
from app.api.v1.keys.export_public import router as key_export_public_router
from app.api.v1.keys.generate import router as key_generate_router
from app.api.v1.keys.list import router as key_list_router
from app.api.v1.keys.revoke import router as key_revoke_router
from app.api.v1.keys.rotate import router as key_rotate_router
from app.api.v1.licenses.bulk_revoke import router as license_bulk_revoke_router
from app.api.v1.licenses.delete import router as license_delete_router
from app.api.v1.licenses.detail import router as license_detail_router
from app.api.v1.licenses.download import router as license_download_router
from app.api.v1.licenses.heartbeat import router as heartbeat_router
from app.api.v1.licenses.issue import router as issue_router
from app.api.v1.licenses.list import router as license_list_router
from app.api.v1.licenses.renew import router as license_renew_router
from app.api.v1.licenses.revoke import router as revoke_router
from app.api.v1.licenses.verify import router as license_verify_router
from app.api.v1.products.create import router as product_create_router
from app.api.v1.products.delete import router as product_delete_router
from app.api.v1.products.detail import router as product_detail_router
from app.api.v1.products.list import router as product_list_router
from app.api.v1.products.update import router as product_update_router
from app.api.v1.public_keys import router as public_keys_router
from app.api.v1.revocation_list import router as revocation_list_router

router = APIRouter()
router.include_router(health_router, tags=["health"])
router.include_router(auth_router, prefix="/auth", tags=["auth"])
router.include_router(public_keys_router, prefix="/public-keys", tags=["public-keys"])
router.include_router(revocation_list_router, prefix="/revocation-list", tags=["revocation-list"])
# 静态路径（/issue, /heartbeat, /verify, /bulk-revoke）必须先注册，再注册带 {license_id} 的动态路由
router.include_router(issue_router, prefix="/licenses", tags=["licenses"])
router.include_router(heartbeat_router, prefix="/licenses", tags=["licenses"])
router.include_router(license_verify_router, prefix="/licenses", tags=["licenses"])
router.include_router(license_bulk_revoke_router, prefix="/licenses", tags=["licenses"])
router.include_router(revoke_router, prefix="/licenses", tags=["licenses"])
router.include_router(license_renew_router, prefix="/licenses", tags=["licenses"])
router.include_router(license_download_router, prefix="/licenses", tags=["licenses"])
router.include_router(license_list_router, prefix="/licenses", tags=["licenses"])
router.include_router(license_detail_router, prefix="/licenses", tags=["licenses"])
router.include_router(license_delete_router, prefix="/licenses", tags=["licenses"])
router.include_router(audit_router, prefix="/audit", tags=["audit"])
# api-keys：list（GET ""）和 issue（POST ""）同前缀同路径；FastAPI 按方法分发
router.include_router(api_key_issue_router, prefix="/api-keys", tags=["api-keys"])
router.include_router(api_key_list_router, prefix="/api-keys", tags=["api-keys"])
router.include_router(api_key_revoke_router, prefix="/api-keys", tags=["api-keys"])
router.include_router(api_key_delete_router, prefix="/api-keys", tags=["api-keys"])
# keys：静态路径 /generate 必须先注册，再注册 {key_id} 动态路由
router.include_router(key_generate_router, prefix="/keys", tags=["keys"])
router.include_router(key_list_router, prefix="/keys", tags=["keys"])
router.include_router(key_rotate_router, prefix="/keys", tags=["keys"])
router.include_router(key_revoke_router, prefix="/keys", tags=["keys"])
router.include_router(key_export_public_router, prefix="/keys", tags=["keys"])
router.include_router(key_delete_router, prefix="/keys", tags=["keys"])
# customers：POST/GET 走 ""，PATCH/GET/DELETE 走 "/{id}"，FastAPI 按 method+path 分发
router.include_router(customer_create_router, prefix="/customers", tags=["customers"])
router.include_router(customer_list_router, prefix="/customers", tags=["customers"])
router.include_router(customer_detail_router, prefix="/customers", tags=["customers"])
router.include_router(customer_update_router, prefix="/customers", tags=["customers"])
router.include_router(customer_delete_router, prefix="/customers", tags=["customers"])
router.include_router(customer_hard_delete_router, prefix="/customers", tags=["customers"])
router.include_router(product_create_router, prefix="/products", tags=["products"])
router.include_router(product_list_router, prefix="/products", tags=["products"])
router.include_router(product_detail_router, prefix="/products", tags=["products"])
router.include_router(product_update_router, prefix="/products", tags=["products"])
router.include_router(product_delete_router, prefix="/products", tags=["products"])
# heartbeats（admin 监控）：静态 /summary 必须先于 /{license_id} 注册
router.include_router(heartbeats_summary_router, prefix="/heartbeats", tags=["heartbeats"])
router.include_router(heartbeats_list_router, prefix="/heartbeats", tags=["heartbeats"])
router.include_router(heartbeats_detail_router, prefix="/heartbeats", tags=["heartbeats"])
# admin/users —— super-admin 管理 admin 团队（list 是 admin session；其余 super-only）
router.include_router(admin_user_create_router, prefix="/admin/users", tags=["admin-users"])
router.include_router(admin_user_list_router, prefix="/admin/users", tags=["admin-users"])
router.include_router(admin_user_deactivate_router, prefix="/admin/users", tags=["admin-users"])
router.include_router(admin_user_reactivate_router, prefix="/admin/users", tags=["admin-users"])
router.include_router(admin_user_reset_password_router, prefix="/admin/users", tags=["admin-users"])
router.include_router(admin_user_delete_router, prefix="/admin/users", tags=["admin-users"])
