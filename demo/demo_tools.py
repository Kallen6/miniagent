"""演示工具与工作流：导入即注册，供网页时间线展示 agent 的完整执行流程。

设计原则：全部为确定性输出（哈希/本地随机），不依赖任何外部 API，
无需额外配置即可演示「思考 → 调用工具 → 返回结果 → 组织回答」的全链路。

用法：python demo/start_demo.py 启动服务后，按 demo/README.md 的演示台词提问。
"""
import hashlib
import random

from agent.agent_tools.build_tools import tool
from agent.workflows.registry import workflow

_WEATHERS = ["晴", "多云", "小雨", "阴", "阵雨转多云"]
_CITIES_EN = {"北京": "Beijing", "上海": "Shanghai", "广州": "Guangzhou",
              "深圳": "Shenzhen", "杭州": "Hangzhou", "成都": "Chengdu"}


def _seed(city: str) -> int:
    return int(hashlib.md5(city.strip().encode("utf-8")).hexdigest(), 16)


@tool(description="查询指定城市的当前天气（演示数据，同一城市结果固定）",
      param_descriptions={"city": "城市名，例如 北京、上海"})
def get_weather(city: str) -> dict:
    seed = _seed(city)
    temp = 5 + seed % 28          # 5~32 ℃
    wind = 1 + seed // 7 % 5      # 1~5 级
    humidity = 30 + seed // 11 % 60  # 30%~89%
    return {
        "city": city,
        "city_en": _CITIES_EN.get(city, city),
        "weather": _WEATHERS[seed % len(_WEATHERS)],
        "temp": f"{temp}℃",
        "wind": f"{wind} 级",
        "humidity": f"{humidity}%",
    }


@tool(description="掷骰子并返回每次的点数（演示用）",
      param_descriptions={"sides": "骰子面数，默认 6", "times": "投掷次数，默认 1，最多 10"})
def roll_dice(sides: int = 6, times: int = 1) -> dict:
    times = max(1, min(times, 10))
    rolls = [random.randint(1, max(2, sides)) for _ in range(times)]
    return {"sides": sides, "rolls": rolls, "total": sum(rolls)}


@tool(description="统计一组数字的平均值、最大值与最小值（演示用）",
      param_descriptions={"numbers": "数字列表，例如 [3, 7, 12]"})
def number_stats(numbers: list) -> dict:
    nums = [float(n) for n in numbers]
    return {
        "count": len(nums),
        "avg": round(sum(nums) / len(nums), 2),
        "max": max(nums),
        "min": min(nums),
    }


@workflow(description="生成城市天气简报：内部调用天气工具汇总温度/风力/湿度（演示用）")
def weather_brief(city: str) -> dict:
    """短固定工作流：一次函数调用内部完成多步，适合演示慢工具与时间线的 tool_result 卡片。"""
    data = get_weather(city)
    return {
        "city": data["city"],
        "brief": f"{data['city']} 当前{data['weather']}，气温 {data['temp']}，"
                 f"风力 {data['wind']}，湿度 {data['humidity']}。",
        "detail": data,
    }
