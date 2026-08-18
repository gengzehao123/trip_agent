"""错误分类与降级策略。"""

# 永久性错误（重试无意义）：参数错误、白名单拒绝、JSON 解析失败、鉴权失败等
NON_RETRYABLE_EXCEPTIONS = (
    ValueError,
    TypeError,
    PermissionError,
)


def is_retryable_error(exc: Exception) -> bool:
    """判断错误是否可重试。

    永久性错误（参数/白名单/JSON 解析等 ValueError）直接抛出不重试；
    其余（超时、网络、服务端错误等）视为瞬时错误，可重试。
    """
    return not isinstance(exc, NON_RETRYABLE_EXCEPTIONS)


def classify_error(exc: Exception) -> str:
    """返回错误分类标签（用于日志与降级）。"""
    if isinstance(exc, ValueError):
        return "参数/解析错误"
    if isinstance(exc, PermissionError):
        return "权限错误"
    if isinstance(exc, TimeoutError):
        return "超时"
    if isinstance(exc, ConnectionError):
        return "连接错误"
    if isinstance(exc, OSError):
        return "IO错误"
    return type(exc).__name__
