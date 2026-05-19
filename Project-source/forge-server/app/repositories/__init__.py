"""Repository 层 —— ORM 模型与业务逻辑的桥接。

每个 repository 接收 `app.adapters.database.Database` 实例（提供 session()），
对外暴露业务方法（add / get / list），把 SQL 细节封装。
"""
from app.repositories.api_keys import ApiKeyRepository, DbBackedApiKeyAuth
from app.repositories.audit import AuditLogRepository
from app.repositories.customers import CustomerRepository, CustomerSlugConflict
from app.repositories.heartbeat import DbBackedHeartbeatCollector
from app.repositories.heartbeat_query import HeartbeatQueryRepository, LicenseHeartbeatSummary
from app.repositories.licenses import LicenseRepository
from app.repositories.products import ProductRepository, ProductSlugConflict
from app.repositories.revocation import DbBackedRevocationStore
from app.repositories.signing_keys import SigningKeyRepository
from app.repositories.users import UserRepository

__all__ = [
    "ApiKeyRepository",
    "AuditLogRepository",
    "CustomerRepository",
    "CustomerSlugConflict",
    "DbBackedApiKeyAuth",
    "DbBackedHeartbeatCollector",
    "DbBackedRevocationStore",
    "HeartbeatQueryRepository",
    "LicenseHeartbeatSummary",
    "LicenseRepository",
    "ProductRepository",
    "ProductSlugConflict",
    "SigningKeyRepository",
    "UserRepository",
]
