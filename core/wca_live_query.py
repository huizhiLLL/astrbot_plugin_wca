"""WCA 官方成绩与 CubeRoot 近期直播成绩的合并查询。"""

import asyncio
from typing import Any

from astrbot.api import logger

from ..clients.cuberoot_live_api import CubeRootLiveAPIClient
from .wca_formatting import EVENT_FORMAT_MAP, EVENT_ID_MAP, EVENT_ORDER
from .wca_person_lookup import WCAPersonLookupService
from .wca_query import WCAQuery


class WCALiveQuery:
    """把官方历史成绩和近期未公示成绩合并成 /wca 同款数据结构。"""

    def __init__(self, wca_query: WCAQuery, live_client: CubeRootLiveAPIClient):
        self.wca_query = wca_query
        self.live_client = live_client

    async def get_person_best_records(
        self,
        person_id: str,
        person_entry: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        official = await self.wca_query.get_person_best_records(
            person_id,
            person_entry=person_entry,
        )
        if not official:
            official = self._empty_person_records(person_id, person_entry)
            if official is None:
                return None

        try:
            live_bundle = await self.live_client.get_person_live_results(person_id)
        except Exception as exc:
            logger.warning(f"CubeRoot 直播成绩查询失败，将返回官方成绩：{exc}")
            return official

        live_rows = live_bundle.get("results", [])
        if not isinstance(live_rows, list):
            live_rows = []

        records = self._merge_records(official, live_rows)
        await self._enrich_ranks(records, official)
        return {**official, **records}

    @staticmethod
    def _empty_person_records(
        person_id: str,
        person_entry: dict[str, Any] | None,
    ) -> dict[str, Any] | None:
        person = person_entry.get("person") if isinstance(person_entry, dict) else None
        if not isinstance(person, dict):
            return None
        country = person.get("country")
        country_iso2 = str(
            person.get("country_iso2")
            or (country.get("iso2") if isinstance(country, dict) else "")
            or ""
        )
        return {
            "person": {
                "wca_id": person.get("wca_id") or person_id,
                "name": person.get("name", ""),
                "country_id": country_iso2,
                "country_iso2": country_iso2,
                "country_name": (country or {}).get("name", "")
                if isinstance(country, dict)
                else "",
                "gender": person.get("gender", ""),
                "url": person.get("url", ""),
                "avatar_thumb_url": "",
            },
            "competition_count": 0,
            "medals": None,
            "records": None,
            "total_solves": 0,
            "single_records": [],
            "average_records": [],
        }

    @staticmethod
    def _merge_records(
        official: dict[str, Any],
        live_rows: list[Any],
    ) -> dict[str, list[dict[str, Any]]]:
        official_single = {
            str(row.get("event_id")): row
            for row in official.get("single_records", [])
            if isinstance(row, dict) and row.get("event_id")
        }
        official_average = {
            str(row.get("event_id")): row
            for row in official.get("average_records", [])
            if isinstance(row, dict) and row.get("event_id")
        }
        live_by_event: dict[str, list[dict[str, Any]]] = {}
        for row in live_rows:
            if not isinstance(row, dict):
                continue
            event_id = str(row.get("event_id") or "")
            if event_id:
                live_by_event.setdefault(event_id, []).append(row)

        event_ids = set(official_single) | set(official_average) | set(live_by_event)
        single_records: list[dict[str, Any]] = []
        average_records: list[dict[str, Any]] = []
        for event_id in event_ids:
            rows = live_by_event.get(event_id, [])
            single = WCALiveQuery._merge_one_type(
                event_id, "single", official_single.get(event_id), rows
            )
            average = WCALiveQuery._merge_one_type(
                event_id, "average", official_average.get(event_id), rows
            )
            if single:
                single_records.append(single)
            if average:
                average_records.append(average)

        return {
            "single_records": sorted(single_records, key=lambda x: x["event_rank"]),
            "average_records": sorted(average_records, key=lambda x: x["event_rank"]),
        }

    @staticmethod
    def _merge_one_type(
        event_id: str,
        result_type: str,
        official: dict[str, Any] | None,
        live_rows: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        candidates: list[int] = []
        if official and isinstance(official.get("best"), int) and official["best"] > 0:
            candidates.append(official["best"])
        live_field = "best" if result_type == "single" else "average"
        for row in live_rows:
            value = row.get(live_field)
            if isinstance(value, int) and value > 0:
                candidates.append(value)
        if not candidates:
            return None

        best = min(candidates)
        base = dict(official or {})
        base.update(
            {
                "event_id": event_id,
                "event_name": EVENT_ID_MAP.get(event_id, event_id),
                "event_format": EVENT_FORMAT_MAP.get(event_id, "time"),
                "best": best,
                "event_rank": EVENT_ORDER.get(event_id, 999),
                "live": bool(official is None or best != official.get("best")),
            }
        )
        return base

    async def _enrich_ranks(
        self,
        records: dict[str, list[dict[str, Any]]],
        official: dict[str, Any],
    ) -> None:
        country = str(official.get("person", {}).get("country_iso2") or "")
        tasks: list[tuple[dict[str, Any], asyncio.Task[Any]]] = []
        for result_type, key in (("single", "single_records"), ("average", "average_records")):
            for row in records[key]:
                task = asyncio.create_task(
                    self.live_client.get_rank(
                        str(row["event_id"]), result_type, int(row["best"]), country
                    )
                )
                tasks.append((row, task))

        if not tasks:
            return
        results = await asyncio.gather(*(task for _, task in tasks), return_exceptions=True)
        for (row, _), rank_data in zip(tasks, results):
            if not isinstance(rank_data, dict):
                continue
            row["world_rank"] = rank_data.get("rank", row.get("world_rank", 0))
            row["country_rank"] = (rank_data.get("national") or {}).get(
                "rank", row.get("country_rank", 0)
            )
            row["continent_rank"] = (rank_data.get("continental") or {}).get(
                "rank", row.get("continent_rank", 0)
            )


class WCALiveCommandService:
    def __init__(self, query: WCALiveQuery, bindings):
        self.query = query
        self.bindings = bindings
        self.lookup = WCAPersonLookupService(query.wca_query)

    async def handle(self, event):
        from .wca_bindings import resolve_bound_wca_search_input

        search_input, missing_binding, qq_id = resolve_bound_wca_search_input(
            event, self.bindings
        )
        if missing_binding == "target":
            yield event.plain_result(f"这个 QQ（{qq_id}）还没有绑定 WCAID 呢").use_t2i(False)
            return
        if missing_binding == "sender":
            yield event.plain_result(
                "你还没有绑定 WCAID 呢\n用法: /wca绑定 <WCAID或姓名>\n示例: /wca绑定 2026LIHU01"
            ).use_t2i(False)
            return
        if not search_input:
            yield event.plain_result(
                "请提供 WCAID 或姓名哦\n用法: /wcalive [WCAID/姓名]\n示例: /wcalive 2026LIHU01"
            ).use_t2i(False)
            return

        try:
            result = await self.lookup.resolve_unique(search_input)
            if result.status == "not_found":
                yield event.plain_result(f"抱歉啦，没有找到关于 {search_input} 的信息哦").use_t2i(False)
                return
            if result.status == "ambiguous":
                yield event.plain_result(
                    self.lookup.format_multiple_persons_prompt(result.persons or [], "/wcalive [WCAID]")
                ).use_t2i(False)
                return
            picked = result.picked or {}
            person_info = self.lookup.get_person_info(picked)
            person_id = str(person_info.get("wca_id", ""))
            if not person_id:
                yield event.plain_result("哎呀，选手信息不完整，无法查询成绩哦").use_t2i(False)
                return
            records_data = await self.query.get_person_best_records(person_id, picked)
            if not records_data:
                yield event.plain_result(
                    f"{person_info.get('name', '该选手')} ({person_id}) 还没有 WCA 成绩记录呢，快去参加比赛吧~"
                ).use_t2i(False)
                return
            from .wca_formatting import format_person_records_text

            yield event.plain_result(format_person_records_text(records_data)).use_t2i(False)
        except Exception as exc:
            logger.error(f"WCA 直播查询异常: {exc}")
            yield event.plain_result(f"查询出了一点小状况呢: {exc}").use_t2i(False)
