import os
from functools import lru_cache
from pathlib import Path

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent
from astrbot.api.star import Context
from astrbot.core.utils.t2i.renderer import HtmlRenderer


TEMPLATE_PATH = Path(__file__).resolve().parent.parent.joinpath("templates", "cube_help.html")


class WCACubeHelpService:
    def __init__(self, context: Context):
        self.context = context

    async def handle(self, event: AstrMessageEvent):
        commands_data = prepare_cube_help_data()
        try:
            cfg = self.context.get_config(umo=event.unified_msg_origin)
            endpoint = cfg.get("t2i_endpoint") if isinstance(cfg, dict) else None

            renderer = HtmlRenderer(endpoint_url=endpoint)
            await renderer.initialize()

            image_path = await renderer.render_custom_template(
                get_cube_help_template(),
                build_cube_help_template_data(commands_data),
                return_url=False,
                options={
                    "full_page": True,
                    "type": "jpeg",
                    "quality": 100,
                    "scale": "device",
                    "device_scale_factor_level": "ultra",
                },
            )

            try:
                await event.send(event.image_result(image_path))
            except Exception as send_err:
                logger.error(f"cube帮助 图片发送失败: {send_err}")
                help_text = format_cube_help_text(commands_data)
                yield event.plain_result("哎呀，图片发送失败啦，先为您展示文字版吧：\n\n" + help_text).use_t2i(False)
            finally:
                if image_path and os.path.exists(image_path):
                    try:
                        os.remove(image_path)
                    except Exception as e:
                        logger.error(f"清理 cube帮助 临时图片失败: {e}")
        except Exception as e:
            logger.error(f"cube帮助 渲染失败: {e}")
            help_text = format_cube_help_text(commands_data)
            yield event.plain_result("渲染图片时出了点小状况呢，先为您展示文字版吧：\n\n" + help_text).use_t2i(False)


def prepare_cube_help_data() -> dict[str, object]:
    return {
        "title": "Cube 命令帮助",
        "subtitle": "WCA 与 one 相关命令一览",
        "commands": [
            {"name": "/wca", "desc": "查询 WCA 个人成绩", "example": "/wca 李华 或 /wca @某人"},
            {"name": "/one", "desc": "查询 one 平台个人成绩", "example": "/one 李华 或 /one 1234"},
            {"name": "/wca绑定", "desc": "绑定你的 WCAID 到 QQ", "example": "/wca绑定 2026LIHU01"},
            {"name": "/wcapic", "desc": "生成 WCA 个人纪录图片", "example": "/wcapic 李华"},
            {"name": "/wcapk", "desc": "WCA 成绩 PK", "example": "/wcapk 李华 张伟"},
            {"name": "/onepk", "desc": "one 成绩 PK", "example": "/onepk 李华 张伟"},
            {"name": "/pktwo", "desc": "同一选手的 WCA / one 双平台 PK", "example": "/pktwo 李华 或 /pktwo 2026LIHU01 1234"},
            {"name": "/pr", "desc": "双平台 PR 查询", "example": "/pr 李华 或 /pr 2026LIHU01 1234"},
            {"name": "/prpk", "desc": "双平台 PR PK 对比", "example": "/prpk 李华 张伟"},
            {"name": "/近期比赛", "desc": "查询近期赛事", "example": "/近期比赛"},            
            {"name": "/宿敌", "desc": "查询 WCA 宿敌", "example": "/宿敌 李华"},
            {"name": "/版本", "desc": "查询宿敌数据库版本日期", "example": "/版本"},
        ],
    }


@lru_cache(maxsize=1)
def get_cube_help_template() -> str:
    return TEMPLATE_PATH.read_text(encoding="utf-8")


def build_cube_help_template_data(data: dict[str, object]) -> dict[str, object]:
    return {
        "title": data.get("title", "命令帮助"),
        "subtitle": data.get("subtitle", ""),
        "commands": data.get("commands", []),
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
