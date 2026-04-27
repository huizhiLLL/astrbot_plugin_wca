from __future__ import annotations

import io
from pathlib import Path
from typing import Iterable

from PIL import Image, ImageDraw, ImageFont

from ..services.wca_pic_template import build_person_card_template_data

ASSETS_DIR = Path(__file__).resolve().parent.parent / "assets"
FONTS_DIR = ASSETS_DIR / "fonts"
DEFAULT_FONT_PATH = FONTS_DIR / "NotoSansSC-Regular.ttf"

CARD_BG = "#F7F8FC"
PANEL_BG = "#FFFFFF"
PANEL_BORDER = "#E5E7EF"
TITLE_COLOR = "#202531"
TEXT_COLOR = "#485061"
MUTED_TEXT = "#7A8295"
ACCENT = "#4D77FF"
ACCENT_LIGHT = "#ECF1FF"
TABLE_HEADER_BG = "#EEF3FF"
TABLE_ALT_BG = "#FAFBFE"
RANK_TOP_BG = "#FFF1CF"
RANK_TOP_TEXT = "#9A6500"
DIVIDER = "#E7EAF2"

CANVAS_WIDTH = 1280
PADDING_X = 52
PADDING_Y = 42
HELP_CARD_GAP = 22
HELP_ROW_HEIGHT = 118
PERSON_ROW_HEIGHT = 56
AVATAR_SIZE = 220


class FontBook:
    def __init__(self, font_path: Path | None = None):
        self.font_path = font_path or DEFAULT_FONT_PATH
        self.title = self._load(40)
        self.subtitle = self._load(22)
        self.h3 = self._load(24)
        self.body = self._load(20)
        self.body_small = self._load(18)
        self.mono = self._load(18)
        self.metric = self._load(30)

    def _load(self, size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
        try:
            return ImageFont.truetype(str(self.font_path), size=size)
        except Exception:
            return ImageFont.load_default()


def render_cube_help_card(data: dict[str, object]) -> bytes:
    fonts = FontBook()
    commands = list(data.get("commands", []))
    canvas_height = max(680, 240 + max(1, len(commands)) * HELP_ROW_HEIGHT)
    image = Image.new("RGB", (CANVAS_WIDTH, canvas_height), CARD_BG)
    draw = ImageDraw.Draw(image)

    _draw_rounded_panel(draw, (32, 28, CANVAS_WIDTH - 32, canvas_height - 28), radius=28)

    title = str(data.get("title", "Cube 命令帮助"))
    subtitle = str(data.get("subtitle", ""))
    title_y = 56
    draw.text((PADDING_X, title_y), title, font=fonts.title, fill=TITLE_COLOR)
    draw.text((PADDING_X, title_y + 56), subtitle, font=fonts.subtitle, fill=MUTED_TEXT)

    top = 148
    content_width = CANVAS_WIDTH - PADDING_X * 2
    for index, command in enumerate(commands):
        if not isinstance(command, dict):
            continue
        row_top = top + index * HELP_ROW_HEIGHT
        row_box = (PADDING_X, row_top, PADDING_X + content_width, row_top + HELP_ROW_HEIGHT - 14)
        fill = TABLE_ALT_BG if index % 2 == 0 else PANEL_BG
        _draw_rounded_panel(draw, row_box, radius=20, fill=fill, outline=PANEL_BORDER)

        name = str(command.get("name", ""))
        desc = str(command.get("desc", ""))
        example = str(command.get("example", ""))

        draw.text((row_box[0] + 22, row_box[1] + 18), name, font=fonts.h3, fill=ACCENT)
        desc_lines = _wrap_text(draw, desc, fonts.body, max_width=420, max_lines=2)
        example_lines = _wrap_text(draw, example, fonts.body_small, max_width=520, max_lines=2)

        _draw_lines(draw, desc_lines, (row_box[0] + 220, row_box[1] + 16), fonts.body, TEXT_COLOR, 10)
        _draw_lines(
            draw,
            [f"示例：{line}" if i == 0 else f"      {line}" for i, line in enumerate(example_lines)],
            (row_box[0] + 220, row_box[1] + 50),
            fonts.body_small,
            MUTED_TEXT,
            8,
        )

    return _image_to_png_bytes(image)


def render_wca_person_card(
    records_data: dict,
    avatar_bytes: bytes | None = None,
) -> bytes:
    fonts = FontBook()
    data = build_person_card_template_data(records_data)
    rows = list(data.get("rows", []))

    canvas_height = max(920, 420 + max(1, len(rows)) * PERSON_ROW_HEIGHT + 80)
    image = Image.new("RGB", (CANVAS_WIDTH, canvas_height), CARD_BG)
    draw = ImageDraw.Draw(image)

    _draw_rounded_panel(draw, (26, 24, CANVAS_WIDTH - 26, canvas_height - 24), radius=30)

    avatar = _prepare_avatar(avatar_bytes)
    image.paste(avatar, (PADDING_X, 56), avatar)

    text_left = PADDING_X + AVATAR_SIZE + 32
    draw.text((text_left, 68), str(data.get("name", "未知")), font=fonts.title, fill=TITLE_COLOR)
    subtitle = f"{data.get('wca_id', '-')}  ·  {data.get('country_name', '-')}  ·  {data.get('gender', '-')}"
    draw.text((text_left, 124), subtitle, font=fonts.subtitle, fill=MUTED_TEXT)

    metrics = [
        ("地区", str(data.get("flag_text", "")) + " " + str(data.get("country_name", "-"))),
        ("比赛", str(data.get("competition_count", "-"))),
        ("复原", str(data.get("total_solves", "-"))),
    ]
    metric_y = 172
    metric_w = 250
    for index, (label, value) in enumerate(metrics):
        left = text_left + index * (metric_w + 18)
        box = (left, metric_y, left + metric_w, metric_y + 82)
        _draw_rounded_panel(draw, box, radius=18, fill=ACCENT_LIGHT, outline=ACCENT_LIGHT)
        draw.text((left + 18, metric_y + 14), label, font=fonts.body_small, fill=MUTED_TEXT)
        draw.text((left + 18, metric_y + 40), value, font=fonts.metric, fill=ACCENT)

    section_top = 308
    draw.text((PADDING_X, section_top), "WCA 最佳成绩", font=fonts.h3, fill=TITLE_COLOR)
    draw.text(
        (PADDING_X, section_top + 34),
        "Single 与 Average 同表展示，排名越靠前越亮眼。",
        font=fonts.body_small,
        fill=MUTED_TEXT,
    )

    table_top = section_top + 86
    table_left = PADDING_X
    table_width = CANVAS_WIDTH - PADDING_X * 2
    columns = [
        ("项目", 190),
        ("NR", 72),
        ("CR", 72),
        ("WR", 72),
        ("Single", 160),
        ("Average", 160),
        ("WR", 72),
        ("CR", 72),
        ("NR", 72),
    ]

    header_box = (table_left, table_top, table_left + table_width, table_top + PERSON_ROW_HEIGHT)
    _draw_rounded_panel(draw, header_box, radius=18, fill=TABLE_HEADER_BG, outline=TABLE_HEADER_BG)

    x = table_left + 18
    for title, width in columns:
        draw.text((x, table_top + 16), title, font=fonts.body_small, fill=TITLE_COLOR)
        x += width

    current_top = table_top + PERSON_ROW_HEIGHT + 10
    if not rows:
        empty_box = (table_left, current_top, table_left + table_width, current_top + 120)
        _draw_rounded_panel(draw, empty_box, radius=18, fill=PANEL_BG, outline=PANEL_BORDER)
        draw.text((table_left + 24, current_top + 42), "暂无有效成绩记录", font=fonts.h3, fill=MUTED_TEXT)
    else:
        for index, row in enumerate(rows):
            row_bottom = current_top + PERSON_ROW_HEIGHT
            fill = TABLE_ALT_BG if index % 2 == 0 else PANEL_BG
            _draw_rounded_panel(
                draw,
                (table_left, current_top, table_left + table_width, row_bottom),
                radius=16,
                fill=fill,
                outline=PANEL_BORDER,
            )
            row_values = [
                str(row.get("event_name", "-")),
                str(row.get("single_nr", "")),
                str(row.get("single_cr", "")),
                str(row.get("single_wr", "")),
                str(row.get("single_best", "-")),
                str(row.get("avg_best", "-")),
                str(row.get("avg_wr", "")),
                str(row.get("avg_cr", "")),
                str(row.get("avg_nr", "")),
            ]
            highlight_flags = [
                False,
                row.get("single_nr_class") == "rank-top",
                row.get("single_cr_class") == "rank-top",
                row.get("single_wr_class") == "rank-top",
                False,
                False,
                row.get("avg_wr_class") == "rank-top",
                row.get("avg_cr_class") == "rank-top",
                row.get("avg_nr_class") == "rank-top",
            ]
            x = table_left + 18
            for (title, width), value, highlight in zip(columns, row_values, highlight_flags):
                if highlight and value:
                    pill_w = max(48, draw.textbbox((0, 0), value, font=fonts.body_small)[2] + 20)
                    pill_box = (
                        x - 8,
                        current_top + 12,
                        x - 8 + pill_w,
                        current_top + 12 + 30,
                    )
                    _draw_rounded_panel(draw, pill_box, radius=14, fill=RANK_TOP_BG, outline=RANK_TOP_BG)
                    draw.text((x + 2, current_top + 16), value, font=fonts.body_small, fill=RANK_TOP_TEXT)
                else:
                    draw.text((x, current_top + 15), value, font=fonts.body_small, fill=TEXT_COLOR)
                x += width
            current_top = row_bottom + 8

    return _image_to_png_bytes(image)


def _prepare_avatar(avatar_bytes: bytes | None) -> Image.Image:
    avatar = None
    if avatar_bytes:
        try:
            avatar = Image.open(io.BytesIO(avatar_bytes)).convert("RGBA")
        except Exception:
            avatar = None

    if avatar is None:
        avatar = Image.new("RGBA", (AVATAR_SIZE, AVATAR_SIZE), "#E9EEF9")
        draw = ImageDraw.Draw(avatar)
        _draw_rounded_panel(draw, (0, 0, AVATAR_SIZE - 1, AVATAR_SIZE - 1), radius=28, fill="#E9EEF9", outline="#DCE3F4")
        draw.ellipse((56, 34, 164, 142), fill="#C8D4F3")
        draw.rounded_rectangle((44, 126, 176, 214), radius=42, fill="#C8D4F3")
        return avatar

    avatar = avatar.resize((AVATAR_SIZE, AVATAR_SIZE), _resample())
    mask = Image.new("L", (AVATAR_SIZE, AVATAR_SIZE), 0)
    mask_draw = ImageDraw.Draw(mask)
    mask_draw.rounded_rectangle((0, 0, AVATAR_SIZE, AVATAR_SIZE), radius=28, fill=255)
    avatar.putalpha(mask)
    return avatar


def _draw_rounded_panel(
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int, int],
    radius: int,
    fill: str = PANEL_BG,
    outline: str = PANEL_BORDER,
) -> None:
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=1)


def _wrap_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.ImageFont,
    max_width: int,
    max_lines: int | None = None,
) -> list[str]:
    text = str(text or "").strip()
    if not text:
        return [""]

    lines: list[str] = []
    for raw_line in text.splitlines() or [text]:
        current = ""
        for char in raw_line:
            candidate = current + char
            bbox = draw.textbbox((0, 0), candidate, font=font)
            if current and bbox[2] - bbox[0] > max_width:
                lines.append(current)
                current = char
            else:
                current = candidate
        if current:
            lines.append(current)

    if max_lines is not None and len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = lines[-1].rstrip() + "…"
    return lines


def _draw_lines(
    draw: ImageDraw.ImageDraw,
    lines: Iterable[str],
    origin: tuple[int, int],
    font: ImageFont.ImageFont,
    fill: str,
    gap: int,
) -> None:
    x, y = origin
    bbox = draw.textbbox((0, 0), "测试Ag", font=font)
    line_height = bbox[3] - bbox[1] + gap
    for index, line in enumerate(lines):
        draw.text((x, y + index * line_height), line, font=font, fill=fill)


def _image_to_png_bytes(image: Image.Image) -> bytes:
    output = io.BytesIO()
    image.save(output, format="PNG", optimize=True)
    return output.getvalue()


def _resample():
    try:
        return Image.Resampling.LANCZOS
    except AttributeError:
        return Image.LANCZOS
