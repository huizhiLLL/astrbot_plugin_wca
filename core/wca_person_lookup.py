from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .wca_query import WCAQuery


@dataclass
class PersonLookupResult:
    status: str
    picked: dict[str, Any] | None = None
    persons: list[dict[str, Any]] | None = None


class WCAPersonLookupService:
    def __init__(self, query: "WCAQuery"):
        self.query = query

    async def search(self, keyword: str) -> list[dict[str, Any]]:
        return await self.query.search_person(keyword)

    async def resolve_unique(
        self,
        keyword: str,
        *,
        prefer_exact_name: bool = False,
        preferred_wca_id: str | None = None,
    ) -> PersonLookupResult:
        persons = await self.search(keyword)
        if not persons:
            return PersonLookupResult(status="not_found", persons=[])

        if preferred_wca_id:
            for item in persons:
                person_info = self.get_person_info(item)
                if str(person_info.get("wca_id", "")).upper() == preferred_wca_id.upper():
                    return PersonLookupResult(status="ok", picked=item, persons=persons)

        if len(persons) == 1:
            return PersonLookupResult(status="ok", picked=persons[0], persons=persons)

        if prefer_exact_name:
            exact = [
                item
                for item in persons
                if self.get_person_info(item).get("name") == keyword
            ]
            if len(exact) == 1:
                return PersonLookupResult(status="ok", picked=exact[0], persons=persons)

        return PersonLookupResult(status="ambiguous", persons=persons)

    def format_multiple_persons_prompt(
        self,
        persons: list[dict[str, Any]],
        usage: str,
        *,
        intro: str = "找到了多个匹配的选手，请使用 WCAID 查询具体哪位呢：\n",
    ) -> str:
        lines = [intro]
        for i, item in enumerate(persons[:10], 1):
            person_info = self.get_person_info(item)
            person_id = person_info.get("wca_id", "未知")
            person_name = person_info.get("name", "未知")
            country = person_info.get("country_iso2", "")
            country_str = f" [{country}]" if country else ""
            lines.append(f"{i}. {person_name} ({person_id}){country_str}")

        if len(persons) > 10:
            lines.append(f"\n... 还有 {len(persons) - 10} 个结果未显示哦")
        lines.append(f"\n使用方法: {usage}")
        return "\n".join(lines)

    @staticmethod
    def get_person_info(person_entry: dict[str, Any] | None) -> dict[str, Any]:
        if isinstance(person_entry, dict):
            person_info = person_entry.get("person")
            if isinstance(person_info, dict):
                return person_info
            return person_entry
        return {}

    @classmethod
    def get_person_id(cls, person_entry: dict[str, Any] | None) -> str:
        person_info = cls.get_person_info(person_entry)
        return str(person_info.get("wca_id", "") or person_info.get("id", ""))
