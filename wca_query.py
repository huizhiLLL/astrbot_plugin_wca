import json
from typing import Any, Optional, Tuple
import aiohttp
from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent

from .wca_bindings import (
    WCABindingStore,
    extract_first_mentioned_qq,
    normalize_wca_id,
    strip_command_prefix,
    strip_mentions,
)

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

    async def get_person_best_records(
        self,
        person_id: str,
        person_entry: dict[str, Any] | None = None,
    ) -> Optional[dict[str, Any]]:
        """获取指定选手的最佳成绩（person info + personal_records）"""
        personal_records: dict[str, Any] | None = None
        person_info: dict[str, Any] | None = None
        competition_count: int | None = None
        medals: dict[str, Any] | None = None
        records: dict[str, Any] | None = None
        total_solves: int | None = None

        if isinstance(person_entry, dict):
            pr = person_entry.get("personal_records")
            if isinstance(pr, dict):
                personal_records = pr

            p = person_entry.get("person")
            if isinstance(p, dict):
                person_info = p

            cc = person_entry.get("competition_count")
            if isinstance(cc, int):
                competition_count = cc

            m = person_entry.get("medals")
            if isinstance(m, dict):
                medals = m

            r = person_entry.get("records")
            if isinstance(r, dict):
                records = r

            ts = person_entry.get("total_solves")
            if isinstance(ts, int):
                total_solves = ts

        if not personal_records:
            url = f"{self.API_BASE}/persons/{person_id}/personal_records"
            data = await self._fetch_json(url)
            personal_records = data if isinstance(data, dict) else None

        if not person_info:
            search_results = await self.search_person(person_id)
            if search_results:
                match = [
                    p
                    for p in search_results
                    if p.get("person", {}).get("wca_id") == person_id
                ]
                picked = match[0] if match else search_results[0]

                if not personal_records:
                    pr = picked.get("personal_records")
                    if isinstance(pr, dict):
                        personal_records = pr

                p = picked.get("person")
                if isinstance(p, dict):
                    person_info = p

                if competition_count is None and isinstance(
                    picked.get("competition_count"),
                    int,
                ):
                    competition_count = picked.get("competition_count")
                if medals is None and isinstance(picked.get("medals"), dict):
                    medals = picked.get("medals")
                if records is None and isinstance(picked.get("records"), dict):
                    records = picked.get("records")
                if total_solves is None and isinstance(picked.get("total_solves"), int):
                    total_solves = picked.get("total_solves")

        if not personal_records or not isinstance(personal_records, dict):
            return None

        if not person_info:
            person_info = {"wca_id": person_id}

        avatar_thumb_url = ""
        avatar = person_info.get("avatar")
        if isinstance(avatar, dict):
            avatar_thumb_url = str(
                avatar.get("thumb_url") or avatar.get("url") or "",
            )

        country_name = ""
        country_obj = person_info.get("country")
        if isinstance(country_obj, dict):
            country_name = str(country_obj.get("name") or "")

        country_iso2 = (
            person_info.get("country_iso2")
            or (person_info.get("country") or {}).get("iso2")
            or ""
        )

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
                "country_id": country_iso2,
                "country_iso2": country_iso2,
                "country_name": country_name,
                "gender": person_info.get("gender", ""),
                "url": person_info.get("url", ""),
                "avatar_thumb_url": avatar_thumb_url,
            },
            "competition_count": competition_count,
            "medals": medals,
            "records": records,
            "total_solves": total_solves,
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
            return f"{header}\n还没有 WCA 成绩记录呢，快去参加比赛吧~"
        
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
                if wr and wr <= 100:
                    single_rank = f"WR{wr}"
                elif cr and cr <= 100:
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
                if wr and wr <= 100:
                    avg_rank = f"WR{wr}"
                elif cr and cr <= 100:
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
            return f"{header}\n还没有有效的成绩记录哦，再接再厉呀~"
        
        return header + "\n".join(lines)


class WCACommandService:
    def __init__(self, query: WCAQuery, bindings: WCABindingStore):
        self.query = query
        self.bindings = bindings

    async def handle(self, event: AstrMessageEvent):
        message_str = event.message_str.strip()
        search_input = strip_command_prefix(message_str, "wca")
        target_qq = extract_first_mentioned_qq(event)

        if target_qq:
            bound_wca_id = self.bindings.get(target_qq)
            if not bound_wca_id:
                yield event.plain_result(f"这个 QQ（{target_qq}）还没有绑定 WCAID 呢").use_t2i(False)
                return
            search_input = bound_wca_id
        elif not search_input:
            sender_qq = event.get_sender_id()
            bound_wca_id = self.bindings.get(sender_qq)
            if not bound_wca_id:
                yield event.plain_result(
                    "你还没有绑定 WCAID 呢\n"
                    "用法: /wca绑定 <WCAID或姓名>\n"
                    "示例: /wca绑定 2026LIHU01"
                ).use_t2i(False)
                return
            search_input = bound_wca_id
        else:
            search_input = strip_mentions(search_input)

        if not search_input:
            yield event.plain_result(
                "请提供 WCAID 或姓名哦\n"
                "用法: /wca [WCAID/姓名]\n"
                "示例: /wca 2026LIHU01\n"
                "也可以先用 /wca绑定 绑定后直接 /wca"
            ).use_t2i(False)
            return

        yield event.plain_result("正在查询选手信息，请稍候哦...").use_t2i(False)

        try:
            persons = await self.query.search_person(search_input)

            if not persons:
                yield event.plain_result(
                    f"抱歉啦，没有找到关于 {search_input} 的信息哦"
                ).use_t2i(False)
                return

            if len(persons) > 1:
                lines = [f"好准哦，找到了多个匹配的选手，请使用 WCAID 查询具体哪位呢：\n"]
                for i, item in enumerate(persons[:10], 1):
                    person_info = item.get("person", {}) if isinstance(item, dict) else {}
                    person_id = person_info.get("wca_id", "未知")
                    person_name = person_info.get("name", "未知")
                    country = person_info.get("country_iso2", "")
                    country_str = f" [{country}]" if country else ""
                    lines.append(f"{i}. {person_name} ({person_id}){country_str}")

                if len(persons) > 10:
                    lines.append(f"\n... 还有 {len(persons) - 10} 个结果未显示哦")

                lines.append("\n使用方法: /wca [WCAID]")
                yield event.plain_result("\n".join(lines)).use_t2i(False)
                return

            picked = persons[0]
            person_info = picked.get("person", {}) if isinstance(picked, dict) else {}
            person_id = person_info.get("wca_id", "")

            if not person_id:
                yield event.plain_result("哎呀，选手信息不完整，无法查询成绩哦").use_t2i(False)
                return

            records_data = await self.query.get_person_best_records(
                person_id,
                person_entry=picked,
            )

            if not records_data:
                person_name = person_info.get("name", "该选手")
                yield event.plain_result(
                    f"{person_name} ({person_id}) 还没有 WCA 成绩记录呢，快去参加比赛吧~"
                ).use_t2i(False)
                return

            result_text = self.query.format_person_records(records_data)
            yield event.plain_result(result_text).use_t2i(False)

        except Exception as e:
            logger.error(f"WCA 查询异常: {e}")
            yield event.plain_result(f"查询出了一点小状况呢: {str(e)}").use_t2i(False)


class WCABindCommandService:
    def __init__(self, query: WCAQuery, bindings: WCABindingStore):
        self.query = query
        self.bindings = bindings

    async def handle(self, event: AstrMessageEvent):
        qq_id = event.get_sender_id()
        if not qq_id:
            yield event.plain_result("哎呀，拿不到你的 QQ 号呢，要在 QQ 里用才行哦~").use_t2i(False)
            return

        search_input = strip_command_prefix(event.message_str, "wca绑定")
        search_input = strip_mentions(search_input)
        if not search_input:
            yield event.plain_result(
                "请输入要绑定的姓名或 WCAID 哦\n"
                "用法: /wca绑定 <姓名或WCAID>\n"
                "示例: /wca绑定 2026LIHU01"
            ).use_t2i(False)
            return

        normalized_wca_id = normalize_wca_id(search_input)

        try:
            if normalized_wca_id:
                persons = await self.query.search_person(normalized_wca_id)
                if not persons:
                    yield event.plain_result(f"没有找到 WCAID 为 {normalized_wca_id} 的选手哦").use_t2i(False)
                    return
                picked = None
                for item in persons:
                    person_info = item.get("person", {}) if isinstance(item, dict) else {}
                    if person_info.get("wca_id", "").upper() == normalized_wca_id:
                        picked = item
                        break
                picked = picked or persons[0]
            else:
                persons = await self.query.search_person(search_input)
                if not persons:
                    yield event.plain_result(f"没有找到名字是 {search_input} 的选手哦").use_t2i(False)
                    return
                if len(persons) > 1:
                    lines = ["找到多个同名选手啦，请改用 WCAID 绑定喵：", ""]
                    for i, item in enumerate(persons[:10], 1):
                        person_info = item.get("person", {}) if isinstance(item, dict) else {}
                        person_id = person_info.get("wca_id", "未知")
                        person_name = person_info.get("name", "未知")
                        country = person_info.get("country_iso2", "")
                        country_str = f" [{country}]" if country else ""
                        lines.append(f"{i}. {person_name} ({person_id}){country_str}")
                    if len(persons) > 10:
                        lines.append(f"\n... 还有 {len(persons) - 10} 个结果未显示哦")
                    yield event.plain_result("\n".join(lines)).use_t2i(False)
                    return
                picked = persons[0]

            person_info = picked.get("person", {}) if isinstance(picked, dict) else {}
            person_id = person_info.get("wca_id", "")
            person_name = person_info.get("name", "未知")
            if not person_id:
                yield event.plain_result("哎呀，选手信息不完整，暂时没法绑定呢").use_t2i(False)
                return

            self.bindings.set(str(qq_id), person_id)
            yield event.plain_result(
                f"绑定成功啦喵~\n你的 QQ：{qq_id}\nWCAID：{person_id}\n姓名：{person_name}"
            ).use_t2i(False)
        except Exception as e:
            logger.error(f"WCA 绑定异常: {e}")
            yield event.plain_result(f"绑定时出了点小状况呢: {str(e)}").use_t2i(False)


class WCANemesisService:
    def __init__(self, query: WCAQuery, api_base: str):
        self.query = query
        self.api_base = api_base

    async def handle(self, event: AstrMessageEvent):
        message_str = event.message_str.strip()
        parts = message_str.split(maxsplit=1)
        if len(parts) < 2:
            yield event.plain_result(
                "请提供 WCAID 或姓名哦\n"
                "用法: /宿敌 [WCAID/姓名]\n"
                "示例: /宿敌 2026LIHU01\n"
            ).use_t2i(False)
            return

        search_input = parts[1].strip()

        try:
            persons = await self.query.search_person(search_input)
            if not persons:
                yield event.plain_result(
                    f"抱歉啦，没有找到关于 {search_input} 的信息哦\n"
                    "提示：可以使用 WCAID（如：2026LIHU01）或姓名进行搜索"
                ).use_t2i(False)
                return

            if len(persons) > 1:
                lines = ["好准哦，找到了多个匹配的选手，请使用 WCAID 查询具体哪位呢：\n"]
                for i, item in enumerate(persons[:10], 1):
                    pinfo = item.get("person", {}) if isinstance(item, dict) else {}
                    person_id = pinfo.get("wca_id", "未知")
                    person_name = pinfo.get("name", "未知")
                    country = pinfo.get("country_iso2", "")
                    country_str = f" [{country}]" if country else ""
                    lines.append(f"{i}. {person_name} ({person_id}){country_str}")

                if len(persons) > 10:
                    lines.append(f"\n... 还有 {len(persons) - 10} 个结果未显示哦")
                lines.append("\n使用方法: /wca宿敌 <WCAID>")
                yield event.plain_result("\n".join(lines)).use_t2i(False)
                return

            pinfo = persons[0].get("person", {}) if isinstance(persons[0], dict) else {}
            person_id = pinfo.get("wca_id", pinfo.get("id", ""))
            if not person_id:
                yield event.plain_result("哎呀，选手信息不完整，无法查询成绩哦").use_t2i(False)
                return

            yield event.plain_result("收到啦！正在为您寻找宿敌，请稍候哦...").use_t2i(False)

            nemesis_data = await self._call_nemesis_api(person_id)
            if not nemesis_data:
                yield event.plain_result("查询宿敌失败了，请稍后重试哦").use_t2i(False)
                return

            world_count = nemesis_data.get("world_count", 0)
            continent_count = nemesis_data.get("continent_count", 0)
            country_count = nemesis_data.get("country_count", 0)
            world_list = nemesis_data.get("world_list", [])
            continent_list = nemesis_data.get("continent_list", [])
            country_list = nemesis_data.get("country_list", [])

            if world_count == 0:
                yield event.plain_result(
                    f"哇！该选手目前还没有宿敌呢，太强啦~"
                ).use_t2i(False)
                return

            person_name = persons[0].get("name", "")
            title = f"选手 {person_name} ({person_id}) 的宿敌结果出来啦："
            summary = f"世界：{world_count}人，洲：{continent_count}人，地区：{country_count}人"

            def _fmt_people(people: list[dict[str, str]]) -> str:
                lines: list[str] = []
                for p in people:
                    pid = p.get("wca_id", "")
                    name = p.get("name", "")
                    ctry = p.get("country_id", "")
                    ctry_str = f" [{ctry}]" if ctry else ""
                    lines.append(f"- {name} ({pid}){ctry_str}")
                return "\n".join(lines)

            details: list[str] = []
            if 0 < world_count <= 10:
                details.append("世界：\n" + _fmt_people(world_list))
            if 0 < continent_count <= 10:
                details.append("洲：\n" + _fmt_people(continent_list))
            if 0 < country_count <= 10:
                details.append("地区：\n" + _fmt_people(country_list))

            text = "\n".join([title, summary] + (["", "\n\n".join(details)] if details else []))
            yield event.plain_result(text).use_t2i(False)

        except Exception as e:
            yield event.plain_result(f"执行出错: {str(e)}").use_t2i(False)

    async def _call_nemesis_api(self, person_id: str) -> dict | None:
        url = f"{self.api_base.rstrip('/')}/nemesis"
        payload = {"person_id": person_id}
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status != 200:
                        logger.error(f"宿敌接口调用失败，状态码: {resp.status}")
                        return None
                    data = await resp.json()
                    if isinstance(data, dict) and "error" in data:
                        logger.error(f"宿敌接口返回错误: {data.get('error')}")
                        return None
                    return data if isinstance(data, dict) else None
        except Exception as e:
            logger.error(f"调用宿敌接口异常: {e}")
            return None
