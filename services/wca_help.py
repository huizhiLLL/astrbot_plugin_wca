import astrbot.api.message_components as Comp
from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent
from astrbot.api.star import Context

from ..core.pillow_cards import render_cube_help_card


class WCACubeHelpService:
    def __init__(self, context: Context):
        self.context = context

    async def handle(self, event: AstrMessageEvent):
        commands_data = prepare_cube_help_data()
        try:
            image_bytes = render_cube_help_card(commands_data)
            logger.warning(
                f"cube帮助 准备发送图片: size={len(image_bytes)} bytes"
            )
            await event.send(event.chain_result([Comp.Image.fromBytes(image_bytes)]))
        except Exception as send_err:
            logger.error(f"cube帮助 图片渲染或发送失败: {send_err}")
            help_text = format_cube_help_text(commands_data)
            yield event.plain_result(
                "哎呀，图片发送失败啦，先为您展示文字版吧：\n\n" + help_text
            ).use_t2i(False)


def prepare_cube_help_data() -> dict[str, object]:
    return {
        "title": "Cube 命令帮助",
        "subtitle": "WCA 与 one 相关命令一览",
        "commands": [
            {"name": "/wca", "desc": "查询 WCA 个人成绩", "example": "/wca 李华 或 /wca @某人"},
            {"name": "/one", "desc": "查询 one 平台个人成绩", "example": "/one 李华 或 /one 1234"},
            {"name": "/wca绑定", "desc": "绑定你的 WCAID 到 QQ", "example": "/wca绑定 2026LIHU01"},
            {"name": "/one绑定", "desc": "绑定你的 oneID 到 QQ", "example": "/one绑定 1234"},
            {"name": "/wcapic", "desc": "生成 WCA 个人纪录图片", "example": "/wcapic 或 /wcapic @某人"},
            {"name": "/wcapk", "desc": "WCA 成绩 PK", "example": "/wcapk @某人 或 /wcapk @甲 @乙"},
            {"name": "/onepk", "desc": "one 成绩 PK", "example": "/onepk @某人 或 /onepk @甲 @乙"},
            {"name": "/pktwo", "desc": "同一选手的 WCA / one 双平台 PK", "example": "/pktwo 李华 或 /pktwo 2026LIHU01 1234"},
            {"name": "/pr", "desc": "双平台 PR 查询", "example": "/pr 或 /pr @某人"},
            {"name": "/prpk", "desc": "双平台 PR PK 对比", "example": "/prpk @某人 或 /prpk @甲 @乙"},
            {"name": "/近期比赛", "desc": "查询近期赛事", "example": "/近期比赛"},
            {"name": "/宿敌", "desc": "查询 WCA 宿敌", "example": "/宿敌 或 /宿敌 @某人"},
            {"name": "/版本", "desc": "查询宿敌数据库版本日期", "example": "/版本"},
        ],
    }


def format_cube_help_text(data: dict[str, object]) -> str:
    lines = [str(data.get("title", "命令帮助")), str(data.get("subtitle", "")), ""]
    for cmd in data.get("commands", []):
        if not isinstance(cmd, dict):
            continue
        lines.append(f"{cmd.get('name')} - {cmd.get('desc')}")
        lines.append(f"  例: {cmd.get('example')}")
        lines.append("")
    return "\n".join(lines)
