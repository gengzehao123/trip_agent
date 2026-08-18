"""高德地图 MCP 工具接入 (langchain-mcp-adapters)。"""

import asyncio
from typing import Any, Dict, Optional

from langchain_core.tools import BaseTool
from langchain_mcp_adapters.client import MultiServerMCPClient

from ..config import get_settings

_client: Optional[MultiServerMCPClient] = None
_tools: Optional[Dict[str, BaseTool]] = None
_lock = asyncio.Lock()

# 允许调用的高德 MCP 工具白名单（本应用实际使用到的工具）
ALLOWED_TOOLS = frozenset({
    "maps_text_search",
    "maps_weather",
    "maps_direction_walking_by_address",
    "maps_direction_driving_by_address",
    "maps_direction_transit_integrated_by_address",
    "maps_geo",
    "maps_search_detail",
})


def is_tool_allowed(tool_name: str) -> bool:
    """检查工具是否在白名单内。"""
    return tool_name in ALLOWED_TOOLS


async def _get_client() -> MultiServerMCPClient:
    global _client
    if _client is None:
        settings = get_settings()
        if not settings.amap_api_key:
            raise ValueError("高德地图API Key未配置,请在.env文件中设置AMAP_API_KEY")
        _client = MultiServerMCPClient({
            "amap": {
                "command": "uvx",
                "args": ["amap-mcp-server"],
                "env": {"AMAP_MAPS_API_KEY": settings.amap_api_key},
                "transport": "stdio",
            }
        })
    return _client


async def get_amap_tools() -> Dict[str, BaseTool]:
    """获取按名称索引的高德 MCP 工具(懒加载单例)。"""
    global _tools
    if _tools is None:
        async with _lock:
            if _tools is None:
                client = await _get_client()
                tools = await client.get_tools()
                _tools = {tool.name: tool for tool in tools}
                print(f"✅ 高德地图MCP工具加载成功: {list(_tools.keys())}")
    return _tools


async def call_amap_tool(tool_name: str, arguments: Dict[str, Any]) -> Any:
    """直接调用指定高德 MCP 工具,返回其文本结果。"""
    if not is_tool_allowed(tool_name):
        raise ValueError(f"工具调用被白名单拒绝: {tool_name}")
    tools = await get_amap_tools()
    tool = tools.get(tool_name)
    if tool is None:
        raise ValueError(f"未知的高德MCP工具: {tool_name}")
    return await tool.ainvoke(arguments)


async def reset_amap_tools() -> None:
    """重置工具缓存(用于测试)。"""
    global _client, _tools
    _client = None
    _tools = None
