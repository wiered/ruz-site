"""Health check routes."""

from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
async def health() -> dict[str, str]:
    """Return application health status."""
    return {"status": "ok"}
