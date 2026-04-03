from dataclasses import dataclass

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent
from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import (
    AiocqhttpMessageEvent,
)


@dataclass(slots=True)
class CommandReactionFeedback:
    enabled: bool = True
    emoji_id: int = 124
    emoji_type: str = "1"

    async def send_processing_reaction(self, event: AstrMessageEvent) -> bool:
        """发送命令已接收的轻量反馈。

        优先使用 QQ 原生消息贴表情；其他平台暂不发送文字兜底，
        以避免把“轻量反馈”退化成额外的提示消息。
        """

        if not self.enabled:
            return False

        if not isinstance(event, AiocqhttpMessageEvent):
            return False

        raw = getattr(event.message_obj, "raw_message", None)
        if not isinstance(raw, dict):
            return False

        message_id = raw.get("message_id")
        if message_id is None:
            return False

        try:
            await event.bot.set_msg_emoji_like(
                message_id=int(message_id),
                emoji_id=int(self.emoji_id),
                emoji_type=self.emoji_type,
                set=True,
            )
            return True
        except Exception as exc:
            logger.debug(f"WCA 轻量表情反馈发送失败: {exc}")
            return False
