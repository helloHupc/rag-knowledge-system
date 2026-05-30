from __future__ import annotations

from fastapi import APIRouter

from app.api.admin import router as admin_router
from app.api.auth import router as auth_router
from app.api.chunking import router as chunking_router
from app.api.configs import router as configs_router
from app.api.dify import router as dify_router
from app.api.documents import router as documents_router
from app.api.evaluation import router as evaluation_router
from app.api.health import router as health_router
from app.api.jobs import router as jobs_router
from app.api.knowledge import router as knowledge_router
from app.api.qa import router as qa_router
from app.api.retrieval import router as retrieval_router
from app.api.sources import router as sources_router


# api_router.include_router(sources_router) # 对象存储同步暂未通过生产测试，暂不启用
api_router = APIRouter()
api_router.include_router(auth_router)
api_router.include_router(admin_router)
api_router.include_router(health_router)
api_router.include_router(configs_router)
api_router.include_router(dify_router)
api_router.include_router(documents_router)
api_router.include_router(jobs_router)
api_router.include_router(knowledge_router)
api_router.include_router(retrieval_router)
api_router.include_router(qa_router)
api_router.include_router(chunking_router)
api_router.include_router(evaluation_router)
# api_router.include_router(sources_router) # 对象存储/文件夹同步暂未通过生产测试，暂不启用
