"""
测试 types 模块：消息类型定义
"""
from __future__ import annotations

import pytest

from mofox_wire.types import (
    FormatInfoPayload,
    GroupInfoPayload,
    MessageDirection,
    MessageEnvelope,
    MessageInfoPayload,
    SegPayload,
    TemplateInfoPayload,
    UserInfoPayload,
)


class TestMessageDirection:
    """测试消息方向类型"""

    def test_incoming_direction(self):
        """测试入站方向"""
        direction: MessageDirection = "incoming"
        assert direction == "incoming"

    def test_outgoing_direction(self):
        """测试出站方向"""
        direction: MessageDirection = "outgoing"
        assert direction == "outgoing"


class TestSegPayload:
    """测试消息段负载"""

    def test_text_segment(self):
        """测试文本段"""
        seg: SegPayload = {"type": "text", "data": "Hello, World!"}
        assert seg["type"] == "text"
        assert seg["data"] == "Hello, World!"

    def test_image_segment(self):
        """测试图片段"""
        seg: SegPayload = {"type": "image", "data": "https://example.com/image.png"}
        assert seg["type"] == "image"

    def test_nested_segment(self):
        """测试嵌套段"""
        inner: SegPayload = {"type": "text", "data": "inner"}
        outer: SegPayload = {"type": "quote", "data": [inner]}
        assert outer["type"] == "quote"
        assert isinstance(outer["data"], list)
        assert outer["data"][0]["type"] == "text"

    def test_segment_with_translated_data(self):
        """测试带翻译数据的段"""
        seg: SegPayload = {
            "type": "text",
            "data": "Hello",
            "translated_data": "你好",
        }
        assert seg["translated_data"] == "你好"


class TestUserInfoPayload:
    """测试用户信息负载"""

    def test_minimal_user_info(self):
        """测试最小用户信息"""
        user: UserInfoPayload = {"user_id": "12345"}
        assert user["user_id"] == "12345"

    def test_full_user_info(self):
        """测试完整用户信息"""
        user: UserInfoPayload = {
            "platform": "qq",
            "user_id": "12345",
            "user_nickname": "TestUser",
            "user_cardname": "Card Name",
            "user_avatar": "https://example.com/avatar.png",
        }
        assert user["platform"] == "qq"
        assert user["user_nickname"] == "TestUser"
        assert user["user_cardname"] == "Card Name"
        assert user["user_avatar"] == "https://example.com/avatar.png"


class TestGroupInfoPayload:
    """测试群组信息负载"""

    def test_minimal_group_info(self):
        """测试最小群组信息"""
        group: GroupInfoPayload = {"group_id": "group_123"}
        assert group["group_id"] == "group_123"

    def test_full_group_info(self):
        """测试完整群组信息"""
        group: GroupInfoPayload = {
            "platform": "qq",
            "group_id": "group_123",
            "group_name": "Test Group",
        }
        assert group["platform"] == "qq"
        assert group["group_name"] == "Test Group"


class TestFormatInfoPayload:
    """测试格式信息负载"""

    def test_format_info(self):
        """测试格式信息"""
        format_info: FormatInfoPayload = {
            "content_format": ["text", "image"],
            "accept_format": ["text", "image", "video"],
        }
        assert "text" in format_info["content_format"]
        assert "video" in format_info["accept_format"]


class TestTemplateInfoPayload:
    """测试模板信息负载"""

    def test_template_info(self):
        """测试模板信息"""
        template: TemplateInfoPayload = {
            "template_items": {"key1": "value1"},
            "template_name": {"name": "template1"},
            "template_default": True,
        }
        assert template["template_items"]["key1"] == "value1"
        assert template["template_default"] is True


class TestMessageInfoPayload:
    """测试消息信息负载"""

    def test_minimal_message_info(self):
        """测试最小消息信息"""
        info: MessageInfoPayload = {
            "platform": "test",
            "message_id": "msg_123",
        }
        assert info["platform"] == "test"
        assert info["message_id"] == "msg_123"

    def test_full_message_info(self):
        """测试完整消息信息"""
        info: MessageInfoPayload = {
            "platform": "qq",
            "message_id": "msg_123",
            "time": 1700000000.0,
            "group_info": {"group_id": "group_1"},
            "user_info": {"user_id": "user_1"},
            "format_info": {"content_format": ["text"]},
            "template_info": {"template_default": False},
            "additional_config": {"custom_key": "custom_value"},
        }
        assert info["time"] == 1700000000.0
        assert info["group_info"]["group_id"] == "group_1"
        assert info["additional_config"]["custom_key"] == "custom_value"


class TestMessageEnvelope:
    """测试消息信封"""

    def test_minimal_envelope(self):
        """测试最小消息信封"""
        envelope: MessageEnvelope = {
            "message_info": {
                "platform": "test",
                "message_id": "msg_1",
            },
            "message_segment": {"type": "text", "data": "hello"},
        }
        assert envelope["message_info"]["platform"] == "test"
        assert envelope["message_segment"]["type"] == "text"

    def test_envelope_with_direction(self):
        """测试带方向的消息信封"""
        envelope: MessageEnvelope = {
            "direction": "incoming",
            "message_info": {
                "platform": "test",
                "message_id": "msg_1",
            },
            "message_segment": {"type": "text", "data": "hello"},
        }
        assert envelope["direction"] == "incoming"

    def test_envelope_with_message_chain(self):
        """测试带消息链的信封"""
        envelope: MessageEnvelope = {
            "message_info": {
                "platform": "test",
                "message_id": "msg_1",
            },
            "message_segment": {"type": "text", "data": "hello"},
            "message_chain": [
                {"type": "text", "data": "hello"},
                {"type": "image", "data": "url"},
            ],
        }
        assert len(envelope["message_chain"]) == 2

    def test_envelope_with_metadata(self):
        """测试带元数据的信封"""
        envelope: MessageEnvelope = {
            "message_info": {
                "platform": "test",
                "message_id": "msg_1",
            },
            "message_segment": {"type": "text", "data": "hello"},
            "metadata": {"trace_id": "trace_123", "custom": "data"},
        }
        assert envelope["metadata"]["trace_id"] == "trace_123"

    def test_envelope_with_all_fields(self):
        """测试包含所有字段的信封"""
        envelope: MessageEnvelope = {
            "direction": "outgoing",
            "message_info": {
                "platform": "qq",
                "message_id": "msg_1",
                "time": 1700000000.0,
            },
            "message_segment": {"type": "text", "data": "hello"},
            "raw_message": {"original": "data"},
            "raw_bytes": b"raw",
            "message_chain": [{"type": "text", "data": "hello"}],
            "platform": "qq",
            "message_id": "msg_1",
            "timestamp_ms": 1700000000000,
            "correlation_id": "corr_123",
            "schema_version": 1,
            "metadata": {"key": "value"},
        }
        assert envelope["timestamp_ms"] == 1700000000000
        assert envelope["correlation_id"] == "corr_123"
        assert envelope["schema_version"] == 1
