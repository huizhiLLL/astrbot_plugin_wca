import asyncio
import aiohttp
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, register
from astrbot.api import logger

from .wca_query import WCAQuery
from .wca_pk import WCAPKService
from .wca_recent_competitions import RecentCompetitionsService

@register("wca", "huizhiLLL", "WCA成绩查询插件", "1.0.5")
class WCAPlugin(Star):
    """WCA 成绩查询插件"""
    
    def __init__(self, context: Context):
        super().__init__(context)
        self.wca_query: WCAQuery | None = None
        self.wca_pk: WCAPKService | None = None
        self.recent_competitions: RecentCompetitionsService | None = None
        self.nemesis_api_base = "https://wca.huizhi.pro"
    
    async def initialize(self):
        """插件初始化"""
        try:
            # 纯 API 模式，无需本地数据库
            self.wca_query = WCAQuery()
            self.wca_pk = WCAPKService(self.wca_query)
            self.recent_competitions = RecentCompetitionsService()
            logger.info("WCA 插件初始化完成")
                
        except Exception as e:
            logger.error(f"WCA 插件初始化失败: {e}")
    
    @filter.command("wca")
    async def wca_command(self, event: AstrMessageEvent):
        """个人最佳记录查询：\n
        /wca <WCA ID 或姓名>\n
        /wca 2012ZHAN01 /wca 张安宇
        """
        if not self.wca_query:
            yield event.plain_result(
                "出错啦，请稍后再试！"
            ).use_t2i(False)
            return
        
        # 解析命令参数
        message_str = event.message_str.strip()
        parts = message_str.split(maxsplit=1)
        
        if len(parts) < 2:
            yield event.plain_result(
                "❌ 请提供 WCA ID 或姓名\n"
                "用法: /wca <WCA ID 或姓名>\n"
                "示例: /wca 2012ZHAN01\n"
                "示例: /wca 张安宇"
            ).use_t2i(False)
            return
        
        search_input = parts[1].strip()
        
        try:
            # 搜索选手
            persons = await self.wca_query.search_person(search_input)
            
            if not persons:
                yield event.plain_result(
                    f"❌ 未找到匹配的选手: {search_input}\n"
                    "提示：可以使用 WCA ID（如：2012ZHAN01）或姓名进行搜索"
                ).use_t2i(False)
                return
            
            # 如果找到多个选手，列出所有匹配的选手
            if len(persons) > 1:
                lines = [f"❌ 找到多个匹配的选手，请使用 WCA ID 查询：\n"]
                for i, item in enumerate(persons[:10], 1):  # 最多显示10个
                    person_info = item.get("person", {}) if isinstance(item, dict) else {}
                    person_id = person_info.get("wca_id", "未知")
                    person_name = person_info.get("name", "未知")
                    country = person_info.get("country_iso2", "")
                    country_str = f" [{country}]" if country else ""
                    lines.append(f"{i}. {person_name} ({person_id}){country_str}")
                
                if len(persons) > 10:
                    lines.append(f"\n... 还有 {len(persons) - 10} 个结果未显示")
                
                lines.append("\n使用方法: /wca <WCA ID>")
                yield event.plain_result("\n".join(lines)).use_t2i(False)
                return
            
            # 只有一个匹配的选手，查询成绩
            picked = persons[0]
            person_info = picked.get("person", {}) if isinstance(picked, dict) else {}
            person_id = person_info.get("wca_id", "")
            
            if not person_id:
                yield event.plain_result("❌ 选手信息不完整，无法查询成绩").use_t2i(False)
                return
            
            # 获取成绩
            records_data = await self.wca_query.get_person_best_records(person_id)
            
            if not records_data:
                person_name = person_info.get("name", "该选手")
                yield event.plain_result(
                    f"❌ {person_name} ({person_id}) 暂无 WCA 成绩记录"
                ).use_t2i(False)
                return
            
            # 格式化并返回结果
            result_text = self.wca_query.format_person_records(records_data)
            yield event.plain_result(result_text).use_t2i(False)
            
        except Exception as e:
            logger.error(f"WCA 查询异常: {e}")
            yield event.plain_result(f"❌ 执行出错: {str(e)}").use_t2i(False)
    
    @filter.command("宿敌")
    async def wca_nemesis_command(self, event: AstrMessageEvent):
        """宿敌查询：\n
        /宿敌 <WCA ID 或姓名>\n
        /宿敌 2012ZHAN01 /宿敌 张安宇
        """
        if not self.wca_query:
            yield event.plain_result("出错啦，请稍后再试！").use_t2i(False)
            return

        message_str = event.message_str.strip()
        parts = message_str.split(maxsplit=1)
        if len(parts) < 2:
            yield event.plain_result(
                "❌ 请提供 WCA ID 或姓名\n"
                "用法: /宿敌 <WCA ID 或姓名>\n"
                "示例: /宿敌 2012ZHAN01\n"
            ).use_t2i(False)
            return

        search_input = parts[1].strip()

        try:
            persons = await self.wca_query.search_person(search_input)
            if not persons:
                yield event.plain_result(
                    f"❌ 未找到匹配的选手: {search_input}\n"
                    "提示：可以使用 WCA ID（如：2012ZHAN01）或姓名进行搜索"
                ).use_t2i(False)
                return

            if len(persons) > 1:
                lines = ["❌ 找到多个匹配的选手，请使用 WCA ID 查询：\n"]
                for i, item in enumerate(persons[:10], 1):
                    pinfo = item.get("person", {}) if isinstance(item, dict) else {}
                    person_id = pinfo.get("wca_id", "未知")
                    person_name = pinfo.get("name", "未知")
                    country = pinfo.get("country_iso2", "")
                    country_str = f" [{country}]" if country else ""
                    lines.append(f"{i}. {person_name} ({person_id}){country_str}")

                if len(persons) > 10:
                    lines.append(f"\n... 还有 {len(persons) - 10} 个结果未显示")
                lines.append("\n使用方法: /wca宿敌 <WCA ID>")
                yield event.plain_result("\n".join(lines)).use_t2i(False)
                return

            pinfo = persons[0].get("person", {}) if isinstance(persons[0], dict) else {}
            person_id = pinfo.get("wca_id", pinfo.get("id", ""))
            if not person_id:
                yield event.plain_result("❌ 选手信息不完整，无法查询").use_t2i(False)
                return

            yield event.plain_result("收到！正在查询宿敌...").use_t2i(False)

            nemesis_data = await self._call_nemesis_api(person_id)
            if not nemesis_data:
                yield event.plain_result("❌ 宿敌查询失败，请稍后重试").use_t2i(False)
                return

            continent = nemesis_data.get("continent", "UNKNOWN")
            world_count = nemesis_data.get("world_count", 0)
            continent_count = nemesis_data.get("continent_count", 0)
            country_count = nemesis_data.get("country_count", 0)
            world_list = nemesis_data.get("world_list", [])
            continent_list = nemesis_data.get("continent_list", [])
            country_list = nemesis_data.get("country_list", [])

            if world_count == 0:
                yield event.plain_result(
                    f"✅ 未找到宿敌"
                ).use_t2i(False)
                return

            person_name = persons[0].get("name", "")
            title = f"选手{person_name}({person_id})的宿敌结果为："
            summary = f"世界：{world_count}人，洲：{continent_count}人，地区：{country_count}人"

            def _fmt_people(people: list[dict[str, str]]) -> str:
                lines: list[str] = []
                for p in people:
                    pid = p.get("wca_id", "")
                    name = p.get("name", "")
                    ctry = p.get("country_id", "")
                    ctry_str = f" [{ctry}]" if ctry else ""
                    lines.append(f"- {name} ({pid}){ctry_str}")
                return "\n".join(lines)

            details: list[str] = []
            if 0 < world_count <= 5:
                details.append("世界：\n" + _fmt_people(world_list))
            if 0 < continent_count <= 5:
                details.append("洲：\n" + _fmt_people(continent_list))
            if 0 < country_count <= 5:
                details.append("地区：\n" + _fmt_people(country_list))

            text = "\n".join([title, summary] + (["", "\n\n".join(details)] if details else []))
            yield event.plain_result(text).use_t2i(False)

        except Exception as e:
            yield event.plain_result(f"❌ 执行出错: {str(e)}").use_t2i(False)

    @filter.command("wcapk")
    async def wca_pk_command(self, event: AstrMessageEvent):
        """wcapk:\n
        /wcapk <选手1> <选手2>\n
        填写WCA ID 或姓名（姓名需唯一匹配）
        """
        if not self.wca_pk:
            yield event.plain_result("❌ 出错啦，请稍后再试！").use_t2i(False)
            return

        msg = event.message_str.strip()
        parts = msg.split(maxsplit=2)
        if len(parts) < 3:
            yield event.plain_result(
                "❌ 参数不足\n用法: /wcapk <选手1> <选手2>\n示例: /wcapk 2012ZHAN01 2009ZEMD01"
            ).use_t2i(False)
            return

        p1, p2 = parts[1].strip(), parts[2].strip()
        try:
            text, err = await self.wca_pk.compare(p1, p2)
            if err:
                yield event.plain_result(err).use_t2i(False)
                return
            yield event.plain_result(text).use_t2i(False)
        except Exception as e:
            logger.error(f"WCA PK 异常: {e}")
            yield event.plain_result(f"❌ 执行出错: {str(e)}").use_t2i(False)
    
    @filter.command("近期比赛")
    async def recent_competitions_command(self, event: AstrMessageEvent):
        """近期比赛查询：\n
        /近期比赛
        列出近期在中国举办的比赛（包含正在和即将要举办的）
        """
        if not self.recent_competitions:
            yield event.plain_result("出错啦，请稍后再试！").use_t2i(False)
            return
        
        try:
            yield event.plain_result("正在查询近期比赛...").use_t2i(False)
            
            # 直接调用异步方法
            competitions = await self.recent_competitions.get_recent_competitions_in_china(limit=50)
            
            # 格式化结果
            result_text = self.recent_competitions.format_competitions_list(competitions)
            
            yield event.plain_result(result_text).use_t2i(False)
            
        except Exception as e:
            logger.error(f"查询近期比赛异常: {e}")
            yield event.plain_result(f"❌ 执行出错: {str(e)}").use_t2i(False)
    
    async def terminate(self):
        """插件销毁"""
        return

    async def _call_nemesis_api(self, person_id: str) -> dict | None:
        """调用外部宿敌查询接口"""
        url = f"{self.nemesis_api_base.rstrip('/')}/nemesis"
        payload = {"person_id": person_id}
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status != 200:
                        logger.error(f"宿敌接口调用失败，状态码: {resp.status}")
                        return None
                    data = await resp.json()
                    if isinstance(data, dict) and "error" in data:
                        logger.error(f"宿敌接口返回错误: {data.get('error')}")
                        return None
                    return data if isinstance(data, dict) else None
        except Exception as e:
            logger.error(f"调用宿敌接口异常: {e}")
            return None

