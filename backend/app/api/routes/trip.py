"""旅行规划API路由"""

import asyncio
from fastapi import APIRouter, HTTPException
from ...models.schemas import (
    TripRequest,
    TaskStatusResponse,
    TripTaskCreateResponse,
    ErrorResponse
)
from ...agents.trip_planner_agent import get_trip_planner_agent
from ...services.task_manager import task_manager

router = APIRouter(prefix="/trip", tags=["旅行规划"])


@router.post(
    "/plan",
    response_model=TripTaskCreateResponse,
    summary="生成旅行计划",
    description="根据用户输入的旅行需求,生成详细的旅行计划"
)
async def plan_trip(request: TripRequest):
    """
    生成旅行计划

    Args:
        request: 旅行请求参数

    Returns:
        旅行计划响应
    """
    try:
        print(f"\n{'='*60}")
        print(f"📥 收到旅行规划请求:")
        print(f"   城市: {request.city}")
        print(f"   日期: {request.start_date} - {request.end_date}")
        print(f"   天数: {request.travel_days}")
        print(f"{'='*60}\n")

        task = task_manager.create()
        agent = get_trip_planner_agent()
        asyncio.create_task(task_manager.run(task.task_id, request, agent))
        return TripTaskCreateResponse(
            task_id=task.task_id,
            status=task.status,
            message=task.message,
        )

    except Exception as e:
        print(f"❌ 生成旅行计划失败: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"生成旅行计划失败: {str(e)}"
        )


@router.get(
    "/tasks/{task_id}",
    response_model=TaskStatusResponse,
    summary="查询旅行规划任务状态",
)
async def get_task_status(task_id: str):
    task = task_manager.get(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    return task


@router.get(
    "/health",
    summary="健康检查",
    description="检查旅行规划服务是否正常"
)
async def health_check():
    """健康检查"""
    try:
        agent = get_trip_planner_agent()
        try:
            nodes = list(agent.graph.get_graph().nodes.keys())
        except Exception:
            nodes = []
        return {
            "status": "healthy",
            "service": "trip-planner",
            "graph_nodes": nodes,
        }
    except Exception as e:
        raise HTTPException(
            status_code=503,
            detail=f"服务不可用: {str(e)}"
        )
