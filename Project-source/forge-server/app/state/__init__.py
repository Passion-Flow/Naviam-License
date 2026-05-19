"""Forge App State —— 进程级单例容器。

FastAPI 路由通过 Depends(get_state) 拿到统一状态，**不**直接 import 全局变量。
测试可在启动前替换 backend（如 InMemoryRevocationStore → 真 store）。

设计：
- AppState 是 dataclass，包含运行期需要的所有 backend / manager
- build_state(settings) 装配；可被 TestClient 在 lifespan 前覆写
- get_state(request) 是 FastAPI 依赖入口
"""
from app.state.container import ApiKeyInfo, AppState, build_state, get_state

__all__ = ["ApiKeyInfo", "AppState", "build_state", "get_state"]
