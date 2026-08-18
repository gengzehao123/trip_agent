# HelloAgents → LangGraph 迁移实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 把旅行规划后端的 Agent 框架从 HelloAgents（`SimpleAgent`/`HelloAgentsLLM`/`MCPTool`）迁移到 LangGraph，前端与对外 API 契约保持不变。

**架构：** 用 LangGraph `StateGraph` 把行程规划编排成 4 个节点（搜索景点 → 查天气 → 搜酒店 → 生成行程），其中前 3 个节点直接调用高德 MCP 工具（经 `langchain-mcp-adapters` 暴露为 LangChain Tool），最后一个节点用 LLM 生成结构化 `TripPlan`。LLM 层改用 `ChatOpenAI`（OpenAI 兼容，支持 DeepSeek/OpenAI 等）。

**技术栈：** Python 3.12、FastAPI、Pydantic v2、LangChain、LangGraph、`langchain-mcp-adapters`、`amap-mcp-server`（经 `uvx` 运行）、pytest + pytest-asyncio。

---

## 关键设计决策

1. **框架**：LangGraph（用户已确认）。LangGraph 建立在 LangChain 之上，天然满足"多步编排 + 状态传递 + 工具调用"。
2. **高德数据**：保留 `amap-mcp-server`，用 `langchain-mcp-adapters` 的 `MultiServerMCPClient` 加载为 LangChain Tool（用户已确认）。
3. **搜索节点确定性化**：现版本 3 个"专家 Agent"其实是通过硬编码 `[TOOL_CALL:...]` 字符串强制 LLM 调用工具（`_build_attraction_query` 里工具参数是写死的），没有真正的 LLM 决策。迁移后改为节点直接调用 MCP 工具，**LLM 只负责最后的行程生成**——行为等价、少 3 次无效 LLM 往返、并彻底移除脆弱的字符串解析 hack。
4. **全链路异步**：`langchain-mcp-adapters` 工具是 async 的，因此 `AmapService`、LangGraph 节点、FastAPI 路由全部改为 async，重试用 `asyncio` 版本。
5. **LLM 接入**：`ChatOpenAI` 通过 `base_url` 指向任意 OpenAI 兼容服务（默认 DeepSeek），配置字段统一为 `LLM_*`。
6. **测试标准化**：测试导入从 `backend.app.*` 改为 `app.*`（与运行时 `uvicorn app.api.main:app` 一致），新增 `backend/pytest.ini` 配置 `pythonpath` 与 `asyncio_mode`。

---

## 文件结构

**创建：**
- `backend/app/services/amap_tools.py` — 用 `MultiServerMCPClient` 加载 amap MCP 工具，提供 `get_amap_tools()` 与 `call_amap_tool()`。
- `backend/pytest.ini` — pytest 配置（testpaths / pythonpath / asyncio_mode）。

**重写：**
- `backend/app/services/llm_service.py` — `get_llm()` 返回 `ChatOpenAI`。
- `backend/app/services/retry.py` — 改为异步 `arun_with_retry`。
- `backend/app/services/amap_service.py` — 异步，基于 `call_amap_tool`，保留字段解析逻辑。
- `backend/app/agents/trip_planner_agent.py` — `LangGraphTripPlanner` + `StateGraph`。
- `backend/requirements.txt` — 替换依赖。

**修改：**
- `backend/app/config.py` — 移除 HelloAgents 相关逻辑，改为 `LLM_*` 配置。
- `backend/app/services/task_manager.py` — `await planner.plan_trip()`。
- `backend/app/api/main.py` — 更新描述文案。
- `backend/app/api/routes/map.py` — `await` 服务方法；修复健康检查。
- `backend/app/api/routes/poi.py` — `await` 服务方法。
- `backend/app/api/routes/trip.py` — 修复健康检查。
- `backend/tests/test_reliability.py`、`test_amap_service.py`、`test_api_routes.py` — 适配 async + LangGraph。
- `backend/.env.example`、`README.md` — 文档更新。

**不变（无需改动）：** 前端全部文件、`backend/app/models/schemas.py`、`backend/app/services/unsplash_service.py`、`backend/app/models/__init__.py`、各 `__init__.py`。

---

## 任务 1：更新依赖与安装

**文件：**
- 修改：`backend/requirements.txt`

- [ ] **步骤 1：替换 requirements.txt 内容**

```text
fastapi>=0.115.0
uvicorn[standard]>=0.32.0
pydantic>=2.0.0
pydantic-settings>=2.0.0

langchain>=0.3.20
langchain-openai>=0.2.14
langgraph>=0.2.60
langchain-mcp-adapters>=0.1.8

httpx>=0.27.0
aiohttp>=3.10.0
python-dotenv>=1.0.0
python-multipart>=0.0.9
loguru>=0.7.0
uv>=0.8.0
python-dateutil>=2.8.2

pytest>=8.0.0
pytest-asyncio>=0.24.0
```

> 移除 `hello-agents[protocols]`、`fastmcp`、`huggingface_hub`；`langchain-mcp-adapters` 会自动拉取所需的 `mcp` 包；保留 `uv` 因为 `amap-mcp-server` 经 `uvx` 启动。

- [ ] **步骤 2：安装依赖**

```powershell
cd E:\agent-project\helloagents-trip-planner\backend
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

预期：安装成功，退出码 0，无版本冲突。

- [ ] **步骤 3：验证导入**

```powershell
.\.venv\Scripts\python.exe -c "import langchain, langgraph, langchain_openai, langchain_mcp_adapters; print('deps OK')"
```

预期：输出 `deps OK`。

- [ ] **步骤 4：Commit**

```bash
git add backend/requirements.txt
git commit -m "build: replace hello-agents with langchain/langgraph stack"
```

---

## 任务 2：配置模块改造

**文件：**
- 修改：`backend/app/config.py`

- [ ] **步骤 1：用以下内容整体替换 `config.py`**

```python
"""配置管理模块"""

from typing import List
from pydantic_settings import BaseSettings
from dotenv import load_dotenv

# 加载 backend/.env（运行时 CWD 为 backend）
load_dotenv()


class Settings(BaseSettings):
    """应用配置"""

    # 应用基本配置
    app_name: str = "LangGraph智能旅行助手"
    app_version: str = "2.0.0"
    debug: bool = False

    # 服务器配置
    host: str = "0.0.0.0"
    port: int = 8000

    # CORS配置
    cors_origins: str = "http://localhost:5173,http://localhost:3000,http://127.0.0.1:5173,http://127.0.0.1:3000,http://127.0.0.1:8000"

    # 高德地图API配置
    amap_api_key: str = ""

    # Unsplash API配置
    unsplash_access_key: str = ""
    unsplash_secret_key: str = ""

    # LLM配置（ChatOpenAI，兼容 OpenAI / DeepSeek 等）
    llm_api_key: str = ""
    llm_base_url: str = "https://api.deepseek.com"
    llm_model_id: str = "deepseek-chat"
    llm_temperature: float = 0.7

    # 日志配置
    log_level: str = "INFO"

    class Config:
        env_file = ".env"
        case_sensitive = False
        extra = "ignore"

    def get_cors_origins_list(self) -> List[str]:
        """获取CORS origins列表"""
        return [origin.strip() for origin in self.cors_origins.split(',')]


# 创建全局配置实例
settings = Settings()


def get_settings() -> Settings:
    """获取配置实例"""
    return settings


def validate_config():
    """验证配置是否完整"""
    errors = []
    warnings = []

    if not settings.amap_api_key:
        errors.append("AMAP_API_KEY未配置")

    if not settings.llm_api_key:
        warnings.append("LLM_API_KEY未配置,行程规划(LLM)功能可能无法使用")

    if errors:
        raise ValueError("配置错误:\n" + "\n".join(f"  - {e}" for e in errors))

    for w in warnings:
        print(f"⚠️  {w}")

    return True


def print_config():
    """打印当前配置(隐藏敏感信息)"""
    print(f"应用名称: {settings.app_name}")
    print(f"版本: {settings.app_version}")
    print(f"服务器: {settings.host}:{settings.port}")
    print(f"高德地图API Key: {'已配置' if settings.amap_api_key else '未配置'}")
    print(f"LLM API Key: {'已配置' if settings.llm_api_key else '未配置'}")
    print(f"LLM Base URL: {settings.llm_base_url}")
    print(f"LLM Model: {settings.llm_model_id}")
    print(f"日志级别: {settings.log_level}")
```

> 说明：pydantic-settings 大小写不敏感，`llm_api_key`/`llm_base_url`/`llm_model_id`/`llm_temperature` 自动映射到环境变量 `LLM_API_KEY`/`LLM_BASE_URL`/`LLM_MODEL_ID`/`LLM_TEMPERATURE`。删除了原来加载 `HelloAgents/.env` 的代码块。

- [ ] **步骤 2：验证导入**

```powershell
cd E:\agent-project\helloagents-trip-planner\backend
.\.venv\Scripts\python.exe -c "from app.config import get_settings, validate_config, print_config; print(get_settings().llm_model_id)"
```

预期：打印配置的模型名（如 `deepseek-chat`），无异常。

- [ ] **步骤 3：Commit**

```bash
git add backend/app/config.py
git commit -m "refactor: replace hello-agents config with langchain LLM_* settings"
```

---

## 任务 3：LLM 服务改造

**文件：**
- 重写：`backend/app/services/llm_service.py`

- [ ] **步骤 1：用以下内容整体替换 `llm_service.py`**

```python
"""LLM服务模块 (LangChain)"""

from langchain_openai import ChatOpenAI

from ..config import get_settings

# 全局LLM实例
_llm_instance = None


def get_llm() -> ChatOpenAI:
    """获取 LLM 实例(单例)。"""
    global _llm_instance

    if _llm_instance is None:
        settings = get_settings()
        _llm_instance = ChatOpenAI(
            model=settings.llm_model_id,
            api_key=settings.llm_api_key,
            base_url=settings.llm_base_url,
            temperature=settings.llm_temperature,
            timeout=60,
            max_retries=2,
        )
        print("✅ LLM服务初始化成功")
        print(f"   Base URL: {settings.llm_base_url}")
        print(f"   模型: {settings.llm_model_id}")

    return _llm_instance


def reset_llm():
    """重置LLM实例(用于测试或重新配置)"""
    global _llm_instance
    _llm_instance = None
```

> 说明：`get_llm()` 只在行程生成节点被调用（懒加载），因此 `/api/map/*` 路线即使没有配置 LLM key 也能正常工作。

- [ ] **步骤 2：验证导入（不触发真实请求）**

```powershell
.\.venv\Scripts\python.exe -c "from app.services.llm_service import get_llm; print(type(get_llm()).__name__)"
```

预期：输出 `ChatOpenAI`。

- [ ] **步骤 3：Commit**

```bash
git add backend/app/services/llm_service.py
git commit -m "refactor: use ChatOpenAI for LLM service"
```

---

## 任务 4：异步重试工具（TDD）

**文件：**
- 重写：`backend/app/services/retry.py`
- 修改：`backend/tests/test_reliability.py`

- [ ] **步骤 1：编写失败测试**

先重写 `backend/tests/test_reliability.py` 为异步版本（此时 `arun_with_retry` 尚不存在，测试会失败）：

```python
import asyncio

import pytest

from app.services.retry import arun_with_retry
from app.agents.trip_planner_agent import LangGraphTripPlanner
from app.models.schemas import TripRequest


@pytest.mark.asyncio
async def test_arun_with_retry_succeeds_on_third_attempt():
    attempts = 0

    async def operation():
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise TimeoutError("temporary failure")
        return "ok"

    result = await arun_with_retry(operation, operation_name="test", backoff_seconds=(0, 0))
    assert result == "ok"
    assert attempts == 3


@pytest.mark.asyncio
async def test_arun_with_retry_raises_after_max_attempts():
    attempts = 0

    async def operation():
        nonlocal attempts
        attempts += 1
        raise ValueError("permanent failure")

    with pytest.raises(ValueError, match="permanent failure"):
        await arun_with_retry(operation, operation_name="test", backoff_seconds=(0, 0))
    assert attempts == 3


@pytest.mark.asyncio
async def test_arun_with_retry_applies_timeout():
    async def operation():
        await asyncio.sleep(0.1)

    with pytest.raises(TimeoutError, match="超时"):
        await arun_with_retry(operation, operation_name="test", timeout_seconds=0.01, backoff_seconds=(0, 0))


def test_trip_plan_validation_rejects_wrong_day_count():
    request = TripRequest(
        city="北京",
        start_date="2026-08-18",
        end_date="2026-08-19",
        travel_days=2,
        transportation="公共交通",
        accommodation="经济型酒店",
    )

    with pytest.raises(ValueError, match="行程天数"):
        LangGraphTripPlanner._validate_trip_plan({
            "city": "北京",
            "start_date": "2026-08-18",
            "end_date": "2026-08-19",
            "days": [],
            "weather_info": [],
            "overall_suggestions": "建议",
        }, request)
```

- [ ] **步骤 2：运行测试确认失败**

```powershell
cd E:\agent-project\helloagents-trip-planner\backend
.\.venv\Scripts\python.exe -m pytest tests/test_reliability.py -q
```

预期：`arun_with_retry` 相关测试 ImportError（函数不存在）；`LangGraphTripPlanner` 相关测试失败（旧类名仍是 `MultiAgentTripPlanner`）。

- [ ] **步骤 3：重写 `retry.py`**

```python
"""异步调用的重试与超时工具。"""

import asyncio
from typing import Awaitable, Callable, TypeVar

T = TypeVar("T")


async def arun_with_retry(
    operation: Callable[[], Awaitable[T]],
    *,
    operation_name: str,
    timeout_seconds: float = 30,
    max_attempts: int = 3,
    backoff_seconds: tuple[float, ...] = (1, 2),
) -> T:
    """在单次超时限制内执行异步操作，失败后按退避重试。"""
    last_error: Exception | None = None

    for attempt in range(max_attempts):
        try:
            return await asyncio.wait_for(operation(), timeout=timeout_seconds)
        except asyncio.TimeoutError:
            last_error = TimeoutError(f"{operation_name} 超时（{timeout_seconds:g} 秒）")
        except Exception as exc:
            last_error = exc

        if attempt < max_attempts - 1:
            await asyncio.sleep(backoff_seconds[min(attempt, len(backoff_seconds) - 1)])

    raise last_error or RuntimeError(f"{operation_name} 调用失败")
```

> `LangGraphTripPlanner._validate_trip_plan` 会在任务 7 才定义，任务 4 先只让 `arun_with_retry` 的三条测试通过。

- [ ] **步骤 4：运行测试验证通过**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_reliability.py -q
```

预期：3 条 `arun_with_retry` 测试 PASS；`LangGraphTripPlanner` 相关测试仍失败（留待任务 7 解决）。

- [ ] **步骤 5：Commit**

```bash
git add backend/app/services/retry.py backend/tests/test_reliability.py
git commit -m "feat: add async retry with timeout"
```

---

## 任务 5：高德 MCP 工具接入

**文件：**
- 创建：`backend/app/services/amap_tools.py`

- [ ] **步骤 1：创建 `amap_tools.py`**

```python
"""高德地图 MCP 工具接入 (langchain-mcp-adapters)。"""

import asyncio
from typing import Any, Dict, Optional

from langchain_core.tools import BaseTool
from langchain_mcp_adapters.client import MultiServerMCPClient

from ..config import get_settings

_client: Optional[MultiServerMCPClient] = None
_tools: Optional[Dict[str, BaseTool]] = None
_lock = asyncio.Lock()


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
```

- [ ] **步骤 2：验证导入**

```powershell
.\.venv\Scripts\python.exe -c "from app.services.amap_tools import call_amap_tool, get_amap_tools; print('amap_tools OK')"
```

预期：输出 `amap_tools OK`（此步不触发 MCP 连接）。

- [ ] **步骤 3：Commit**

```bash
git add backend/app/services/amap_tools.py
git commit -m "feat: expose amap mcp server as langchain tools"
```

---

## 任务 6：高德服务层改造（TDD）

**文件：**
- 重写：`backend/app/services/amap_service.py`
- 重写：`backend/tests/test_amap_service.py`

- [ ] **步骤 1：重写测试为异步版本**

```python
import json

import pytest

from app.models.schemas import Location, POIInfo, WeatherInfo
from app.services import amap_service as amap_mod
from app.services.amap_service import AmapService


def _fake_call(results):
    """返回一个把预设结果依次吐出的异步 call_amap_tool 替身。"""
    async def fake(tool_name, arguments):
        return results.pop(0)
    return fake


@pytest.mark.asyncio
async def test_search_poi_parses_wrapped_json_result(monkeypatch):
    results = [
        json.dumps({"pois": [{
            "id": "B001",
            "name": "故宫",
            "typecode": "风景名胜",
            "address": "北京市东城区景山前街4号",
        }]}),
        json.dumps({
            "id": "B001",
            "name": "故宫",
            "type": "风景名胜",
            "address": "北京市东城区景山前街4号",
            "location": "116.397128,39.916527",
            "tel": "010-12345678",
        }),
    ]
    monkeypatch.setattr(amap_mod, "call_amap_tool", _fake_call(results))

    pois = await AmapService().search_poi("故宫", "北京")

    assert pois == [POIInfo(
        id="B001",
        name="故宫",
        type="风景名胜",
        address="北京市东城区景山前街4号",
        location=Location(longitude=116.397128, latitude=39.916527),
        tel="010-12345678",
    )]


@pytest.mark.asyncio
async def test_get_weather_parses_json_code_block_and_temperature_units(monkeypatch):
    result = "```json\n" + json.dumps({"forecasts": [{
        "date": "2026-08-18",
        "dayweather": "晴",
        "nightweather": "多云",
        "daytemp": "32℃",
        "nighttemp": "24℃",
        "daywind": "南",
        "daypower": "1-3级",
    }]}) + "\n```"
    monkeypatch.setattr(amap_mod, "call_amap_tool", _fake_call([result]))

    weather = await AmapService().get_weather("北京")

    assert weather == [WeatherInfo(
        date="2026-08-18",
        day_weather="晴",
        night_weather="多云",
        day_temp=32,
        night_temp=24,
        wind_direction="南",
        wind_power="1-3级",
    )]


@pytest.mark.asyncio
async def test_plan_route_parses_route_info(monkeypatch):
    result = json.dumps({"route": {"paths": [{
        "distance": "1200",
        "duration": "900",
        "steps": [{"instruction": "沿道路步行"}],
    }]}})
    monkeypatch.setattr(amap_mod, "call_amap_tool", _fake_call([result]))

    route = await AmapService().plan_route("起点", "终点")

    assert route == {
        "distance": 1200,
        "duration": 900,
        "route_type": "walking",
        "description": "沿道路步行",
    }


@pytest.mark.asyncio
async def test_geocode_parses_location_string(monkeypatch):
    result = json.dumps({"return": [{"location": "116.397128,39.916527"}]})
    monkeypatch.setattr(amap_mod, "call_amap_tool", _fake_call([result]))

    location = await AmapService().geocode("故宫", "北京")

    assert location == Location(longitude=116.397128, latitude=39.916527)
```

> 关键点：monkeypatch 的目标是 `app.services.amap_service` 里 import 的 `call_amap_tool` 名字（`amap_mod.call_amap_tool`），`AmapService._call` 通过该模块级名字调用它。

- [ ] **步骤 2：运行测试确认失败**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_amap_service.py -q
```

预期：失败（旧 `AmapService` 是同步的且依赖 `self.mcp_tool.run`）。

- [ ] **步骤 3：用以下内容整体替换 `amap_service.py`**

```python
"""高德地图服务封装 (基于 langchain-mcp-adapters 工具)。"""

import json
import re
from typing import Any, Dict, List, Optional

from ..models.schemas import Location, POIInfo, WeatherInfo
from .amap_tools import call_amap_tool
from .retry import arun_with_retry


class AmapService:
    """高德地图服务封装类(异步)。"""

    async def _call(self, tool_name: str, arguments: Dict[str, Any], operation_name: str) -> Any:
        """调用 MCP 工具,带统一超时和重试。"""
        return await arun_with_retry(
            lambda: call_amap_tool(tool_name, arguments),
            operation_name=operation_name,
        )

    @staticmethod
    def _parse_json_result(result: Any) -> Any:
        """从 MCP 返回值中提取 JSON,兼容代码块和文本包装。"""
        if isinstance(result, (dict, list)):
            return result

        if not isinstance(result, str):
            raise ValueError("MCP 返回结果不是 JSON 或字符串")

        text = result.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.IGNORECASE).strip()

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            object_match = re.search(r"\{.*\}", text, re.DOTALL)
            if object_match:
                return json.loads(object_match.group(0))
            array_match = re.search(r"\[.*\]", text, re.DOTALL)
            if array_match:
                return json.loads(array_match.group(0))
            raise ValueError("MCP 返回结果中未找到有效 JSON")

    @staticmethod
    def _first_value(data: Dict[str, Any], *keys: str, default: Any = None) -> Any:
        """从多个候选字段名中取第一个非空值。"""
        for key in keys:
            value = data.get(key)
            if value is not None and value != "":
                return value
        return default

    @staticmethod
    def _parse_location(value: Any) -> Optional[Location]:
        """解析高德常见的 longitude,latitude 坐标格式。"""
        if isinstance(value, dict):
            longitude = value.get("longitude", value.get("lng"))
            latitude = value.get("latitude", value.get("lat"))
            if longitude is not None and latitude is not None:
                return Location(longitude=float(longitude), latitude=float(latitude))

        if isinstance(value, str):
            parts = [part.strip() for part in value.split(",")]
            if len(parts) == 2:
                return Location(longitude=float(parts[0]), latitude=float(parts[1]))

        return None

    @staticmethod
    def _unwrap_payload(payload: Any, *keys: str) -> Any:
        """从常见包装字段中取出实际数据。"""
        if isinstance(payload, dict):
            for key in keys:
                if key in payload:
                    return payload[key]
        return payload

    async def search_poi(self, keywords: str, city: str, citylimit: bool = True) -> List[POIInfo]:
        """搜索 POI。"""
        try:
            result = await self._call(
                "maps_text_search",
                {"keywords": keywords, "city": city, "citylimit": str(citylimit).lower()},
                "高德 POI 搜索",
            )
            print(f"POI搜索结果: {str(result)[:200]}...")

            payload = self._unwrap_payload(self._parse_json_result(result), "pois", "data", "results")
            if isinstance(payload, dict):
                payload = payload.get("pois", payload.get("results", []))

            pois = []
            for item in payload if isinstance(payload, list) else []:
                poi_id = self._first_value(item, "id", "poi_id", default="")
                detail = await self.get_poi_detail(str(poi_id)) if poi_id else {}
                merged = {**item, **detail}
                location = self._parse_location(merged.get("location"))
                if not location:
                    continue
                pois.append(POIInfo(
                    id=str(self._first_value(merged, "id", "poi_id", default="")),
                    name=str(self._first_value(merged, "name", default="")),
                    type=str(self._first_value(merged, "type", "typecode", default="")),
                    address=str(self._first_value(merged, "address", default="")),
                    location=location,
                    tel=self._first_value(merged, "tel", "telephone"),
                ))
            return pois
        except Exception as e:
            print(f"❌ POI搜索失败: {str(e)}")
            return []

    async def get_weather(self, city: str) -> List[WeatherInfo]:
        """查询天气。"""
        try:
            result = await self._call(
                "maps_weather",
                {"city": city},
                "高德天气查询",
            )
            print(f"天气查询结果: {str(result)[:200]}...")

            payload = self._parse_json_result(result)
            if isinstance(payload, dict):
                payload = payload.get("forecasts", payload.get("casts", payload.get("data", [])))

            weather = []
            for item in payload if isinstance(payload, list) else []:
                weather.append(WeatherInfo(
                    date=str(self._first_value(item, "date", "week", default="")),
                    day_weather=str(self._first_value(item, "dayweather", "day_weather", default="")),
                    night_weather=str(self._first_value(item, "nightweather", "night_weather", default="")),
                    day_temp=self._first_value(item, "daytemp", "day_temp", default=0),
                    night_temp=self._first_value(item, "nighttemp", "night_temp", default=0),
                    wind_direction=str(self._first_value(item, "daywind", "wind_direction", default="")),
                    wind_power=str(self._first_value(item, "daypower", "wind_power", default="")),
                ))
            return weather
        except Exception as e:
            print(f"❌ 天气查询失败: {str(e)}")
            return []

    async def plan_route(
        self,
        origin_address: str,
        destination_address: str,
        origin_city: Optional[str] = None,
        destination_city: Optional[str] = None,
        route_type: str = "walking",
    ) -> Dict[str, Any]:
        """规划路线。"""
        try:
            tool_map = {
                "walking": "maps_direction_walking_by_address",
                "driving": "maps_direction_driving_by_address",
                "transit": "maps_direction_transit_integrated_by_address",
            }
            tool_name = tool_map.get(route_type, "maps_direction_walking_by_address")

            arguments = {
                "origin_address": origin_address,
                "destination_address": destination_address,
            }
            if origin_city:
                arguments["origin_city"] = origin_city
            if destination_city:
                arguments["destination_city"] = destination_city

            result = await self._call(tool_name, arguments, "高德路线规划")
            print(f"路线规划结果: {str(result)[:200]}...")

            payload = self._parse_json_result(result)
            route = payload.get("route", {}) if isinstance(payload, dict) else {}
            paths = route.get("paths", []) if isinstance(route, dict) else []
            if not paths:
                return {}
            path = paths[0]
            steps = path.get("steps", []) if isinstance(path, dict) else []
            instructions = [step.get("instruction") for step in steps if isinstance(step, dict) and step.get("instruction")]
            return {
                "distance": float(self._first_value(path, "distance", default=0)),
                "duration": int(float(self._first_value(path, "duration", default=0))),
                "route_type": route_type,
                "description": "；".join(instructions),
            }
        except Exception as e:
            print(f"❌ 路线规划失败: {str(e)}")
            return {}

    async def geocode(self, address: str, city: Optional[str] = None) -> Optional[Location]:
        """地理编码(地址转坐标)。"""
        try:
            arguments = {"address": address}
            if city:
                arguments["city"] = city

            result = await self._call("maps_geo", arguments, "高德地理编码")
            print(f"地理编码结果: {str(result)[:200]}...")

            payload = self._parse_json_result(result)
            geocodes = payload.get("return", []) if isinstance(payload, dict) else []
            first = geocodes[0] if isinstance(geocodes, list) and geocodes else None
            return self._parse_location(first.get("location") if isinstance(first, dict) else first)
        except Exception as e:
            print(f"❌ 地理编码失败: {str(e)}")
            return None

    async def get_poi_detail(self, poi_id: str) -> Dict[str, Any]:
        """获取 POI 详情。"""
        try:
            result = await self._call(
                "maps_search_detail",
                {"id": poi_id},
                "高德 POI 详情",
            )
            print(f"POI详情结果: {str(result)[:200]}...")

            data = self._parse_json_result(result)
            return data if isinstance(data, dict) else {"raw": result}
        except Exception as e:
            print(f"❌ 获取POI详情失败: {str(e)}")
            return {}


# 创建全局服务实例
_amap_service = None


def get_amap_service() -> AmapService:
    """获取高德地图服务实例(单例模式)"""
    global _amap_service
    if _amap_service is None:
        _amap_service = AmapService()
    return _amap_service
```

> 说明：`AmapService.__init__` 不再立即初始化 MCP（懒加载），因此即使没有 `uvx`/API key，也能安全导入和实例化。

- [ ] **步骤 4：运行测试验证通过**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_amap_service.py -q
```

预期：4 条测试全部 PASS。

- [ ] **步骤 5：Commit**

```bash
git add backend/app/services/amap_service.py backend/tests/test_amap_service.py
git commit -m "refactor: make amap service async over langchain mcp tools"
```

---

## 任务 7：LangGraph 行程规划器（TDD）

**文件：**
- 重写：`backend/app/agents/trip_planner_agent.py`
- 修改：`backend/tests/test_reliability.py`（已在任务 4 写好，此处补全类名）

- [ ] **步骤 1：用以下内容整体替换 `trip_planner_agent.py`**

```python
"""基于 LangGraph 的旅行规划工作流。"""

import json
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, TypedDict

from langchain_core.messages import HumanMessage
from langgraph.graph import END, START, StateGraph

from ..models.schemas import (
    Attraction,
    DayPlan,
    Location,
    Meal,
    TripPlan,
    TripRequest,
)
from ..services.amap_service import get_amap_service
from ..services.llm_service import get_llm


PLANNER_PROMPT = """你是行程规划专家。你的任务是根据景点信息和天气信息,生成详细的旅行计划。

请严格按照以下JSON格式返回旅行计划:
```json
{
  "city": "城市名称",
  "start_date": "YYYY-MM-DD",
  "end_date": "YYYY-MM-DD",
  "days": [
    {
      "date": "YYYY-MM-DD",
      "day_index": 0,
      "description": "第1天行程概述",
      "transportation": "交通方式",
      "accommodation": "住宿类型",
      "hotel": {
        "name": "酒店名称",
        "address": "酒店地址",
        "location": {"longitude": 116.397128, "latitude": 39.916527},
        "price_range": "300-500元",
        "rating": "4.5",
        "distance": "距离景点2公里",
        "type": "经济型酒店",
        "estimated_cost": 400
      },
      "attractions": [
        {
          "name": "景点名称",
          "address": "详细地址",
          "location": {"longitude": 116.397128, "latitude": 39.916527},
          "visit_duration": 120,
          "description": "景点详细描述",
          "category": "景点类别",
          "ticket_price": 60
        }
      ],
      "meals": [
        {"type": "breakfast", "name": "早餐推荐", "description": "早餐描述", "estimated_cost": 30},
        {"type": "lunch", "name": "午餐推荐", "description": "午餐描述", "estimated_cost": 50},
        {"type": "dinner", "name": "晚餐推荐", "description": "晚餐描述", "estimated_cost": 80}
      ]
    }
  ],
  "weather_info": [
    {
      "date": "YYYY-MM-DD",
      "day_weather": "晴",
      "night_weather": "多云",
      "day_temp": 25,
      "night_temp": 15,
      "wind_direction": "南风",
      "wind_power": "1-3级"
    }
  ],
  "overall_suggestions": "总体建议",
  "budget": {
    "total_attractions": 180,
    "total_hotels": 1200,
    "total_meals": 480,
    "total_transportation": 200,
    "total": 2060
  }
}
```

**重要提示:**
1. weather_info数组必须包含每一天的天气信息
2. 温度必须是纯数字(不要带°C等单位)
3. 每天安排2-3个景点
4. 考虑景点之间的距离和游览时间
5. 每天必须包含早中晚三餐
6. 提供实用的旅行建议
7. **必须包含预算信息**:
   - 景点门票价格(ticket_price)
   - 餐饮预估费用(estimated_cost)
   - 酒店预估费用(estimated_cost)
   - 预算汇总(budget)包含各项总费用
"""


class PlannerState(TypedDict, total=False):
    request: TripRequest
    attractions: List[Dict[str, Any]]
    weather: List[Dict[str, Any]]
    hotels: List[Dict[str, Any]]
    plan: Optional[TripPlan]


class LangGraphTripPlanner:
    """LangGraph 旅行规划工作流。"""

    def __init__(self):
        self.service = get_amap_service()
        self.graph = self._build_graph()

    def _build_graph(self):
        builder = StateGraph(PlannerState)
        builder.add_node("search_attractions", self._search_attractions)
        builder.add_node("query_weather", self._query_weather)
        builder.add_node("search_hotels", self._search_hotels)
        builder.add_node("plan_itinerary", self._plan_itinerary)
        builder.add_edge(START, "search_attractions")
        builder.add_edge("search_attractions", "query_weather")
        builder.add_edge("query_weather", "search_hotels")
        builder.add_edge("search_hotels", "plan_itinerary")
        builder.add_edge("plan_itinerary", END)
        return builder.compile()

    async def _search_attractions(self, state: PlannerState) -> Dict[str, Any]:
        request = state["request"]
        keywords = request.preferences[0] if request.preferences else "景点"
        pois = await self.service.search_poi(keywords, request.city)
        return {"attractions": [p.model_dump() for p in pois]}

    async def _query_weather(self, state: PlannerState) -> Dict[str, Any]:
        weather = await self.service.get_weather(state["request"].city)
        return {"weather": [w.model_dump() for w in weather]}

    async def _search_hotels(self, state: PlannerState) -> Dict[str, Any]:
        request = state["request"]
        pois = await self.service.search_poi(f"{request.accommodation}酒店", request.city)
        return {"hotels": [p.model_dump() for p in pois]}

    async def _plan_itinerary(self, state: PlannerState) -> Dict[str, Any]:
        request = state["request"]
        prompt = self._build_planner_prompt(
            request,
            state.get("attractions", []),
            state.get("weather", []),
            state.get("hotels", []),
        )
        plan = await self._generate_plan(prompt, request)
        return {"plan": plan}

    async def plan_trip(self, request: TripRequest) -> TripPlan:
        """执行完整工作流,返回旅行计划。"""
        result = await self.graph.ainvoke({"request": request})
        plan = result.get("plan")
        if plan is None:
            return self._create_fallback_plan(request)
        return plan

    def _build_planner_prompt(
        self,
        request: TripRequest,
        attractions: List[Dict[str, Any]],
        weather: List[Dict[str, Any]],
        hotels: List[Dict[str, Any]],
    ) -> str:
        attractions_json = json.dumps(attractions, ensure_ascii=False, indent=2)
        weather_json = json.dumps(weather, ensure_ascii=False, indent=2)
        hotels_json = json.dumps(hotels, ensure_ascii=False, indent=2)

        query = f"""请根据以下信息生成{request.city}的{request.travel_days}天旅行计划:

**基本信息:**
- 城市: {request.city}
- 日期: {request.start_date} 至 {request.end_date}
- 天数: {request.travel_days}天
- 交通方式: {request.transportation}
- 住宿: {request.accommodation}
- 偏好: {', '.join(request.preferences) if request.preferences else '无'}

**景点信息(JSON):**
{attractions_json}

**天气信息(JSON):**
{weather_json}

**酒店信息(JSON):**
{hotels_json}

**要求:**
1. 每天安排2-3个景点
2. 每天必须包含早中晚三餐
3. 每天推荐一个具体的酒店(从酒店信息中选择)
4. 考虑景点之间的距离和交通方式
5. 返回完整的JSON格式数据
6. 景点的经纬度坐标要真实准确
"""
        if request.free_text_input:
            query += f"\n**额外要求:** {request.free_text_input}"
        return query

    async def _generate_plan(self, prompt: str, request: TripRequest) -> TripPlan:
        llm = get_llm()
        try:
            response = await llm.ainvoke([HumanMessage(content=prompt)])
            data = self._extract_json(response.content)
            return self._validate_trip_plan(data, request)
        except Exception as e:
            print(f"⚠️ 生成行程计划失败: {str(e)}, 尝试让 LLM 修复 JSON")
            try:
                repair_prompt = (
                    f"上一次旅行计划输出未通过校验({e})。请只返回完整、合法的 JSON，"
                    f"并生成 {request.city} {request.travel_days} 天行程。"
                )
                repaired = await llm.ainvoke([HumanMessage(content=repair_prompt)])
                repaired_data = self._extract_json(repaired.content)
                return self._validate_trip_plan(repaired_data, request)
            except Exception as repair_error:
                print(f"⚠️ 修复行程计划失败: {repair_error}")
                return self._create_fallback_plan(request)

    @staticmethod
    def _extract_json(response: Any) -> Dict[str, Any]:
        """从 LLM 文本中提取 JSON 对象。"""
        if not isinstance(response, str):
            raise ValueError("LLM 响应不是字符串")

        if "```" in response:
            parts = response.split("```")
            response = parts[1] if len(parts) > 1 else response
            response = response.removeprefix("json").strip()

        start, end = response.find("{"), response.rfind("}")
        if start < 0 or end <= start:
            raise ValueError("响应中未找到 JSON 对象")
        return json.loads(response[start:end + 1])

    @staticmethod
    def _validate_trip_plan(data: Dict[str, Any], request: TripRequest) -> TripPlan:
        """校验结构化计划和基本业务约束。"""
        plan = TripPlan.model_validate(data)
        if len(plan.days) != request.travel_days:
            raise ValueError("行程天数与请求不一致")
        for day in plan.days:
            if not day.attractions:
                raise ValueError(f"{day.date} 没有景点")
            meal_types = {meal.type for meal in day.meals}
            if not {"breakfast", "lunch", "dinner"}.issubset(meal_types):
                raise ValueError(f"{day.date} 缺少早中晚餐")
        return plan

    @staticmethod
    def _create_fallback_plan(request: TripRequest) -> TripPlan:
        """创建备用计划(当 Agent 失败时)。"""
        start_date = datetime.strptime(request.start_date, "%Y-%m-%d")

        days = []
        for i in range(request.travel_days):
            current_date = start_date + timedelta(days=i)

            day_plan = DayPlan(
                date=current_date.strftime("%Y-%m-%d"),
                day_index=i,
                description=f"第{i+1}天行程",
                transportation=request.transportation,
                accommodation=request.accommodation,
                attractions=[
                    Attraction(
                        name=f"{request.city}景点{j+1}",
                        address=f"{request.city}市",
                        location=Location(longitude=116.4 + i * 0.01 + j * 0.005, latitude=39.9 + i * 0.01 + j * 0.005),
                        visit_duration=120,
                        description=f"这是{request.city}的著名景点",
                        category="景点",
                    )
                    for j in range(2)
                ],
                meals=[
                    Meal(type="breakfast", name=f"第{i+1}天早餐", description="当地特色早餐"),
                    Meal(type="lunch", name=f"第{i+1}天午餐", description="午餐推荐"),
                    Meal(type="dinner", name=f"第{i+1}天晚餐", description="晚餐推荐"),
                ],
            )
            days.append(day_plan)

        return TripPlan(
            city=request.city,
            start_date=request.start_date,
            end_date=request.end_date,
            days=days,
            weather_info=[],
            overall_suggestions=f"这是为您规划的{request.city}{request.travel_days}日游行程,建议提前查看各景点的开放时间。",
        )


# 全局规划器实例
_planner = None


def get_trip_planner_agent() -> LangGraphTripPlanner:
    """获取旅行规划工作流实例(单例模式)。"""
    global _planner
    if _planner is None:
        _planner = LangGraphTripPlanner()
    return _planner
```

- [ ] **步骤 2：运行任务 4 已写好的校验测试**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_reliability.py -q
```

预期：`test_trip_plan_validation_rejects_wrong_day_count` 与 3 条重试测试全部 PASS（此时 `LangGraphTripPlanner` 已存在）。

- [ ] **步骤 3：补充图的编译冒烟测试**

在 `tests/test_reliability.py` 末尾追加：

```python
def test_graph_compiles_with_expected_nodes():
    planner = LangGraphTripPlanner.__new__(LangGraphTripPlanner)  # 跳过 __init__ 的 MCP 依赖
    graph = planner._build_graph()
    nodes = set(graph.get_graph().nodes.keys())
    assert {"search_attractions", "query_weather", "search_hotels", "plan_itinerary"} <= nodes
```

> `_build_graph` 不触发 LLM/MCP 连接，只构建图结构，因此用 `__new__` 绕过 `__init__` 即可安全测试。

- [ ] **步骤 4：运行测试验证通过**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_reliability.py -q
```

预期：5 条测试全部 PASS。

- [ ] **步骤 5：Commit**

```bash
git add backend/app/agents/trip_planner_agent.py backend/tests/test_reliability.py
git commit -m "refactor: replace hello-agents multi-agent with langgraph state graph"
```

---

## 任务 8：任务管理器改为直接 await

**文件：**
- 修改：`backend/app/services/task_manager.py`

- [ ] **步骤 1：修改 `run` 方法**

把 `task_manager.py` 第 46 行：

```python
            plan: TripPlan = await asyncio.to_thread(planner.plan_trip, request)
```

替换为：

```python
            plan: TripPlan = await planner.plan_trip(request)
```

同时删除文件顶部不再使用的 `import asyncio`（第 3 行）。

- [ ] **步骤 2：验证导入**

```powershell
.\.venv\Scripts\python.exe -c "from app.services.task_manager import task_manager; print('task_manager OK')"
```

预期：输出 `task_manager OK`。

- [ ] **步骤 3：Commit**

```bash
git add backend/app/services/task_manager.py
git commit -m "refactor: await async planner directly in task manager"
```

---

## 任务 9：路由适配 async 并修复健康检查（TDD）

**文件：**
- 修改：`backend/app/api/routes/map.py`
- 修改：`backend/app/api/routes/poi.py`
- 修改：`backend/app/api/routes/trip.py`
- 修改：`backend/app/api/main.py`
- 修改：`backend/tests/test_api_routes.py`

- [ ] **步骤 1：改写测试（适配 async 服务与 planner）**

用以下内容整体替换 `backend/tests/test_api_routes.py`：

```python
from fastapi.testclient import TestClient

from app.api.main import app
from app.api.routes import map as map_routes
from app.api.routes import trip as trip_routes
from app.models.schemas import TripPlan


client = TestClient(app)


class FakeMapService:
    def __init__(self, route_result=None):
        self.route_result = route_result

    async def search_poi(self, *_args):
        return []

    async def get_weather(self, *_args):
        return []

    async def plan_route(self, **_kwargs):
        return self.route_result


def test_root_and_health():
    assert client.get("/").status_code == 200
    assert client.get("/health").json()["status"] == "healthy"


def test_map_poi_and_weather_return_success(monkeypatch):
    monkeypatch.setattr(map_routes, "get_amap_service", lambda: FakeMapService())

    poi_response = client.get("/api/map/poi", params={"keywords": "故宫", "city": "北京"})
    weather_response = client.get("/api/map/weather", params={"city": "北京"})

    assert poi_response.status_code == 200
    assert poi_response.json() == {"success": True, "message": "POI搜索成功", "data": []}
    assert weather_response.status_code == 200
    assert weather_response.json() == {"success": True, "message": "天气查询成功", "data": []}


def test_map_route_returns_route_info(monkeypatch):
    route = {
        "distance": 1200,
        "duration": 900,
        "route_type": "walking",
        "description": "沿道路步行",
    }
    monkeypatch.setattr(map_routes, "get_amap_service", lambda: FakeMapService(route))

    response = client.post("/api/map/route", json={
        "origin_address": "起点",
        "destination_address": "终点",
    })

    assert response.status_code == 200
    assert response.json()["data"] == route


def test_map_route_returns_502_when_service_fails(monkeypatch):
    monkeypatch.setattr(map_routes, "get_amap_service", lambda: FakeMapService({}))

    response = client.post("/api/map/route", json={
        "origin_address": "起点",
        "destination_address": "终点",
    })

    assert response.status_code == 502
    assert response.json()["detail"] == "高德地图路线服务暂时不可用"


def test_trip_plan_rejects_invalid_request():
    response = client.post("/api/trip/plan", json={"city": "北京"})
    assert response.status_code == 422


def test_trip_plan_returns_structured_response(monkeypatch):
    plan = TripPlan(
        city="北京",
        start_date="2026-08-18",
        end_date="2026-08-18",
        days=[],
        weather_info=[],
        overall_suggestions="建议提前预约",
    )

    class FakeAgent:
        async def plan_trip(self, _request):
            return plan

    monkeypatch.setattr(trip_routes, "get_trip_planner_agent", lambda: FakeAgent())
    response = client.post("/api/trip/plan", json={
        "city": "北京",
        "start_date": "2026-08-18",
        "end_date": "2026-08-18",
        "travel_days": 1,
        "transportation": "公共交通",
        "accommodation": "经济型酒店",
        "preferences": [],
        "free_text_input": "",
    })

    assert response.status_code == 200
    assert response.json()["success"] is True
    assert response.json()["data"]["city"] == "北京"
```

- [ ] **步骤 2：运行测试确认失败**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_api_routes.py -q
```

预期：失败——因为路由里还是同步调用 `service.search_poi(...)`（`await` 一个普通返回值会报错），且 `trip.py` 健康检查引用了不存在的 `agent.agent`。

- [ ] **步骤 3：修改 `map.py`**

将三处服务调用加 `await`，并改写健康检查：

```python
        pois = service.search_poi(keywords, city, citylimit)
```
改为：
```python
        pois = await service.search_poi(keywords, city, citylimit)
```

```python
        weather_info = service.get_weather(city)
```
改为：
```python
        weather_info = await service.get_weather(city)
```

```python
        route_info = service.plan_route(
```
改为：
```python
        route_info = await service.plan_route(
```

在文件顶部 import 区域新增：

```python
from ...services.amap_tools import get_amap_tools
```

把 `health_check` 函数体替换为：

```python
    try:
        tools = await get_amap_tools()
        return {
            "status": "healthy",
            "service": "map-service",
            "mcp_tools_count": len(tools),
        }
    except Exception as e:
        raise HTTPException(
            status_code=503,
            detail=f"服务不可用: {str(e)}"
        )
```

- [ ] **步骤 4：修改 `poi.py`**

两处加 `await`：

```python
        result = amap_service.get_poi_detail(poi_id)
```
改为：
```python
        result = await amap_service.get_poi_detail(poi_id)
```

```python
        result = amap_service.search_poi(keywords, city)
```
改为：
```python
        result = await amap_service.search_poi(keywords, city)
```

> `/poi/photo` 调用的是同步 `unsplash_service`，保持不变。

- [ ] **步骤 5：修改 `trip.py` 健康检查**

把 `health_check` 函数体替换为：

```python
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
```

- [ ] **步骤 6：修改 `main.py` 描述文案**

把第 15 行：

```python
    description="基于HelloAgents框架的智能旅行规划助手API",
```
改为：
```python
    description="基于LangGraph框架的智能旅行规划助手API",
```

- [ ] **步骤 7：运行测试验证通过**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_api_routes.py -q
```

预期：6 条测试全部 PASS。

- [ ] **步骤 8：Commit**

```bash
git add backend/app/api/main.py backend/app/api/routes/map.py backend/app/api/routes/poi.py backend/app/api/routes/trip.py backend/tests/test_api_routes.py
git commit -m "refactor: await async map/poi services and fix health checks"
```

---

## 任务 10：新增 pytest 配置

**文件：**
- 创建：`backend/pytest.ini`

- [ ] **步骤 1：创建 `pytest.ini`**

```ini
[pytest]
testpaths = tests
pythonpath = .
asyncio_mode = auto
```

> `pythonpath = .` 让 `app.*` 在从任意目录运行 pytest 时都可导入；`asyncio_mode = auto` 使 async 测试无需手动加 `@pytest.mark.asyncio`（保留了装饰器也无副作用）。

- [ ] **步骤 2：从仓库根目录运行全量测试验证**

```powershell
cd E:\agent-project\helloagents-trip-planner\backend
.\.venv\Scripts\python.exe -m pytest -q
```

预期：`tests/test_reliability.py`、`tests/test_amap_service.py`、`tests/test_api_routes.py` 全部 PASS。

- [ ] **步骤 3：Commit**

```bash
git add backend/pytest.ini
git commit -m "test: add pytest config for app package and asyncio"
```

---

## 任务 11：文档更新

**文件：**
- 修改：`backend/.env.example`
- 修改：`README.md`

- [ ] **步骤 1：更新 `.env.example`**

用以下内容整体替换：

```dotenv
# LLM配置（OpenAI 兼容，支持 DeepSeek / OpenAI 等）
# 模型名称（DeepSeek 官方模型为 deepseek-chat / deepseek-reasoner）
LLM_MODEL_ID=deepseek-chat

# API密钥
LLM_API_KEY=sk-your-key-here

# 服务地址（OpenAI 兼容端点）
LLM_BASE_URL=https://api.deepseek.com

# 温度（0-1，可选，默认 0.7）
LLM_TEMPERATURE=0.7

# 服务器配置
HOST=0.0.0.0
PORT=8000

# CORS配置
CORS_ORIGINS=http://localhost:5173,http://localhost:3000,http://127.0.0.1:5173

# 日志级别
LOG_LEVEL=INFO

# Unsplash API Credentials（用于景点配图）
UNSPLASH_ACCESS_KEY=your-unsplash-access-key
UNSPLASH_SECRET_KEY=your-unsplash-secret-key

# 高德地图API配置（Web服务API Key）
AMAP_API_KEY=your-amap-web-service-key
```

> 注意：旧的 `LLM_TIMEOUT` 已不再使用；`LLM_API_KEY`/`LLM_BASE_URL`/`LLM_MODEL_ID`/`LLM_TEMPERATURE` 由 `Settings` 直接映射。

- [ ] **步骤 2：更新 `README.md`**

  - 把标题下"基于HelloAgents框架"改为"基于 LangGraph + LangChain 框架"。
  - "技术栈 → 后端"一节，把"框架: HelloAgents (基于SimpleAgent)"改为"框架: LangGraph + LangChain"，"LLM: 支持多种LLM提供商(OpenAI, DeepSeek等)"保持不变。
  - "核心实现"一节，把 HelloAgents Agent 集成代码示例替换为 LangGraph 说明（一句话即可，指向 `backend/app/agents/trip_planner_agent.py`）。
  - "致谢"保留，新增 LangChain/LangGraph 链接。
  - 项目结构里 `trip_planner_agent.py` 描述改为"LangGraph 工作流实现"。

- [ ] **步骤 3：Commit**

```bash
git add backend/.env.example README.md
git commit -m "docs: update env example and readme for langgraph"
```

---

## 任务 12：全量验证

- [ ] **步骤 1：运行完整测试与编译检查**

```powershell
cd E:\agent-project\helloagents-trip-planner\backend
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m compileall -q app
```

预期：全部测试 PASS，编译退出码 0。

- [ ] **步骤 2：启动服务冒烟测试**

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.api.main:app --host 0.0.0.0 --port 8000
```

另开一个终端验证：

```powershell
curl.exe http://127.0.0.1:8000/health
curl.exe http://127.0.0.1:8000/api/trip/health
curl.exe http://127.0.0.1:8000/api/map/health
```

预期：`/health` 返回 `{"status":"healthy",...}`；`/api/trip/health` 返回 `graph_nodes` 包含 4 个节点；`/api/map/health` 返回 `mcp_tools_count > 0`（需要本机已安装 `uvx` 且 `amap-mcp-server` 可用）。

- [ ] **步骤 3：端到端行程生成（需要有效的 LLM 与高德 Key）**

```powershell
curl.exe -X POST http://127.0.0.1:8000/api/trip/plan -H "Content-Type: application/json" -d "{\"city\":\"北京\",\"start_date\":\"2026-08-20\",\"end_date\":\"2026-08-21\",\"travel_days\":2,\"transportation\":\"公共交通\",\"accommodation\":\"经济型酒店\",\"preferences\":[\"历史文化\"],\"free_text_input\":\"\"}"
```

然后用返回的 `task_id` 轮询：

```powershell
curl.exe http://127.0.0.1:8000/api/trip/tasks/<task_id>
```

预期：`status` 最终为 `completed`，`data` 是符合 `TripPlan` 结构的行程。

- [ ] **步骤 4：变更复核**

  - `grep -rn "hello_agents\|HelloAgents\|SimpleAgent\|MCPTool" backend/app` 应无结果（`README.md` 致谢部分除外）。
  - 检查 `.env` 未被修改、密钥未入库（`git diff --stat` 确认）。
  - 确认前端 `frontend/src/services/api.ts` 与 `frontend/src/types/index.ts` 未改动，API 契约一致。

---

## 风险与注意事项

1. **`uvx`/`amap-mcp-server` 环境**：`/api/map/*` 与行程搜索节点依赖本机 `uvx` 可用。若 CI 无 `uvx`，需在 CI 安装 `uv`。
2. **LLM 模型名**：`.env` 中的 `LLM_MODEL_ID` 必须是目标 provider 真实存在的模型（DeepSeek 为 `deepseek-chat`/`deepseek-reasoner`）；若用户使用自建代理，按代理文档填写。
3. **MCP 会话开销**：`MultiServerMCPClient.get_tools()` 返回的工具每次调用会新建 stdio 子进程会话，`search_poi` 还会对每个 POI 追加一次 `get_poi_detail`，慢城市下 N+1 明显。MVP 可接受；后续可改为持久会话或直连 REST。
4. **健康检查真实依赖**：`/api/map/health` 会真实拉起 MCP 工具（`get_amap_tools()`），首次调用较慢；测试中已用 mock 规避。
5. **`plan_trip` 的失败降级**：若 LLM 或 MCP 任一环节异常，最终都会走 `_create_fallback_plan`，保证 API 始终返回可用结构，不会 500。
