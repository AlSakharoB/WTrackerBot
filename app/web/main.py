import uvicorn

from app.config import get_settings
from app.core.logging import setup_logging
from app.web.app import create_web_app


def main() -> None:
    settings = get_settings()
    setup_logging(settings)
    uvicorn.run(
        create_web_app(settings),
        host=settings.miniapp_host,
        port=settings.miniapp_port,
        log_config=None,
        access_log=False,
    )


if __name__ == "__main__":
    main()
