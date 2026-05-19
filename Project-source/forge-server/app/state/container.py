"""AppState 容器 + FastAPI 依赖入口。"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from fastapi import Request

from app.adapters.database.interface.protocol import Database
from app.core.key_storage import KeyStorage, get_key_storage
from app.core.license.crl import CrlManager, RevocationStore
from app.core.license.heartbeat import (
    HeartbeatCollector,
    MultiEnvDetector,
)
from app.settings import Settings


@dataclass(slots=True)
class AppState:
    """跨请求共享的运行期状态。"""

    settings: Settings
    key_storage: KeyStorage
    revocation_store: RevocationStore
    crl_manager: CrlManager
    heartbeat_collector: HeartbeatCollector
    multi_env_detector: MultiEnvDetector

    # API key 注册表（in-memory 用；后期 DB-backed 换 model）
    # 形如：{api_key_hash: ApiKeyInfo}
    api_keys: dict[str, "ApiKeyInfo"]

    # 可选：DB-backed repositories（None 时走 in-memory 路径）
    database: "Database | None" = None
    license_repository: "object | None" = None
    api_key_auth: "object | None" = None
    api_key_repository: "object | None" = None
    user_repository: "object | None" = None
    session_store: "object | None" = None
    audit_log_repository: "object | None" = None
    customer_repository: "object | None" = None
    product_repository: "object | None" = None
    signing_key_repository: "object | None" = None
    heartbeat_query_repository: "object | None" = None
    login_rate_limiter: "object | None" = None
    api_key_quota_limiter: "object | None" = None


@dataclass(frozen=True, slots=True)
class ApiKeyInfo:
    """单条 API Key 信息（in-memory store；正式版走 DB）。"""

    key_id: str               # 内部 ID
    key_hash: str             # 明文哈希 (sha256 hex) 用于查表
    customer_id: str          # 该 key 关联客户
    project_label: str        # 消费方项目标签
    status: str = "active"    # active / revoked
    expires_at: "datetime | None" = None  # None = 永不过期


def build_state(settings: Settings) -> AppState:
    """装配 AppState —— 全 DB-backed。

    单一启动路径：DB / Cache / KeyStorage 都从 settings 实例化。
    测试路径用 create_app(state_builder=...) 替换整个 state（见 forge_state.py 等用法）。
    """
    # 函数内 import 是为了避开 app.state ↔ app.repositories 的循环引入：
    # repositories 在模块顶层会 import ApiKeyInfo，而 ApiKeyInfo 由本模块导出。
    from app.adapters.cache import get_cache
    from app.adapters.database import get_database
    from app.core.auth import SessionStore
    from app.core.auth.api_key_quota import ApiKeyQuotaLimiter
    from app.core.auth.rate_limit import LoginRateLimiter
    from app.repositories import (
        ApiKeyRepository,
        AuditLogRepository,
        CustomerRepository,
        DbBackedApiKeyAuth,
        DbBackedHeartbeatCollector,
        DbBackedRevocationStore,
        HeartbeatQueryRepository,
        LicenseRepository,
        ProductRepository,
        SigningKeyRepository,
        UserRepository,
    )

    key_storage = get_key_storage()
    database: Database = get_database()
    revocation_store: RevocationStore = DbBackedRevocationStore(database)
    crl_manager = CrlManager(
        store=revocation_store,
        key_storage=key_storage,
        algorithm=settings.signing_default_algorithm,
    )
    heartbeat_collector: HeartbeatCollector = DbBackedHeartbeatCollector(database)
    multi_env_detector = MultiEnvDetector(
        window=timedelta(hours=24),
        threshold=1,
        grace_count=0,
    )

    # Auth backends
    session_cache = get_cache(db=settings.cache_db_session)
    session_store = SessionStore(
        session_cache, max_age_seconds=settings.auth_session_max_age_seconds
    )
    rate_limit_cache = get_cache(db=settings.cache_db_app)
    login_rate_limiter = LoginRateLimiter(
        rate_limit_cache,
        threshold=settings.auth_login_rate_limit_threshold,
        window_seconds=settings.auth_login_rate_limit_window_seconds,
    )
    api_key_quota_limiter = ApiKeyQuotaLimiter(
        rate_limit_cache, per_hour=settings.api_key_rate_limit_per_hour
    )

    api_key_repo = ApiKeyRepository(database)

    return AppState(
        settings=settings,
        key_storage=key_storage,
        revocation_store=revocation_store,
        crl_manager=crl_manager,
        heartbeat_collector=heartbeat_collector,
        multi_env_detector=multi_env_detector,
        api_keys={},
        database=database,
        license_repository=LicenseRepository(database),
        api_key_auth=DbBackedApiKeyAuth(api_key_repo),
        api_key_repository=api_key_repo,
        user_repository=UserRepository(database),
        session_store=session_store,
        audit_log_repository=AuditLogRepository(database),
        customer_repository=CustomerRepository(database),
        product_repository=ProductRepository(database),
        signing_key_repository=SigningKeyRepository(database),
        heartbeat_query_repository=HeartbeatQueryRepository(database),
        login_rate_limiter=login_rate_limiter,
        api_key_quota_limiter=api_key_quota_limiter,
    )


def get_state(request: Request) -> AppState:
    """FastAPI Depends 入口。"""
    state = getattr(request.app.state, "forge_state", None)
    if state is None:
        raise RuntimeError("Forge AppState not initialized — call lifespan setup first")
    return state
