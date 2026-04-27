from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent

from ..clients.one_api import EVENT_ID_TO_CODE, OneRecordHandler, PersonalRecordAPIClient, format_time_ms
from ..core.reaction_feedback import CommandReactionFeedback
from ..core.wca_bindings import strip_first_command_token


NUMBER_FORMAT_EVENT_IDS = {16}


class OnePKService:
    """one 平台选手 PK"""

    def __init__(
        self,
        one_client: PersonalRecordAPIClient,
        one_handler: OneRecordHandler,
        reaction_feedback: CommandReactionFeedback,
    ):
        self.one_client = one_client
        self.one_handler = one_handler
        self.reaction_feedback = reaction_feedback

    async def _resolve_player(self, keyword: str):
        user_id, user_name, error = await self.one_handler.resolve_user(keyword)
        if error:
            return None, None, error
        resolved_name = user_name or keyword
        return user_id, resolved_name, None

    def _build_best_maps(self, response: dict):
        single_map: dict[int, int] = {}
        avg_map: dict[int, int] = {}
        name_map: dict[int, str] = {}
        rank_data = response.get("data", {}).get("rank", []) if response else []

        for record in rank_data or []:
            event_id = record.get("e_id")
            if not isinstance(event_id, int):
                continue

            event_name = EVENT_ID_TO_CODE.get(event_id) or f"项目{event_id}"
            name_map[event_id] = event_name

            single_value = record.get("time_single")
            avg_value = record.get("time_avg")

            if isinstance(single_value, int) and single_value > 0 and single_value != 999999:
                current_single = single_map.get(event_id)
                if current_single is None or single_value < current_single:
                    single_map[event_id] = single_value

            if isinstance(avg_value, int) and avg_value > 0 and avg_value != 999999:
                current_avg = avg_map.get(event_id)
                if current_avg is None or avg_value < current_avg:
                    avg_map[event_id] = avg_value

        return single_map, avg_map, name_map

    def _format_one_value(self, value: int | None, event_id: int, *, is_average: bool) -> str:
        if value is None or value <= 0 or value == 999999:
            return "-"
        if event_id in NUMBER_FORMAT_EVENT_IDS:
            if is_average:
                return f"{value / 100:.2f}" if value >= 100 else f"{value:.2f}"
            return str(value)
        return format_time_ms(value)

    def _normalize_compare_value(self, value: int | None, event_id: int, *, is_average: bool):
        if value is None or value <= 0 or value == 999999:
            return None
        if event_id in NUMBER_FORMAT_EVENT_IDS and is_average:
            return value / 100 if value >= 100 else float(value)
        return value

    def _compare(self, left: int | None, right: int | None, event_id: int, *, is_average: bool):
        left_norm = self._normalize_compare_value(left, event_id, is_average=is_average)
        right_norm = self._normalize_compare_value(right, event_id, is_average=is_average)
        left_text = self._format_one_value(left, event_id, is_average=is_average)
        right_text = self._format_one_value(right, event_id, is_average=is_average)

        if left_norm is None and right_norm is None:
            return left_text, right_text, 0, 0
        if left_norm is not None and right_norm is None:
            return left_text, right_text, 1, 0
        if right_norm is not None and left_norm is None:
            return left_text, right_text, 0, 1
        if left_norm < right_norm:
            return left_text, right_text, 1, 0
        if right_norm < left_norm:
            return left_text, right_text, 0, 1
        return left_text, right_text, 0, 0

    async def compare(self, kw1: str, kw2: str):
        user1_id, user1_name, err1 = await self._resolve_player(kw1)
        if err1:
            return "", err1

        user2_id, user2_name, err2 = await self._resolve_player(kw2)
        if err2:
            return "", err2

        if user1_id is None or user2_id is None:
            return "", "无法确认 one 选手身份哦~"

        resp1 = await self.one_client.get_personal_records(user1_id)
        resp2 = await self.one_client.get_personal_records(user2_id)

        if resp1.get("code") != 10000:
            error_msg = resp1.get("err", "未知错误")
            return "", f"获取 {user1_name} 的 one 成绩失败啦：{error_msg}"
        if resp2.get("code") != 10000:
            error_msg = resp2.get("err", "未知错误")
            return "", f"获取 {user2_name} 的 one 成绩失败啦：{error_msg}"

        single1, avg1, names1 = self._build_best_maps(resp1)
        single2, avg2, names2 = self._build_best_maps(resp2)

        all_events = set(single1) | set(avg1) | set(single2) | set(avg2)
        if not all_events:
            return "", "这两位选手好像都没有 one 成绩记录呢，没法对比呀~"

        event_names = {**names1, **names2}
        score_a = 0
        score_b = 0
        lines = [f"{user1_name} ({user1_id}) VS {user2_name} ({user2_id})\n"]

        for event_id in sorted(all_events):
            event_name = event_names.get(event_id) or f"项目{event_id}"
            single_text1, single_text2, single_score1, single_score2 = self._compare(
                single1.get(event_id), single2.get(event_id), event_id, is_average=False
            )
            avg_text1, avg_text2, avg_score1, avg_score2 = self._compare(
                avg1.get(event_id), avg2.get(event_id), event_id, is_average=True
            )

            score_a += single_score1 + avg_score1
            score_b += single_score2 + avg_score2

            if (
                single_score1
                or single_score2
                or avg_score1
                or avg_score2
                or single_text1 != "-"
                or single_text2 != "-"
                or avg_text1 != "-"
                or avg_text2 != "-"
            ):
                single_star1 = " (☆)" if single_score1 > single_score2 else ""
                single_star2 = " (★)" if single_score2 > single_score1 else ""
                avg_star1 = " (☆)" if avg_score1 > avg_score2 else ""
                avg_star2 = " (★)" if avg_score2 > avg_score1 else ""
                event_name_str = str(event_name)
                lines.append(f"{event_name_str}  {single_text1}{single_star1} || {single_text2}{single_star2}")
                indent_spaces = " " * (len(event_name_str) + 5)
                lines.append(f"{indent_spaces}  {avg_text1}{avg_star1} || {avg_text2}{avg_star2}")

        result_text = "\n".join(lines) if lines else ""
        if score_a > score_b:
            result_text += f"\n\n (⭐) {score_a} : {score_b}\n恭喜 {user1_name} 胜利啦！"
        elif score_b > score_a:
            result_text += f"\n\n {score_a} : {score_b} (⭐)\n恭喜 {user2_name} 胜利啦！"
        else:
            result_text += f"\n\n {score_a} : {score_b} \n竟然是平局呢~"
        return result_text, None

    async def handle(self, event: AstrMessageEvent):
        args = strip_first_command_token(event.message_str)
        parts = args.split(maxsplit=1) if args else []
        if len(parts) < 2:
            yield event.plain_result(
                "参数不足哦\n用法: /onepk <选手1> <选手2>\n示例: /onepk 1234 5678"
            ).use_t2i(False)
            return

        p1, p2 = parts[0].strip(), parts[1].strip()
        await self.reaction_feedback.send_processing_reaction(event)
        try:
            text, err = await self.compare(p1, p2)
            if err:
                yield event.plain_result(f"对比出了一点小状况呢: {err}").use_t2i(False)
                return
            yield event.plain_result(text).use_t2i(False)
        except Exception as e:
            logger.error(f"one PK 异常: {e}")
            yield event.plain_result(f"对比出了一点小状况呢: {str(e)}").use_t2i(False)
