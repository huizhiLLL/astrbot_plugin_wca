from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

from astrbot.api import logger
from .wca_query import WCAQuery, format_wca_time, EVENT_ID_MAP


@dataclass
class PlayerRecord:
    person: Dict[str, Any]
    single_map: Dict[Any, Dict[str, Any]]
    average_map: Dict[Any, Dict[str, Any]]


class WCAPKService:
    """选手 PK """

    def __init__(self, query: WCAQuery):
        self.query = query

    async def _resolve_person(self, keyword: str) -> Optional[Dict[str, Any]]:
        """根据 ID 或姓名解析唯一选手（调用 WCA API）"""
        persons = await self.query.search_person(keyword)
        if not persons:
            return None
        if len(persons) == 1:
            return persons[0]
        # 多个结果时，尝试精确姓名匹配
        exact = [p for p in persons if p.get("person", {}).get("name") == keyword]
        if len(exact) == 1:
            return exact[0]
        # 仍多于 1 个，视为歧义
        return None

    async def _build_player_record(self, person: Dict[str, Any]) -> PlayerRecord:
        person_info = person.get("person", person)
        person_id = person_info.get("wca_id", "")
        data = await self.query.get_person_best_records(person_id)
        if not data:
            return PlayerRecord(person_info, {}, {})
        single_map = {r["event_id"]: r for r in data["single_records"]}
        average_map = {r["event_id"]: r for r in data["average_records"]}
        return PlayerRecord(person_info, single_map, average_map)

    def _compare(self, a_val: Any, b_val: Any, event_format: str = "time") -> Tuple[str, str, int, int]:
        """比较两个成绩值（默认厘秒，越小越好；最少步用 number 格式）
        返回: (a_text, b_text, a_score, b_score)
        """
        def to_int(v: Any) -> int:
            try:
                return int(v)
            except Exception:
                return 0

        def fmt(v: int) -> str:
            return format_wca_time(v, event_format) if v and v > 0 else "-"

        a_val = to_int(a_val)
        b_val = to_int(b_val)

        a_valid = a_val and a_val > 0
        b_valid = b_val and b_val > 0
        a_text = fmt(a_val)
        b_text = fmt(b_val)
        if not a_valid and not b_valid:
            return a_text, b_text, 0, 0
        if a_valid and not b_valid:
            return a_text, b_text, 1, 0
        if b_valid and not a_valid:
            return a_text, b_text, 0, 1
        # 双方有效，数值越小越好
        if a_val < b_val:
            return a_text, b_text, 1, 0
        elif b_val < a_val:
            return a_text, b_text, 0, 1
        else:
            return a_text, b_text, 0, 0

    async def compare(self, kw1: str, kw2: str) -> Tuple[str, Optional[str]]:
        """对比两位选手成绩"""
        p1 = await self._resolve_person(kw1)
        p2 = await self._resolve_person(kw2)
        if not p1:
            return "", f"❌ 未找到选手：{kw1}"
        if not p2:
            return "", f"❌ 未找到选手：{kw2}"

        r1 = await self._build_player_record(p1)
        r2 = await self._build_player_record(p2)

        # 事件并集
        all_events = set(r1.single_map.keys()) | set(r1.average_map.keys()) | set(r2.single_map.keys()) | set(r2.average_map.keys())
        if not all_events:
            return "", "❌ 两位选手均无成绩记录"

        lines = []
        name1 = r1.person.get("name", kw1)
        name2 = r2.person.get("name", kw2)
        header = f"{name1} VS {name2}\n"
        lines.append(header)

        score_a = 0
        score_b = 0

        for e_id in sorted(all_events, key=lambda x: str(x)):
            s1 = r1.single_map.get(e_id)
            s2 = r2.single_map.get(e_id)
            a1 = r1.average_map.get(e_id)
            a2 = r2.average_map.get(e_id)

            # 用 event_name 优先（API 返回的已经是简化格式）
            event_name = ""
            if s1 and s1.get("event_name"):
                event_name = s1["event_name"]
            elif s2 and s2.get("event_name"):
                event_name = s2["event_name"]
            elif a1 and a1.get("event_name"):
                event_name = a1["event_name"]
            elif a2 and a2.get("event_name"):
                event_name = a2["event_name"]
            else:
                # 如果没有 event_name，使用 event_id 并映射
                event_name = EVENT_ID_MAP.get(e_id, e_id)
            
            # event_name 已经是简化格式，不需要再次映射

            # 单次
            event_format_single: str = "time"
            if s1 and s1.get("event_format"):
                event_format_single = str(s1.get("event_format", "time"))
            elif s2 and s2.get("event_format"):
                event_format_single = str(s2.get("event_format", "time"))
            elif a1 and a1.get("event_format"):
                event_format_single = str(a1.get("event_format", "time"))
            elif a2 and a2.get("event_format"):
                event_format_single = str(a2.get("event_format", "time"))
            a_single_val = s1.get("best", 0) if s1 else 0
            b_single_val = s2.get("best", 0) if s2 else 0
            a_txt, b_txt, a_pt, b_pt = self._compare(a_single_val, b_single_val, event_format_single)
            score_a += a_pt
            score_b += b_pt
            star_a = " (☆)" if a_pt > b_pt else ""
            star_b = " (★)" if b_pt > a_pt else ""

            # 平均
            event_format_avg: str = "time"
            if a1 and a1.get("event_format"):
                event_format_avg = str(a1.get("event_format", "time"))
            elif a2 and a2.get("event_format"):
                event_format_avg = str(a2.get("event_format", "time"))
            elif s1 and s1.get("event_format"):
                event_format_avg = str(s1.get("event_format", "time"))
            elif s2 and s2.get("event_format"):
                event_format_avg = str(s2.get("event_format", "time"))
            a_avg_val = a1.get("best", 0) if a1 else 0
            b_avg_val = a2.get("best", 0) if a2 else 0
            a_avg_txt, b_avg_txt, a_avg_pt, b_avg_pt = self._compare(a_avg_val, b_avg_val, event_format_avg)
            score_a += a_avg_pt
            score_b += b_avg_pt
            star_a_avg = " (☆)" if a_avg_pt > b_avg_pt else ""
            star_b_avg = " (★)" if b_avg_pt > a_avg_pt else ""

            # 仅当至少一方有成绩才输出
            if (a_pt or b_pt or a_avg_pt or b_avg_pt or a_txt != "-" or b_txt != "-" or a_avg_txt != "-" or b_avg_txt != "-"):
                event_name_str = str(event_name) if event_name else ""
                lines.append(f"{event_name_str}  {a_txt}{star_a} || {b_txt}{star_b}")
                indent_spaces = " " * (len(event_name_str) + 3)
                lines.append(f"{indent_spaces}  {a_avg_txt}{star_a_avg} || {b_avg_txt}{star_b_avg}")

        result_text = "\n".join(lines) if lines else ""
        if score_a > score_b:
            result_text += f"\n\n胜利 (⭐){score_a} : {score_b}"
        elif score_b > score_a:
            result_text += f"\n\n   {score_a} : {score_b} (⭐) 胜利"
        else:
            result_text += f"\n\n   {score_a} : {score_b} 平局"
        return result_text, None

