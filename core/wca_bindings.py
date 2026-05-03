from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from astrbot.api import logger
from astrbot.api.star import StarTools

try:
    from astrbot.core.message.components import At
except Exception:  # pragma: no cover
    At = None

WCA_ID_PATTERN = re.compile(r"^[0-9]{4}[A-Z]{4}[0-9]{2}$")


class WCABindingStore:
    def __init__(self, plugin_name: str = "astrbot_plugin_wca"):
        self.data_dir = StarTools.get_data_dir(plugin_name)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.bindings_path = self.data_dir / "wca_bindings.json"

    def load(self) -> dict[str, str]:
        if not self.bindings_path.exists():
            self.save({})
            return {}
        try:
            data = json.loads(self.bindings_path.read_text("utf-8"))
        except json.JSONDecodeError:
            logger.error(f"WCA 绑定文件解析失败，已重置: {self.bindings_path}")
            self.save({})
            return {}
        if not isinstance(data, dict):
            self.save({})
            return {}
        cleaned: dict[str, str] = {}
        for qq_id, wca_id in data.items():
            qq_text = str(qq_id).strip()
            wca_text = normalize_wca_id(wca_id)
            if qq_text.isdigit() and wca_text:
                cleaned[qq_text] = wca_text
        if cleaned != data:
            self.save(cleaned)
        return cleaned

    def save(self, data: dict[str, str]) -> None:
        self.bindings_path.parent.mkdir(parents=True, exist_ok=True)
        self.bindings_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )

    def get(self, qq_id: str | int | None) -> str | None:
        if qq_id is None:
            return None
        return self.load().get(str(qq_id).strip())

    def set(self, qq_id: str | int, wca_id: str) -> None:
        data = self.load()
        data[str(qq_id).strip()] = normalize_wca_id(wca_id) or wca_id
        self.save(data)


def normalize_wca_id(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip().upper()
    return text if WCA_ID_PATTERN.fullmatch(text) else None


def extract_first_mentioned_qq(event: Any) -> str | None:
    mentioned = extract_mentioned_qqs(event)
    return mentioned[0] if mentioned else None


def extract_mentioned_qqs(event: Any) -> list[str]:
    qqs: list[str] = []

    def append_qq(value: Any) -> None:
        if value is None:
            return
        text = str(value).strip()
        if text.isdigit() and text not in qqs:
            qqs.append(text)

    getter = getattr(event, "get_messages", None)
    if callable(getter):
        try:
            messages = getter()
        except Exception:
            messages = []
        if not isinstance(messages, list):
            messages = []
        for seg in messages[1:]:
            if At is not None and isinstance(seg, At):
                append_qq(getattr(seg, "qq", None))
                continue
            for attr in ("qq", "user_id", "userId"):
                append_qq(getattr(seg, attr, None))

    raw = getattr(event, "message_str", "")
    if isinstance(raw, str):
        for arg in raw.split():
            if arg.startswith("@") and arg[1:].isdigit():
                append_qq(arg[1:])
        for match in re.finditer(r"qq=(\d{5,})", raw):
            append_qq(match.group(1))
    return qqs


def resolve_bound_wca_search_input(
    event: Any,
    bindings: WCABindingStore,
) -> tuple[str, str | None, str | None]:
    search_input = strip_first_command_token(getattr(event, "message_str", ""))
    target_qq = extract_first_mentioned_qq(event)

    if target_qq:
        bound_wca_id = bindings.get(target_qq)
        if not bound_wca_id:
            return "", "target", target_qq
        return bound_wca_id, None, target_qq

    search_input = strip_mentions(search_input)
    if search_input:
        return search_input, None, None

    sender_getter = getattr(event, "get_sender_id", None)
    sender_qq = sender_getter() if callable(sender_getter) else None
    bound_wca_id = bindings.get(sender_qq)
    if not bound_wca_id:
        return "", "sender", str(sender_qq) if sender_qq is not None else None
    return bound_wca_id, None, str(sender_qq) if sender_qq is not None else None


def strip_command_prefix(message: str, command_name: str) -> str:
    text = (message or "").strip()
    pattern = rf"^/?{re.escape(command_name)}"
    return re.sub(pattern, "", text, count=1).strip()


def strip_first_command_token(message: str) -> str:
    text = (message or "").strip()
    if not text:
        return ""
    parts = text.split(maxsplit=1)
    return parts[1].strip() if len(parts) > 1 else ""


def strip_mentions(text: str) -> str:
    text = re.sub(r"\[CQ:at,[^\]]+\]", " ", text)
    text = re.sub(r"@\S+", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()
