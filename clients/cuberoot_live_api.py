"""CubeRoot 近期 WCA 直播成绩客户端。"""

from typing import Any

import aiohttp


class CubeRootLiveAPIClient:
    """读取 CubeRoot 的选手直播成绩和实时排名。"""

    BASE_URL = "https://api.cuberoot.me/v1"

    def __init__(self, timeout_seconds: float = 15.0):
        self.timeout = aiohttp.ClientTimeout(total=timeout_seconds)

    async def _request_json(
        self,
        method: str,
        path: str,
        **kwargs: Any,
    ) -> Any:
        url = f"{self.BASE_URL}{path}"
        async with aiohttp.ClientSession(timeout=self.timeout) as session:
            async with session.request(method, url, **kwargs) as response:
                if response.status != 200:
                    raise RuntimeError(f"CubeRoot API 请求失败：HTTP {response.status}")
                return await response.json()

    async def get_person_live_results(self, wca_id: str) -> dict[str, Any]:
        data = await self._request_json(
            "GET",
            "/wca/person-live-results",
            params={"wcaId": wca_id, "v": "1"},
        )
        if not isinstance(data, dict):
            raise RuntimeError("CubeRoot API 返回格式异常")
        return data

    async def get_rank(
        self,
        event_id: str,
        result_type: str,
        value: int,
        country: str = "",
    ) -> dict[str, Any] | None:
        data = await self._request_json(
            "GET",
            "/wca/rank-for",
            params={
                "event": event_id,
                "type": result_type,
                "centis": str(value),
                "country": country,
            },
        )
        return data if isinstance(data, dict) else None
