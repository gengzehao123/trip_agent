import json

from ..app.models.schemas import Location, POIInfo, RouteInfo, WeatherInfo
from ..app.services.amap_service import AmapService


class FakeMCPTool:
    def __init__(self, results):
        self.results = iter(results if isinstance(results, list) else [results])

    def run(self, _request):
        return next(self.results)


def service_with_result(result):
    service = AmapService.__new__(AmapService)
    service.mcp_tool = FakeMCPTool(result)
    return service


def test_search_poi_parses_wrapped_json_result():
    search_result = json.dumps({"pois": [{
        "id": "B001",
        "name": "故宫",
        "typecode": "风景名胜",
        "address": "北京市东城区景山前街4号",
    }]})
    detail_result = json.dumps({
        "id": "B001",
        "name": "故宫",
        "type": "风景名胜",
        "address": "北京市东城区景山前街4号",
        "location": "116.397128,39.916527",
        "tel": "010-12345678",
    })

    pois = service_with_result([search_result, detail_result]).search_poi("故宫", "北京")

    assert pois == [POIInfo(
        id="B001",
        name="故宫",
        type="风景名胜",
        address="北京市东城区景山前街4号",
        location=Location(longitude=116.397128, latitude=39.916527),
        tel="010-12345678",
    )]


def test_get_weather_parses_json_code_block_and_temperature_units():
    result = "```json\n" + json.dumps({"forecasts": [{
        "date": "2026-08-18",
        "dayweather": "晴",
        "nightweather": "多云",
        "daytemp": "32℃",
        "nighttemp": "24℃",
        "daywind": "南",
        "daypower": "1-3级",
    }]}) + "\n```"

    weather = service_with_result(result).get_weather("北京")

    assert weather == [WeatherInfo(
        date="2026-08-18",
        day_weather="晴",
        night_weather="多云",
        day_temp=32,
        night_temp=24,
        wind_direction="南",
        wind_power="1-3级",
    )]


def test_plan_route_parses_route_info():
    result = json.dumps({"route": {"paths": [{
        "distance": "1200",
        "duration": "900",
        "steps": [{"instruction": "沿道路步行"}],
    }]}})

    route = service_with_result(result).plan_route("起点", "终点")

    assert route == RouteInfo(
        distance=1200,
        duration=900,
        route_type="walking",
        description="沿道路步行",
    ).model_dump()


def test_geocode_parses_location_string():
    result = json.dumps({"return": [{"location": "116.397128,39.916527"}]})

    location = service_with_result(result).geocode("故宫", "北京")

    assert location == Location(longitude=116.397128, latitude=39.916527)
