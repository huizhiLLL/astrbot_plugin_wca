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
    getter = getattr(event, "get_messages", None)
    if callable(getter):
        try:
            messages = getter() or []
        except Exception:
            messages = []
        for seg in list(messages)[1:]:
            if At is not None and isinstance(seg, At):
                qq = getattr(seg, "qq", None)
                if qq is not None:
                    text = str(qq).strip()
                    if text.isdigit():
                        return text
            for attr in ("qq", "user_id", "userId"):
                value = getattr(seg, attr, None)
                if value is not None and str(value).strip().isdigit():
                    return str(value).strip()

    raw = getattr(event, "message_str", "")
    if isinstance(raw, str):
        for arg in raw.split():
            if arg.startswith("@") and arg[1:].isdigit():
                return arg[1:]
        m = re.search(r"qq=(\d{5,})", raw)
        if m:
            return m.group(1)
    return None


def strip_command_prefix(message: str, command_name: str) -> str:
    text = (message or "").strip()
    pattern = rf"^/?{re.escape(command_name)}"
    return re.sub(pattern, "", text, count=1).strip()


def strip_mentions(text: str) -> str:
    text = re.sub(r"\[CQ:at,[^\]]+\]", " ", text)
    text = re.sub(r"@\S+", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()
