"""旅行规划会话上下文的进程内存储。"""

from copy import deepcopy
from datetime import datetime, timezone
from threading import RLock
from typing import Dict, Optional

from ..models.schemas import (
    ConversationContext,
    ConversationMessage,
    TripPlan,
)


class ConversationService:
    """保存有限会话历史、当前行程和用户偏好。

    该实现只适用于单进程部署。所有读取都返回深拷贝，避免调用方直接
    修改内存中的会话状态。
    """

    def __init__(self, max_messages: int = 20):
        if max_messages < 1:
            raise ValueError("max_messages 必须大于 0")
        self._max_messages = max_messages
        self._sessions: Dict[str, ConversationContext] = {}
        self._active_revisions: Dict[str, str] = {}
        self._lock = RLock()

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)

    def create(self, session_id: Optional[str] = None) -> ConversationContext:
        """创建或复用会话，并返回会话快照。"""
        from uuid import uuid4

        sid = session_id or str(uuid4())
        with self._lock:
            if sid not in self._sessions:
                now = self._now()
                self._sessions[sid] = ConversationContext(
                    session_id=sid,
                    created_at=now,
                    updated_at=now,
                )
            return self._copy(self._sessions[sid])

    def get(self, session_id: str) -> Optional[ConversationContext]:
        with self._lock:
            context = self._sessions.get(session_id)
            return self._copy(context) if context else None

    def get_revision_context(
        self, session_id: str
    ) -> Optional[tuple[TripPlan, list[ConversationMessage], list[str]]]:
        """读取修改任务所需的完整上下文快照。"""
        with self._lock:
            context = self._sessions.get(session_id)
            if context is None or context.current_trip_plan is None:
                return None
            return (
                deepcopy(context.current_trip_plan),
                deepcopy(context.messages),
                deepcopy(context.user_preferences),
            )

    def add_message(self, session_id: str, role: str, content: str) -> bool:
        if role not in {"user", "assistant"}:
            raise ValueError("消息角色必须是 user 或 assistant")
        message = ConversationMessage(role=role, content=content.strip())
        with self._lock:
            context = self._sessions.get(session_id)
            if context is None:
                return False
            context.messages.append(message)
            context.messages = context.messages[-self._max_messages :]
            context.updated_at = self._now()
            return True

    def merge_preferences(self, session_id: str, preferences: list[str]) -> bool:
        with self._lock:
            context = self._sessions.get(session_id)
            if context is None:
                return False
            existing = set(context.user_preferences)
            for preference in preferences:
                value = preference.strip()
                if value and value not in existing:
                    context.user_preferences.append(value)
                    existing.add(value)
            context.updated_at = self._now()
            return True

    def set_current_plan(self, session_id: str, plan: TripPlan) -> bool:
        with self._lock:
            context = self._sessions.get(session_id)
            if context is None:
                return False
            context.current_trip_plan = deepcopy(plan)
            context.updated_at = self._now()
            return True

    def start_revision(self, session_id: str, task_id: str) -> bool:
        """为会话保留一个修改任务，防止并发修改覆盖结果。"""
        with self._lock:
            context = self._sessions.get(session_id)
            if context is None or context.current_trip_plan is None:
                return False
            if session_id in self._active_revisions:
                return False
            self._active_revisions[session_id] = task_id
            return True

    def finish_revision(self, session_id: str, task_id: str) -> None:
        with self._lock:
            if self._active_revisions.get(session_id) == task_id:
                del self._active_revisions[session_id]

    def complete_revision(
        self, session_id: str, task_id: str, plan: TripPlan
    ) -> bool:
        """原子替换当前计划并追加助手消息。"""
        with self._lock:
            context = self._sessions.get(session_id)
            if context is None or self._active_revisions.get(session_id) != task_id:
                return False
            context.current_trip_plan = deepcopy(plan)
            context.messages.append(
                ConversationMessage(role="assistant", content="已更新旅行计划")
            )
            context.messages = context.messages[-self._max_messages :]
            context.updated_at = self._now()
            return True

    @staticmethod
    def _copy(context: ConversationContext) -> ConversationContext:
        return context.model_copy(deep=True)


conversation_service = ConversationService()
