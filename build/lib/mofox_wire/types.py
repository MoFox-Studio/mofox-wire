from __future__ import annotations

from typing import Any, Dict, List, Literal, NotRequired, TypedDict, Required

MessageDirection = Literal["incoming", "outgoing"]

# ----------------------------
# maim_message 风格的 TypedDict
# ----------------------------


class SegPayload(TypedDict, total=False):
    """
    对齐 maim_message.Seg 的片段定义，使用纯 dict 便于 JSON 传输。
    """

    type: Required[str]
    data: Required[str | List["SegPayload"]]
    translated_data: NotRequired[str | List["SegPayload"]]


class UserInfoPayload(TypedDict, total=False):
    platform: NotRequired[str]
    user_id: Required[str]
    user_nickname: NotRequired[str]
    user_cardname: NotRequired[str]
    user_avatar: NotRequired[str]


class GroupInfoPayload(TypedDict, total=False):
    platform: NotRequired[str]
    group_id: Required[str]
    group_name: NotRequired[str]


class FormatInfoPayload(TypedDict, total=False):
    content_format: NotRequired[List[str]]
    accept_format: NotRequired[List[str]]


class TemplateInfoPayload(TypedDict, total=False):
    template_items: NotRequired[Dict[str, str]]
    template_name: NotRequired[Dict[str, str]]
    template_default: NotRequired[bool]


class MessageInfoPayload(TypedDict, total=False):
    platform: Required[str]
    message_id: Required[str]
    time: NotRequired[float]
    group_info: NotRequired[GroupInfoPayload]
    user_info: NotRequired[UserInfoPayload]
    format_info: NotRequired[FormatInfoPayload]
    template_info: NotRequired[TemplateInfoPayload]
    additional_config: NotRequired[Dict[str, Any]]

# ----------------------------
# MessageEnvelope
# ----------------------------


class MessageEnvelope(TypedDict, total=False):
    """
    mofox-bus 传输层统一使用的消息信封。

    - 采用 maim_message 风格：message_info + message_segment。
    """

    direction: MessageDirection
    message_info: Required[MessageInfoPayload]
    message_segment: Required[SegPayload] | List[SegPayload]
    raw_message: NotRequired[Any]
    raw_bytes: NotRequired[bytes]
    message_chain: NotRequired[List[SegPayload]]  # seglist 的直观别名
    platform: NotRequired[str]  # 快捷访问，等价于 message_info.platform
    message_id: NotRequired[str]  # 快捷访问，等价于 message_info.message_id
    timestamp_ms: NotRequired[int]
    correlation_id: NotRequired[str]
    schema_version: NotRequired[int]
    metadata: NotRequired[Dict[str, Any]]

__all__ = [
    # maim_message style payloads
    "SegPayload",
    "UserInfoPayload",
    "GroupInfoPayload",
    "FormatInfoPayload",
    "TemplateInfoPayload",
    "MessageInfoPayload",
    # legacy content style
    "MessageDirection",
    "MessageEnvelope",
]
