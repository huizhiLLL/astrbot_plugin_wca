from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent

from ..clients.one_api import (
    EVENT_ID_TO_CODE,
    OneRecordHandler,
    PersonalRecordAPIClient,
    format_time_ms,
)
from ..core.reaction_feedback import CommandReactionFeedback
from ..core.wca_bindings import strip_first_command_token
from ..core.wca_formatting import EVENT_ID_MAP, EVENT_ORDER, format_wca_time
from ..core.wca_person_lookup import WCAPersonLookupService
from ..core.wca_query import WCAQuery


NUMBER_FORMAT_EVENTS: set[str] = {"333fm"}
ONE_EVENT_TO_WCA: dict[str, str] = {
    "333": "333",
    "222": "222",
    "444": "444",
    "555": "555",
    "666": "666",
    "777": "777",
    "333oh": "333oh",
    "333bf": "333bf",
    "444bf": "444bf",
    "555bf": "555bf",
    "333mbf": "333mbf",
    "333mbld": "333mbf",
    "333fm": "333fm",
    "py": "py",
    "pyram": "py",
    "sk": "sk",
    "skewb": "sk",
    "sq1": "sq1",
    "clock": "clock",
    "minx": "minx",
    "meg": "minx",
}

WCA_EVENT_CODES: set[str] = set()
for event_id in EVENT_ID_MAP.keys():
    normalized = (
        "py" if event_id == "pyram" else "sk" if event_id == "skewb" else event_id
    )
    WCA_EVENT_CODES.add(normalized)

CROSS_PLATFORM_EVENT_ORDER: list[str] = []
for event_id in EVENT_ORDER.keys():
    normalized = (
        "py" if event_id == "pyram" else "sk" if event_id == "skewb" else event_id
    )
    if normalized not in CROSS_PLATFORM_EVENT_ORDER:
        CROSS_PLATFORM_EVENT_ORDER.append(normalized)


@dataclass
class ResolvedCrossPlatformPlayer:
    wca_person: dict[str, Any] | None
    one_user_id: int | None
    one_user_name: str | None
    wca_error: str | None = None
    one_error: str | None = None


class WCAOneService:
    def __init__(self, client: PersonalRecordAPIClient, handler: OneRecordHandler):
        self.client = client
        self.handler = handler

    async def handle(self, event: AstrMessageEvent):
        search_input = strip_first_command_token(event.message_str)
        if not search_input:
            yield event.plain_result(
                "请提供姓名或 oneID 哦\n用法：/one [姓名或ID]\n示例：/one 李华"
            ).use_t2i(False)
            return

        try:
            user_id, user_name, error_msg = await self.handler.resolve_user(
                search_input
            )
            if error_msg:
                yield event.plain_result(error_msg).use_t2i(False)
                return

            if user_id is None:
                yield event.plain_result("哎呀，没拿到用户 ID 呢").use_t2i(False)
                return

            records_result = await self.client.get_personal_records(user_id)
            if records_result.get("code") != 10000:
                error_msg = records_result.get("err", "未知错误")
                yield event.plain_result(
                    f"呜呜，没拿到成绩记录呢...\n错误：{error_msg}"
                ).use_t2i(False)
                return

            rank_data = records_result.get("data", {}).get("rank", []) or []
            if not rank_data:
                yield event.plain_result(
                    f"{user_name or '这位选手'} 还没有个人记录呢，快去录一个吧~"
                ).use_t2i(False)
                return

            if not user_name:
                user_name = rank_data[0].get("u_name", "未知用户")

            lines = []
            for record in sorted(rank_data, key=lambda x: x.get("e_id", 0)):
                event_code = (
                    EVENT_ID_TO_CODE.get(record.get("e_id"))
                    or f"项目{record.get('e_id')}"
                )

                single_text = "-"
                avg_text = "-"
                time_single = record.get("time_single")
                time_avg = record.get("time_avg")
                if time_single and time_single != 999999:
                    single_text = format_time_ms(time_single)
                if time_avg and time_avg != 999999:
                    avg_text = format_time_ms(time_avg)

                if single_text == "-" and avg_text == "-":
                    continue
                lines.append(f"{event_code}  {single_text} || {avg_text}")

            if not lines:
                yield event.plain_result(
                    f"{user_name} 还没有有效个人记录呢，快去录一个吧~"
                ).use_t2i(False)
                return

            header = f"{user_name}（{user_id}）在 one 平台的成绩为：\n"
            yield event.plain_result(header + "\n" + "\n".join(lines)).use_t2i(False)

        except Exception as e:
            logger.error(f"one 查询异常: {e}")
            yield event.plain_result(f"哎呀，出错了呢：{str(e)}").use_t2i(False)


class WCAPRService:
    def __init__(
        self,
        query: WCAQuery,
        one_client: PersonalRecordAPIClient,
        one_handler: OneRecordHandler,
        reaction_feedback: CommandReactionFeedback,
    ):
        self.query = query
        self.one_client = one_client
        self.one_handler = one_handler
        self.lookup = WCAPersonLookupService(query)
        self.reaction_feedback = reaction_feedback

    async def handle(self, event: AstrMessageEvent):
        args = strip_first_command_token(event.message_str)
        parts = args.split(maxsplit=1) if args else []
        if not parts:
            yield event.plain_result(
                "哎呀，请提供参数哦~\n"
                "用法：/pr [姓名]\n"
                "如果有同名选手，请用：/pr [WCAID] [oneID]\n"
                "示例：/pr 2026LIHUA01 1234"
            ).use_t2i(False)
            return

        search_input = parts[0].strip()
        one_id_input = parts[1].strip() if len(parts) >= 2 else None
        await self.reaction_feedback.send_processing_reaction(event)
        player = await self._resolve_player(
            search_input,
            forced_wca_id=search_input if one_id_input else None,
            forced_one_id=one_id_input,
        )

        if not player.wca_person or player.one_user_id is None:
            lines = ["无法唯一确认选手"]
            if player.wca_error:
                lines.append(player.wca_error)
            if player.one_error:
                lines.append(player.one_error)
            lines.append("请使用：/pr [WCAID] [oneID]")
            yield event.plain_result("\n".join(lines)).use_t2i(False)
            return

        wca_id = player.wca_person.get("wca_id", "")
        wca_name = player.wca_person.get("name", wca_id)

        try:
            wca_records = await self.query.get_person_best_records(wca_id)
        except Exception as e:
            logger.error(f"PR 查询 WCA 异常: {e}")
            yield event.plain_result("查询 WCA 成绩时出错，请稍后重试").use_t2i(False)
            return

        if not wca_records:
            yield event.plain_result(
                f"未找到 {wca_name} ({wca_id}) 的 WCA 成绩记录"
            ).use_t2i(False)
            return

        try:
            one_records_resp = await self.one_client.get_personal_records(
                player.one_user_id
            )
        except Exception as e:
            logger.error(f"PR 查询 one 异常: {e}")
            yield event.plain_result("查询 one 成绩时出错，请稍后重试").use_t2i(False)
            return

        if one_records_resp.get("code") != 10000:
            one_error = one_records_resp.get("err", "未知错误")
            yield event.plain_result(f"获取 one 成绩失败\n错误：{one_error}").use_t2i(
                False
            )
            return

        lines = self._build_merged_pr_lines(wca_records, one_records_resp)
        if not lines:
            yield event.plain_result("两个平台均无有效成绩").use_t2i(False)
            return

        yield event.plain_result(
            f"{wca_name}的 PR 成绩如下：\n\n" + "\n".join(lines)
        ).use_t2i(False)

    async def _resolve_player(
        self,
        keyword: str,
        *,
        forced_wca_id: str | None = None,
        forced_one_id: str | None = None,
    ) -> ResolvedCrossPlatformPlayer:
        wca_person = None
        one_user_id = None
        one_user_name = None
        wca_error = None
        one_error = None

        if forced_wca_id:
            wca_result = await self.lookup.resolve_unique(
                forced_wca_id, preferred_wca_id=forced_wca_id
            )
        else:
            wca_result = await self.lookup.resolve_unique(
                keyword, prefer_exact_name=True
            )

        if wca_result.status == "ok":
            wca_person = self.lookup.get_person_info(wca_result.picked)
        elif wca_result.status == "ambiguous":
            wca_error = self.lookup.format_multiple_persons_prompt(
                wca_result.persons or [],
                "/pr [WCAID] [oneID]",
                intro="找到多个匹配的 WCA 选手，请使用 WCAID：\n",
            )
        else:
            wca_error = f"未找到匹配的 WCA 选手：{forced_wca_id or keyword}"

        if forced_one_id:
            if forced_one_id.isdigit():
                one_user_id = int(forced_one_id)
            else:
                one_error = f"oneID 无效：{forced_one_id}"
        else:
            one_user_id, one_user_name, one_error = await self.one_handler.resolve_user(
                keyword
            )

        return ResolvedCrossPlatformPlayer(
            wca_person, one_user_id, one_user_name, wca_error, one_error
        )

    def _build_merged_pr_lines(
        self, wca_records: dict[str, Any], one_records_resp: dict[str, Any]
    ) -> list[str]:
        wca_single, wca_avg, wca_fmt, _ = build_wca_best_maps(wca_records)
        one_single, one_avg = build_one_best_maps(one_records_resp)

        all_events = set(wca_single) | set(wca_avg) | set(one_single) | set(one_avg)
        lines: list[str] = []
        for code in sorted(all_events, key=event_order_key):
            fmt = (
                "number" if code in NUMBER_FORMAT_EVENTS else wca_fmt.get(code, "time")
            )
            single_value = choose_better_value(
                wca_single.get(code), one_single.get(code), fmt=fmt, is_average=False
            )
            avg_value = choose_better_value(
                wca_avg.get(code), one_avg.get(code), fmt=fmt, is_average=True
            )
            single_text = format_cross_platform_value(
                single_value, fmt, is_average=False
            )
            avg_text = format_cross_platform_value(avg_value, fmt, is_average=True)
            if single_text == "-" and avg_text == "-":
                continue
            lines.append(f"{code}  {single_text}  ||  {avg_text}")
        return lines


class WCAPRPKService:
    def __init__(
        self,
        query: WCAQuery,
        one_client: PersonalRecordAPIClient,
        one_handler: OneRecordHandler,
        reaction_feedback: CommandReactionFeedback,
    ):
        self.query = query
        self.one_client = one_client
        self.one_handler = one_handler
        self.lookup = WCAPersonLookupService(query)
        self.reaction_feedback = reaction_feedback

    async def handle(self, event: AstrMessageEvent):
        args = strip_first_command_token(event.message_str)
        parts = args.split(maxsplit=3) if args else []
        if len(parts) < 2:
            yield event.plain_result(
                "参数不够呢，请提供两个选手哦~\n"
                "用法：/prpk [选手1] [选手2]\n"
                "同名请用：/prpk [WCAID1] [oneID1] [WCAID2] [oneID2]"
            ).use_t2i(False)
            return

        await self.reaction_feedback.send_processing_reaction(event)

        if len(parts) >= 4:
            player1 = await self._resolve_player(
                parts[0].strip(),
                forced_wca_id=parts[0].strip(),
                forced_one_id=parts[1].strip(),
            )
            player2 = await self._resolve_player(
                parts[2].strip(),
                forced_wca_id=parts[2].strip(),
                forced_one_id=parts[3].strip(),
            )
        else:
            player1 = await self._resolve_player(parts[0].strip())
            player2 = await self._resolve_player(parts[1].strip())

        if (
            not player1.wca_person
            or not player2.wca_person
            or player1.one_user_id is None
            or player2.one_user_id is None
        ):
            lines = ["无法唯一确认选手"]
            for err in (
                player1.wca_error,
                player1.one_error,
                player2.wca_error,
                player2.one_error,
            ):
                if err:
                    lines.append(err)
            lines.append("请使用：/prpk [WCAID1] [oneID1] [WCAID2] [oneID2]")
            yield event.plain_result("\n".join(lines)).use_t2i(False)
            return

        w1_name = player1.wca_person.get("name", player1.wca_person.get("wca_id", ""))
        w2_name = player2.wca_person.get("name", player2.wca_person.get("wca_id", ""))

        try:
            w1_records = await self.query.get_person_best_records(
                player1.wca_person.get("wca_id", "")
            )
            w2_records = await self.query.get_person_best_records(
                player2.wca_person.get("wca_id", "")
            )
        except Exception as e:
            logger.error(f"PRPK 查询 WCA 异常: {e}")
            yield event.plain_result("查询 WCA 成绩时出错，请稍后重试").use_t2i(False)
            return

        one1_resp = await safe_fetch_one_records(self.one_client, player1.one_user_id)
        one2_resp = await safe_fetch_one_records(self.one_client, player2.one_user_id)

        if not w1_records and not one1_resp:
            yield event.plain_result(f"{w1_name} 无成绩记录").use_t2i(False)
            return
        if not w2_records and not one2_resp:
            yield event.plain_result(f"{w2_name} 无成绩记录").use_t2i(False)
            return

        lines = build_prpk_lines(
            w1_name, w2_name, w1_records, w2_records, one1_resp, one2_resp
        )
        yield event.plain_result("\n".join(lines)).use_t2i(False)

    async def _resolve_player(
        self,
        keyword: str,
        *,
        forced_wca_id: str | None = None,
        forced_one_id: str | None = None,
    ) -> ResolvedCrossPlatformPlayer:
        wca_person = None
        one_user_id = None
        one_user_name = None
        wca_error = None
        one_error = None

        if forced_wca_id:
            wca_result = await self.lookup.resolve_unique(
                forced_wca_id, preferred_wca_id=forced_wca_id
            )
        else:
            wca_result = await self.lookup.resolve_unique(
                keyword, prefer_exact_name=True
            )

        if wca_result.status == "ok":
            wca_person = self.lookup.get_person_info(wca_result.picked)
        elif wca_result.status == "ambiguous":
            wca_error = self.lookup.format_multiple_persons_prompt(
                wca_result.persons or [],
                "/prpk [WCAID1] [oneID1] [WCAID2] [oneID2]",
                intro="找到多个匹配的 WCA 选手，请使用 WCAID：\n",
            )
        else:
            wca_error = f"未找到匹配的 WCA 选手：{forced_wca_id or keyword}"

        if forced_one_id:
            if forced_one_id.isdigit():
                one_user_id = int(forced_one_id)
            else:
                one_error = f"oneID 无效：{forced_one_id}"
        else:
            one_user_id, one_user_name, one_error = await self.one_handler.resolve_user(
                keyword
            )

        return ResolvedCrossPlatformPlayer(
            wca_person, one_user_id, one_user_name, wca_error, one_error
        )


def normalize_wca_event_id(event_id: str | None) -> str | None:
    if not event_id:
        return None
    event_id = event_id.lower()
    if event_id == "pyram":
        return "py"
    if event_id == "skewb":
        return "sk"
    return event_id


def normalize_one_event_code(event_code: str | None) -> str | None:
    if not event_code:
        return None
    mapped = ONE_EVENT_TO_WCA.get(event_code.lower())
    if not mapped:
        return None
    mapped_lower = mapped.lower()
    if mapped_lower in WCA_EVENT_CODES:
        return mapped_lower
    return None


def one_time_to_centiseconds(time_value: int | None) -> int | None:
    if not time_value or time_value == 999999:
        return None
    try:
        value_str = str(int(time_value)).zfill(6)
        minutes = int(value_str[:2])
        seconds = int(value_str[2:4])
        centi = int(value_str[4:6])
        total_centis = (minutes * 60 + seconds) * 100 + centi
        return total_centis if total_centis > 0 else None
    except (ValueError, TypeError):
        return None


def one_value_to_number_or_centiseconds(
    time_value: int | None, event_code: str
) -> int | None:
    if not time_value or time_value == 999999:
        return None

    if event_code in NUMBER_FORMAT_EVENTS:
        try:
            value_int = int(time_value)
            if value_int < 100:
                return value_int if value_int > 0 else None
            value_str = str(value_int).zfill(6)
            minutes = int(value_str[:2])
            seconds = int(value_str[2:4])
            if minutes == 0:
                return seconds if seconds > 0 else None
            return None
        except (ValueError, TypeError):
            return None
    return one_time_to_centiseconds(time_value)


def choose_better_value(
    v1: int | None, v2: int | None, *, fmt: str, is_average: bool
) -> int | None:
    if v1 is None:
        return v2
    if v2 is None:
        return v1
    if fmt == "number" and is_average:
        n1 = v1 / 100 if v1 >= 100 else float(v1)
        n2 = v2 / 100 if v2 >= 100 else float(v2)
        return v1 if n1 <= n2 else v2
    return v1 if v1 <= v2 else v2


def format_cross_platform_value(
    value: int | None, fmt: str, *, is_average: bool
) -> str:
    if value is None:
        return "-"
    if fmt == "number" and is_average:
        if value >= 100:
            return f"{value / 100:.2f}"
        return f"{value:.2f}"
    return format_wca_time(value, fmt)


def build_wca_best_maps(records: dict[str, Any] | None):
    single_map: dict[str, int] = {}
    avg_map: dict[str, int] = {}
    fmt_map: dict[str, str] = {}
    rank_map: dict[str, int] = {}

    if not records:
        return single_map, avg_map, fmt_map, rank_map

    for record in records.get("single_records", []):
        code = normalize_wca_event_id(str(record.get("event_id", "")))
        value = record.get("best")
        if code in WCA_EVENT_CODES and isinstance(value, int) and value > 0:
            single_map[code] = (
                min(single_map.get(code, value), value) if code in single_map else value
            )
            fmt_map[code] = str(record.get("event_format", "time"))
            rank_map[code] = min(
                rank_map.get(code, 999), int(record.get("event_rank", 999))
            )

    for record in records.get("average_records", []):
        code = normalize_wca_event_id(str(record.get("event_id", "")))
        value = record.get("best")
        if code in WCA_EVENT_CODES and isinstance(value, int) and value > 0:
            avg_map[code] = (
                min(avg_map.get(code, value), value) if code in avg_map else value
            )
            fmt_map.setdefault(code, str(record.get("event_format", "time")))
            rank_map[code] = min(
                rank_map.get(code, 999), int(record.get("event_rank", 999))
            )

    return single_map, avg_map, fmt_map, rank_map


def build_one_best_maps(resp: dict[str, Any] | None):
    single_map: dict[str, int] = {}
    avg_map: dict[str, int] = {}
    rank_data = (
        resp.get("data", {}).get("rank", [])
        if resp and resp.get("code") == 10000
        else []
    )

    for record in rank_data:
        event_code_raw = EVENT_ID_TO_CODE.get(record.get("e_id"))
        code = normalize_one_event_code(event_code_raw)
        if not code:
            continue
        single_value = one_value_to_number_or_centiseconds(
            record.get("time_single"), code
        )
        avg_value = one_value_to_number_or_centiseconds(record.get("time_avg"), code)

        if single_value is not None:
            current_single = single_map.get(code)
            single_map[code] = (
                min(current_single, single_value)
                if current_single is not None
                else single_value
            )
        if avg_value is not None:
            current_avg = avg_map.get(code)
            avg_map[code] = (
                min(current_avg, avg_value) if current_avg is not None else avg_value
            )

    return single_map, avg_map


@lru_cache(maxsize=1)
def _event_order_index() -> dict[str, int]:
    return {code: idx for idx, code in enumerate(CROSS_PLATFORM_EVENT_ORDER)}


def event_order_key(code: str):
    return (_event_order_index().get(code, 999), code)


async def safe_fetch_one_records(
    client: PersonalRecordAPIClient, user_id: int
) -> dict[str, Any] | None:
    try:
        return await client.get_personal_records(user_id)
    except Exception as e:
        logger.error(f"跨平台查询 one 异常: {e}")
        return None


def build_prpk_lines(
    name1: str,
    name2: str,
    wca_records1: dict[str, Any] | None,
    wca_records2: dict[str, Any] | None,
    one_resp1: dict[str, Any] | None,
    one_resp2: dict[str, Any] | None,
) -> list[str]:
    w1_s, w1_a, w1_fmt, _ = build_wca_best_maps(wca_records1)
    w2_s, w2_a, w2_fmt, _ = build_wca_best_maps(wca_records2)
    o1_s, o1_a = build_one_best_maps(one_resp1)
    o2_s, o2_a = build_one_best_maps(one_resp2)

    a_s, a_a, a_fmt = build_merged_best_maps(w1_s, w1_a, w1_fmt, o1_s, o1_a)
    b_s, b_a, b_fmt = build_merged_best_maps(w2_s, w2_a, w2_fmt, o2_s, o2_a)

    all_events = set(a_s) | set(a_a) | set(b_s) | set(b_a)
    if not all_events:
        return ["两位选手均无有效成绩"]

    score_a = 0
    score_b = 0
    lines = [f"PR PK 结果：\n{name1} VS {name2}\n"]

    for code in sorted(all_events, key=event_order_key):
        fmt = a_fmt.get(code) or b_fmt.get(code) or "time"
        s1, s2, p1, p2 = compare_values(
            a_s.get(code), b_s.get(code), fmt=fmt, is_average=False
        )
        score_a += p1
        score_b += p2
        avg1, avg2, ap1, ap2 = compare_values(
            a_a.get(code), b_a.get(code), fmt=fmt, is_average=True
        )
        score_a += ap1
        score_b += ap2

        if (
            p1
            or p2
            or ap1
            or ap2
            or s1 != "-"
            or s2 != "-"
            or avg1 != "-"
            or avg2 != "-"
        ):
            star1 = " (☆)" if p1 > p2 else ""
            star2 = " (★)" if p2 > p1 else ""
            star1_avg = " (☆)" if ap1 > ap2 else ""
            star2_avg = " (★)" if ap2 > ap1 else ""
            lines.append(f"{code}  {s1}{star1} || {s2}{star2}")
            lines.append(f"    {avg1}{star1_avg} || {avg2}{star2_avg}")

    if score_a > score_b:
        lines.append(f" 胜利(⭐) {score_a} : {score_b} 失败")
    elif score_b > score_a:
        lines.append(f"   失败 {score_a} : {score_b}(⭐) 胜利")
    else:
        lines.append(f"   {score_a} : {score_b} 平局")
    return lines


def build_merged_best_maps(
    wca_single: dict[str, int],
    wca_avg: dict[str, int],
    wca_fmt: dict[str, str],
    one_single: dict[str, int],
    one_avg: dict[str, int],
):
    best_single: dict[str, int | None] = {}
    best_avg: dict[str, int | None] = {}
    best_fmt: dict[str, str] = {}

    for code in set(wca_single) | set(wca_avg) | set(one_single) | set(one_avg):
        fmt = "number" if code in NUMBER_FORMAT_EVENTS else wca_fmt.get(code, "time")
        best_single[code] = choose_better_value(
            wca_single.get(code), one_single.get(code), fmt=fmt, is_average=False
        )
        best_avg[code] = choose_better_value(
            wca_avg.get(code), one_avg.get(code), fmt=fmt, is_average=True
        )
        best_fmt[code] = fmt

    return best_single, best_avg, best_fmt


def compare_values(v1: int | None, v2: int | None, *, fmt: str, is_average: bool):
    normalized1 = normalize_comparison_value(v1, fmt=fmt, is_average=is_average)
    normalized2 = normalize_comparison_value(v2, fmt=fmt, is_average=is_average)
    text1 = format_cross_platform_value(v1, fmt, is_average=is_average)
    text2 = format_cross_platform_value(v2, fmt, is_average=is_average)

    if normalized1 is None and normalized2 is None:
        return text1, text2, 0, 0
    if normalized1 is not None and normalized2 is None:
        return text1, text2, 1, 0
    if normalized2 is not None and normalized1 is None:
        return text1, text2, 0, 1
    left = normalized1
    right = normalized2
    if left is None or right is None:
        return text1, text2, 0, 0
    if left < right:
        return text1, text2, 1, 0
    if right < left:
        return text1, text2, 0, 1
    return text1, text2, 0, 0


def normalize_comparison_value(value: int | None, *, fmt: str, is_average: bool):
    if value is None:
        return None
    if fmt == "number" and is_average:
        return value / 100 if value >= 100 else float(value)
    return value
