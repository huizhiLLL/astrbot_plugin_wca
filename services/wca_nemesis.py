import aiohttp
from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent

from ..core.wca_person_lookup import WCAPersonLookupService
from ..core.wca_query import WCAQuery


class WCANemesisApiClient:
    def __init__(self, api_base: str):
        self.api_base = api_base.rstrip("/")

    async def get_nemesis(self, person_id: str) -> dict | None:
        return await self._request_json(
            method="post",
            path="/nemesis",
            json_payload={"person_id": person_id},
            log_name="宿敌接口",
        )

    async def get_version(self) -> str | None:
        data = await self._request_json(
            method="get",
            path="/version",
            log_name="版本接口",
        )
        if not isinstance(data, dict):
            return None

        export_date = str(data.get("export_date", "")).strip()
        if not export_date:
            logger.error(f"版本接口缺少 export_date 字段: {data}")
            return None
        return export_date

    async def _request_json(
        self,
        method: str,
        path: str,
        *,
        json_payload: dict | None = None,
        log_name: str,
    ) -> dict | None:
        url = f"{self.api_base}{path}"
        try:
            async with aiohttp.ClientSession() as session:
                request = getattr(session, method)
                async with request(
                    url,
                    json=json_payload,
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    if resp.status != 200:
                        error_text = (await resp.text()).strip()
                        logger.error(
                            f"{log_name}调用失败，状态码: {resp.status}, 响应: {error_text[:200]}"
                        )
                        return None
                    data = await resp.json()
                    if not isinstance(data, dict):
                        logger.error(f"{log_name}返回格式异常: {data}")
                        return None
                    if "error" in data:
                        logger.error(f"{log_name}返回错误: {data.get('error')}")
                        return None
                    return data
        except Exception as e:
            logger.error(f"调用{log_name}异常: {e}")
            return None


class WCANemesisService:
    def __init__(self, query: WCAQuery, api_base: str):
        self.query = query
        self.client = WCANemesisApiClient(api_base)
        self.lookup = WCAPersonLookupService(query)

    async def handle(self, event: AstrMessageEvent):
        message_str = event.message_str.strip()
        parts = message_str.split(maxsplit=1)
        if len(parts) < 2:
            yield event.plain_result(
                "请提供 WCAID 或姓名哦\n"
                "用法: /宿敌 [WCAID/姓名]\n"
                "示例: /宿敌 2026LIHU01\n"
            ).use_t2i(False)
            return

        search_input = parts[1].strip()

        try:
            result = await self.lookup.resolve_unique(search_input)
            if result.status == "not_found":
                yield event.plain_result(
                    f"抱歉啦，没有找到关于 {search_input} 的信息哦\n"
                    "提示：可以使用 WCAID（如：2026LIHU01）或姓名进行搜索"
                ).use_t2i(False)
                return

            if result.status == "ambiguous":
                yield event.plain_result(
                    self.lookup.format_multiple_persons_prompt(
                        result.persons or [],
                        "/宿敌 <WCAID>",
                    )
                ).use_t2i(False)
                return

            picked = result.picked or {}
            pinfo = self.lookup.get_person_info(picked)
            person_id = pinfo.get("wca_id", pinfo.get("id", ""))
            if not person_id:
                yield event.plain_result("哎呀，选手信息不完整，无法查询成绩哦").use_t2i(False)
                return

            yield event.plain_result("收到啦！正在为您寻找宿敌，请稍候哦...").use_t2i(False)

            nemesis_data = await self.client.get_nemesis(person_id)
            if not nemesis_data:
                yield event.plain_result("查询宿敌失败了，请稍后重试哦").use_t2i(False)
                return

            text = self._format_nemesis_result(
                person_info=pinfo,
                person_id=person_id,
                nemesis_data=nemesis_data,
            )
            yield event.plain_result(text).use_t2i(False)

        except Exception as e:
            logger.error(f"宿敌查询异常: {e}")
            yield event.plain_result(f"执行出错: {str(e)}").use_t2i(False)

    def _format_nemesis_result(
        self,
        *,
        person_info: dict,
        person_id: str,
        nemesis_data: dict,
    ) -> str:
        world_count = nemesis_data.get("world_count", 0)
        continent_count = nemesis_data.get("continent_count", 0)
        country_count = nemesis_data.get("country_count", 0)
        world_list = nemesis_data.get("world_list", [])
        continent_list = nemesis_data.get("continent_list", [])
        country_list = nemesis_data.get("country_list", [])

        if world_count == 0:
            return "哇！该选手目前还没有宿敌呢，太强啦~"

        person_name = person_info.get("name", "未知")
        continent = str(nemesis_data.get("continent", "")).strip()
        continent_label = f"洲" if continent else "洲"

        title = f"选手({person_id}) 的宿敌结果出来啦："
        summary = (
            f"世界：{world_count}人，"
            f"{continent_label}：{continent_count}人，"
            f"地区：{country_count}人"
        )

        details: list[str] = []
        if 0 < world_count <= 10:
            details.append("世界：\n" + self._format_people(world_list))
        if 0 < continent_count <= 10:
            details.append(f"洲：\n" + self._format_people(continent_list))
        if 0 < country_count <= 10:
            details.append("地区：\n" + self._format_people(country_list))

        return "\n".join([title, summary] + (["", "\n\n".join(details)] if details else []))

    def _format_people(self, people: list[dict[str, str]]) -> str:
        lines: list[str] = []
        for p in people:
            pid = p.get("wca_id", "")
            name = p.get("name", "")
            ctry = p.get("country_id", "")
            ctry_str = f" [{ctry}]" if ctry else ""
            lines.append(f"- {name} ({pid}){ctry_str}")
        return "\n".join(lines)


class WCAVersionService:
    def __init__(self, api_base: str):
        self.client = WCANemesisApiClient(api_base)

    async def handle(self, event: AstrMessageEvent):
        export_date = await self.client.get_version()
        if not export_date:
            yield event.plain_result("查询版本失败了，请稍后重试哦").use_t2i(False)
            return

        yield event.plain_result(
            f"当前宿敌数据库版本日期是：{export_date}"
        ).use_t2i(False)
