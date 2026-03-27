import json
from typing import Any, Optional
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
from .wca_formatting import EVENT_FORMAT_MAP, EVENT_ID_MAP, EVENT_ORDER, format_person_records_text
from .wca_person_lookup import WCAPersonLookupService


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
    
class WCACommandService:
    def __init__(self, query: WCAQuery, bindings: WCABindingStore):
        self.query = query
        self.bindings = bindings
        self.lookup = WCAPersonLookupService(query)

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

        try:
            result = await self.lookup.resolve_unique(search_input)
            if result.status == "not_found":
                yield event.plain_result(
                    f"抱歉啦，没有找到关于 {search_input} 的信息哦"
                ).use_t2i(False)
                return

            if result.status == "ambiguous":
                yield event.plain_result(
                    self.lookup.format_multiple_persons_prompt(
                        result.persons or [],
                        "/wca [WCAID]",
                    )
                ).use_t2i(False)
                return

            picked = result.picked or {}
            person_info = self.lookup.get_person_info(picked)
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

            result_text = format_person_records_text(records_data)
            yield event.plain_result(result_text).use_t2i(False)

        except Exception as e:
            logger.error(f"WCA 查询异常: {e}")
            yield event.plain_result(f"查询出了一点小状况呢: {str(e)}").use_t2i(False)


class WCABindCommandService:
    def __init__(self, query: WCAQuery, bindings: WCABindingStore):
        self.query = query
        self.bindings = bindings
        self.lookup = WCAPersonLookupService(query)

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
                result = await self.lookup.resolve_unique(
                    normalized_wca_id,
                    preferred_wca_id=normalized_wca_id,
                )
                if result.status == "not_found":
                    yield event.plain_result(f"没有找到 WCAID 为 {normalized_wca_id} 的选手哦").use_t2i(False)
                    return
                if result.status != "ok":
                    yield event.plain_result(f"没有找到 WCAID 为 {normalized_wca_id} 的选手哦").use_t2i(False)
                    return
                picked = result.picked or {}
            else:
                result = await self.lookup.resolve_unique(search_input)
                if result.status == "not_found":
                    yield event.plain_result(f"没有找到名字是 {search_input} 的选手哦").use_t2i(False)
                    return
                if result.status == "ambiguous":
                    yield event.plain_result(
                        self.lookup.format_multiple_persons_prompt(
                            result.persons or [],
                            "/wca绑定 <WCAID>",
                            intro="找到多个同名选手啦，请改用 WCAID 绑定喵：\n",
                        )
                    ).use_t2i(False)
                    return
                picked = result.picked or {}

            person_info = self.lookup.get_person_info(picked)
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
