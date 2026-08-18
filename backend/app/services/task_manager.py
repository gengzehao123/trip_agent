"""旅行规划任务的进程内状态管理。"""

from datetime import datetime, timezone
from typing import Any, Dict, Optional
from uuid import uuid4

from ..models.schemas import TaskStatusResponse, TripRequest, TripPlan


class TripTaskManager:
    """单进程任务管理器；多实例部署时应替换为 Redis 等共享存储。"""

    def __init__(self):
        self._tasks: Dict[str, TaskStatusResponse] = {}

    def create(self) -> TaskStatusResponse:
        task = TaskStatusResponse(
            task_id=str(uuid4()),
            status="queued",
            stage="queued",
            progress=0,
            message="任务已排队",
        )
        self._tasks[task.task_id] = task
        return task

    def get(self, task_id: str) -> Optional[TaskStatusResponse]:
        return self._tasks.get(task_id)

    def update(self, task_id: str, **changes: Any) -> TaskStatusResponse:
        current = self._tasks[task_id]
        updated = current.model_copy(update={
            **changes,
            "updated_at": datetime.now(timezone.utc),
        })
        self._tasks[task_id] = updated
        return updated

    async def run(self, task_id: str, request: TripRequest, planner: Any) -> None:
        try:
            self.update(task_id, status="running", stage="search_attractions", progress=5, message="🔍 正在搜索景点")

            async def on_progress(stage: str, message: str, progress: int) -> None:
                self.update(task_id, stage=stage, message=message, progress=progress)

            plan: TripPlan = await planner.plan_trip(request, on_progress=on_progress)
            self.update(
                task_id,
                status="completed",
                stage="completed",
                progress=100,
                message="旅行计划生成成功",
                data=plan,
            )
        except Exception as exc:
            self.update(
                task_id,
                status="failed",
                stage="failed",
                progress=100,
                message="旅行计划生成失败",
                error=str(exc),
            )


task_manager = TripTaskManager()
