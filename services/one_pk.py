from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent

from ..clients.one_api import OneRecordHandler, PersonalRecordAPIClient
from ..core.reaction_feedback import CommandReactionFeedback
from ..core.wca_bindings import strip_first_command_token
from .wca_cross_platform import build_one_best_maps, compare_values, event_order_key


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

        single1, avg1 = build_one_best_maps(resp1)
        single2, avg2 = build_one_best_maps(resp2)

        all_events = set(single1) | set(avg1) | set(single2) | set(avg2)
        if not all_events:
            return "", "这两位选手好像都没有 one 成绩记录呢，没法对比呀~"

        score_a = 0
        score_b = 0
        lines = [f"{user1_name} VS {user2_name}\n"]

        for code in sorted(all_events, key=event_order_key):
            single_text1, single_text2, single_score1, single_score2 = compare_values(
                single1.get(code), single2.get(code), fmt="time", is_average=False
            )
            avg_text1, avg_text2, avg_score1, avg_score2 = compare_values(
                avg1.get(code), avg2.get(code), fmt="time", is_average=True
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
                lines.append(f"{code}  {single_text1}{single_star1} || {single_text2}{single_star2}")
                lines.append(f"    {avg_text1}{avg_star1} || {avg_text2}{avg_star2}")

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
