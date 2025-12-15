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
                "CREATE INDEX IF NOT EXISTS idx_rankssingle_event_best ON RanksSingle(eventId, best)"
            )
            c.execute(
                "CREATE INDEX IF NOT EXISTS idx_ranksaverage_event_best ON RanksAverage(eventId, best)"
            )
            c.execute(
                "CREATE INDEX IF NOT EXISTS idx_rankssingle_event_best_person ON RanksSingle(eventId, best, personId)"
            )
            c.execute(
                "CREATE INDEX IF NOT EXISTS idx_ranksaverage_event_best_person ON RanksAverage(eventId, best, personId)"
            )
            conn.commit()
        finally:
            conn.close()

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _get_target_records(self, person_id: str) -> Tuple[Dict[str, int], Dict[str, int], str]:
        """返回目标选手的最佳单次/平均映射，以及国家代码"""
        conn = self._get_conn()
        try:
            c = conn.cursor()
            c.execute("SELECT countryId FROM Persons WHERE id = ?", (person_id,))
            row = c.fetchone()
            country = row["countryId"] if row else ""

            c.execute(
                "SELECT eventId, best FROM RanksSingle WHERE personId = ? AND best > 0",
                (person_id,),
            )
            single = {r["eventId"]: r["best"] for r in c.fetchall()}

            c.execute(
                "SELECT eventId, best FROM RanksAverage WHERE personId = ? AND best > 0",
                (person_id,),
            )
            average = {r["eventId"]: r["best"] for r in c.fetchall()}

            # 只保留同时有单次和平均的项目（题意“单次平均成绩都比…好”）
            common_events = set(single.keys()) & set(average.keys())
            single = {k: v for k, v in single.items() if k in common_events}
            average = {k: v for k, v in average.items() if k in common_events}
            return single, average, country
        finally:
            conn.close()

    def _filter_better_players(
        self, single: Dict[str, int], average: Dict[str, int]
    ) -> Set[str]:
        """找出在所有这些项目的单次和平均都优于目标的 personId"""
        if not single or not average:
            return set()

        # 仅保留两侧同时存在的项目
        events = [(ev, single[ev], average[ev]) for ev in single.keys() if ev in average]
        if not events:
            return set()

        # 为了输出真实进度，这里改为逐项目查询并在 Python 中做交集。
        # 由于交集会快速收缩候选集合，通常不会比单条巨型 SQL 更慢。
        events.sort(key=lambda x: (x[1], x[2]))

        conn = self._get_conn()
        try:
            c = conn.cursor()
            candidates: Set[str] | None = None
            total = len(events)
            fetch_size = 10000

            sql_single = """
                SELECT personId
                FROM RanksSingle
                WHERE eventId = ?
                  AND best > 0
                  AND best < ?
            """

            sql_average = """
                SELECT personId
                FROM RanksAverage
                WHERE eventId = ?
                  AND best > 0
                  AND best < ?
            """

            for idx, (ev, s_val, a_val) in enumerate(events, start=1):
                def _fetch_set(phase: str) -> Set[str]:
                    out: Set[str] = set()
                    while True:
                        rows = c.fetchmany(fetch_size)
                        if not rows:
                            break
                        for row in rows:
                            out.add(row[0])
                    return out

                c.execute(sql_single, (ev, s_val))
                single_set = _fetch_set("single")

                c.execute(sql_average, (ev, a_val))
                average_set = _fetch_set("average")

                ev_set = single_set & average_set

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
                f"SELECT id, name, countryId FROM Persons WHERE id IN ({placeholders})",
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
                f"SELECT id, continentId FROM Countries WHERE id IN ({placeholders})",
                tuple(country_ids),
            )
            return {row["id"]: row["continentId"] for row in c.fetchall()}
        except sqlite3.Error:
            return {}
        finally:
            conn.close()

    def query(self, person_id: str) -> Tuple[str, int, int, int, List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
        """返回 (continent, world_count, continent_count, country_count, world_list, continent_list, country_list)"""
        single, average, country = self._get_target_records(person_id)
        better_ids = self._filter_better_players(single, average)
        people = self._get_people(better_ids)

        country_ids = {p.get("countryId") for p in people if p.get("countryId")}
        if country:
            country_ids.add(country)
        country_continent = self._get_country_continent_map(country_ids)

        target_continent = country_continent.get(country) or COUNTRY_TO_CONTINENT.get(country, "UNKNOWN")

        world_list = people
        continent_list = [
            p
            for p in people
            if (country_continent.get(p.get("countryId")) or COUNTRY_TO_CONTINENT.get(p.get("countryId"), "UNKNOWN"))
            == target_continent
        ]
        country_list = [p for p in people if p.get("countryId") == country]

        return (
            target_continent,
            len(world_list),
            len(continent_list),
            len(country_list),
            world_list,
            continent_list,
            country_list,
        )

