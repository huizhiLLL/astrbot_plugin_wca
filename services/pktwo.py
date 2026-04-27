from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent

from ..clients.one_api import OneRecordHandler, PersonalRecordAPIClient
from ..core.reaction_feedback import CommandReactionFeedback
from ..core.wca_bindings import strip_first_command_token
from ..core.wca_query import WCAQuery
from .wca_cross_platform import (
    EVENT_ID_MAP,
    NUMBER_FORMAT_EVENTS,
    ResolvedCrossPlatformPlayer,
    WCAPRService,
    build_one_best_maps,
    build_wca_best_maps,
    compare_values,
    event_order_key,
)


class PKTwoService:
    """同一选手在 WCA 与 one 平台的成绩 PK"""

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
        self.reaction_feedback = reaction_feedback
        self._resolver = WCAPRService(query, one_client, one_handler, reaction_feedback)

    async def handle(self, event: AstrMessageEvent):
        args = strip_first_command_token(event.message_str)
        parts = args.split(maxsplit=1) if args else []
        if not parts:
            yield event.plain_result(
                "哎呀，请提供参数哦~\n"
                "用法：/pktwo [姓名]\n"
                "如果有同名选手，请用：/pktwo [WCAID] [oneID]\n"
                "示例：/pktwo 2026LIHUA01 1234"
            ).use_t2i(False)
            return

        search_input = parts[0].strip()
        one_id_input = parts[1].strip() if len(parts) >= 2 else None
        await self.reaction_feedback.send_processing_reaction(event)

        player = await self._resolver._resolve_player(
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
            lines.append("请使用：/pktwo [WCAID] [oneID]")
            yield event.plain_result("\n".join(lines)).use_t2i(False)
            return

        wca_id = player.wca_person.get("wca_id", "")
        wca_name = player.wca_person.get("name", wca_id)

        try:
            wca_records = await self.query.get_person_best_records(wca_id)
        except Exception as e:
            logger.error(f"PKTWO 查询 WCA 异常: {e}")
            yield event.plain_result("查询 WCA 成绩时出错，请稍后重试").use_t2i(False)
            return

        if not wca_records:
            yield event.plain_result(
                f"未找到 {wca_name} ({wca_id}) 的 WCA 成绩记录"
            ).use_t2i(False)
            return

        try:
            one_records_resp = await self.one_client.get_personal_records(player.one_user_id)
        except Exception as e:
            logger.error(f"PKTWO 查询 one 异常: {e}")
            yield event.plain_result("查询 one 成绩时出错，请稍后重试").use_t2i(False)
            return

        if one_records_resp.get("code") != 10000:
            one_error = one_records_resp.get("err", "未知错误")
            yield event.plain_result(f"获取 one 成绩失败\n错误：{one_error}").use_t2i(False)
            return

        one_user_name = player.one_user_name or self._extract_one_user_name(one_records_resp)
        text = self._build_compare_text(
            wca_name,
            one_user_name,
            wca_id,
            player.one_user_id,
            wca_records,
            one_records_resp,
        )
        if not text:
            yield event.plain_result("两个平台均无有效成绩").use_t2i(False)
            return

        yield event.plain_result(text).use_t2i(False)

    def _build_compare_text(
        self,
        wca_name: str,
        one_user_name: str | None,
        wca_id: str,
        one_user_id: int,
        wca_records: dict,
        one_records_resp: dict,
    ):
        wca_single, wca_avg, wca_fmt, _ = build_wca_best_maps(wca_records)
        one_single, one_avg = build_one_best_maps(one_records_resp)

        all_events = set(wca_single) | set(wca_avg) | set(one_single) | set(one_avg)
        if not all_events:
            return ""

        display_name = (
            f"{wca_name} ({one_user_name})" if one_user_name and one_user_name != wca_name else wca_name
        )
        lines = [f"{display_name}\n{wca_id} VS {one_user_id}\n"]
        score_wca = 0
        score_one = 0

        for code in sorted(all_events, key=event_order_key):
            fmt = "number" if code in NUMBER_FORMAT_EVENTS else wca_fmt.get(code, "time")
            s1, s2, p1, p2 = compare_values(
                wca_single.get(code), one_single.get(code), fmt=fmt, is_average=False
            )
            avg1, avg2, ap1, ap2 = compare_values(
                wca_avg.get(code), one_avg.get(code), fmt=fmt, is_average=True
            )
            score_wca += p1 + ap1
            score_one += p2 + ap2

            if (
                p1 or p2 or ap1 or ap2 or
                s1 != "-" or s2 != "-" or avg1 != "-" or avg2 != "-"
            ):
                event_name = EVENT_ID_MAP.get(code, code)
                event_name_str = str(event_name)
                star1 = " (☆)" if p1 > p2 else ""
                star2 = " (★)" if p2 > p1 else ""
                star1_avg = " (☆)" if ap1 > ap2 else ""
                star2_avg = " (★)" if ap2 > ap1 else ""
                lines.append(f"{event_name_str}  {s1}{star1} || {s2}{star2}")
                indent_spaces = " " * (len(event_name_str) + 3)
                lines.append(f"{indent_spaces}  {avg1}{star1_avg} || {avg2}{star2_avg}")

        result_text = "\n".join(lines)
        if score_wca > score_one:
            result_text += f"\n\n (⭐) {score_wca} : {score_one}\nWCA 平台胜利啦！"
        elif score_one > score_wca:
            result_text += f"\n\n {score_wca} : {score_one} (⭐)\none 平台胜利啦！"
        else:
            result_text += f"\n\n {score_wca} : {score_one} \n两个平台打平了呢~"
        return result_text

    @staticmethod
    def _extract_one_user_name(one_records_resp: dict) -> str | None:
        rank_data = one_records_resp.get("data", {}).get("rank", []) or []
        for record in rank_data:
            user_name = str(record.get("u_name") or "").strip()
            if user_name:
                return user_name
        return None
