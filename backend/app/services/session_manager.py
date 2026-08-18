"""会话管理（进程内）。"""

from datetime import datetime, timezone
from typing import Any, Dict, Optional
from uuid import uuid4


class SessionManager:
    """单进程会话注册表；多实例部署时应替换为 Redis 等共享存储。"""

    def __init__(self):
        self._sessions: Dict[str, Dict[str, Any]] = {}

    def create(self, session_id: Optional[str] = None) -> str:
        """创建（或复用）一个会话，返回 session_id。"""
        sid = session_id or str(uuid4())
        if sid not in self._sessions:
            self._sessions[sid] = {
                "session_id": sid,
                "created_at": datetime.now(timezone.utc),
                "task_ids": [],
            }
        return sid

    def add_task(self, session_id: str, task_id: str) -> None:
        """把任务关联到会话。"""
        session = self._sessions.get(session_id)
        if session is not None:
            session["task_ids"].append(task_id)

    def get(self, session_id: str) -> Optional[Dict[str, Any]]:
        return self._sessions.get(session_id)


session_manager = SessionManager()
