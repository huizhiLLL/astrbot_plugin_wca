import asyncio
import io
import os

import astrbot.api.message_components as Comp
from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent
from astrbot.api.star import Context
from astrbot.core.utils.t2i.renderer import HtmlRenderer
from PIL import Image

from .wca_query import WCAQuery, format_wca_time


class WCAPicService:
    IMAGE_RENDER_TIMEOUT_SECONDS = 60
    IMAGE_SEND_MAX_BYTES = 1024 * 1024

    def __init__(self, query: WCAQuery, context: Context):
        self.query = query
        self.context = context

    async def handle(self, event: AstrMessageEvent):
        message_str = event.message_str.strip()
        parts = message_str.split(maxsplit=1)

        if len(parts) < 2:
            yield event.plain_result(
                "请提供 WCAID 或姓名哦\n"
                "用法: /wcapic [WCAID/姓名]\n"
                "示例: /wcapic 2026LIHU01\n"
                "示例: /wcapic 李华"
            ).use_t2i(False)
            return

        search_input = parts[1].strip()
        yield event.plain_result("正在为您生成 WCA 成绩图，请稍候哦...（查看原图更加清晰~）").use_t2i(False)

        try:
            persons = await self.query.search_person(search_input)

            if not persons:
                yield event.plain_result(
                    f"抱歉啦，没有找到关于 {search_input} 的信息哦\n"
                    "提示：可以使用 WCAID（如：2026LIHU01）或姓名进行搜索"
                ).use_t2i(False)
                return

            if len(persons) > 1:
                lines = [f"好准哦，找到了多个匹配的选手，请使用 WCAID 查询具体哪位呢：\n"]
                for i, item in enumerate(persons[:10], 1):
                    person_info = item.get("person", {}) if isinstance(item, dict) else {}
                    person_id = person_info.get("wca_id", "未知")
                    person_name = person_info.get("name", "未知")
                    country = person_info.get("country_iso2", "")
                    country_str = f" [{country}]" if country else ""
                    lines.append(f"{i}. {person_name} ({person_id}){country_str}")

                if len(persons) > 10:
                    lines.append(f"\n... 还有 {len(persons) - 10} 个结果未显示哦")

                lines.append("\n使用方法: /wcapic <WCAID>")
                yield event.plain_result("\n".join(lines)).use_t2i(False)
                return

            picked = persons[0]
            person_info = picked.get("person", {}) if isinstance(picked, dict) else {}
            person_id = person_info.get("wca_id", "") or person_info.get("id", "")

            if not person_id:
                yield event.plain_result("哎呀，选手信息不完整，无法查询成绩哦").use_t2i(False)
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
                    pic_text = self._format_person_records_for_pic(records_data)
                    yield event.plain_result("哎呀，图片发送超时啦，先为您展示文字版吧：\n\n" + pic_text).use_t2i(False)
                finally:
                    if image_path and os.path.exists(image_path):
                        try:
                            os.remove(image_path)
                            logger.debug(f"已清理 WCA 临时图片: {image_path}")
                        except Exception as e:
                            logger.error(f"清理临时图片失败: {e}")
            except asyncio.TimeoutError:
                logger.error("WCA PIC 渲染超时")
                pic_text = self._format_person_records_for_pic(records_data)
                yield event.plain_result("生成图片用时有点久，先为您展示文字版吧：\n\n" + pic_text).use_t2i(False)
            except Exception as e:
                logger.error(f"WCA PIC 渲染失败: {e}")
                pic_text = self._format_person_records_for_pic(records_data)
                yield event.plain_result("渲染图片时出了点小状况呢，先为您展示文字版吧：\n\n" + pic_text).use_t2i(False)

        except Exception as e:
            logger.error(f"WCA PIC 查询异常: {e}")
            yield event.plain_result(f"生成图片时出了一点小状况呢: {str(e)}").use_t2i(False)

    async def _render_person_records_card(self, records_data: dict, event: AstrMessageEvent) -> str:
        cfg = self.context.get_config(umo=event.unified_msg_origin)
        endpoint = cfg.get("t2i_endpoint") if isinstance(cfg, dict) else None

        renderer = HtmlRenderer(endpoint_url=endpoint)
        await renderer.initialize()

        tmpl_str = self._person_card_template()
        tmpl_data = self._person_card_template_data(records_data)
        return await renderer.render_custom_template(
            tmpl_str,
            tmpl_data,
            return_url=False,
            options={
                "full_page": True,
                "type": "jpeg",
                "quality": 85,
                "scale": "device",
                "device_scale_factor_level": "high",
            },
        )

    async def _send_image(self, event: AstrMessageEvent, image_path: str):
        file_size = os.path.getsize(image_path)
        logger.warning(f"WCA PIC 准备发送图片: path={image_path}, size={file_size} bytes")

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
            logger.warning(f"WCA PIC 字节发送失败，回退路径发送: {bytes_err}")
            image_result = event.image_result(image_path)
            await event.send(image_result)

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
                img.save(output, format="JPEG", quality=80, optimize=True, progressive=True)
                return output.getvalue()
        except Exception as compress_err:
            logger.warning(f"WCA PIC 图片压缩失败，继续使用原图发送: {compress_err}")
            return None

    def _person_card_template(self) -> str:
        return r"""
<!DOCTYPE html>
<html lang="zh-CN">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <style>
      * { 
        box-sizing: border-box; 
      }
      body {
        margin: 0;
        background: #ffffff;
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
        color: #333;
      }
      .wrap {
        width: 1200px;
        margin: 0 auto;
        padding: 40px;
        background: #fff;
      }
      
      /* Header & Avatar */
      .name {
        text-align: center;
        font-size: 32px;
        font-weight: 600;
        margin-bottom: 24px;
        color: #222;
      }
      .avatar-area {
        display: flex;
        justify-content: center;
        margin-bottom: 30px;
      }
      .avatar {
        /* 放大了头像区域的限制 */
        max-width: 600px; 
        max-height: 400px; 
        object-fit: contain;
        border-radius: 4px;
      }
      .avatar.placeholder {
        width: 300px;
        height: 300px;
        background: #f5f5f5;
        border-radius: 4px;
      }

      /* Meta Table */
      .meta {
        width: 100%;
        border-collapse: collapse;
        margin-bottom: 30px;
        font-size: 15px;
      }
      .meta th {
        background: #f4f4f4;
        color: #333;
        font-weight: 600;
        text-align: center;
        padding: 12px 10px;
        border: none;
      }
      .meta td {
        text-align: center;
        padding: 16px 10px;
        color: #222;
        border: none;
      }
      .country {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        gap: 6px;
      }
      .flag {
        font-size: 18px;
        line-height: 1;
      }

      /* Records Section */
      .section-title {
        text-align: center;
        font-size: 20px;
        font-weight: 700;
        margin: 40px 0 20px;
        color: #222;
      }
      .records {
        width: 100%;
        border-collapse: collapse;
        font-size: 15px;
      }
      .records th {
        color: #333;
        font-weight: 600;
        padding: 12px 10px;
        border-bottom: 2px solid #e0e0e0;
        text-align: right;
      }
      .records td {
        padding: 10px;
        text-align: right;
        border: none;
      }
      /* Event column left alignment */
      .records th.event,
      .records td.event {
        text-align: left;
        padding-left: 20px;
      }
      .records td.event {
        color: #333;
      }
      /* Zebra Striping */
      .records tbody tr:nth-child(odd) {
        background-color: #f6f6f6;
      }
      .records tbody tr:nth-child(even) {
        background-color: #ffffff;
      }
      /* Typography for records */
      .muted { 
        color: #777; 
      }
      .strong { 
        font-weight: 700; 
        color: #111; 
      }
      .rank-top { 
        color: #00de00; 
        font-weight: 700; 
      }
    </style>
  </head>
  <body>
    <div class="wrap">
      <div class="name">{{ name }}</div>
      
      <div class="avatar-area">
        {% if avatar_url %}
          <img class="avatar" src="{{ avatar_url }}" alt="{{ name }}"/>
        {% else %}
          <div class="avatar placeholder"></div>
        {% endif %}
      </div>

      <table class="meta">
        <thead>
          <tr>
            <th>国家/地区</th>
            <th>WCA ID</th>
            <th>性别</th>
            <th>比赛</th>
            <th>复原次数</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <td>
              <span class="country">
                {% if flag_text %}<span class="flag">{{ flag_text }}</span>{% endif %}
                <span>{{ country_name }}</span>
              </span>
            </td>
            <td>{{ wca_id }}</td>
            <td>{{ gender }}</td>
            <td>{{ competition_count }}</td>
            <td>{{ total_solves }}</td>
          </tr>
        </tbody>
      </table>

      <div class="section-title">当前个人记录</div>

      <table class="records">
        <thead>
          <tr>
            <th class="event">项目</th>
            <th>NR</th>
            <th>CR</th>
            <th>WR</th>
            <th>单次</th>
            <th>平均</th>
            <th>WR</th>
            <th>CR</th>
            <th>NR</th>
          </tr>
        </thead>
        <tbody>
          {% for row in rows %}
          <tr>
            <td class="event">{{ row.event_name }}</td>
            <td class="muted {{ row.single_nr_class }}">{{ row.single_nr }}</td>
            <td class="muted {{ row.single_cr_class }}">{{ row.single_cr }}</td>
            <td class="muted {{ row.single_wr_class }}">{{ row.single_wr }}</td>
            <td class="strong">{{ row.single_best }}</td>
            <td class="strong">{{ row.avg_best }}</td>
            <td class="muted {{ row.avg_wr_class }}">{{ row.avg_wr }}</td>
            <td class="muted {{ row.avg_cr_class }}">{{ row.avg_cr }}</td>
            <td class="muted {{ row.avg_nr_class }}">{{ row.avg_nr }}</td>
          </tr>
          {% endfor %}
        </tbody>
      </table>
    </div>
  </body>
</html>
"""

    def _person_card_template_data(self, records_data: dict) -> dict:
        person = records_data.get("person") or {}
        country_iso2 = (person.get("country_iso2") or person.get("country_id") or "").upper()
        country_name = person.get("country_name") or country_iso2 or "-"

        def gender_cn(g: str) -> str:
            g = str(g or "").lower()
            if g.startswith("m"):
                return "男"
            if g.startswith("f"):
                return "女"
            if g:
                return "其他"
            return "-"

        def rank_text(v: object) -> str:
            if isinstance(v, int) and v > 0:
                return str(v)
            return ""

        def rank_class(v: object) -> str:
            if isinstance(v, int) and 0 < v < 100:
                return "rank-top"
            return ""

        def flag_text(iso2: str) -> str:
            iso2 = iso2.strip().upper()
            if iso2 == "CN":
                return "🇨🇳"
            if len(iso2) == 2 and iso2.isalpha():
                return f"[{iso2}]"
            return ""

        event_cn_map: dict[str, str] = {
            "222": "二阶",
            "333": "三阶",
            "444": "四阶",
            "555": "五阶",
            "666": "六阶",
            "777": "七阶",
            "333bf": "三盲",
            "333fm": "最少步",
            "333oh": "单手",
            "clock": "魔表",
            "minx": "五魔方",
            "pyram": "金字塔",
            "skewb": "斜转",
            "sq1": "SQ1",
            "444bf": "四盲",
            "555bf": "五盲",
            "333mbf": "多盲",
            "333ft": "脚拧",
        }

        single_records = records_data.get("single_records") or []
        average_records = records_data.get("average_records") or []

        single_map = {r.get("event_id"): r for r in single_records if isinstance(r, dict)}
        average_map = {r.get("event_id"): r for r in average_records if isinstance(r, dict)}

        all_event_ids = set(single_map.keys()) | set(average_map.keys())
        all_event_ids.discard(None)

        rows: list[dict] = []
        for event_id in sorted(
            (e for e in all_event_ids if isinstance(e, str)),
            key=lambda e: int((single_map.get(e) or average_map.get(e) or {}).get("event_rank", 999)),
        ):
            s = single_map.get(event_id) or {}
            a = average_map.get(event_id) or {}
            event_format = s.get("event_format") or a.get("event_format") or "time"

            single_best_val = s.get("best", 0) if isinstance(s, dict) else 0
            avg_best_val = a.get("best", 0) if isinstance(a, dict) else 0

            single_best = (
                format_wca_time(int(single_best_val), str(event_format))
                if isinstance(single_best_val, int) and single_best_val
                else "-"
            )
            avg_best = (
                format_wca_time(int(avg_best_val), str(event_format))
                if isinstance(avg_best_val, int) and avg_best_val
                else "-"
            )

            if single_best == "-" and avg_best == "-":
                continue

            event_name = event_cn_map.get(str(event_id), s.get("event_name") or a.get("event_name") or str(event_id))

            single_nr_val = s.get("country_rank") if isinstance(s, dict) else 0
            single_cr_val = s.get("continent_rank") if isinstance(s, dict) else 0
            single_wr_val = s.get("world_rank") if isinstance(s, dict) else 0
            avg_wr_val = a.get("world_rank") if isinstance(a, dict) else 0
            avg_cr_val = a.get("continent_rank") if isinstance(a, dict) else 0
            avg_nr_val = a.get("country_rank") if isinstance(a, dict) else 0
            rows.append(
                {
                    "event_name": event_name,
                    "single_nr": rank_text(single_nr_val),
                    "single_nr_class": rank_class(single_nr_val),
                    "single_cr": rank_text(single_cr_val),
                    "single_cr_class": rank_class(single_cr_val),
                    "single_wr": rank_text(single_wr_val),
                    "single_wr_class": rank_class(single_wr_val),
                    "single_best": single_best,
                    "avg_best": avg_best,
                    "avg_wr": rank_text(avg_wr_val),
                    "avg_wr_class": rank_class(avg_wr_val),
                    "avg_cr": rank_text(avg_cr_val),
                    "avg_cr_class": rank_class(avg_cr_val),
                    "avg_nr": rank_text(avg_nr_val),
                    "avg_nr_class": rank_class(avg_nr_val),
                }
            )

        competition_count = records_data.get("competition_count")
        total_solves = records_data.get("total_solves")

        return {
            "name": person.get("name") or "未知",
            "avatar_url": person.get("avatar_thumb_url") or "",
            "flag_text": flag_text(country_iso2),
            "country_name": country_name,
            "wca_id": person.get("wca_id") or "-",
            "gender": gender_cn(person.get("gender", "")),
            "competition_count": competition_count if isinstance(competition_count, int) else "-",
            "total_solves": total_solves if isinstance(total_solves, int) else "-",
            "rows": rows,
        }

    def _format_person_records_for_pic(self, records_data: dict) -> str:
        person = records_data.get("person") or {}
        name = person.get("name", "未知")
        person_id = person.get("wca_id", "")
        country = person.get("country_iso2") or person.get("country_id") or ""
        gender = person.get("gender", "")
        gender_str = ""
        if gender:
            gender_str = "Male" if str(gender).lower().startswith("m") else "Female"

        header_lines = [f"{name}", ", ".join([person_id, country or "-", gender_str or "-"])]

        competition_count = records_data.get("competition_count")
        medals = records_data.get("medals") or {}
        records = records_data.get("records") or {}
        total_solves = records_data.get("total_solves")

        stats_parts: list[str] = []
        if isinstance(competition_count, int):
            stats_parts.append(f"比赛: {competition_count}")
        if isinstance(total_solves, int):
            stats_parts.append(f"复原: {total_solves}")
        if isinstance(medals, dict) and isinstance(medals.get("total"), int):
            stats_parts.append(f"奖牌: {medals.get('total')}")
        if isinstance(records, dict) and isinstance(records.get("total"), int):
            stats_parts.append(f"纪录: {records.get('total')}")

        if stats_parts:
            header_lines.append(" | ".join(stats_parts))

        single_records = records_data.get("single_records") or []
        average_records = records_data.get("average_records") or []

        single_map = {r.get("event_id"): r for r in single_records if isinstance(r, dict)}
        average_map = {r.get("event_id"): r for r in average_records if isinstance(r, dict)}
        all_event_ids = set(single_map.keys()) | set(average_map.keys())
        all_event_ids.discard(None)

        if not all_event_ids:
            return "\n".join(header_lines + ["", "暂无 WCA 成绩记录"])

        event_records: list[tuple[int, str]] = []
        for event_id in all_event_ids:
            if not isinstance(event_id, str):
                continue
            rank = 999
            if single_map.get(event_id):
                rank = int(single_map[event_id].get("event_rank", 999))
            elif average_map.get(event_id):
                rank = int(average_map[event_id].get("event_rank", 999))
            event_records.append((rank, event_id))
        event_records.sort(key=lambda x: x[0])

        lines: list[str] = []
        for _, event_id in event_records:
            s = single_map.get(event_id) or {}
            a = average_map.get(event_id) or {}
            event_name = s.get("event_name") or a.get("event_name") or event_id
            event_format = s.get("event_format") or a.get("event_format") or "time"

            single_best = s.get("best", 0) if isinstance(s, dict) else 0
            avg_best = a.get("best", 0) if isinstance(a, dict) else 0

            single_txt = (
                format_wca_time(int(single_best), str(event_format))
                if isinstance(single_best, int) and single_best
                else "-"
            )
            avg_txt = (
                format_wca_time(int(avg_best), str(event_format))
                if isinstance(avg_best, int) and avg_best
                else "-"
            )

            if single_txt == "-" and avg_txt == "-":
                continue

            lines.append(f"{event_name}  {single_txt}  ||  {avg_txt}")

        if not lines:
            lines = ["暂无有效成绩记录"]

        return "\n".join(header_lines + [""] + lines)
