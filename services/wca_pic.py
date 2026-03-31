import asyncio
import io
import os
import time

import astrbot.api.message_components as Comp
from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent
from astrbot.api.star import Context
from astrbot.core.utils.t2i.renderer import HtmlRenderer
from PIL import Image

from .wca_pic_template import (
    build_person_card_template_data,
    format_person_records_for_pic,
    get_person_card_template,
)
from ..core.wca_bindings import strip_first_command_token
from ..core.wca_person_lookup import WCAPersonLookupService
from ..core.wca_query import WCAQuery


class WCAPicService:
    IMAGE_RENDER_TIMEOUT_SECONDS = 60
    IMAGE_SEND_MAX_BYTES = 1024 * 1024

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
            "正在为您生成 WCA 成绩图，请稍候哦...（查看原图更加清晰~）"
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
                image_path = await asyncio.wait_for(
                    self._render_person_records_card(records_data, event),
                    timeout=self.IMAGE_RENDER_TIMEOUT_SECONDS,
                )
                try:
                    await self._send_image(event, image_path)
                except Exception as send_err:
                    logger.error(f"WCA PIC 发送超时或失败: {send_err}")
                    pic_text = format_person_records_for_pic(records_data)
                    yield event.plain_result(
                        "哎呀，图片发送超时啦，先为您展示文字版吧：\n\n" + pic_text
                    ).use_t2i(False)
                finally:
                    if image_path and os.path.exists(image_path):
                        try:
                            os.remove(image_path)
                            logger.debug(f"已清理 WCA 临时图片: {image_path}")
                        except Exception as e:
                            logger.error(f"清理临时图片失败: {e}")
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

    async def _render_person_records_card(
        self, records_data: dict, event: AstrMessageEvent
    ) -> str:
        cfg = self.context.get_config(umo=event.unified_msg_origin)
        endpoint = cfg.get("t2i_endpoint") if isinstance(cfg, dict) else None

        renderer = HtmlRenderer(endpoint_url=endpoint)
        await renderer.initialize()

        tmpl_str = get_person_card_template()
        tmpl_data = build_person_card_template_data(records_data)
        return await renderer.render_custom_template(
            tmpl_str,
            tmpl_data,
            return_url=False,
            options={
                "full_page": True,
                "type": "jpeg",
                "quality": 100,
                "scale": "device",
                "device_scale_factor_level": "ultra",
            },
        )

    async def _send_image(self, event: AstrMessageEvent, image_path: str):
        file_size = os.path.getsize(image_path)
        logger.warning(
            f"WCA PIC 准备发送图片: path={image_path}, size={file_size} bytes"
        )

        with open(image_path, "rb") as f:
            image_bytes = f.read()

        compressed_bytes = self._compress_image_for_send(image_bytes)
        if compressed_bytes is not None and len(compressed_bytes) < len(image_bytes):
            logger.warning(
                "WCA PIC 图片已压缩后发送: "
                f"original={len(image_bytes)} bytes, compressed={len(compressed_bytes)} bytes"
            )
            image_bytes = compressed_bytes

        try:
            await event.send(event.chain_result([Comp.Image.fromBytes(image_bytes)]))
            logger.debug("WCA PIC 使用内存字节发送成功")
        except Exception as bytes_err:
            if await self._handle_potential_send_success(event, bytes_err):
                return
            logger.warning(f"WCA PIC 字节发送失败，回退路径发送: {bytes_err}")
            image_result = event.image_result(image_path)
            try:
                await event.send(image_result)
            except Exception as path_err:
                if await self._handle_potential_send_success(event, path_err):
                    return
                raise

    async def _handle_potential_send_success(
        self,
        event: AstrMessageEvent,
        send_err: Exception,
    ) -> bool:
        if not self._is_potential_success_error(send_err):
            return False

        group_id = event.get_group_id()
        if not group_id:
            return False

        logger.warning(f"WCA PIC 命中疑似假失败，进入观察期: {send_err}")
        await asyncio.sleep(10)

        if await self._was_image_sent_recently(event, seconds=30):
            logger.info("WCA PIC 已通过历史消息确认图片实际送达，拦截后续降级")
            return True

        logger.warning("WCA PIC 观察期结束，未确认图片送达")
        return False

    def _is_potential_success_error(self, err: Exception) -> bool:
        error_str = str(err).lower()
        return (
            "timeout" in error_str or "retcode=1200" in error_str or "1200" in error_str
        )

    async def _was_image_sent_recently(
        self, event: AstrMessageEvent, seconds: int = 30
    ) -> bool:
        group_id = event.get_group_id()
        if not group_id:
            return False

        history = await self._get_group_msg_history(event, group_id, count=50)
        if not history:
            return False

        messages = (
            history.get("messages", history) if isinstance(history, dict) else history
        )
        if not isinstance(messages, list):
            return False

        self_id = str(event.get_self_id() or "")
        now = time.time()

        for msg in reversed(messages):
            if not isinstance(msg, dict):
                continue

            msg_time = msg.get("time", 0)
            try:
                if now - float(msg_time) > seconds:
                    break
            except Exception:
                continue

            user_id = str(msg.get("user_id", msg.get("sender", {}).get("user_id", "")))
            if self_id and user_id != self_id:
                continue

            message_chain = msg.get("message", [])
            if isinstance(message_chain, str):
                continue

            for seg in message_chain:
                if isinstance(seg, dict) and seg.get("type") == "image":
                    return True

        return False

    async def _get_group_msg_history(
        self,
        event: AstrMessageEvent,
        group_id: str,
        count: int = 50,
    ):
        bot = getattr(event, "bot", None)
        if bot is None:
            return None

        try:
            if hasattr(bot, "get_group_msg_history"):
                return await bot.get_group_msg_history(
                    group_id=int(group_id), count=count
                )
        except Exception as e:
            logger.warning(f"WCA PIC 读取群历史失败(get_group_msg_history): {e}")

        try:
            api = getattr(bot, "api", None)
            if api is not None and hasattr(api, "call_action"):
                return await api.call_action(
                    "get_group_msg_history",
                    group_id=int(group_id),
                    count=count,
                )
        except Exception as e:
            logger.warning(f"WCA PIC 读取群历史失败(api.call_action): {e}")

        try:
            if hasattr(bot, "call_action"):
                return await bot.call_action(
                    "get_group_msg_history",
                    group_id=int(group_id),
                    count=count,
                )
        except Exception as e:
            logger.warning(f"WCA PIC 读取群历史失败(call_action): {e}")

        return None

    def _compress_image_for_send(self, image_bytes: bytes) -> bytes | None:
        if len(image_bytes) <= self.IMAGE_SEND_MAX_BYTES:
            return None

        try:
            with Image.open(io.BytesIO(image_bytes)) as img:
                if img.mode not in ("RGB", "L"):
                    img = img.convert("RGB")

                if max(img.size) > 1600:
                    img.thumbnail((1600, 1600), Image.Resampling.LANCZOS)

                output = io.BytesIO()
                img.save(
                    output, format="JPEG", quality=80, optimize=True, progressive=True
                )
                return output.getvalue()
        except Exception as compress_err:
            logger.warning(f"WCA PIC 图片压缩失败，继续使用原图发送: {compress_err}")
            return None
