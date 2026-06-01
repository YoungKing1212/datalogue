from fastapi import APIRouter

from app.api import datasource, dataset, conversation, chat

router = APIRouter()

router.include_router(datasource.router, prefix="/datasource", tags=["数据源"])
router.include_router(dataset.router, prefix="/dataset", tags=["数据集"])
router.include_router(conversation.router, prefix="/conversation", tags=["对话"])
router.include_router(chat.router, prefix="/chat", tags=["问数"])
