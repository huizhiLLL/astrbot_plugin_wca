import asyncio
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, StarTools, register
from astrbot.api import logger

from .wca_query import WCAQuery
from .wca_updater import WCAUpdater
from .wca_pk import WCAPKService
from .wca_nemesis import NemesisService


@register("wca", "huizhiLLL", "WCA成绩查询插件", "1.0.3")
class WCAPlugin(Star):
    """WCA 成绩查询插件"""
    
    def __init__(self, context: Context):
        super().__init__(context)
        self.db_path = StarTools.get_data_dir("astrbot_plugin_wca") / "wca_data.db"
        self.wca_updater: WCAUpdater | None = None
        self.wca_query: WCAQuery | None = None
        self.wca_pk: WCAPKService | None = None
        self.wca_nemesis: NemesisService | None = None
        self._update_task: asyncio.Task | None = None
    
    async def initialize(self):
        """插件初始化"""
        try:
            # 初始化更新器
            self.wca_updater = WCAUpdater(self.db_path)
            
            # 检查并更新数据库
            logger.info("正在检查 WCA 数据库...")
            db_exists = self.db_path.exists()
            
            if not db_exists:
                logger.info("WCA 数据库不存在，开始下载...")
                success = await self.wca_updater.update_database(force=True)
                if not success:
                    logger.error("WCA 数据库下载失败")
                    return
                logger.info("WCA 数据库下载完成")
            else:
                # 数据库已存在，尝试更新（不强制）
                logger.info("WCA 数据库已存在，检查更新...")
                await self.wca_updater.update_database(force=False)
            
            # 初始化查询器
            if self.db_path.exists():
                self.wca_query = WCAQuery(self.db_path)
                self.wca_pk = WCAPKService(self.wca_query)
                self.wca_nemesis = NemesisService(self.db_path)
                logger.info("WCA 插件初始化完成")
                # 启动定时更新任务（每 12 小时检查一次）
                self._update_task = asyncio.create_task(self._periodic_update())
            else:
                logger.error("WCA 数据库文件不存在，插件无法正常工作")
                
        except Exception as e:
            logger.error(f"WCA 插件初始化失败: {e}")
    
    @filter.command("wca")
    async def wca_command(self, event: AstrMessageEvent):
        """个人官方最佳记录查询：\n
        /wca <WCA ID 或姓名>
        /wca 2010ZHAN01 /wca 张安宇
        """
        if not self.wca_query:
            yield event.plain_result(
                "❌ WCA 数据库未初始化，请稍后重试"
            ).use_t2i(False)
            return
        
        # 解析命令参数
        message_str = event.message_str.strip()
        parts = message_str.split(maxsplit=1)
        
        if len(parts) < 2:
            yield event.plain_result(
                "❌ 请提供 WCA ID 或姓名\n"
                "用法: /wca <WCA ID 或姓名>\n"
                "示例: /wca 2010ZHAN01\n"
                "示例: /wca 张安宇"
            ).use_t2i(False)
            return
        
        search_input = parts[1].strip()
        
        try:
            # 搜索选手
            persons = self.wca_query.search_person(search_input)
            
            if not persons:
                yield event.plain_result(
                    f"❌ 未找到匹配的选手: {search_input}\n"
                    "提示：可以使用 WCA ID（如：2010ZHAN01）或姓名进行搜索"
                ).use_t2i(False)
                return
            
            # 如果找到多个选手，列出所有匹配的选手
            if len(persons) > 1:
                lines = [f"❌ 找到多个匹配的选手，请使用 WCA ID 查询：\n"]
                for i, person in enumerate(persons[:10], 1):  # 最多显示10个
                    person_id = person.get("id", "未知")
                    person_name = person.get("name", "未知")
                    country = person.get("countryId", "")
                    country_str = f" [{country}]" if country else ""
                    lines.append(f"{i}. {person_name} ({person_id}){country_str}")
                
                if len(persons) > 10:
                    lines.append(f"\n... 还有 {len(persons) - 10} 个结果未显示")
                
                lines.append("\n使用方法: /wca <WCA ID>")
                yield event.plain_result("\n".join(lines)).use_t2i(False)
                return
            
            # 只有一个匹配的选手，查询成绩
            person = persons[0]
            person_id = person.get("id", "")
            
            if not person_id:
                yield event.plain_result("❌ 选手信息不完整，无法查询成绩").use_t2i(False)
                return
            
            # 获取成绩
            records_data = self.wca_query.get_person_best_records(person_id)
            
            if not records_data:
                person_name = person.get("name", "该选手")
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
    
    @filter.command("wca更新")
    async def wca_update_command(self, event: AstrMessageEvent):
        """手动更新 WCA 数据库：\n
        /wca更新
        """
        if not self.wca_updater:
            yield event.plain_result("❌ WCA 更新器未初始化").use_t2i(False)
            return
        
        try:
            yield event.plain_result("正在更新 WCA 数据库，请稍候...").use_t2i(False)
            
            success = await self.wca_updater.update_database(force=True)
            
            if success:
                # 重新初始化查询器
                if self.db_path.exists():
                    self.wca_query = WCAQuery(self.db_path)
                    self.wca_pk = WCAPKService(self.wca_query)
                    self.wca_nemesis = NemesisService(self.db_path)
                    yield event.plain_result("✅ WCA 数据库更新成功").use_t2i(False)
                else:
                    yield event.plain_result("❌ 数据库更新失败：文件不存在").use_t2i(False)
            else:
                yield event.plain_result("❌ WCA 数据库更新失败，请查看日志").use_t2i(False)
                
        except Exception as e:
            logger.error(f"WCA 数据库更新异常: {e}")
            yield event.plain_result(f"❌ 更新出错: {str(e)}").use_t2i(False)

    @filter.command("宿敌")
    async def wca_nemesis_command(self, event: AstrMessageEvent):
        if not self.wca_query or not self.wca_nemesis:
            yield event.plain_result("❌ WCA 数据库未初始化，请稍后重试").use_t2i(False)
            return

        message_str = event.message_str.strip()
        parts = message_str.split(maxsplit=1)
        if len(parts) < 2:
            yield event.plain_result(
                "❌ 请提供 WCA ID 或姓名\n"
                "用法: /宿敌 <WCA ID 或姓名>\n"
                "示例: /宿敌 2010ZHAN01\n"
            ).use_t2i(False)
            return

        search_input = parts[1].strip()

        try:
            persons = self.wca_query.search_person(search_input)
            if not persons:
                yield event.plain_result(
                    f"❌ 未找到匹配的选手: {search_input}\n"
                    "提示：可以使用 WCA ID（如：2010ZHAN01）或姓名进行搜索"
                ).use_t2i(False)
                return

            if len(persons) > 1:
                lines = ["❌ 找到多个匹配的选手，请使用 WCA ID 查询：\n"]
                for i, person in enumerate(persons[:10], 1):
                    person_id = person.get("id", "未知")
                    person_name = person.get("name", "未知")
                    country = person.get("countryId", "")
                    country_str = f" [{country}]" if country else ""
                    lines.append(f"{i}. {person_name} ({person_id}){country_str}")

                if len(persons) > 10:
                    lines.append(f"\n... 还有 {len(persons) - 10} 个结果未显示")
                lines.append("\n使用方法: /wca宿敌 <WCA ID>")
                yield event.plain_result("\n".join(lines)).use_t2i(False)
                return

            person_id = persons[0].get("id", "")
            if not person_id:
                yield event.plain_result("❌ 选手信息不完整，无法查询").use_t2i(False)
                return

            yield event.plain_result("收到！正在查询宿敌...").use_t2i(False)

            continent, world_count, continent_count, country_count, world_list, continent_list, country_list = (
                await asyncio.to_thread(self.wca_nemesis.query, person_id)
            )

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
                    pid = p.get("id", "")
                    name = p.get("name", "")
                    ctry = p.get("countryId", "")
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
        /wcapk <选手1> <选手2>
        填写WCA ID 或姓名（姓名需唯一匹配）
        """
        if not self.wca_pk:
            yield event.plain_result("❌ WCA 数据库未初始化，请稍后重试").use_t2i(False)
            return

        msg = event.message_str.strip()
        parts = msg.split(maxsplit=2)
        if len(parts) < 3:
            yield event.plain_result(
                "❌ 参数不足\n用法: /wcapk <选手1> <选手2>\n示例: /wcapk 2010ZHAN01 2009ZEMD01"
            ).use_t2i(False)
            return

        p1, p2 = parts[1].strip(), parts[2].strip()
        try:
            text, err = self.wca_pk.compare(p1, p2)
            if err:
                yield event.plain_result(err).use_t2i(False)
                return
            yield event.plain_result(text).use_t2i(False)
        except Exception as e:
            logger.error(f"WCA PK 异常: {e}")
            yield event.plain_result(f"❌ 执行出错: {str(e)}").use_t2i(False)
    
    async def terminate(self):
        """插件销毁"""
        if self.wca_updater:
            await self.wca_updater.close()
        if self._update_task:
            self._update_task.cancel()
            try:
                await self._update_task
            except asyncio.CancelledError:
                pass

    async def _periodic_update(self):
        """周期性检查/更新数据库（12 小时一次，使用非强制更新）"""
        while True:
            try:
                await asyncio.sleep(12 * 60 * 60)  # 12 小时
                if self.wca_updater:
                    logger.info("定时任务：检查 WCA 数据库更新（非强制）")
                    await self.wca_updater.update_database(force=False)
            except asyncio.CancelledError:
                logger.info("定时更新任务已取消")
                break
            except Exception as e:
                logger.warning(f"定时更新任务异常: {e}")

