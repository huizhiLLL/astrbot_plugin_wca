import asyncio
from typing import Any

import aiohttp
from astrbot.api import logger


PERSONAL_RECORD_API_BASE = "https://ss.sxmfxh.com"
REQUEST_TIMEOUT = 10


def format_time_ms(time_ms: int | None) -> str:
    if not time_ms or time_ms == 999999:
        return "DNF"

    try:
        time_ms_int = int(time_ms)
        if time_ms_int <= 0 or time_ms_int == 999999:
            return "DNF"

        time_str = str(time_ms_int).zfill(6)
        minutes = int(time_str[:2])
        seconds_str = time_str[2:4]
        milliseconds = time_str[4:6]

        if minutes > 0:
            return f"{minutes}:{seconds_str}.{milliseconds}"
        return f"{int(seconds_str)}.{milliseconds}"
    except (ValueError, TypeError):
        return "DNF"


EVENT_ID_TO_CODE = {
    1: "三阶",
    2: "二阶",
    3: "四阶",
    4: "五阶",
    5: "六阶",
    6: "七阶",
    7: "三单",
    8: "斜转",
    9: "金字塔",
    10: "五魔",
    11: "三盲",
    12: "四盲",
    13: "五盲",
    14: "多盲",
    15: "SQ1",
    16: "最少步",
    17: "魔表",
    18: "枫叶",
    19: "FTO",
    20: "镜面",
    41: "智能三阶",
    42: "智能三单",
    43: "智能二阶",
    61: "三阶单面",
    91: "趣味1",
    92: "趣味2",
    93: "趣味3",
    94: "趣味4",
    95: "趣味5",
}


class PersonalRecordAPIClient:
    def __init__(self, base_url: str = PERSONAL_RECORD_API_BASE, timeout: int = REQUEST_TIMEOUT):
        self.base_url = base_url.rstrip("/")
        self.timeout = aiohttp.ClientTimeout(total=timeout)
        self.session: aiohttp.ClientSession | None = None

    async def _ensure_session(self):
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession(timeout=self.timeout)
        return self.session

    async def search_user(self, search_input: str, page: int = 1, size: int = 5) -> dict[str, Any]:
        session = await self._ensure_session()
        url = f"{self.base_url}/api/user"
        params = {
            "type": "list",
            "searchInput": search_input,
            "page": page,
            "size": size,
        }

        try:
            async with session.get(url, params=params) as response:
                if response.status == 200:
                    return await response.json()
                text = await response.text()
                return {
                    "code": response.status,
                    "err": f"请求失败，状态码：{response.status}",
                    "error": text,
                }
        except asyncio.TimeoutError:
            return {
                "code": 500,
                "err": "请求超时",
                "error": f"请求超时（{self.timeout.total}秒）",
            }
        except Exception as e:
            logger.error(f"搜索 one 用户异常: {e}")
            return {
                "code": 500,
                "err": "请求异常",
                "error": str(e),
            }

    async def get_personal_records(self, user_id: int) -> dict[str, Any]:
        session = await self._ensure_session()
        url = f"{self.base_url}/api/grade/grade-rank"
        params = {"u_id": user_id}

        try:
            async with session.get(url, params=params) as response:
                if response.status == 200:
                    return await response.json()
                text = await response.text()
                return {
                    "code": response.status,
                    "err": f"请求失败，状态码：{response.status}",
                    "error": text,
                }
        except asyncio.TimeoutError:
            return {
                "code": 500,
                "err": "请求超时",
                "error": f"请求超时（{self.timeout.total}秒）",
            }
        except Exception as e:
            logger.error(f"获取 one 个人记录异常: {e}")
            return {
                "code": 500,
                "err": "请求异常",
                "error": str(e),
            }

    async def close(self):
        if self.session and not self.session.closed:
            await self.session.close()


class OneRecordHandler:
    def __init__(self, personal_record_client: PersonalRecordAPIClient):
        self.personal_record_client = personal_record_client

    async def resolve_user(self, search_input: str) -> tuple[int | None, str | None, str | None]:
        search_input = search_input.strip()

        if search_input.isdigit():
            return int(search_input), None, None

        search_result = await self.personal_record_client.search_user(search_input, page=1, size=5)

        if search_result.get("code") != 10000:
            error_msg = search_result.get("err", "未知错误")
            return None, None, f"哎呀，搜索用户失败了呢...\n错误：{error_msg}"

        users = search_result.get("data", [])
        if not users:
            return None, None, f"找不到这个 one 用户呢：{search_input}"

        exact_matches = [user for user in users if user.get("u_name") == search_input]
        if not exact_matches:
            return None, None, (
                f"没找到完全匹配的 one 用户「{search_input}」呢~\n"
                "提示：姓名查询需要完全匹配哦"
            )

        if len(exact_matches) > 1:
            lines = [f"哎呀，有好几个叫「{search_input}」的呢，请用 ID 查询哦：\n"]
            for i, user in enumerate(exact_matches, 1):
                lines.append(f"{i}. {user.get('u_name')}（ID: {user.get('u_id')}）")
            lines.append("\n使用方法：/one <ID>")
            return None, None, "\n".join(lines)

        user_id = exact_matches[0].get("u_id")
        user_name = exact_matches[0].get("u_name")
        return user_id, user_name, None
