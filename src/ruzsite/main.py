"""Application entrypoint."""

import uvicorn

from ruzsite.app import app
from ruzsite.services.request_metadata_service import get_uvicorn_forwarded_allow_ips
from ruzsite.settings import get_settings

settings = get_settings()


def main():
    """Run the development server."""
    uvicorn.run(
        "ruzsite.main:app",
        host=settings.host,
        port=settings.port,
        proxy_headers=True,
        forwarded_allow_ips=get_uvicorn_forwarded_allow_ips(),
    )


if __name__ == "__main__":
    main()
