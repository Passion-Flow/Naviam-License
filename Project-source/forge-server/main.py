from __future__ import annotations

import uvicorn

from app.settings import get_settings


def main() -> None:
    settings = get_settings()
    uvicorn.run(
        "app.main:app",
        host=settings.server_host,
        port=settings.server_port,
        reload=settings.server_reload,
        log_config=None,
    )


if __name__ == "__main__":
    main()
