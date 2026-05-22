"""Application entrypoint."""

import uvicorn

from ruzsite.app import app
from ruzsite.settings import get_settings

settings = get_settings()


def main():
    """Run the development server."""
    uvicorn.run("ruzsite.main:app", host=settings.host, port=settings.port, reload=True)


if __name__ == "__main__":
    main()
