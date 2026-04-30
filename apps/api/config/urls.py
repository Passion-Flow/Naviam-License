"""Root URL conf.

每个业务模块自己注册路由；本文件仅做编排。
"""
from __future__ import annotations

from django.urls import include, path

urlpatterns = [
    path("v1/auth/", include("modules.accounts.urls")),
    path("v1/customers/", include("modules.customers.urls")),
    path("v1/products/", include("modules.products.urls")),
    path("v1/licenses/", include("modules.licenses.urls")),
    path("v1/activations/", include("modules.activations.urls")),
    path("v1/audit/", include("modules.audit.urls")),
    path("v1/notifications/", include("modules.notifications.urls")),
    path("v1/settings/", include("modules.security.urls")),
    path("healthz", include("modules.security.health_urls")),
    path("readyz", include("modules.security.health_urls")),
]
