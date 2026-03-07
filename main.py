from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, register
from astrbot.api import logger

from .wca_pic import WCAPicService
from .wca_query import WCAQuery, WCACommandService, WCANemesisService
from .wca_pk import WCAPKService
from .wca_recent_competitions import RecentCompetitionsService

@register("wca", "huizhiLLL", "WCA成绩查询插件", "1.0.6")
class WCAPlugin(Star):
    """WCA 成绩查询插件"""
    
    def __init__(self, context: Context):
        super().__init__(context)
        self.wca_query: WCAQuery | None = None
        self.wca_command: WCACommandService | None = None
        self.wca_pic: WCAPicService | None = None
        self.wca_pk: WCAPKService | None = None
        self.recent_competitions: RecentCompetitionsService | None = None
        self.wca_nemesis: WCANemesisService | None = None
        self.nemesis_api_base = "https://wca.huizhi.pro"
    
    async def initialize(self):
        """插件初始化"""
        try:
            # 纯 API 模式，无需本地数据库
            self.wca_query = WCAQuery()
            self.wca_command = WCACommandService(self.wca_query)
            self.wca_pic = WCAPicService(self.wca_query, self.context)
            self.wca_pk = WCAPKService(self.wca_query)
            self.recent_competitions = RecentCompetitionsService()
            self.wca_nemesis = WCANemesisService(self.wca_query, self.nemesis_api_base)
            logger.info("WCA 插件初始化完成")
                
        except Exception as e:
            logger.error(f"WCA 插件初始化失败: {e}")
    
    @filter.command("wca")
    async def wca_command(self, event: AstrMessageEvent):
        """查询 WCA 选手信息"""
        if not self.wca_command:
            yield event.plain_result(
                "哎呀，初始化 WCA 查询出错啦，请稍后再试哦！"
            ).use_t2i(False)
            return
        async for result in self.wca_command.handle(event):
            yield result

    @filter.command("wcapic")
    async def wcapic_command(self, event: AstrMessageEvent):
        """个人记录图片：\n
        /wcapic [WCAID/姓名]\n
        /wcapic 2026LIHU01 /wcapic 李华
        """
        if not self.wca_pic:
            yield event.plain_result("哎呀，初始化 WCA 查询出错啦，请稍后再试哦！").use_t2i(False)
            return

        async for result in self.wca_pic.handle(event):
            yield result
    
    @filter.command("宿敌")
    async def wca_nemesis_command(self, event: AstrMessageEvent):
        """宿敌查询：\n
        /宿敌 [WCAID/姓名]\n
        /宿敌 2026LIHU01 /宿敌 李华
        """
        if not self.wca_nemesis:
            yield event.plain_result("哎呀，初始化 WCA 查询出错啦，请稍后再试哦！").use_t2i(False)
            return
        async for result in self.wca_nemesis.handle(event):
            yield result

    @filter.command("wcapk")
    async def wca_pk_command(self, event: AstrMessageEvent):
        """wcapk:\n
        /wcapk <选手1> <选手2>\n
        填写 WCAID 或姓名（姓名需唯一匹配）
        """
        if not self.wca_pk:
            yield event.plain_result("哎呀，初始化 WCA 查询出错啦，请稍后再试哦！").use_t2i(False)
            return
        async for result in self.wca_pk.handle(event):
            yield result
    
    @filter.command("近期比赛")
    async def recent_competitions_command(self, event: AstrMessageEvent):
        """近期比赛查询：\n
        /近期比赛
        列出近期在中国举办的比赛（包含正在和即将要举办的）
        """
        if not self.recent_competitions:
            yield event.plain_result("哎呀，初始化 WCA 查询出错啦，请稍后再试哦！").use_t2i(False)
            return
        async for result in self.recent_competitions.handle(event):
            yield result
    
    async def terminate(self):
        """插件销毁"""
        return
