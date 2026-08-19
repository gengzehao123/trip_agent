"""旅行规划任务的进程内状态管理。"""

from datetime import datetime, timezone
from typing import Any, Dict, Optional
from uuid import uuid4

from ..models.schemas import TaskStatusResponse, TripRequest, TripPlan
from .conversation_service import conversation_service, ConversationService
from .tool_logger import set_session_id, set_task_id


class TripTaskManager:
    """单进程任务管理器；多实例部署时应替换为 Redis 等共享存储。"""

    def __init__(self, conversations: ConversationService = conversation_service):
        self._tasks: Dict[str, TaskStatusResponse] = {}
        self._conversations = conversations

    def create(self, session_id: Optional[str] = None) -> TaskStatusResponse:
        task = TaskStatusResponse(
            task_id=str(uuid4()),
            session_id=session_id,
            status="queued",
            stage="queued",
            progress=0,
            message="任务已排队",
        )
        self._tasks[task.task_id] = task
        return task

    def get(self, task_id: str) -> Optional[TaskStatusResponse]:
        return self._tasks.get(task_id)

    def discard(self, task_id: str) -> None:
        """丢弃尚未启动的任务，例如会话并发冲突时。"""
        self._tasks.pop(task_id, None)

    def update(self, task_id: str, **changes: Any) -> TaskStatusResponse:
        current = self._tasks[task_id]
        updated = current.model_copy(update={
            **changes,
            "updated_at": datetime.now(timezone.utc),
        })
        self._tasks[task_id] = updated
        return updated

    async def run(self, task_id: str, request: TripRequest, planner: Any) -> None:
        set_task_id(task_id)
        session_id = self._tasks[task_id].session_id
        if session_id:
            set_session_id(session_id)
        try:
            self.update(task_id, status="running", stage="search_attractions", progress=5, message="🔍 正在搜索景点")

            plan: TripPlan = await planner.plan_trip(
                request, on_progress=self._progress_callback(task_id)
            )
            if session_id:
                self._conversations.set_current_plan(session_id, plan)
                self._conversations.add_message(
                    session_id, "assistant", "已生成旅行计划"
                )
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

    async def run_revision(self, task_id: str, instruction: str, planner: Any) -> None:
        """执行会话中的行程修改任务。"""
        task = self._tasks[task_id]
        session_id = task.session_id
        if not session_id:
            self.update(
                task_id,
                status="failed",
                stage="failed",
                progress=100,
                message="旅行计划修改失败",
                error="任务没有关联会话",
            )
            return

        set_task_id(task_id)
        set_session_id(session_id)
        try:
            revision_context = self._conversations.get_revision_context(session_id)
            if revision_context is None:
                raise ValueError("会话中没有当前旅行计划")
            current_plan, history, preferences = revision_context
            self.update(
                task_id,
                status="running",
                stage="revising",
                progress=5,
                message="📝 正在根据会话上下文修改行程",
            )
            plan: TripPlan = await planner.revise_trip(
                current_plan,
                instruction,
                history,
                preferences,
                on_progress=self._progress_callback(task_id),
            )
            if not self._conversations.complete_revision(session_id, task_id, plan):
                raise ValueError("会话修改任务已失效")
            self.update(
                task_id,
                status="completed",
                stage="completed",
                progress=100,
                message="旅行计划修改成功",
                data=plan,
            )
        except Exception as exc:
            self.update(
                task_id,
                status="failed",
                stage="failed",
                progress=100,
                message="旅行计划修改失败",
                error=str(exc),
            )
        finally:
            self._conversations.finish_revision(session_id, task_id)

    def _progress_callback(self, task_id: str):
        async def on_progress(stage: str, message: str, progress: int) -> None:
            self.update(task_id, stage=stage, message=message, progress=progress)

        return on_progress


task_manager = TripTaskManager()
