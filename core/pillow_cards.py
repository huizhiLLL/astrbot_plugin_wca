from __future__ import annotations

import io
import unicodedata
from pathlib import Path
from typing import Iterable

from PIL import Image, ImageDraw, ImageFont

from ..services.wca_pic_template import build_person_card_template_data

ASSETS_DIR = Path(__file__).resolve().parent.parent / "assets"
FONTS_DIR = ASSETS_DIR / "fonts"
DEFAULT_FONT_PATH = FONTS_DIR / "NotoSansSC-Regular.ttf"
SYSTEM_FONT_DIRS = [
    Path("C:/Windows/Fonts"),
    Path("/usr/share/fonts"),
    Path("/usr/local/share/fonts"),
]
FALLBACK_FONT_FILES = {
    "latin": [
        "arial.ttf",
        "tahoma.ttf",
        "DejaVuSans.ttf",
        "LiberationSans-Regular.ttf",
        "NotoSans-Regular.ttf",
    ],
    "thai": [
        "Loma.otf",
        "tahoma.ttf",
        "leelawad.ttf",
        "FreeSans.ttf",
        "NotoSansThai-Regular.ttf",
        "NotoSansThaiUI-Regular.ttf",
        "Garuda.ttf",
    ],
    "korean": [
        "wqy-zenhei.ttc",
        "malgun.ttf",
        "NotoSansKR-Regular.otf",
        "NotoSansCJK-Regular.ttc",
        "NotoSansCJKkr-Regular.ttc",
        "NotoSansCJKkr-Regular.otf",
    ],
    "japanese": [
        "wqy-zenhei.ttc",
        "YuGothR.ttc",
        "meiryo.ttc",
        "NotoSansJP-Regular.otf",
        "NotoSansCJK-Regular.ttc",
        "NotoSansCJKjp-Regular.ttc",
        "NotoSansCJKjp-Regular.otf",
    ],
}

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


class FontBook:
    def __init__(self, font_path: Path | None = None):
        self.font_path = font_path or DEFAULT_FONT_PATH
        self.title = self._stack(40 * SCALE)
        self.subtitle = self._stack(22 * SCALE)
        self.h3 = self._stack(24 * SCALE)
        self.body = self._stack(20 * SCALE)
        self.body_small = self._stack(18 * SCALE)
        self.mono = self._stack(18 * SCALE)
        self.metric = self._stack(30 * SCALE)

    def _load(self, size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
        try:
            return ImageFont.truetype(str(self.font_path), size=size)
        except Exception:
            return ImageFont.load_default()

    def _stack(self, size: int) -> "FontStack":
        return FontStack(
            primary=self._load(size),
            latin=_load_first_available_font(FALLBACK_FONT_FILES["latin"], size),
            thai=_load_first_available_font(FALLBACK_FONT_FILES["thai"], size),
            korean=_load_first_available_font(FALLBACK_FONT_FILES["korean"], size),
            japanese=_load_first_available_font(FALLBACK_FONT_FILES["japanese"], size),
        )


class FontStack:
    def __init__(
        self,
        *,
        primary: ImageFont.FreeTypeFont | ImageFont.ImageFont,
        latin: ImageFont.FreeTypeFont | ImageFont.ImageFont | None,
        thai: ImageFont.FreeTypeFont | ImageFont.ImageFont | None,
        korean: ImageFont.FreeTypeFont | ImageFont.ImageFont | None,
        japanese: ImageFont.FreeTypeFont | ImageFont.ImageFont | None,
    ):
        self.primary = primary
        self.latin = latin or primary
        self.thai = thai or self.latin
        self.korean = korean or primary
        self.japanese = japanese or primary

    def font_for(self, char: str) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
        code = ord(char)
        if 0x0E00 <= code <= 0x0E7F:
            return self.thai
        if (
            0x1100 <= code <= 0x11FF
            or 0x3130 <= code <= 0x318F
            or 0xAC00 <= code <= 0xD7AF
        ):
            return self.korean
        if 0x3040 <= code <= 0x30FF:
            return self.japanese
        if _is_latin_extended(char):
            return self.latin
        return self.primary


def _load_first_available_font(
    filenames: list[str],
    size: int,
) -> ImageFont.FreeTypeFont | ImageFont.ImageFont | None:
    for filename in filenames:
        font_path = _find_system_font(filename)
        if not font_path:
            continue
        try:
            return ImageFont.truetype(str(font_path), size=size)
        except Exception:
            continue
    return None


def _find_system_font(filename: str) -> Path | None:
    target = filename.lower()
    for base_dir in SYSTEM_FONT_DIRS:
        if not base_dir.exists():
            continue
        direct = base_dir / filename
        if direct.exists():
            return direct
        try:
            for path in base_dir.rglob("*"):
                if path.is_file() and path.name.lower() == target:
                    return path
        except OSError:
            continue
    return None


def _is_latin_extended(char: str) -> bool:
    code = ord(char)
    if code <= 0x024F:
        return True
    try:
        return "LATIN" in unicodedata.name(char)
    except ValueError:
        return False


def _text_bbox(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: FontStack | ImageFont.ImageFont,
) -> tuple[int, int, int, int]:
    text = str(text or "")
    if isinstance(font, FontStack):
        width = 0
        top = 0
        bottom = 0
        for run_text, run_font in _iter_font_runs(text, font):
            bbox = draw.textbbox((0, 0), run_text, font=run_font)
            width += bbox[2] - bbox[0]
            top = min(top, bbox[1])
            bottom = max(bottom, bbox[3])
        return (0, top, width, bottom)
    return draw.textbbox((0, 0), text, font=font)


def _text_width(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: FontStack | ImageFont.ImageFont,
) -> int:
    bbox = _text_bbox(draw, text, font)
    return bbox[2] - bbox[0]


def _draw_text(
    draw: ImageDraw.ImageDraw,
    xy: tuple[float, float],
    text: str,
    font: FontStack | ImageFont.ImageFont,
    fill: str,
) -> None:
    text = str(text or "")
    if not isinstance(font, FontStack):
        draw.text(xy, text, font=font, fill=fill)
        return

    x, y = xy
    for run_text, run_font in _iter_font_runs(text, font):
        draw.text((x, y), run_text, font=run_font, fill=fill)
        x += _text_width(draw, run_text, run_font)


def _iter_font_runs(
    text: str,
    font_stack: FontStack,
) -> Iterable[tuple[str, ImageFont.FreeTypeFont | ImageFont.ImageFont]]:
    current_text = ""
    current_font: ImageFont.FreeTypeFont | ImageFont.ImageFont | None = None
    for char in text:
        char_font = font_stack.font_for(char)
        if current_font is not None and char_font is not current_font:
            yield current_text, current_font
            current_text = char
            current_font = char_font
        else:
            current_text += char
            current_font = char_font
    if current_text and current_font is not None:
        yield current_text, current_font


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
    _draw_text(draw, (PADDING_X, title_y), title, fonts.title, TITLE_COLOR)
    _draw_text(draw, (PADDING_X, title_y + 56 * SCALE), subtitle, fonts.subtitle, MUTED_TEXT)

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

        _draw_text(draw, (row_box[0] + 22 * SCALE, row_box[1] + 18 * SCALE), name, fonts.h3, ACCENT)
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
) -> bytes:
    fonts = FontBook()
    data = build_person_card_template_data(records_data)
    rows = list(data.get("rows", []))

    wrap_pad = 40 * SCALE
    meta_header_h = 52 * SCALE
    meta_row_h = 62 * SCALE
    records_header_h = 52 * SCALE
    records_row_h = 46 * SCALE
    section_gap = 40 * SCALE

    rows_count = max(1, len(rows))
    canvas_height = (
        wrap_pad * 2
        + 48 * SCALE
        + 42 * SCALE
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
    name_bbox = _text_bbox(draw, name, fonts.title)
    name_w = name_bbox[2] - name_bbox[0]
    _draw_text(draw, ((CANVAS_WIDTH - name_w) / 2, wrap_top), name, fonts.title, "#222222")

    meta_top = wrap_top + 90 * SCALE
    meta_cols = _columns_from_ratios(
        [
            ("国家/地区", 1),
            ("WCA ID", 1),
            ("性别", 1),
            ("比赛", 1),
            ("复原次数", 1),
        ],
        content_w,
    )
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
    sec_bbox = _text_bbox(draw, section_title, fonts.h3)
    sec_w = sec_bbox[2] - sec_bbox[0]
    _draw_text(draw, ((CANVAS_WIDTH - sec_w) / 2, section_top), section_title, fonts.h3, "#222222")

    records_top = section_top + 44 * SCALE
    record_cols = _columns_from_ratios(
        [
            ("项目", 1.8),
            ("NR", 1),
            ("CR", 1),
            ("WR", 1),
            ("单次", 1),
            ("平均", 1),
            ("WR", 1),
            ("CR", 1),
            ("NR", 1),
        ],
        content_w,
    )
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


def render_wca_nemesis_list_card(
    *,
    person_info: dict,
    person_id: str,
    nemesis_data: dict,
    display_limit: int = 100,
) -> bytes:
    fonts = FontBook()
    rows, truncated = _build_nemesis_rows(nemesis_data, display_limit)

    row_height = 58 * SCALE
    header_height = 58 * SCALE
    top_area = 220 * SCALE
    bottom_padding = 58 * SCALE
    rows_count = max(1, len(rows))
    canvas_height = top_area + header_height + rows_count * row_height + bottom_padding
    image = Image.new("RGB", (CANVAS_WIDTH, canvas_height), CARD_BG)
    draw = ImageDraw.Draw(image)

    _draw_rounded_panel(
        draw,
        (32 * SCALE, 28 * SCALE, CANVAS_WIDTH - 32 * SCALE, canvas_height - 28 * SCALE),
        radius=28 * SCALE,
    )

    person_name = str(person_info.get("name", "未知选手")).strip() or "未知选手"
    country = str(person_info.get("country_iso2", "") or person_info.get("country_id", "")).strip()
    country_text = f" · {country}" if country else ""
    world_count = int(nemesis_data.get("world_count", 0) or 0)
    continent_count = int(nemesis_data.get("continent_count", 0) or 0)
    country_count = int(nemesis_data.get("country_count", 0) or 0)
    title = f"{person_name} 的宿敌列表"
    subtitle = f"{person_id}{country_text}"
    summary = (
        f"世界 {world_count} 人 · 洲 {continent_count} 人 · "
        f"地区 {country_count} 人"
    )
    if truncated:
        summary += f" · 图片最多展示前 {display_limit} 人"

    _draw_text(draw, (PADDING_X, 58 * SCALE), title, fonts.title, TITLE_COLOR)
    _draw_text(draw, (PADDING_X, 116 * SCALE), subtitle, fonts.subtitle, MUTED_TEXT)
    _draw_text(draw, (PADDING_X, 154 * SCALE), summary, fonts.body, TEXT_COLOR)

    table_left = PADDING_X
    table_top = top_area
    table_width = CANVAS_WIDTH - PADDING_X * 2
    columns = _columns_from_ratios(
        [
            ("#", 0.45),
            ("范围", 1.0),
            ("选手", 2.8),
            ("WCA ID", 1.45),
            ("地区", 0.9),
        ],
        table_width,
    )
    _draw_nemesis_table(
        draw,
        table_top,
        table_left,
        columns,
        rows,
        header_height,
        row_height,
        fonts,
    )

    return _image_to_png_bytes(image)


def _columns_from_ratios(
    ratios: list[tuple[str, float]],
    target_width: int,
) -> list[tuple[str, int]]:
    if not ratios:
        return []

    total_ratio = sum(max(0, ratio) for _, ratio in ratios)
    if total_ratio <= 0:
        width, remainder = divmod(target_width, len(ratios))
        return [(title, width + (1 if index < remainder else 0)) for index, (title, _) in enumerate(ratios)]

    raw_widths = [(title, target_width * max(0, ratio) / total_ratio) for title, ratio in ratios]
    widths = [(title, int(width)) for title, width in raw_widths]
    remainder = target_width - sum(width for _, width in widths)
    for index in range(remainder):
        title, width = widths[index % len(widths)]
        widths[index % len(widths)] = (title, width + 1)
    return widths


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
            "left" if index == 0 else "center",
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
            (str(row.get("single_nr", "")), "center", row.get("single_nr_class") == "rank-top"),
            (str(row.get("single_cr", "")), "center", row.get("single_cr_class") == "rank-top"),
            (str(row.get("single_wr", "")), "center", row.get("single_wr_class") == "rank-top"),
            (str(row.get("single_best", "-")), "center", False),
            (str(row.get("avg_best", "-")), "center", False),
            (str(row.get("avg_wr", "")), "center", row.get("avg_wr_class") == "rank-top"),
            (str(row.get("avg_cr", "")), "center", row.get("avg_cr_class") == "rank-top"),
            (str(row.get("avg_nr", "")), "center", row.get("avg_nr_class") == "rank-top"),
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


def _draw_nemesis_table(
    draw: ImageDraw.ImageDraw,
    top: int,
    left: int,
    widths: list[tuple[str, int]],
    rows: list[dict[str, str]],
    header_height: int,
    row_height: int,
    fonts: FontBook,
) -> None:
    x = left
    total_width = sum(width for _, width in widths)
    draw.rounded_rectangle(
        (left, top, left + total_width, top + header_height),
        radius=16 * SCALE,
        fill=TABLE_HEADER_BG,
    )
    for index, (title, width) in enumerate(widths):
        _draw_cell_text(
            draw,
            title,
            (x, top, x + width, top + header_height),
            fonts.body_small,
            TITLE_COLOR,
            "left" if index == 2 else "center",
            pad_x=18 * SCALE,
        )
        x += width

    if not rows:
        _draw_cell_text(
            draw,
            "暂无宿敌",
            (left, top + header_height, left + total_width, top + header_height + row_height),
            fonts.body,
            MUTED_TEXT,
            "center",
        )
        return

    current_top = top + header_height
    for index, row in enumerate(rows):
        fill = TABLE_ALT_BG if index % 2 == 0 else PANEL_BG
        draw.rectangle((left, current_top, left + total_width, current_top + row_height), fill=fill)
        values = [
            str(index + 1),
            row.get("scope", ""),
            row.get("name", ""),
            row.get("wca_id", ""),
            row.get("country_id", ""),
        ]
        x = left
        for col_index, ((_, width), value) in enumerate(zip(widths, values)):
            cell_text = _fit_text_to_width(
                draw,
                value,
                fonts.body_small,
                width - 36 * SCALE,
            )
            _draw_cell_text(
                draw,
                cell_text,
                (x, current_top, x + width, current_top + row_height),
                fonts.body_small,
                ACCENT if col_index == 3 else TEXT_COLOR,
                "left" if col_index == 2 else "center",
                pad_x=18 * SCALE,
            )
            x += width
        draw.line((left, current_top + row_height, left + total_width, current_top + row_height), fill=DIVIDER, width=1 * SCALE)
        current_top += row_height


def _build_nemesis_rows(
    nemesis_data: dict,
    display_limit: int,
) -> tuple[list[dict[str, str]], bool]:
    sources = [
        ("地区", nemesis_data.get("country_list", [])),
        ("洲内其他", nemesis_data.get("continent_list", [])),
        ("世界其他", nemesis_data.get("world_list", [])),
    ]
    rows: list[dict[str, str]] = []
    seen: set[str] = set()

    for scope, people in sources:
        if not isinstance(people, list):
            continue
        for person in people:
            if not isinstance(person, dict):
                continue
            wca_id = str(person.get("wca_id", "")).strip()
            name = str(person.get("name", "")).strip()
            dedupe_key = wca_id or name
            if not dedupe_key or dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            rows.append(
                {
                    "scope": scope,
                    "name": name or "未知",
                    "wca_id": wca_id,
                    "country_id": str(person.get("country_id", "")).strip(),
                }
            )

    limit = max(0, int(display_limit or 0))
    if limit and len(rows) > limit:
        return rows[:limit], True
    return rows, False


def _draw_cell_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    box: tuple[int, int, int, int],
    font: FontStack | ImageFont.ImageFont,
    fill: str,
    align: str,
    pad_x: int = 12,
) -> None:
    x1, y1, x2, y2 = box
    bbox = _text_bbox(draw, text, font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]
    y = y1 + (y2 - y1 - text_h) / 2 - bbox[1]
    if align == "left":
        x = x1 + pad_x
    elif align == "right":
        x = x2 - pad_x - text_w
    else:
        x = x1 + (x2 - x1 - text_w) / 2
    _draw_text(draw, (x, y), text, font, fill)


def _fit_text_to_width(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: FontStack | ImageFont.ImageFont,
    max_width: int,
) -> str:
    text = str(text or "")
    if not text:
        return ""
    if _text_width(draw, text, font) <= max_width:
        return text
    ellipsis = "…"
    current = ""
    for char in text:
        candidate = current + char + ellipsis
        if _text_width(draw, candidate, font) > max_width:
            return current + ellipsis if current else ellipsis
        current += char
    return current


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
    font: FontStack | ImageFont.ImageFont,
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
            if current and _text_width(draw, candidate, font) > max_width:
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
    font: FontStack | ImageFont.ImageFont,
    fill: str,
    gap: int,
) -> None:
    x, y = origin
    bbox = _text_bbox(draw, "测试Ag", font)
    line_height = bbox[3] - bbox[1] + gap
    for index, line in enumerate(lines):
        _draw_text(draw, (x, y + index * line_height), line, font, fill)


def _image_to_png_bytes(image: Image.Image) -> bytes:
    output = io.BytesIO()
    image.save(output, format="PNG", optimize=True)
    return output.getvalue()




