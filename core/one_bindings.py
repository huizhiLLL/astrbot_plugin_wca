from __future__ import annotations

import json
from typing import Any

from astrbot.api import logger
from astrbot.api.star import StarTools

from .wca_bindings import (
    extract_first_mentioned_qq,
    strip_first_command_token,
    strip_mentions,
)


class OneBindingStore:
    def __init__(self, plugin_name: str = "astrbot_plugin_wca"):
        self.data_dir = StarTools.get_data_dir(plugin_name)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.bindings_path = self.data_dir / "one_bindings.json"

    def load(self) -> dict[str, int]:
        if not self.bindings_path.exists():
            self.save({})
            return {}
        try:
            data = json.loads(self.bindings_path.read_text("utf-8"))
        except json.JSONDecodeError:
            logger.error(f"one 绑定文件解析失败，已重置: {self.bindings_path}")
            self.save({})
            return {}
        if not isinstance(data, dict):
            self.save({})
            return {}

        cleaned: dict[str, int] = {}
        for qq_id, one_id in data.items():
            qq_text = str(qq_id).strip()
            normalized_one_id = normalize_one_id(one_id)
            if qq_text.isdigit() and normalized_one_id is not None:
                cleaned[qq_text] = normalized_one_id
        if cleaned != data:
            self.save(cleaned)
        return cleaned

    def save(self, data: dict[str, int]) -> None:
        self.bindings_path.parent.mkdir(parents=True, exist_ok=True)
        self.bindings_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )

    def get(self, qq_id: str | int | None) -> int | None:
        if qq_id is None:
            return None
        return self.load().get(str(qq_id).strip())

    def set(self, qq_id: str | int, one_id: str | int) -> None:
        normalized_one_id = normalize_one_id(one_id)
        if normalized_one_id is None:
            raise ValueError("oneID 必须是正整数")
        data = self.load()
        data[str(qq_id).strip()] = normalized_one_id
        self.save(data)


def normalize_one_id(value: Any) -> int | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text.isdigit():
        return None
    one_id = int(text)
    return one_id if one_id > 0 else None


def resolve_bound_one_search_input(
    event: Any,
    bindings: OneBindingStore,
) -> tuple[str, str | None, str | None]:
    search_input = strip_first_command_token(getattr(event, "message_str", ""))
    target_qq = extract_first_mentioned_qq(event)

    if target_qq:
        bound_one_id = bindings.get(target_qq)
        if bound_one_id is None:
            return "", "target", target_qq
        return str(bound_one_id), None, target_qq

    search_input = strip_mentions(search_input)
    if search_input:
        return search_input, None, None

    sender_getter = getattr(event, "get_sender_id", None)
    sender_qq = sender_getter() if callable(sender_getter) else None
    bound_one_id = bindings.get(sender_qq)
    if bound_one_id is None:
        return "", "sender", str(sender_qq) if sender_qq is not None else None
    return str(bound_one_id), None, str(sender_qq) if sender_qq is not None else None
