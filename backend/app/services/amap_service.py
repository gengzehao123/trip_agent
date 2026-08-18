"""高德地图MCP服务封装"""

import json
import re
from typing import List, Dict, Any, Optional
from hello_agents.tools import MCPTool
from ..config import get_settings
from ..models.schemas import Location, POIInfo, WeatherInfo
from .retry import run_with_retry

# 全局MCP工具实例
_amap_mcp_tool = None


def get_amap_mcp_tool() -> MCPTool:
    """
    获取高德地图MCP工具实例(单例模式)
    
    Returns:
        MCPTool实例
    """
    global _amap_mcp_tool
    
    if _amap_mcp_tool is None:
        settings = get_settings()
        
        if not settings.amap_api_key:
            raise ValueError("高德地图API Key未配置,请在.env文件中设置AMAP_API_KEY")
        
        # 创建MCP工具
        _amap_mcp_tool = MCPTool(
            name="amap",
            description="高德地图服务,支持POI搜索、路线规划、天气查询等功能",
            server_command=["uvx", "amap-mcp-server"],
            env={"AMAP_MAPS_API_KEY": settings.amap_api_key},
            auto_expand=True  # 自动展开为独立工具
        )
        
        print(f"✅ 高德地图MCP工具初始化成功")
        print(f"   工具数量: {len(_amap_mcp_tool._available_tools)}")
        
        # 打印可用工具列表
        if _amap_mcp_tool._available_tools:
            print("   可用工具:")
            for tool in _amap_mcp_tool._available_tools[:5]:  # 只打印前5个
                print(f"     - {tool.get('name', 'unknown')}")
            if len(_amap_mcp_tool._available_tools) > 5:
                print(f"     ... 还有 {len(_amap_mcp_tool._available_tools) - 5} 个工具")
    
    return _amap_mcp_tool


class AmapService:
    """高德地图服务封装类"""
    
    def __init__(self):
        """初始化服务"""
        self.mcp_tool = get_amap_mcp_tool()

    def _run_mcp(self, request: Dict[str, Any], operation_name: str) -> Any:
        """调用 MCP，并提供统一的超时和重试。"""
        return run_with_retry(
            lambda: self.mcp_tool.run(request),
            operation_name=operation_name,
        )

    @staticmethod
    def _parse_json_result(result: Any) -> Any:
        """从 MCP 返回值中提取 JSON，兼容代码块和文本包装。"""
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
    
    def search_poi(self, keywords: str, city: str, citylimit: bool = True) -> List[POIInfo]:
        """
        搜索POI
        
        Args:
            keywords: 搜索关键词
            city: 城市
            citylimit: 是否限制在城市范围内
            
        Returns:
            POI信息列表
        """
        try:
            # 调用MCP工具
            result = self._run_mcp({
                "action": "call_tool",
                "tool_name": "maps_text_search",
                "arguments": {
                    "keywords": keywords,
                    "city": city,
                    "citylimit": str(citylimit).lower()
                }
            }, "高德 POI 搜索")
            
            # 解析结果
            # 注意: MCP工具返回的是字符串,需要解析
            # 这里简化处理,实际应该解析JSON
            print(f"POI搜索结果: {str(result)[:200]}...")  # 打印前200字符
            
            payload = self._unwrap_payload(self._parse_json_result(result), "pois", "data", "results")
            if isinstance(payload, dict):
                payload = payload.get("pois", payload.get("results", []))

            pois = []
            for item in payload if isinstance(payload, list) else []:
                detail = {}
                poi_id = self._first_value(item, "id", "poi_id", default="")
                if poi_id:
                    detail = self.get_poi_detail(str(poi_id))
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
    
    def get_weather(self, city: str) -> List[WeatherInfo]:
        """
        查询天气
        
        Args:
            city: 城市名称
            
        Returns:
            天气信息列表
        """
        try:
            # 调用MCP工具
            result = self._run_mcp({
                "action": "call_tool",
                "tool_name": "maps_weather",
                "arguments": {
                    "city": city
                }
            }, "高德天气查询")
            
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
    
    def plan_route(
        self,
        origin_address: str,
        destination_address: str,
        origin_city: Optional[str] = None,
        destination_city: Optional[str] = None,
        route_type: str = "walking"
    ) -> Dict[str, Any]:
        """
        规划路线
        
        Args:
            origin_address: 起点地址
            destination_address: 终点地址
            origin_city: 起点城市
            destination_city: 终点城市
            route_type: 路线类型 (walking/driving/transit)
            
        Returns:
            路线信息
        """
        try:
            # 根据路线类型选择工具
            tool_map = {
                "walking": "maps_direction_walking_by_address",
                "driving": "maps_direction_driving_by_address",
                "transit": "maps_direction_transit_integrated_by_address"
            }
            
            tool_name = tool_map.get(route_type, "maps_direction_walking_by_address")
            
            # 构建参数
            arguments = {
                "origin_address": origin_address,
                "destination_address": destination_address
            }
            
            # 公共交通需要城市参数
            if route_type == "transit":
                if origin_city:
                    arguments["origin_city"] = origin_city
                if destination_city:
                    arguments["destination_city"] = destination_city
            else:
                # 其他路线类型也可以提供城市参数提高准确性
                if origin_city:
                    arguments["origin_city"] = origin_city
                if destination_city:
                    arguments["destination_city"] = destination_city
            
            # 调用MCP工具
            result = self._run_mcp({
                "action": "call_tool",
                "tool_name": tool_name,
                "arguments": arguments
            }, "高德路线规划")
            
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
    
    def geocode(self, address: str, city: Optional[str] = None) -> Optional[Location]:
        """
        地理编码(地址转坐标)

        Args:
            address: 地址
            city: 城市

        Returns:
            经纬度坐标
        """
        try:
            arguments = {"address": address}
            if city:
                arguments["city"] = city

            result = self._run_mcp({
                "action": "call_tool",
                "tool_name": "maps_geo",
                "arguments": arguments
            }, "高德地理编码")

            print(f"地理编码结果: {str(result)[:200]}...")

            payload = self._parse_json_result(result)
            geocodes = payload.get("return", []) if isinstance(payload, dict) else []
            first = geocodes[0] if isinstance(geocodes, list) and geocodes else None
            return self._parse_location(first.get("location") if isinstance(first, dict) else first)

        except Exception as e:
            print(f"❌ 地理编码失败: {str(e)}")
            return None

    def get_poi_detail(self, poi_id: str) -> Dict[str, Any]:
        """
        获取POI详情

        Args:
            poi_id: POI ID

        Returns:
            POI详情信息
        """
        try:
            result = self._run_mcp({
                "action": "call_tool",
                "tool_name": "maps_search_detail",
                "arguments": {
                    "id": poi_id
                }
            }, "高德 POI 详情")

            print(f"POI详情结果: {str(result)[:200]}...")

            # 解析结果并提取图片
            import json
            import re

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
