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
