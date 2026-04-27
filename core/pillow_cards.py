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

SCALE = 2

CANVAS_WIDTH = 1280 * SCALE
PADDING_X = 52 * SCALE
PADDING_Y = 42 * SCALE
HELP_CARD_GAP = 22 * SCALE
HELP_ROW_HEIGHT = 118 * SCALE
PERSON_ROW_HEIGHT = 56 * SCALE
PHOTO_WIDTH = 460 * SCALE
PHOTO_HEIGHT = 306 * SCALE


class FontBook:
    def __init__(self, font_path: Path | None = None):
        self.font_path = font_path or DEFAULT_FONT_PATH
        self.title = self._load(40 * SCALE)
        self.subtitle = self._load(22 * SCALE)
        self.h3 = self._load(24 * SCALE)
        self.body = self._load(20 * SCALE)
        self.body_small = self._load(18 * SCALE)
        self.mono = self._load(18 * SCALE)
        self.metric = self._load(30 * SCALE)

    def _load(self, size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
        try:
            return ImageFont.truetype(str(self.font_path), size=size)
        except Exception:
            return ImageFont.load_default()


def render_cube_help_card(data: dict[str, object]) -> bytes:
    fonts = FontBook()
    commands = list(data.get("commands", []))
    canvas_height = max(680 * SCALE, 240 * SCALE + max(1, len(commands)) * HELP_ROW_HEIGHT)
    image = Image.new("RGB", (CANVAS_WIDTH, canvas_height), CARD_BG)
    draw = ImageDraw.Draw(image)

    _draw_rounded_panel(draw, (32 * SCALE, 28 * SCALE, CANVAS_WIDTH - 32 * SCALE, canvas_height - 28 * SCALE), radius=28 * SCALE)

    title = str(data.get("title", "Cube 命令帮助"))
    subtitle = str(data.get("subtitle", ""))
    title_y = 56 * SCALE
    draw.text((PADDING_X, title_y), title, font=fonts.title, fill=TITLE_COLOR)
    draw.text((PADDING_X, title_y + 56 * SCALE), subtitle, font=fonts.subtitle, fill=MUTED_TEXT)

    top = 148 * SCALE
    content_width = CANVAS_WIDTH - PADDING_X * 2
    for index, command in enumerate(commands):
        if not isinstance(command, dict):
            continue
        row_top = top + index * HELP_ROW_HEIGHT
        row_box = (
            PADDING_X,
            row_top,
            PADDING_X + content_width,
            row_top + HELP_ROW_HEIGHT - 14 * SCALE,
        )
        fill = TABLE_ALT_BG if index % 2 == 0 else PANEL_BG
        _draw_rounded_panel(draw, row_box, radius=20 * SCALE, fill=fill, outline=PANEL_BORDER)

        name = str(command.get("name", ""))
        desc = str(command.get("desc", ""))
        example = str(command.get("example", ""))

        draw.text((row_box[0] + 22 * SCALE, row_box[1] + 18 * SCALE), name, font=fonts.h3, fill=ACCENT)
        desc_lines = _wrap_text(draw, desc, fonts.body, max_width=420 * SCALE, max_lines=2)
        example_lines = _wrap_text(draw, example, fonts.body_small, max_width=520 * SCALE, max_lines=2)

        _draw_lines(draw, desc_lines, (row_box[0] + 220 * SCALE, row_box[1] + 16 * SCALE), fonts.body, TEXT_COLOR, 10 * SCALE)
        _draw_lines(
            draw,
            [f"示例：{line}" if i == 0 else f"      {line}" for i, line in enumerate(example_lines)],
            (row_box[0] + 220 * SCALE, row_box[1] + 50 * SCALE),
            fonts.body_small,
            MUTED_TEXT,
            8 * SCALE,
        )

    return _image_to_png_bytes(image)


def render_wca_person_card(
    records_data: dict,
    avatar_bytes: bytes | None = None,
) -> bytes:
    fonts = FontBook()
    data = build_person_card_template_data(records_data)
    rows = list(data.get("rows", []))

    wrap_pad = 40 * SCALE
    inner_pad = 40 * SCALE
    meta_header_h = 52 * SCALE
    meta_row_h = 62 * SCALE
    records_header_h = 52 * SCALE
    records_row_h = 46 * SCALE
    section_gap = 40 * SCALE

    rows_count = max(1, len(rows))
    canvas_height = (
        wrap_pad * 2
        + 48 * SCALE
        + 30 * SCALE
        + PHOTO_HEIGHT
        + 30 * SCALE
        + meta_header_h
        + meta_row_h
        + section_gap
        + 32 * SCALE
        + 24 * SCALE
        + records_header_h
        + rows_count * records_row_h
    )
    image = Image.new("RGB", (CANVAS_WIDTH, canvas_height), "#FFFFFF")
    draw = ImageDraw.Draw(image)

    wrap_left = wrap_pad
    wrap_top = wrap_pad
    wrap_right = CANVAS_WIDTH - wrap_pad
    content_w = wrap_right - wrap_left

    name = str(data.get("name", "未知"))
    name_bbox = draw.textbbox((0, 0), name, font=fonts.title)
    name_w = name_bbox[2] - name_bbox[0]
    draw.text(((CANVAS_WIDTH - name_w) / 2, wrap_top), name, font=fonts.title, fill="#222222")

    avatar_top = wrap_top + 48 * SCALE
    avatar = _prepare_photo(avatar_bytes, old_style=True)
    avatar_x = (CANVAS_WIDTH - PHOTO_WIDTH) // 2
    image.paste(avatar, (avatar_x, avatar_top), avatar)

    meta_top = avatar_top + PHOTO_HEIGHT + 30 * SCALE
    meta_cols = [
        ("国家/地区", 260 * SCALE),
        ("WCA ID", 270 * SCALE),
        ("性别", 140 * SCALE),
        ("比赛", 160 * SCALE),
        ("复原次数", 210 * SCALE),
    ]
    meta_cols = _expand_columns_to_width(meta_cols, content_w)
    meta_values = [
        f"{str(data.get('flag_text', '')).strip()} {str(data.get('country_name', '-')).strip()}".strip(),
        str(data.get("wca_id", "-")),
        str(data.get("gender", "-")),
        str(data.get("competition_count", "-")),
        str(data.get("total_solves", "-")),
    ]
    _draw_simple_table(
        draw,
        top=meta_top,
        left=wrap_left,
        widths=meta_cols,
        row_values=meta_values,
        header_height=meta_header_h,
        row_height=meta_row_h,
        header_bg="#F4F4F4",
        alt_bg="#FFFFFF",
        text_fill="#222222",
        header_fill="#333333",
        body_font=fonts.body_small,
        header_font=fonts.body_small,
        alignments=["center"] * len(meta_cols),
        zebra=False,
    )

    section_title = "当前个人记录"
    section_top = meta_top + meta_header_h + meta_row_h + section_gap
    sec_bbox = draw.textbbox((0, 0), section_title, font=fonts.h3)
    sec_w = sec_bbox[2] - sec_bbox[0]
    draw.text(((CANVAS_WIDTH - sec_w) / 2, section_top), section_title, font=fonts.h3, fill="#222222")

    records_top = section_top + 44 * SCALE
    record_cols = [
        ("项目", 260 * SCALE),
        ("NR", 82 * SCALE),
        ("CR", 82 * SCALE),
        ("WR", 82 * SCALE),
        ("单次", 170 * SCALE),
        ("平均", 170 * SCALE),
        ("WR", 82 * SCALE),
        ("CR", 82 * SCALE),
        ("NR", 82 * SCALE),
    ]
    record_cols = _expand_columns_to_width(record_cols, content_w, grow_indices=[0, 4, 5])
    _draw_records_table(
        draw,
        top=records_top,
        left=wrap_left,
        widths=record_cols,
        rows=rows,
        header_height=records_header_h,
        row_height=records_row_h,
        fonts=fonts,
    )

    return _image_to_png_bytes(image)


def _prepare_photo(avatar_bytes: bytes | None, old_style: bool = False) -> Image.Image:
    photo = None
    if avatar_bytes:
        try:
            photo = Image.open(io.BytesIO(avatar_bytes)).convert("RGBA")
        except Exception:
            photo = None

    if photo is None:
        photo = Image.new("RGBA", (PHOTO_WIDTH, PHOTO_HEIGHT), "#F5F5F5" if old_style else "#E9EEF9")
        draw = ImageDraw.Draw(photo)
        radius = 4 * SCALE if old_style else 28 * SCALE
        fill = "#F5F5F5" if old_style else "#E9EEF9"
        draw.rounded_rectangle((0, 0, PHOTO_WIDTH - 1, PHOTO_HEIGHT - 1), radius=radius, fill=fill)
        if not old_style:
            cx = PHOTO_WIDTH // 2
            draw.ellipse((cx - 54 * SCALE, 64 * SCALE, cx + 54 * SCALE, 172 * SCALE), fill="#C8D4F3")
            draw.rounded_rectangle((cx - 90 * SCALE, 182 * SCALE, cx + 90 * SCALE, 330 * SCALE), radius=42 * SCALE, fill="#C8D4F3")
        return photo

    photo = _resize_to_cover(photo, PHOTO_WIDTH, PHOTO_HEIGHT)
    canvas = Image.new("RGBA", (PHOTO_WIDTH, PHOTO_HEIGHT), (245, 245, 245, 255) if old_style else (233, 238, 249, 255))
    px = (PHOTO_WIDTH - photo.width) // 2
    py = (PHOTO_HEIGHT - photo.height) // 2
    canvas.paste(photo, (px, py), photo)
    mask = Image.new("L", (PHOTO_WIDTH, PHOTO_HEIGHT), 0)
    mask_draw = ImageDraw.Draw(mask)
    mask_draw.rounded_rectangle((0, 0, PHOTO_WIDTH, PHOTO_HEIGHT), radius=(4 if old_style else 28) * SCALE, fill=255)
    canvas.putalpha(mask)
    return canvas


def _resize_to_cover(image: Image.Image, target_width: int, target_height: int) -> Image.Image:
    width_ratio = target_width / image.width
    height_ratio = target_height / image.height
    scale = max(width_ratio, height_ratio)
    resized = image.resize(
        (max(1, round(image.width * scale)), max(1, round(image.height * scale))),
        _resample(),
    )
    left = max(0, (resized.width - target_width) // 2)
    top = max(0, (resized.height - target_height) // 2)
    return resized.crop((left, top, left + target_width, top + target_height))


def _expand_columns_to_width(
    widths: list[tuple[str, int]],
    target_width: int,
    grow_indices: list[int] | None = None,
) -> list[tuple[str, int]]:
    current_width = sum(width for _, width in widths)
    if current_width >= target_width or not widths:
        return widths

    expanded = list(widths)
    indices = grow_indices or list(range(len(expanded)))
    valid_indices = [index for index in indices if 0 <= index < len(expanded)]
    if not valid_indices:
        valid_indices = [len(expanded) - 1]

    extra = target_width - current_width
    base_extra, remainder = divmod(extra, len(valid_indices))
    for offset, index in enumerate(valid_indices):
        title, width = expanded[index]
        expanded[index] = (title, width + base_extra + (1 if offset < remainder else 0))
    return expanded


def _draw_simple_table(
    draw: ImageDraw.ImageDraw,
    top: int,
    left: int,
    widths: list[tuple[str, int]],
    row_values: list[str],
    header_height: int,
    row_height: int,
    header_bg: str,
    alt_bg: str,
    text_fill: str,
    header_fill: str,
    body_font: ImageFont.ImageFont,
    header_font: ImageFont.ImageFont,
    alignments: list[str],
    zebra: bool,
) -> None:
    x = left
    for index, ((title, width), value) in enumerate(zip(widths, row_values)):
        draw.rectangle((x, top, x + width, top + header_height), fill=header_bg)
        _draw_cell_text(draw, title, (x, top, x + width, top + header_height), header_font, header_fill, alignments[index])
        draw.rectangle((x, top + header_height, x + width, top + header_height + row_height), fill=alt_bg)
        _draw_cell_text(draw, value, (x, top + header_height, x + width, top + header_height + row_height), body_font, text_fill, alignments[index])
        x += width


def _draw_records_table(
    draw: ImageDraw.ImageDraw,
    top: int,
    left: int,
    widths: list[tuple[str, int]],
    rows: list[dict],
    header_height: int,
    row_height: int,
    fonts: FontBook,
) -> None:
    x = left
    for index, (title, width) in enumerate(widths):
        _draw_cell_text(
            draw,
            title,
            (x, top, x + width, top + header_height),
            fonts.body_small,
            "#333333",
            "left" if index == 0 else "right",
            pad_x=20 * SCALE if index == 0 else 10 * SCALE,
        )
        x += width
    draw.line((left, top + header_height, left + sum(width for _, width in widths), top + header_height), fill="#E0E0E0", width=2 * SCALE)

    if not rows:
        _draw_cell_text(
            draw,
            "暂无有效成绩记录",
            (left, top + header_height, left + sum(width for _, width in widths), top + header_height + row_height),
            fonts.body,
            "#777777",
            "center",
        )
        return

    current_top = top + header_height
    for idx, row in enumerate(rows):
        bg = "#F6F6F6" if idx % 2 == 0 else "#FFFFFF"
        draw.rectangle((left, current_top, left + sum(width for _, width in widths), current_top + row_height), fill=bg)
        values = [
            (str(row.get("event_name", "-")), "left", False),
            (str(row.get("single_nr", "")), "right", row.get("single_nr_class") == "rank-top"),
            (str(row.get("single_cr", "")), "right", row.get("single_cr_class") == "rank-top"),
            (str(row.get("single_wr", "")), "right", row.get("single_wr_class") == "rank-top"),
            (str(row.get("single_best", "-")), "right", False),
            (str(row.get("avg_best", "-")), "right", False),
            (str(row.get("avg_wr", "")), "right", row.get("avg_wr_class") == "rank-top"),
            (str(row.get("avg_cr", "")), "right", row.get("avg_cr_class") == "rank-top"),
            (str(row.get("avg_nr", "")), "right", row.get("avg_nr_class") == "rank-top"),
        ]
        x = left
        for col_index, ((_, width), (text, align, is_top)) in enumerate(zip(widths, values)):
            font = fonts.body_small if col_index not in (4, 5) else fonts.body_small
            fill = "#00DE00" if is_top and text else ("#111111" if col_index in (4, 5) else ("#777777" if col_index in (1,2,3,6,7,8) else "#333333"))
            _draw_cell_text(
                draw,
                text,
                (x, current_top, x + width, current_top + row_height),
                font,
                fill,
                align,
                pad_x=20 * SCALE if align == "left" else 10 * SCALE,
            )
            x += width
        current_top += row_height


def _draw_cell_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    box: tuple[int, int, int, int],
    font: ImageFont.ImageFont,
    fill: str,
    align: str,
    pad_x: int = 12,
) -> None:
    x1, y1, x2, y2 = box
    bbox = draw.textbbox((0, 0), text, font=font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]
    y = y1 + (y2 - y1 - text_h) / 2 - bbox[1]
    if align == "left":
        x = x1 + pad_x
    elif align == "right":
        x = x2 - pad_x - text_w
    else:
        x = x1 + (x2 - x1 - text_w) / 2
    draw.text((x, y), text, font=font, fill=fill)


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
