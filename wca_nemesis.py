import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

# 国家到洲映射（ISO-2 -> 大洲）
# 数据源：WCA 国家列表常规划分；若缺省则记为 "UNKNOWN"
COUNTRY_TO_CONTINENT: Dict[str, str] = {
    # 非洲
    "DZ": "Africa", "AO": "Africa", "BJ": "Africa", "BW": "Africa", "BF": "Africa",
    "BI": "Africa", "CM": "Africa", "CV": "Africa", "CF": "Africa", "TD": "Africa",
    "KM": "Africa", "CG": "Africa", "CD": "Africa", "DJ": "Africa", "EG": "Africa",
    "GQ": "Africa", "ER": "Africa", "SZ": "Africa", "ET": "Africa", "GA": "Africa",
    "GM": "Africa", "GH": "Africa", "GN": "Africa", "GW": "Africa", "CI": "Africa",
    "KE": "Africa", "LS": "Africa", "LR": "Africa", "LY": "Africa", "MG": "Africa",
    "MW": "Africa", "ML": "Africa", "MR": "Africa", "MU": "Africa", "YT": "Africa",
    "MA": "Africa", "MZ": "Africa", "NA": "Africa", "NE": "Africa", "NG": "Africa",
    "RE": "Africa", "RW": "Africa", "ST": "Africa", "SN": "Africa", "SC": "Africa",
    "SL": "Africa", "SO": "Africa", "ZA": "Africa", "SS": "Africa", "SD": "Africa",
    "TZ": "Africa", "TG": "Africa", "TN": "Africa", "UG": "Africa", "EH": "Africa",
    "ZM": "Africa", "ZW": "Africa",
    # 亚洲
    "AF": "Asia", "AM": "Asia", "AZ": "Asia", "BH": "Asia", "BD": "Asia",
    "BT": "Asia", "BN": "Asia", "KH": "Asia", "CN": "Asia", "CY": "Asia",
    "GE": "Asia", "HK": "Asia", "IN": "Asia", "ID": "Asia", "IR": "Asia",
    "IQ": "Asia", "IL": "Asia", "JP": "Asia", "JO": "Asia", "KZ": "Asia",
    "KW": "Asia", "KG": "Asia", "LA": "Asia", "LB": "Asia", "MO": "Asia",
    "MY": "Asia", "MV": "Asia", "MN": "Asia", "MM": "Asia", "NP": "Asia",
    "KP": "Asia", "OM": "Asia", "PK": "Asia", "PS": "Asia", "PH": "Asia",
    "QA": "Asia", "SA": "Asia", "SG": "Asia", "KR": "Asia", "LK": "Asia",
    "SY": "Asia", "TW": "Asia", "TJ": "Asia", "TH": "Asia", "TR": "Asia",
    "TM": "Asia", "AE": "Asia", "UZ": "Asia", "VN": "Asia", "YE": "Asia",
    # 欧洲
    "AL": "Europe", "AD": "Europe", "AT": "Europe", "BY": "Europe", "BE": "Europe",
    "BA": "Europe", "BG": "Europe", "HR": "Europe", "CZ": "Europe", "DK": "Europe",
    "EE": "Europe", "FI": "Europe", "FR": "Europe", "DE": "Europe", "GR": "Europe",
    "HU": "Europe", "IS": "Europe", "IE": "Europe", "IT": "Europe", "XK": "Europe",
    "LV": "Europe", "LI": "Europe", "LT": "Europe", "LU": "Europe", "MT": "Europe",
    "MD": "Europe", "MC": "Europe", "ME": "Europe", "NL": "Europe", "MK": "Europe",
    "NO": "Europe", "PL": "Europe", "PT": "Europe", "RO": "Europe", "RU": "Europe",
    "SM": "Europe", "RS": "Europe", "SK": "Europe", "SI": "Europe", "ES": "Europe",
    "SE": "Europe", "CH": "Europe", "UA": "Europe", "GB": "Europe", "VA": "Europe",
    # 北美（含中美、加勒比）
    "AG": "North America", "BS": "North America", "BB": "North America", "BZ": "North America",
    "BM": "North America", "CA": "North America", "KY": "North America", "CR": "North America",
    "CU": "North America", "DM": "North America", "DO": "North America", "SV": "North America",
    "GL": "North America", "GD": "North America", "GT": "North America", "HT": "North America",
    "HN": "North America", "JM": "North America", "MX": "North America", "NI": "North America",
    "PA": "North America", "PR": "North America", "KN": "North America", "LC": "North America",
    "VC": "North America", "TT": "North America", "US": "North America",
    # 南美
    "AR": "South America", "BO": "South America", "BR": "South America", "CL": "South America",
    "CO": "South America", "EC": "South America", "GY": "South America", "PY": "South America",
    "PE": "South America", "SR": "South America", "UY": "South America", "VE": "South America",
    # 大洋洲
    "AS": "Oceania", "AU": "Oceania", "CK": "Oceania", "FJ": "Oceania", "PF": "Oceania",
    "GU": "Oceania", "KI": "Oceania", "MH": "Oceania", "FM": "Oceania", "NR": "Oceania",
    "NC": "Oceania", "NZ": "Oceania", "MP": "Oceania", "PW": "Oceania", "PG": "Oceania",
    "WS": "Oceania", "SB": "Oceania", "TO": "Oceania", "TV": "Oceania", "VU": "Oceania",
}


class NemesisService:
    """宿敌查询：找出所有项目单次&平均均优于目标的选手"""

    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        if not self.db_path.exists():
            raise FileNotFoundError(f"WCA 数据库不存在: {db_path}")
        self._ensure_indexes()

    def _ensure_indexes(self) -> None:
        conn = self._get_conn()
        try:
            c = conn.cursor()
            c.execute(
                "CREATE INDEX IF NOT EXISTS idx_rankssingle_event_best ON ranks_single(event_id, best)"
            )
            c.execute(
                "CREATE INDEX IF NOT EXISTS idx_ranksaverage_event_best ON ranks_average(event_id, best)"
            )
            c.execute(
                "CREATE INDEX IF NOT EXISTS idx_rankssingle_event_best_person ON ranks_single(event_id, best, person_id)"
            )
            c.execute(
                "CREATE INDEX IF NOT EXISTS idx_ranksaverage_event_best_person ON ranks_average(event_id, best, person_id)"
            )
            conn.commit()
        finally:
            conn.close()

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _get_target_records(self, person_id: str) -> Tuple[Dict[str, int], Dict[str, int], str]:
        """返回目标选手的最佳单次/平均映射，以及国家代码

        不再强制要求同一项目同时存在单次和平均，后续过滤时按各自存在的指标逐项比较。
        """
        conn = self._get_conn()
        try:
            c = conn.cursor()
            c.execute("SELECT country_id FROM persons WHERE wca_id = ?", (person_id,))
            row = c.fetchone()
            country = row["country_id"] if row else ""

            c.execute(
                "SELECT event_id, best FROM ranks_single WHERE person_id = ? AND best > 0",
                (person_id,),
            )
            single = {r["event_id"]: r["best"] for r in c.fetchall()}

            c.execute(
                "SELECT event_id, best FROM ranks_average WHERE person_id = ? AND best > 0",
                (person_id,),
            )
            average = {r["event_id"]: r["best"] for r in c.fetchall()}

            return single, average, country
        finally:
            conn.close()

    def _filter_better_players(
        self, single: Dict[str, int], average: Dict[str, int]
    ) -> Set[str]:
        """找出在所有这些项目的单次/平均均优于目标的 personId

        逻辑放宽：每个项目只比对目标实际拥有的指标。
        - 若目标仅有单次，则要求候选单次更好；
        - 若目标仅有平均，则要求候选平均更好；
        - 若同时有单次与平均，则两者都需更好。
        """
        if not single and not average:
            return set()

        # 统一收集所有出现的项目，逐项目做交集过滤
        events: list[Tuple[str, int | None, int | None]] = []
        all_events = set(single.keys()) | set(average.keys())
        for ev in all_events:
            events.append((ev, single.get(ev), average.get(ev)))
        # 为了收敛更快，按数值较小的指标排序（None 视为大值）
        def _sort_key(item: Tuple[str, int | None, int | None]):
            _, s_val, a_val = item
            s_sort = s_val if s_val is not None else 10**9
            a_sort = a_val if a_val is not None else 10**9
            return (min(s_sort, a_sort), s_sort, a_sort)
        events.sort(key=_sort_key)

        conn = self._get_conn()
        try:
            c = conn.cursor()
            candidates: Set[str] | None = None
            total = len(events)
            fetch_size = 10000

            sql_single = """
                SELECT person_id
                FROM ranks_single
                WHERE event_id = ?
                  AND best > 0
                  AND best < ?
            """

            sql_average = """
                SELECT person_id
                FROM ranks_average
                WHERE event_id = ?
                  AND best > 0
                  AND best < ?
            """

            def _fetch_set() -> Set[str]:
                out: Set[str] = set()
                while True:
                    rows = c.fetchmany(fetch_size)
                    if not rows:
                        break
                    for row in rows:
                        out.add(row[0])
                return out

            for idx, (ev, s_val, a_val) in enumerate(events, start=1):
                if s_val is None and a_val is None:
                    continue  # 没有任何指标可比

                ev_set: Set[str] | None = None

                if s_val is not None:
                    c.execute(sql_single, (ev, s_val))
                    single_set = _fetch_set()
                    ev_set = single_set if ev_set is None else ev_set & single_set

                if a_val is not None:
                    c.execute(sql_average, (ev, a_val))
                    average_set = _fetch_set()
                    ev_set = average_set if ev_set is None else ev_set & average_set

                if ev_set is None:
                    continue

                if candidates is None:
                    candidates = ev_set
                else:
                    candidates &= ev_set

                if not candidates:
                    break

            return candidates or set()
        finally:
            conn.close()

    def _get_people(self, ids: Set[str]) -> List[Dict[str, Any]]:
        if not ids:
            return []
        conn = self._get_conn()
        try:
            c = conn.cursor()
            placeholders = ",".join(["?"] * len(ids))
            c.execute(
                f"SELECT wca_id, name, country_id FROM persons WHERE wca_id IN ({placeholders})",
                tuple(ids),
            )
            return [dict(r) for r in c.fetchall()]
        finally:
            conn.close()

    def _get_country_continent_map(self, country_ids: Set[str]) -> Dict[str, str]:
        if not country_ids:
            return {}
        conn = self._get_conn()
        try:
            c = conn.cursor()
            placeholders = ",".join(["?"] * len(country_ids))
            c.execute(
                f"SELECT id, continent_id FROM countries WHERE id IN ({placeholders})",
                tuple(country_ids),
            )
            return {row["id"]: row["continent_id"] for row in c.fetchall()}
        except sqlite3.Error:
            return {}
        finally:
            conn.close()

    def query(self, person_id: str) -> Tuple[str, int, int, int, List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
        """返回 (continent, world_count, continent_count, country_count, world_list, continent_list, country_list)"""
        single, average, country = self._get_target_records(person_id)
        better_ids = self._filter_better_players(single, average)
        people = self._get_people(better_ids)

        country_ids: Set[str] = set()
        for p in people:
            country_id = p.get("country_id")
            if country_id and isinstance(country_id, str):
                country_ids.add(country_id)
        if country:
            country_ids.add(country)
        country_continent = self._get_country_continent_map(country_ids)

        target_continent = country_continent.get(country) or COUNTRY_TO_CONTINENT.get(country, "UNKNOWN")

        world_list = people
        continent_list = []
        for p in people:
            p_country_id = p.get("country_id")
            if p_country_id and isinstance(p_country_id, str):
                p_continent = country_continent.get(p_country_id) or COUNTRY_TO_CONTINENT.get(p_country_id, "UNKNOWN")
                if p_continent == target_continent:
                    continent_list.append(p)
        country_list = [p for p in people if p.get("country_id") == country]

        return (
            target_continent,
            len(world_list),
            len(continent_list),
            len(country_list),
            world_list,
            continent_list,
            country_list,
        )

