"""会话上下文和多轮行程修改 API。"""

import asyncio

from fastapi import APIRouter, HTTPException

from ...agents.trip_planner_agent import get_trip_planner_agent
from ...models.schemas import (
    ConversationMessageRequest,
    ConversationResponse,
    TripTaskCreateResponse,
)
from ...services.conversation_service import conversation_service
from ...services.session_manager import session_manager
from ...services.task_manager import task_manager


router = APIRouter(prefix="/conversations", tags=["会话"])


@router.get("/{session_id}", response_model=ConversationResponse)
async def get_conversation(session_id: str):
    context = conversation_service.get(session_id)
    if context is None:
        raise HTTPException(status_code=404, detail="会话不存在")
    return context


@router.post("/{session_id}/messages", response_model=TripTaskCreateResponse)
async def revise_conversation(
    session_id: str, request: ConversationMessageRequest
):
    context = conversation_service.get(session_id)
    if context is None:
        raise HTTPException(status_code=404, detail="会话不存在")
    if context.current_trip_plan is None:
        raise HTTPException(status_code=409, detail="请先生成旅行计划")

    task = task_manager.create(session_id=session_id)
    if not conversation_service.start_revision(session_id, task.task_id):
        task_manager.discard(task.task_id)
        raise HTTPException(status_code=409, detail="该会话已有正在进行的修改任务")

    conversation_service.add_message(session_id, "user", request.content)
    session_manager.add_task(session_id, task.task_id)
    asyncio.create_task(
        task_manager.run_revision(task.task_id, request.content, get_trip_planner_agent())
    )
    return TripTaskCreateResponse(
        task_id=task.task_id,
        session_id=session_id,
        status=task.status,
        message=task.message,
    )
