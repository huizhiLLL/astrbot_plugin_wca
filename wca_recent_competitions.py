import aiohttp
from datetime import datetime, date
from typing import List, Dict, Any
from astrbot.api import logger


class RecentCompetitionsService:
    """近期比赛查询服务（通过 cubing.com API）"""
    
    API_BASE_URL = "https://cubing.com/api/v0/competition"
    
    def __init__(self, db_path: str | None = None):
        """
        Args:
            db_path: 保留参数以兼容旧代码，现在不再使用
        """
        # 不再需要数据库路径，但保留参数以兼容
        pass
    
    async def _fetch_competitions_from_api(self, year: str = "current", type: str = "WCA") -> List[Dict[str, Any]]:
        """从 API 获取比赛列表
        
        Args:
            year: 年份参数，'current' 表示最近6个月
            type: 比赛类型，'WCA' 表示 WCA 官方比赛
        
        Returns:
            API 返回的比赛列表
        """
        try:
            url = f"{self.API_BASE_URL}?year={year}&type={type}"
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as response:
                    if response.status != 200:
                        logger.error(f"API 请求失败，状态码: {response.status}")
                        return []
                    
                    data = await response.json()
                    
                    if data.get("status") != 0:
                        logger.error(f"API 返回错误: {data.get('message', 'Unknown error')}")
                        return []
                    
                    return data.get("data", [])
                    
        except aiohttp.ClientError as e:
            logger.error(f"API 请求异常: {e}")
            return []
        except Exception as e:
            logger.error(f"获取比赛列表失败: {e}")
            return []
    
    def _filter_china_competitions(self, competitions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """过滤出中国的比赛
        
        Args:
            competitions: 比赛列表
        
        Returns:
            中国的比赛列表
        """
        china_competitions = []
        
        for comp in competitions:
            locations = comp.get("locations", [])
            
            # 检查所有地点是否都在中国
            # 使用 region 字段判断，更准确
            is_china_competition = all(
                location.get("region") == "China" or location.get("region") == "中国"
                for location in locations
            )
            
            if is_china_competition and locations:
                china_competitions.append(comp)
        
        return china_competitions
    
    def _parse_timestamp_to_date_str(self, timestamp: int) -> str:
        """将 Unix 时间戳转换为日期字符串
        
        Args:
            timestamp: Unix 时间戳（秒）
        
        Returns:
            日期字符串，格式：YYYY-MM-DD
        """
        try:
            dt = datetime.fromtimestamp(timestamp)
            return dt.strftime("%Y-%m-%d")
        except (ValueError, TypeError, OSError):
            return "日期未知"
    
    async def get_recent_competitions_in_china(self, limit: int = 50) -> List[Dict[str, Any]]:
        """获取近期在中国举办的比赛
        
        Args:
            limit: 返回结果的最大数量
        
        Returns:
            比赛列表，每个比赛包含 id, name, city_name, start_date, end_date 等信息
        """
        try:
            # 从 API 获取比赛列表
            competitions = await self._fetch_competitions_from_api(year="current", type="WCA")
            
            if not competitions:
                return []
            
            # 过滤出中国的比赛
            china_competitions = self._filter_china_competitions(competitions)
            
            # 格式化数据
            formatted_competitions = []
            for comp in china_competitions[:limit]:
                # 获取比赛名称（中文）
                name = comp.get("name", "未知比赛")
                
                # 获取地点信息（优先使用中文字段）
                locations = comp.get("locations", [])
                city_name = ""
                province_name = ""
                if locations:
                    first_location = locations[0]
                    # 城市名称：优先使用中文
                    city_name_zh = first_location.get("city_name_zh", "")
                    city_name_en = first_location.get("city_name", "")
                    city_name = city_name_zh or city_name_en
                    
                    # 省份名称：优先使用中文
                    province = first_location.get("province", {})
                    province_name_zh = province.get("name_zh", "")
                    province_name_en = province.get("name", "")
                    province_name = province_name_zh or province_name_en
                
                # 获取日期信息
                date_info = comp.get("date", {})
                start_timestamp = date_info.get("from", 0)
                end_timestamp = date_info.get("to", start_timestamp)
                
                start_date_str = self._parse_timestamp_to_date_str(start_timestamp)
                end_date_str = self._parse_timestamp_to_date_str(end_timestamp)
                
                formatted_comp = {
                    "id": comp.get("id"),
                    "name": name,
                    "city_name": city_name,
                    "province_name": province_name,
                    "start_date_str": start_date_str,
                    "end_date_str": end_date_str,
                }
                
                formatted_competitions.append(formatted_comp)
            
            return formatted_competitions
            
        except Exception as e:
            logger.error(f"查询近期比赛失败: {e}")
            return []
    
    def format_competitions_list(self, competitions: List[Dict[str, Any]]) -> str:
        """格式化比赛列表为字符串
        
        Args:
            competitions: 比赛列表
        
        Returns:
            格式化后的字符串
        """
        if not competitions:
            return "暂无近期在中国举办的比赛"
        
        lines = [f"近期在中国举办的比赛（共 {len(competitions)} 场）：\n"]
        
        for i, comp in enumerate(competitions, 1):
            name = comp.get("name", "未知比赛")
            city = comp.get("city_name", "")
            province = comp.get("province_name", "")
            start_str = comp.get("start_date_str", "日期未知")
            end_str = comp.get("end_date_str", "")
            
            # 如果开始和结束日期相同，只显示一个日期
            if start_str == end_str:
                date_str = start_str
            else:
                date_str = f"{start_str} ~ {end_str}"
            
            # 构建地点信息：优先显示省份+城市，如果只有城市则只显示城市
            location_parts = []
            if province:
                location_parts.append(province)
            if city:
                location_parts.append(city)
            location_str = " ".join(location_parts)
            location_display = f" [{location_str}]" if location_str else ""
            
            lines.append(f"{i}. {name}{location_display}")
            lines.append(f"   日期: {date_str}")
            lines.append("")  # 空行分隔
        
        return "\n".join(lines)
