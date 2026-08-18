# Agent 可靠性增强实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 为旅行规划后端增加 LLM/MCP 重试与超时、结构化行程校验、稳定的路线失败响应和 API 路由测试。

**架构：** 在服务层提供统一的同步调用重试封装，Agent 层负责 TripPlan 业务校验和一次修复请求，路由层把服务失败转换成稳定的 HTTP 响应模型。测试使用假的 Agent/MCP，避免真实外部服务。

**技术栈：** Python、FastAPI、Pydantic v2、pytest、HelloAgents `SimpleAgent`/`MCPTool`。

---

### 任务 1：建立重试与超时测试

**文件：**
- 创建：`backend/tests/test_reliability.py`
- 修改：`backend/app/services/amap_service.py`
- 修改：`backend/app/agents/trip_planner_agent.py`

- [x] **步骤 1：编写失败测试**
  - 测试 MCP 调用前两次抛出 `TimeoutError`、第三次返回结果，断言调用 3 次并成功。
  - 测试 Agent 调用前两次失败、第三次成功，断言调用 3 次。
  - 测试超过最大次数后保留最终异常。

- [x] **步骤 2：运行测试确认失败**

```powershell
cd backend
python -m pytest tests/test_reliability.py -q
```

预期：失败，因为当前没有统一重试入口。

- [x] **步骤 3：实现最小重试封装**
  - 在地图服务中增加 `_run_mcp_with_retry()`。
  - 使用 `ThreadPoolExecutor` 对同步 MCP 调用施加 30 秒超时。
  - 最大尝试次数为 3，等待时间为 1 秒、2 秒。
  - Agent 层增加 `_run_agent_with_retry()`，同样使用 30 秒超时和 3 次尝试。

- [x] **步骤 4：运行测试确认通过**

```powershell
python -m pytest tests/test_reliability.py -q
```

预期：所有重试和超时测试通过。

### 任务 2：结构化 TripPlan 输出校验

**文件：**
- 修改：`backend/app/agents/trip_planner_agent.py`
- 修改：`backend/tests/test_reliability.py`

- [x] **步骤 1：编写失败测试**
  - 测试完整 JSON 能转换为 `TripPlan`。
  - 测试缺少 `days`、每日无景点或日期数量不一致时校验失败。
  - 测试第一次返回非法 JSON、第二次返回合法 JSON 时最终成功。

- [x] **步骤 2：运行测试确认失败**

```powershell
python -m pytest tests/test_reliability.py -q
```

预期：业务校验测试失败。

- [x] **步骤 3：实现校验与修复流程**
  - 保留现有 JSON 提取逻辑。
  - 使用 `TripPlan.model_validate()` 校验结构。
  - 校验 `days` 数量、日期连续性、每日景点数量和三餐完整性。
  - 校验失败后向 planner Agent 发起一次“仅返回修正 JSON”的请求。
  - 修复仍失败时调用 `_create_fallback_plan()`。

- [x] **步骤 4：运行测试确认通过**

```powershell
python -m pytest tests/test_reliability.py -q
```

预期：结构化输出测试通过。

### 任务 3：修复路线失败响应

**文件：**
- 修改：`backend/app/api/routes/map.py`
- 修改：`backend/app/services/amap_service.py`
- 修改：`backend/tests/test_api_routes.py`

- [x] **步骤 1：编写失败测试**
  - 模拟 `plan_route()` 返回失败，断言 HTTP 状态为 502、响应 `data` 为 `null`。
  - 模拟成功路线，断言响应符合 `RouteResponse`。

- [x] **步骤 2：运行测试确认失败**

```powershell
python -m pytest tests/test_api_routes.py -q
```

预期：失败，因为当前路由始终以成功响应包装路线结果。

- [x] **步骤 3：实现稳定错误响应**
  - 服务层失败时返回明确的服务异常或 `None`，不返回不完整字典。
  - 路由层判断结果，成功时返回 `RouteInfo`，失败时抛出 `HTTPException(status_code=502)`。

- [x] **步骤 4：运行测试确认通过**

```powershell
python -m pytest tests/test_api_routes.py -q
```

预期：路线成功和失败测试通过。

### 任务 4：增加 API 路由测试

**文件：**
- 创建：`backend/tests/test_api_routes.py`

- [x] **步骤 1：添加路由测试**
  - 测试 `GET /` 和 `GET /health`。
  - 测试 `/api/map/poi` 和 `/api/map/weather` 成功响应。
  - 测试 `/api/map/route` 成功和失败响应。
  - 测试无效 `TripRequest` 返回 422。
  - 模拟旅行 Agent，测试 `/api/trip/plan` 成功返回 `TripPlanResponse`。

- [x] **步骤 2：运行完整后端测试**

```powershell
python -m pytest -q
python -m compileall -q app
```

预期：全部测试通过，编译检查退出码为 0。

### 任务 5：变更复核

- [x] 检查所有 LLM/MCP 调用都经过重试/超时封装。
- [x] 检查路线失败不会再把 `{}` 交给 `RouteInfo`。
- [x] 检查非法 LLM 输出会校验、修复或降级。
- [x] 查看 `git diff`，确认没有修改 `.env`、密钥或无关文件。
