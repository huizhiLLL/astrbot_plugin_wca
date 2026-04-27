import asyncio

import aiohttp
import astrbot.api.message_components as Comp
from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent
from astrbot.api.star import Context

from .wca_pic_template import format_person_records_for_pic
from ..core.pillow_cards import render_wca_person_card
from ..core.wca_bindings import strip_first_command_token
from ..core.wca_person_lookup import WCAPersonLookupService
from ..core.wca_query import WCAQuery


class WCAPicService:
    IMAGE_RENDER_TIMEOUT_SECONDS = 60
    AVATAR_TIMEOUT_SECONDS = 12

    def __init__(self, query: WCAQuery, context: Context):
        self.query = query
        self.context = context
        self.lookup = WCAPersonLookupService(query)

    async def handle(self, event: AstrMessageEvent):
        search_input = strip_first_command_token(event.message_str)

        if not search_input:
            yield event.plain_result(
                "请提供 WCAID 或姓名哦\n"
                "用法: /wcapic [WCAID/姓名]\n"
                "示例: /wcapic 2026LIHU01\n"
                "示例: /wcapic 李华"
            ).use_t2i(False)
            return
        yield event.plain_result(
            "正在为您生成 WCA 成绩图，请稍候哦...（新版改成稳定本地绘制啦）"
        ).use_t2i(False)

        try:
            result = await self.lookup.resolve_unique(search_input)
            if result.status == "not_found":
                yield event.plain_result(
                    f"抱歉啦，没有找到关于 {search_input} 的信息哦\n"
                    "提示：可以使用 WCAID（如：2026LIHU01）或姓名进行搜索"
                ).use_t2i(False)
                return

            if result.status == "ambiguous":
                yield event.plain_result(
                    self.lookup.format_multiple_persons_prompt(
                        result.persons or [],
                        "/wcapic <WCAID>",
                    )
                ).use_t2i(False)
                return

            picked = result.picked or {}
            person_info = self.lookup.get_person_info(picked)
            person_id = person_info.get("wca_id", "") or person_info.get("id", "")

            if not person_id:
                yield event.plain_result(
                    "哎呀，选手信息不完整，无法查询成绩哦"
                ).use_t2i(False)
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

            try:
                image_bytes = await asyncio.wait_for(
                    self._render_person_records_card(records_data),
                    timeout=self.IMAGE_RENDER_TIMEOUT_SECONDS,
                )
                try:
                    await self._send_image(event, image_bytes)
                except Exception as send_err:
                    logger.error(f"WCA PIC 发送失败: {send_err}")
                    pic_text = format_person_records_for_pic(records_data)
                    yield event.plain_result(
                        "哎呀，图片发送失败啦，先为您展示文字版吧：\n\n" + pic_text
                    ).use_t2i(False)
            except asyncio.TimeoutError:
                logger.error("WCA PIC 渲染超时")
                pic_text = format_person_records_for_pic(records_data)
                yield event.plain_result(
                    "生成图片用时有点久，先为您展示文字版吧：\n\n" + pic_text
                ).use_t2i(False)
            except Exception as e:
                logger.error(f"WCA PIC 渲染失败: {e}")
                pic_text = format_person_records_for_pic(records_data)
                yield event.plain_result(
                    "渲染图片时出了点小状况呢，先为您展示文字版吧：\n\n" + pic_text
                ).use_t2i(False)

        except Exception as e:
            logger.error(f"WCA PIC 查询异常: {e}")
            yield event.plain_result(f"生成图片时出了一点小状况呢: {str(e)}").use_t2i(
                False
            )

    async def _render_person_records_card(self, records_data: dict) -> bytes:
        avatar_bytes = await self._fetch_avatar_bytes(records_data)
        image_bytes = render_wca_person_card(records_data, avatar_bytes=avatar_bytes)
        logger.warning(
            f"WCA PIC 本地绘制完成: size={len(image_bytes)} bytes"
        )
        return image_bytes

    async def _fetch_avatar_bytes(self, records_data: dict) -> bytes | None:
        person = records_data.get("person") or {}
        avatar_url = person.get("avatar_thumb_url") or person.get("avatar_url") or ""
        if not avatar_url:
            return None

        try:
            timeout = aiohttp.ClientTimeout(total=self.AVATAR_TIMEOUT_SECONDS)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(str(avatar_url)) as response:
                    if response.status != 200:
                        logger.warning(
                            f"WCA PIC 头像下载失败，状态码: {response.status}, url={avatar_url}"
                        )
                        return None
                    return await response.read()
        except Exception as avatar_err:
            logger.warning(f"WCA PIC 头像下载失败: {avatar_err}")
            return None

    async def _send_image(self, event: AstrMessageEvent, image_bytes: bytes):
        logger.warning(
            f"WCA PIC 准备发送 Pillow 图片: size={len(image_bytes)} bytes"
        )
        await event.send(event.chain_result([Comp.Image.fromBytes(image_bytes)]))
        logger.debug("WCA PIC 使用 Pillow 字节发送成功")
