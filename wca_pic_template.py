from functools import lru_cache
from pathlib import Path

from .wca_query import format_wca_time


TEMPLATE_PATH = Path(__file__).with_name("templates").joinpath("person_card.html")

EVENT_CN_MAP: dict[str, str] = {
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


@lru_cache(maxsize=1)
def get_person_card_template() -> str:
    return TEMPLATE_PATH.read_text(encoding="utf-8")


def build_person_card_template_data(records_data: dict) -> dict:
    person = records_data.get("person") or {}
    country_iso2 = (person.get("country_iso2") or person.get("country_id") or "").upper()
    country_name = person.get("country_name") or country_iso2 or "-"

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

        event_name = EVENT_CN_MAP.get(
            str(event_id),
            s.get("event_name") or a.get("event_name") or str(event_id),
        )

        single_nr_val = s.get("country_rank") if isinstance(s, dict) else 0
        single_cr_val = s.get("continent_rank") if isinstance(s, dict) else 0
        single_wr_val = s.get("world_rank") if isinstance(s, dict) else 0
        avg_wr_val = a.get("world_rank") if isinstance(a, dict) else 0
        avg_cr_val = a.get("continent_rank") if isinstance(a, dict) else 0
        avg_nr_val = a.get("country_rank") if isinstance(a, dict) else 0

        rows.append(
            {
                "event_name": event_name,
                "single_nr": _rank_text(single_nr_val),
                "single_nr_class": _rank_class(single_nr_val),
                "single_cr": _rank_text(single_cr_val),
                "single_cr_class": _rank_class(single_cr_val),
                "single_wr": _rank_text(single_wr_val),
                "single_wr_class": _rank_class(single_wr_val),
                "single_best": single_best,
                "avg_best": avg_best,
                "avg_wr": _rank_text(avg_wr_val),
                "avg_wr_class": _rank_class(avg_wr_val),
                "avg_cr": _rank_text(avg_cr_val),
                "avg_cr_class": _rank_class(avg_cr_val),
                "avg_nr": _rank_text(avg_nr_val),
                "avg_nr_class": _rank_class(avg_nr_val),
            }
        )

    competition_count = records_data.get("competition_count")
    total_solves = records_data.get("total_solves")

    return {
        "name": person.get("name") or "未知",
        "avatar_url": person.get("avatar_thumb_url") or "",
        "flag_text": _flag_text(country_iso2),
        "country_name": country_name,
        "wca_id": person.get("wca_id") or "-",
        "gender": _gender_cn(person.get("gender", "")),
        "competition_count": competition_count if isinstance(competition_count, int) else "-",
        "total_solves": total_solves if isinstance(total_solves, int) else "-",
        "rows": rows,
    }


def format_person_records_for_pic(records_data: dict) -> str:
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


def _gender_cn(gender: str) -> str:
    gender = str(gender or "").lower()
    if gender.startswith("m"):
        return "男"
    if gender.startswith("f"):
        return "女"
    if gender:
        return "其他"
    return "-"


def _rank_text(value: object) -> str:
    if isinstance(value, int) and value > 0:
        return str(value)
    return ""


def _rank_class(value: object) -> str:
    if isinstance(value, int) and 0 < value < 100:
        return "rank-top"
    return ""


def _flag_text(iso2: str) -> str:
    iso2 = iso2.strip().upper()
    if iso2 == "CN":
        return "🇨🇳"
    if len(iso2) == 2 and iso2.isalpha():
        return f"[{iso2}]"
    return ""
