"""工具调用结构化日志。"""

from contextvars import ContextVar
from pathlib import Path
from typing import Any, Dict, Optional

from loguru import logger

# 当前任务 ID，用于把工具调用关联到具体任务
_current_task_id: ContextVar[Optional[str]] = ContextVar("tool_call_task_id", default=None)

_LOG_FILE = Path(__file__).resolve().parent.parent.parent / "logs" / "tool_calls.log"
_LOG_FILE.parent.mkdir(exist_ok=True)

# 工具调用日志：JSON 行写入文件（serialize=True 直接序列化整条记录，业务字段在 record.extra 中）
logger.add(
    str(_LOG_FILE),
    serialize=True,
    level="INFO",
    filter=lambda record: record["extra"].get("event") == "tool_call",
    rotation="10 MB",
    retention="7 days",
)


def set_task_id(task_id: str) -> None:
    """设置当前协程上下文的 task_id。"""
    _current_task_id.set(task_id)


def get_task_id() -> Optional[str]:
    return _current_task_id.get()


def log_tool_call(
    tool_name: str,
    arguments: Dict[str, Any],
    *,
    duration_ms: float,
    success: bool,
    error: Optional[str] = None,
) -> None:
    """记录一次工具调用。"""
    logger.bind(
        event="tool_call",
        task_id=get_task_id(),
        tool=tool_name,
        arguments=arguments,
        duration_ms=round(duration_ms, 2),
        success=success,
        error=error,
    ).info("tool_call")
