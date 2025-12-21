import sqlite3
from pathlib import Path
from typing import Any, Optional, Tuple
from astrbot.api import logger

# WCA 英文名称映射为显示名称
EVENT_NAME_MAP: dict[str, str] = {
    "3x3x3 Cube": "333",
    "2x2x2 Cube": "222",
    "4x4x4 Cube": "444",
    "5x5x5 Cube": "555",
    "6x6x6 Cube": "666",
    "7x7x7 Cube": "777",
    "3x3x3 Blindfolded": "333bf",
    "3x3x3 Fewest Moves": "333fm",
    "3x3x3 One-Handed": "333oh",
    "Clock": "clock",
    "Megaminx": "minx",
    "Pyraminx": "py",
    "Skewb": "sk",
    "Square-1": "sq1",
    "4x4x4 Blindfolded": "444bf",
    "5x5x5 Blindfolded": "555bf",
    "3x3x3 Multi-Blind": "333mbf",
    "3x3x3 With Feet": "333ft",
}


def format_wca_time(centiseconds: int, event_format: str = "time") -> str:
    """格式化 WCA 时间（厘秒转换为可读格式）
    
    Args:
        centiseconds: 时间值（厘秒）
        event_format: 项目格式，"time" 表示时间格式，"number" 表示数字格式，"multi" 表示多盲格式
    
    Returns:
        格式化后的时间字符串
    """
    # 处理特殊值
    if centiseconds == -1:
        return "DNF"
    if centiseconds == -2:
        return "DNS"
    if centiseconds == 0:
        return "-"
    
    # 处理多盲格式
    if event_format == "multi":
        return format_multi_blind(centiseconds)
    
    # 处理数字格式（最少步）
    if event_format == "number":
        # 最少步的平均值存储为 100 倍，需要除以 100
        if centiseconds >= 100:
            return f"{centiseconds / 100:.2f}"
        return str(centiseconds)
    
    # 处理时间格式（大多数项目）
    # 使用纯整数运算，避免浮点精度导致误差
    total_cs = int(centiseconds)
    minutes = total_cs // 6000              # 6000 cs = 60 s
    sec_cs = total_cs % 6000
    seconds = sec_cs // 100
    cs = sec_cs % 100
    
    if minutes > 0:
        # 有分钟：M:SS.cc
        return f"{minutes}:{seconds:02d}.{cs:02d}"
    else:
        # 只有秒：S.cc（秒不补前导零）
        return f"{seconds}.{cs:02d}"


def format_multi_blind(value: int) -> str:
    """格式化多盲成绩
    
    Args:
        value: 多盲编码值
    
    Returns:
        格式化后的多盲成绩字符串，格式：solved/attempted time
    """
    # 按 WCA 新旧格式解析，使用 10 位零填充（0DDTTTTTMM / 1SSAATTTTT）
    value_str = str(value).zfill(10)
    
    if value_str[0] == '1':
        # 旧格式：1SSAATTTTT
        ss = int(value_str[1:3])
        aa = int(value_str[3:5])
        ttttt = int(value_str[5:10])
        
        solved = 99 - ss
        attempted = aa
        time_seconds = ttttt if ttttt != 99999 else None
    else:
        # 新格式：0DDTTTTTMM
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
    
    # 格式化时间
    hours = time_seconds // 3600
    minutes = (time_seconds % 3600) // 60
    seconds = time_seconds % 60
    
    if hours > 0:
        time_str = f"{hours}:{minutes:02d}:{seconds:02d}"
    else:
        time_str = f"{minutes}:{seconds:02d}"
    
    return f"{solved}/{attempted} {time_str}"


class WCAQuery:
    """WCA 数据库查询类"""
    
    def __init__(self, db_path: str | Path):
        """
        Args:
            db_path: SQLite 数据库文件路径
        """
        self.db_path = Path(db_path)
        if not self.db_path.exists():
            raise FileNotFoundError(f"WCA 数据库文件不存在: {db_path}")
    
    def _get_connection(self) -> sqlite3.Connection:
        """获取数据库连接"""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row  # 使用 Row 工厂，方便访问列
        return conn
    
    def search_person(self, search_input: str) -> list[dict[str, Any]]:
        """搜索选手
        
        Args:
            search_input: 搜索关键词（WCA ID 或姓名）
        
        Returns:
            匹配的选手列表
        """
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            
            # 如果是 WCA ID 格式（例如：2010ZHAN01），直接查询
            if len(search_input) >= 10 and search_input[:4].isdigit():
                cursor.execute(
                    "SELECT * FROM persons WHERE wca_id = ? COLLATE NOCASE",
                    (search_input.upper(),)
                )
            else:
                # 按姓名搜索（支持部分匹配）
                cursor.execute(
                    "SELECT * FROM persons WHERE name LIKE ? COLLATE NOCASE",
                    (f"%{search_input}%",)
                )
            
            results = cursor.fetchall()
            return [dict(row) for row in results]
        finally:
            conn.close()
    
    def get_person_best_records(self, person_id: str) -> Optional[dict[str, Any]]:
        """获取选手的最佳单次和平均成绩
        
        Args:
            person_id: WCA ID
        
        Returns:
            包含最佳单次和平均成绩的字典，如果未找到则返回 None
        """
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            
            # 获取选手信息
            cursor.execute("SELECT * FROM persons WHERE wca_id = ?", (person_id,))
            person_row = cursor.fetchone()
            if not person_row:
                return None
            
            person = dict(person_row)
            
            # 获取最佳单次成绩
            cursor.execute("""
                SELECT rs.*, e.id as event_id, e.name as event_name, e.format as event_format, e.rank as event_rank
                FROM ranks_single rs
                JOIN events e ON rs.event_id = e.id
                WHERE rs.person_id = ?
                ORDER BY e.rank
            """, (person_id,))
            
            single_records = cursor.fetchall()
            
            # 获取最佳平均成绩
            cursor.execute("""
                SELECT ra.*, e.id as event_id, e.name as event_name, e.format as event_format, e.rank as event_rank
                FROM ranks_average ra
                JOIN events e ON ra.event_id = e.id
                WHERE ra.person_id = ?
                ORDER BY e.rank
            """, (person_id,))
            
            average_records = cursor.fetchall()
            
            return {
                "person": person,
                "single_records": [dict(row) for row in single_records],
                "average_records": [dict(row) for row in average_records],
            }
        finally:
            conn.close()
    
    def format_person_records(self, records_data: dict[str, Any]) -> str:
        """格式化选手成绩为文本
        
        Args:
            records_data: get_person_best_records 返回的数据
        
        Returns:
            格式化后的文本
        """
        person = records_data["person"]
        person_name = person.get("name", "未知")
        person_id = person.get("wca_id", "")
        country = person.get("country_id", "")
        
        # 构建标题（两行：姓名（含本地名）+ 基本信息）
        # Persons 表通常有本地名字段 "name"（含中文），这里保留原始 name
        header_lines = []
        # 第一行：姓名（保留表中的 name 字段）
        display_name = person.get("name", person_name)
        header_lines.append(f"{display_name}")
        gender = person.get("gender", "")
        gender_str = ""
        if gender:
            gender_str = "Male" if str(gender).lower().startswith("m") else "Female"
        basic_parts = [person_id, country or "-", gender_str or "-"]
        header_lines.append(", ".join(basic_parts))
        header = "\n".join(header_lines) + "\n\n"
        
        single_records = records_data["single_records"]
        average_records = records_data["average_records"]
        
        # 创建事件ID到记录的映射
        single_map = {r["event_id"]: r for r in single_records}
        average_map = {r["event_id"]: r for r in average_records}
        
        # 获取所有有记录的事件
        all_event_ids = set(single_map.keys()) | set(average_map.keys())
        
        if not all_event_ids:
            return f"{header}\n❌ 暂无 WCA 成绩记录"
        
        lines = []
        
        # 按事件排序（使用 rank 字段）
        event_records = []
        for event_id in all_event_ids:
            single = single_map.get(event_id)
            average = average_map.get(event_id)
            
            # 获取 rank（用于排序）
            rank = 999
            if single:
                rank = single.get("event_rank", 999)
            elif average:
                rank = average.get("event_rank", 999)
            
            event_records.append((rank, event_id, single, average))
        
        event_records.sort(key=lambda x: x[0])
        
        # 格式化输出
        for rank, event_id, single, average in event_records:
            event_name = ""
            event_format = "time"
            
            if single:
                event_name = single.get("event_name", f"项目{event_id}")
                event_format = single.get("event_format", "time")
            elif average:
                event_name = average.get("event_name", f"项目{event_id}")
                event_format = average.get("event_format", "time")

            # 友好名称映射：仅按英文名称映射
            event_name = EVENT_NAME_MAP.get(event_name, event_name)
            
            # 格式化单次成绩
            single_time = "-"
            single_rank = "-"
            if single:
                best = single.get("best", 0)
                single_time = format_wca_time(best, event_format)
                wr = single.get("world_rank", 0)
                cr = single.get("continent_rank", 0)
                nr = single.get("country_rank", 0)
                if wr and wr <= 200:
                    single_rank = f"WR{wr}"
                elif cr and cr <= 200:
                    single_rank = f"CR{cr}"
                elif nr and nr <= 200:
                    single_rank = f"NR{nr}"
            
            # 格式化平均成绩
            avg_time = "-"
            avg_rank = "-"
            if average:
                best = average.get("best", 0)
                avg_time = format_wca_time(best, event_format)
                wr = average.get("world_rank", 0)
                cr = average.get("continent_rank", 0)
                nr = average.get("country_rank", 0)
                if wr and wr <= 200:
                    avg_rank = f"WR{wr}"
                elif cr and cr <= 200:
                    avg_rank = f"CR{cr}"
                elif nr and nr <= 200:
                    avg_rank = f"NR{nr}"
            
            # 跳过两个成绩都是无效的记录
            if single_time == "-" and avg_time == "-":
                continue
            
            # 格式：项目名称  单次成绩(排名) || 平均成绩(排名)；排名仅当进入前200时显示，优先 WR > CR > NR
            line = f"{event_name}  {single_time}"
            if single_rank != "-":
                line += f" ({single_rank})"
            line += "  ||  "
            line += avg_time
            if avg_rank != "-":
                line += f" ({avg_rank})"
            
            lines.append(line)
        
        if not lines:
            return f"{header}\n❌ 暂无有效成绩记录"
        
        return header + "\n".join(lines)

