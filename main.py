from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, register

from .clients.one_api import OneRecordHandler, PersonalRecordAPIClient
from .core.one_bindings import OneBindingStore
from .core.reaction_feedback import CommandReactionFeedback
from .core.wca_bindings import WCABindingStore
from .core.wca_query import (
    WCAQuery,
    WCACommandService,
    WCABindCommandService,
)
from .services.wca_cross_platform import (
    OneBindCommandService,
    WCAOneService,
    WCAPRPKService,
    WCAPRService,
)
from .services.wca_help import WCACubeHelpService
from .services.wca_nemesis import WCANemesisService, WCAVersionService
from .services.wca_pic import WCAPicService
from .services.wca_pk import WCAPKService
from .services.one_pk import OnePKService
from .services.pktwo import PKTwoService
from .services.wca_recent_competitions import RecentCompetitionsService


@register("wca", "huizhiLLL", "WCA成绩查询插件", "1.1.10")
class WCAPlugin(Star):
    """WCA 与 one 成绩查询插件"""

    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config
        self.wca_query: WCAQuery | None = None
        self.wca_bindings = WCABindingStore()
        self.one_bindings = OneBindingStore()
        self.wca_command_service: WCACommandService | None = None
        self.wca_bind_command: WCABindCommandService | None = None
        self.one_bind_command: OneBindCommandService | None = None
        self.wca_pic: WCAPicService | None = None
        self.wca_pk: WCAPKService | None = None
        self.one_pk: OnePKService | None = None
        self.pktwo_service: PKTwoService | None = None
        self.recent_competitions: RecentCompetitionsService | None = None
        self.wca_nemesis: WCANemesisService | None = None
        self.wca_version: WCAVersionService | None = None
        self.one_client: PersonalRecordAPIClient | None = None
        self.one_handler: OneRecordHandler | None = None
        self.cube_help_service: WCACubeHelpService | None = None
        self.one_service: WCAOneService | None = None
        self.pr_service: WCAPRService | None = None
        self.prpk_service: WCAPRPKService | None = None
        self.nemesis_api_base = "https://wca.huizhi.pro"
        self.command_reaction_feedback = CommandReactionFeedback(
            enabled=bool(config.get("enable_command_reaction", True)),
            emoji_id=int(config.get("command_reaction_emoji_id", 181)),
        )

    async def initialize(self):
        """插件初始化"""
        try:
            # 纯 API 模式，无需本地数据库
            self.wca_query = WCAQuery()
            self.wca_command_service = WCACommandService(
                self.wca_query, self.wca_bindings
            )
            self.wca_bind_command = WCABindCommandService(
                self.wca_query, self.wca_bindings
            )
            self.wca_pic = WCAPicService(
                self.wca_query, self.context, self.wca_bindings
            )
            self.wca_pk = WCAPKService(
                self.wca_query, self.command_reaction_feedback, self.wca_bindings
            )
            self.recent_competitions = RecentCompetitionsService(
                reaction_feedback=self.command_reaction_feedback
            )
            self.wca_nemesis = WCANemesisService(
                self.wca_query,
                self.nemesis_api_base,
                self.command_reaction_feedback,
                self.wca_bindings,
            )
            self.wca_version = WCAVersionService(self.nemesis_api_base)
            self.one_client = PersonalRecordAPIClient()
            self.one_handler = OneRecordHandler(self.one_client)
            self.one_pk = OnePKService(
                self.one_client,
                self.one_handler,
                self.command_reaction_feedback,
                self.one_bindings,
            )
            self.pktwo_service = PKTwoService(
                self.wca_query,
                self.one_client,
                self.one_handler,
                self.command_reaction_feedback,
            )
            self.cube_help_service = WCACubeHelpService(self.context)
            self.one_service = WCAOneService(
                self.one_client,
                self.one_handler,
                self.one_bindings,
            )
            self.one_bind_command = OneBindCommandService(
                self.one_client,
                self.one_handler,
                self.one_bindings,
            )
            self.pr_service = WCAPRService(
                self.wca_query,
                self.one_client,
                self.one_handler,
                self.command_reaction_feedback,
                self.wca_bindings,
                self.one_bindings,
            )
            self.prpk_service = WCAPRPKService(
                self.wca_query,
                self.one_client,
                self.one_handler,
                self.command_reaction_feedback,
                self.wca_bindings,
                self.one_bindings,
            )
            logger.info("WCA 插件初始化完成")

        except Exception as e:
            logger.error(f"WCA 插件初始化失败: {e}")

    @filter.command("cube帮助", alias={"CUBE帮助"})
    async def cube_help_command(self, event: AstrMessageEvent):
        """显示魔方相关命令帮助"""
        if not self.cube_help_service:
            yield event.plain_result(
                "哎呀，初始化帮助页出错啦，请稍后再试哦！"
            ).use_t2i(False)
            return
        async for result in self.cube_help_service.handle(event):
            yield result

    @filter.command("wca", alias={"WCA"})
    async def wca_command(self, event: AstrMessageEvent):
        """查询 WCA 选手信息"""
        if not self.wca_command_service:
            yield event.plain_result(
                "哎呀，初始化 WCA 查询出错啦，请稍后再试哦！"
            ).use_t2i(False)
            return
        async for result in self.wca_command_service.handle(event):
            yield result

    @filter.command("wca绑定", alias={"WCA绑定"})
    async def wca_bind(self, event: AstrMessageEvent):
        """绑定 QQ 与 WCAID"""
        if not self.wca_bind_command:
            yield event.plain_result(
                "哎呀，初始化 WCA 绑定出错啦，请稍后再试哦！"
            ).use_t2i(False)
            return
        async for result in self.wca_bind_command.handle(event):
            yield result

    @filter.command("wcapic", alias={"WCAPIC"})
    async def wcapic_command(self, event: AstrMessageEvent):
        """个人记录图片：\n
        /wcapic [WCAID/姓名]\n
        /wcapic 2026LIHU01 /wcapic 李华
        """
        if not self.wca_pic:
            yield event.plain_result(
                "哎呀，初始化 WCA 查询出错啦，请稍后再试哦！"
            ).use_t2i(False)
            return

        async for result in self.wca_pic.handle(event):
            yield result

    @filter.command("one", alias={"ONE"})
    async def one_command(self, event: AstrMessageEvent):
        """查询 one 平台个人成绩"""
        if not self.one_service:
            yield event.plain_result(
                "哎呀，初始化 one 查询出错啦，请稍后再试哦！"
            ).use_t2i(False)
            return
        async for result in self.one_service.handle(event):
            yield result

    @filter.command("one绑定", alias={"ONE绑定"})
    async def one_bind(self, event: AstrMessageEvent):
        """绑定 QQ 与 oneID"""
        if not self.one_bind_command:
            yield event.plain_result(
                "哎呀，初始化 one 绑定出错啦，请稍后再试哦！"
            ).use_t2i(False)
            return
        async for result in self.one_bind_command.handle(event):
            yield result

    @filter.command("pr", alias={"PR"})
    async def pr_command(self, event: AstrMessageEvent):
        """跨平台 PR 查询"""
        if not self.pr_service:
            yield event.plain_result(
                "哎呀，初始化 PR 查询出错啦，请稍后再试哦！"
            ).use_t2i(False)
            return
        async for result in self.pr_service.handle(event):
            yield result

    @filter.command("prpk", alias={"PRPK"})
    async def prpk_command(self, event: AstrMessageEvent):
        """跨平台 PR PK 查询"""
        if not self.prpk_service:
            yield event.plain_result(
                "哎呀，初始化 PRPK 查询出错啦，请稍后再试哦！"
            ).use_t2i(False)
            return
        async for result in self.prpk_service.handle(event):
            yield result

    @filter.command("宿敌")
    async def wca_nemesis_command(self, event: AstrMessageEvent):
        """宿敌查询：\n
        /宿敌 [WCAID/姓名]\n
        /宿敌 2026LIHU01 /宿敌 李华
        """
        if not self.wca_nemesis:
            yield event.plain_result(
                "哎呀，初始化 WCA 查询出错啦，请稍后再试哦！"
            ).use_t2i(False)
            return
        async for result in self.wca_nemesis.handle(event):
            yield result

    @filter.command("版本")
    async def wca_version_command(self, event: AstrMessageEvent):
        """数据库版本查询：\n
        /版本
        返回宿敌后端当前使用的数据库导出日期
        """
        if not self.wca_version:
            yield event.plain_result(
                "哎呀，初始化版本查询出错啦，请稍后再试哦！"
            ).use_t2i(False)
            return
        async for result in self.wca_version.handle(event):
            yield result

    @filter.command("wcapk", alias={"WCAPK"})
    async def wca_pk_command(self, event: AstrMessageEvent):
        """wcapk:\n
        /wcapk <选手1> <选手2>\n
        填写 WCAID 或姓名（姓名需唯一匹配）
        """
        if not self.wca_pk:
            yield event.plain_result(
                "哎呀，初始化 WCA 查询出错啦，请稍后再试哦！"
            ).use_t2i(False)
            return
        async for result in self.wca_pk.handle(event):
            yield result

    @filter.command("onepk", alias={"ONEPK"})
    async def one_pk_command(self, event: AstrMessageEvent):
        """onepk:\n
        /onepk <选手1> <选手2>\n
        填写 one 用户名或 ID（姓名需完全匹配）
        """
        if not self.one_pk:
            yield event.plain_result(
                "哎呀，初始化 one 查询出错啦，请稍后再试哦！"
            ).use_t2i(False)
            return
        async for result in self.one_pk.handle(event):
            yield result

    @filter.command("pktwo", alias={"PKTWO"})
    async def pktwo_command(self, event: AstrMessageEvent):
        """pktwo:\n
        /pktwo <姓名>\n
        /pktwo <WCAID> <oneID>\n
        比较同一选手在 WCA 与 one 两个平台的成绩
        """
        if not self.pktwo_service:
            yield event.plain_result(
                "哎呀，初始化双平台对比出错啦，请稍后再试哦！"
            ).use_t2i(False)
            return
        async for result in self.pktwo_service.handle(event):
            yield result

    @filter.command("近期比赛")
    async def recent_competitions_command(self, event: AstrMessageEvent):
        """近期比赛查询：\n
        /近期比赛
        列出近期在中国举办的比赛（包含正在和即将要举办的）
        """
        if not self.recent_competitions:
            yield event.plain_result(
                "哎呀，初始化 WCA 查询出错啦，请稍后再试哦！"
            ).use_t2i(False)
            return
        async for result in self.recent_competitions.handle(event):
            yield result

    async def terminate(self):
        """插件销毁"""
        if self.one_client:
            await self.one_client.close()
        return
