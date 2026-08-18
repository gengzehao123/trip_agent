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
