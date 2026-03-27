from typing import Any


# API 项目ID到显示名称的映射（API 返回的是简化的项目ID）
EVENT_ID_MAP: dict[str, str] = {
    "222": "222",
    "333": "333",
    "444": "444",
    "555": "555",
    "666": "666",
    "777": "777",
    "333bf": "333bf",
    "333fm": "333fm",
    "333oh": "333oh",
    "clock": "clock",
    "minx": "minx",
    "pyram": "py",
    "skewb": "sk",
    "sq1": "sq1",
    "444bf": "444bf",
    "555bf": "555bf",
    "333mbf": "333mbf",
    "333ft": "333ft",
}

# 项目ID到格式的映射（用于格式化时间）
EVENT_FORMAT_MAP: dict[str, str] = {
    "222": "time",
    "333": "time",
    "444": "time",
    "555": "time",
    "666": "time",
    "777": "time",
    "333bf": "time",
    "333fm": "number",
    "333oh": "time",
    "clock": "time",
    "minx": "time",
    "pyram": "time",
    "skewb": "time",
    "sq1": "time",
    "444bf": "time",
    "555bf": "time",
    "333mbf": "multi",
    "333ft": "time",
}

# 项目排序顺序（用于在没有 event_rank 时排序）
EVENT_ORDER: dict[str, int] = {
    "222": 1,
    "333": 2,
    "444": 3,
    "555": 4,
    "666": 5,
    "777": 6,
    "333bf": 7,
    "333fm": 8,
    "333oh": 9,
    "clock": 10,
    "minx": 11,
    "pyram": 12,
    "skewb": 13,
    "sq1": 14,
    "444bf": 15,
    "555bf": 16,
    "333mbf": 17,
    "333ft": 18,
}


def format_wca_time(centiseconds: int, event_format: str = "time") -> str:
    """格式化 WCA 时间（厘秒转换为可读格式）"""
    if centiseconds == -1:
        return "DNF"
    if centiseconds == -2:
        return "DNS"
    if centiseconds == 0:
        return "-"

    if event_format == "multi":
        return format_multi_blind(centiseconds)

    if event_format == "number":
        if centiseconds >= 100:
            return f"{centiseconds / 100:.2f}"
        return str(centiseconds)

    total_cs = int(centiseconds)
    minutes = total_cs // 6000
    sec_cs = total_cs % 6000
    seconds = sec_cs // 100
    cs = sec_cs % 100

    if minutes > 0:
        return f"{minutes}:{seconds:02d}.{cs:02d}"
    return f"{seconds}.{cs:02d}"


def format_multi_blind(value: int) -> str:
    """格式化多盲成绩，格式：solved/attempted time"""
    value_str = str(value).zfill(10)

    if value_str[0] == "1":
        ss = int(value_str[1:3])
        aa = int(value_str[3:5])
        ttttt = int(value_str[5:10])

        solved = 99 - ss
        attempted = aa
        time_seconds = ttttt if ttttt != 99999 else None
    else:
        dd = int(value_str[1:3])
        ttttt = int(value_str[3:8])
        mm = int(value_str[8:10])

        difference = 99 - dd
        missed = mm
        solved = difference + missed
        attempted = solved + missed
        time_seconds = ttttt if ttttt != 99999 else None

    if time_seconds is None:
        return f"{solved}/{attempted} (时间未知)"

    hours = time_seconds // 3600
    minutes = (time_seconds % 3600) // 60
    seconds = time_seconds % 60

    if hours > 0:
        time_str = f"{hours}:{minutes:02d}:{seconds:02d}"
    else:
        time_str = f"{minutes}:{seconds:02d}"

    return f"{solved}/{attempted} {time_str}"


def format_person_records_text(records_data: dict[str, Any]) -> str:
    person = records_data["person"]
    person_name = person.get("name", "未知")
    person_id = person.get("wca_id", "")
    country = person.get("country_id", "")

    header_lines = [str(person.get("name", person_name))]
    gender = person.get("gender", "")
    gender_str = ""
    if gender:
        gender_str = "Male" if str(gender).lower().startswith("m") else "Female"
    header_lines.append(", ".join([person_id, country or "-", gender_str or "-"]))
    header = "\n".join(header_lines) + "\n\n"

    single_records = records_data["single_records"]
    average_records = records_data["average_records"]

    single_map = {r["event_id"]: r for r in single_records}
    average_map = {r["event_id"]: r for r in average_records}
    all_event_ids = set(single_map.keys()) | set(average_map.keys())

    if not all_event_ids:
        return f"{header}\n还没有 WCA 成绩记录呢，快去参加比赛吧~"

    event_records: list[tuple[int, str, dict[str, Any] | None, dict[str, Any] | None]] = []
    for event_id in all_event_ids:
        single = single_map.get(event_id)
        average = average_map.get(event_id)
        rank = 999
        if single:
            rank = single.get("event_rank", 999)
        elif average:
            rank = average.get("event_rank", 999)
        event_records.append((rank, event_id, single, average))

    event_records.sort(key=lambda x: x[0])

    lines: list[str] = []
    for _, event_id, single, average in event_records:
        event_name = ""
        event_format = "time"

        if single:
            event_name = single.get("event_name", event_id)
            event_format = single.get("event_format", "time")
        elif average:
            event_name = average.get("event_name", event_id)
            event_format = average.get("event_format", "time")

        if not event_name:
            event_name = event_id

        single_time = "-"
        single_rank = "-"
        if single:
            best = single.get("best", 0)
            single_time = format_wca_time(best, event_format)
            single_rank = _rank_label(
                single.get("world_rank", 0),
                single.get("continent_rank", 0),
                single.get("country_rank", 0),
            )

        avg_time = "-"
        avg_rank = "-"
        if average:
            best = average.get("best", 0)
            avg_time = format_wca_time(best, event_format)
            avg_rank = _rank_label(
                average.get("world_rank", 0),
                average.get("continent_rank", 0),
                average.get("country_rank", 0),
            )

        if single_time == "-" and avg_time == "-":
            continue

        line = f"{event_name}  {single_time}"
        if single_rank != "-":
            line += f" ({single_rank})"
        line += "  ||  "
        line += avg_time
        if avg_rank != "-":
            line += f" ({avg_rank})"
        lines.append(line)

    if not lines:
        return f"{header}\n还没有有效的成绩记录哦，再接再厉呀~"

    return header + "\n".join(lines)


def _rank_label(world_rank: object, continent_rank: object, country_rank: object) -> str:
    if isinstance(country_rank, int) and country_rank <= 200 and country_rank > 0:
        if country_rank == 1:
            return "NR"
        return f"NR{country_rank}"
    return "-"
