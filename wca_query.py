import json
from typing import Any, Optional, Tuple
import aiohttp
from astrbot.api import logger

# API 项目ID到显示名称的映射（API 返回的是简化的项目ID）
EVENT_ID_MAP: dict[str, str] = {
    "222": "222",
    "333": "333",
    "444": "444",
    "555": "555",
    "666": "666",
    "777": "777",
    "333bf": "333bf",
    "333fm": "333fm",
    "333oh": "333oh",
    "clock": "clock",
    "minx": "minx",
    "pyram": "py",
    "skewb": "sk",
    "sq1": "sq1",
    "444bf": "444bf",
    "555bf": "555bf",
    "333mbf": "333mbf",
    "333ft": "333ft",
}

# 项目ID到格式的映射（用于格式化时间）
EVENT_FORMAT_MAP: dict[str, str] = {
    "222": "time",
    "333": "time",
    "444": "time",
    "555": "time",
    "666": "time",
    "777": "time",
    "333bf": "time",
    "333fm": "number",
    "333oh": "time",
    "clock": "time",
    "minx": "time",
    "pyram": "time",
    "skewb": "time",
    "sq1": "time",
    "444bf": "time",
    "555bf": "time",
    "333mbf": "multi",
    "333ft": "time",
}

# 项目排序顺序（用于在没有 event_rank 时排序）
EVENT_ORDER: dict[str, int] = {
    "222": 1,
    "333": 2,
    "444": 3,
    "555": 4,
    "666": 5,
    "777": 6,
    "333bf": 7,
    "333fm": 8,
    "333oh": 9,
    "clock": 10,
    "minx": 11,
    "pyram": 12,
    "skewb": 13,
    "sq1": 14,
    "444bf": 15,
    "555bf": 16,
    "333mbf": 17,
    "333ft": 18,
}


def format_wca_time(centiseconds: int, event_format: str = "time") -> str:
    """格式化 WCA 时间（厘秒转换为可读格式）
    
    Args:
        centiseconds: 时间值（厘秒）
        event_format: 项目格式，"time" 表示时间格式，"number" 表示数字格式，"multi" 表示多盲格式
    
    Returns:
        格式化后的时间字符串
    """
    # 处理特殊值
    if centiseconds == -1:
        return "DNF"
    if centiseconds == -2:
        return "DNS"
    if centiseconds == 0:
        return "-"
    
    # 处理多盲格式
    if event_format == "multi":
        return format_multi_blind(centiseconds)
    
    # 处理数字格式（最少步）
    if event_format == "number":
        # 最少步的平均值存储为 100 倍，需要除以 100
        if centiseconds >= 100:
            return f"{centiseconds / 100:.2f}"
        return str(centiseconds)
    
    # 处理时间格式（大多数项目）
    # 使用纯整数运算，避免浮点精度导致误差
    total_cs = int(centiseconds)
    minutes = total_cs // 6000              # 6000 cs = 60 s
    sec_cs = total_cs % 6000
    seconds = sec_cs // 100
    cs = sec_cs % 100
    
    if minutes > 0:
        # 有分钟：M:SS.cc
        return f"{minutes}:{seconds:02d}.{cs:02d}"
    else:
        # 只有秒：S.cc（秒不补前导零）
        return f"{seconds}.{cs:02d}"


def format_multi_blind(value: int) -> str:
    """格式化多盲成绩
    
    Args:
        value: 多盲编码值
    
    Returns:
        格式化后的多盲成绩字符串，格式：solved/attempted time
    """
    # 按 WCA 新旧格式解析，使用 10 位零填充（0DDTTTTTMM / 1SSAATTTTT）
    value_str = str(value).zfill(10)
    
    if value_str[0] == '1':
        # 旧格式：1SSAATTTTT
        ss = int(value_str[1:3])
        aa = int(value_str[3:5])
        ttttt = int(value_str[5:10])
        
        solved = 99 - ss
        attempted = aa
        time_seconds = ttttt if ttttt != 99999 else None
    else:
        # 新格式：0DDTTTTTMM
        dd = int(value_str[1:3])
        ttttt = int(value_str[3:8])
        mm = int(value_str[8:10])
        
        difference = 99 - dd
        missed = mm
        solved = difference + missed
        attempted = solved + missed
        time_seconds = ttttt if ttttt != 99999 else None
    
    if time_seconds is None:
        return f"{solved}/{attempted} (时间未知)"
    
    # 格式化时间
    hours = time_seconds // 3600
    minutes = (time_seconds % 3600) // 60
    seconds = time_seconds % 60
    
    if hours > 0:
        time_str = f"{hours}:{minutes:02d}:{seconds:02d}"
    else:
        time_str = f"{minutes}:{seconds:02d}"
    
    return f"{solved}/{attempted} {time_str}"


class WCAQuery:
    """基于 WCA 官方 API 的查询类（不依赖本地数据库）"""

    API_BASE = "https://www.worldcubeassociation.org/api/v0"

    async def _fetch_json(self, url: str, params: dict | None = None) -> Any:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status != 200:
                        logger.error(f"API 请求失败，状态码: {resp.status}, url: {url}")
                        return None
                    text = await resp.text()
                    try:
                        return json.loads(text)
                    except ValueError as e:
                        logger.error(f"JSON 解析失败: {e}, 响应前 200 字符: {text[:200]}")
                        return None
        except aiohttp.ClientError as e:
            logger.error(f"API 请求异常: {e}")
            return None
        except Exception as e:
            logger.error(f"请求 {url} 失败: {e}")
            return None

    async def search_person(self, search_input: str) -> list[dict[str, Any]]:
        """通过姓名或 WCA ID 搜索选手，返回数组，包含 personal_records 字段"""
        url = f"{self.API_BASE}/persons"
        data = await self._fetch_json(url, params={"q": search_input})
        if not isinstance(data, list):
            return []
        return data

    async def get_person_best_records(self, person_id: str) -> Optional[dict[str, Any]]:
        """获取指定选手的最佳成绩（person info + personal_records）"""
        # 专用 personal_records 接口
        url = f"{self.API_BASE}/persons/{person_id}/personal_records"
        data = await self._fetch_json(url)
        personal_records = data if isinstance(data, dict) else None

        person_info: dict[str, Any] | None = None
        # 个人信息及可能的 personal_records 回退从 search 获取
        search_results = await self.search_person(person_id)
        if search_results:
            match = [p for p in search_results if p.get("person", {}).get("wca_id") == person_id]
            picked = match[0] if match else search_results[0]
            if not personal_records:
                personal_records = picked.get("personal_records")
            person_info = picked.get("person")

        if not personal_records or not isinstance(personal_records, dict):
            return None
        if not person_info:
            person_info = {"wca_id": person_id}

        single_records: list[dict[str, Any]] = []
        average_records: list[dict[str, Any]] = []

        for event_id, rec in personal_records.items():
            if not isinstance(rec, dict):
                continue
            event_format = EVENT_FORMAT_MAP.get(event_id, "time")
            single = rec.get("single")
            if isinstance(single, dict):
                single_records.append(
                    {
                        "event_id": event_id,
                        "event_name": EVENT_ID_MAP.get(event_id, event_id),
                        "event_format": event_format,
                        "best": single.get("best", 0),
                        "world_rank": single.get("world_rank", 0),
                        "continent_rank": single.get("continent_rank", 0),
                        "country_rank": single.get("country_rank", 0),
                        "event_rank": EVENT_ORDER.get(event_id, 999),
                    }
                )
            average = rec.get("average")
            if isinstance(average, dict):
                average_records.append(
                    {
                        "event_id": event_id,
                        "event_name": EVENT_ID_MAP.get(event_id, event_id),
                        "event_format": event_format,
                        "best": average.get("best", 0),
                        "world_rank": average.get("world_rank", 0),
                        "continent_rank": average.get("continent_rank", 0),
                        "country_rank": average.get("country_rank", 0),
                        "event_rank": EVENT_ORDER.get(event_id, 999),
                    }
                )

        return {
            "person": {
                "wca_id": person_info.get("wca_id", ""),
                "name": person_info.get("name", ""),
                "country_id": person_info.get("country_iso2", ""),
                "gender": person_info.get("gender", ""),
            },
            "single_records": single_records,
            "average_records": average_records,
        }
    
    def format_person_records(self, records_data: dict[str, Any]) -> str:
        """格式化选手成绩为文本
        
        Args:
            records_data: get_person_best_records 返回的数据
        
        Returns:
            格式化后的文本
        """
        person = records_data["person"]
        person_name = person.get("name", "未知")
        person_id = person.get("wca_id", "")
        country = person.get("country_id", "")
        
        # 构建标题（两行：姓名（含本地名）+ 基本信息）
        # Persons 表通常有本地名字段 "name"（含中文），这里保留原始 name
        header_lines = []
        # 第一行：姓名（保留表中的 name 字段）
        display_name = person.get("name", person_name)
        header_lines.append(f"{display_name}")
        gender = person.get("gender", "")
        gender_str = ""
        if gender:
            gender_str = "Male" if str(gender).lower().startswith("m") else "Female"
        basic_parts = [person_id, country or "-", gender_str or "-"]
        header_lines.append(", ".join(basic_parts))
        header = "\n".join(header_lines) + "\n\n"
        
        single_records = records_data["single_records"]
        average_records = records_data["average_records"]
        
        # 创建事件ID到记录的映射
        single_map = {r["event_id"]: r for r in single_records}
        average_map = {r["event_id"]: r for r in average_records}
        
        # 获取所有有记录的事件
        all_event_ids = set(single_map.keys()) | set(average_map.keys())
        
        if not all_event_ids:
            return f"{header}\n❌ 暂无 WCA 成绩记录"
        
        lines = []
        
        # 按事件排序（使用 rank 字段）
        event_records = []
        for event_id in all_event_ids:
            single = single_map.get(event_id)
            average = average_map.get(event_id)
            
            # 获取 rank（用于排序）
            rank = 999
            if single:
                rank = single.get("event_rank", 999)
            elif average:
                rank = average.get("event_rank", 999)
            
            event_records.append((rank, event_id, single, average))
        
        event_records.sort(key=lambda x: x[0])
        
        # 格式化输出
        for rank, event_id, single, average in event_records:
            event_name = ""
            event_format = "time"
            
            if single:
                event_name = single.get("event_name", event_id)
                event_format = single.get("event_format", "time")
            elif average:
                event_name = average.get("event_name", event_id)
                event_format = average.get("event_format", "time")
            
            # event_name 已经是简化格式（如 "333", "py"），不需要再次映射
            # 如果为空，使用 event_id
            if not event_name:
                event_name = event_id
            
            # 格式化单次成绩
            single_time = "-"
            single_rank = "-"
            if single:
                best = single.get("best", 0)
                single_time = format_wca_time(best, event_format)
                wr = single.get("world_rank", 0)
                cr = single.get("continent_rank", 0)
                nr = single.get("country_rank", 0)
                if wr and wr <= 200:
                    single_rank = f"WR{wr}"
                elif cr and cr <= 200:
                    single_rank = f"CR{cr}"
                elif nr and nr <= 200:
                    single_rank = f"NR{nr}"
            
            # 格式化平均成绩
            avg_time = "-"
            avg_rank = "-"
            if average:
                best = average.get("best", 0)
                avg_time = format_wca_time(best, event_format)
                wr = average.get("world_rank", 0)
                cr = average.get("continent_rank", 0)
                nr = average.get("country_rank", 0)
                if wr and wr <= 200:
                    avg_rank = f"WR{wr}"
                elif cr and cr <= 200:
                    avg_rank = f"CR{cr}"
                elif nr and nr <= 200:
                    avg_rank = f"NR{nr}"
            
            # 跳过两个成绩都是无效的记录
            if single_time == "-" and avg_time == "-":
                continue
            
            # 格式：项目名称  单次成绩(排名) || 平均成绩(排名)；排名仅当进入前200时显示，优先 WR > CR > NR
            line = f"{event_name}  {single_time}"
            if single_rank != "-":
                line += f" ({single_rank})"
            line += "  ||  "
            line += avg_time
            if avg_rank != "-":
                line += f" ({avg_rank})"
            
            lines.append(line)
        
        if not lines:
            return f"{header}\n❌ 暂无有效成绩记录"
        
        return header + "\n".join(lines)

