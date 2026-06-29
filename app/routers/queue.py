from fastapi import APIRouter, Depends

from app.routers.auth_db import get_current_user
from app.services.queue_service import QueueService, get_queue_service

router = APIRouter()


@router.get("/stats")
async def queue_stats(user: dict = Depends(get_current_user), svc: QueueService = Depends(get_queue_service)):
    stats = await svc.stats()
    return {"user": user["id"], **stats}
