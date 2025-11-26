"""
测试 builder 模块：消息构建器
"""
from __future__ import annotations

import time
import uuid

import pytest

from mofox_wire import MessageBuilder, MessageEnvelope


class TestMessageBuilderBasic:
    """测试消息构建器基本功能"""

    def test_build_simple_text_message(self):
        """测试构建简单文本消息"""
        msg = (
            MessageBuilder()
            .platform("test")
            .from_user("user_1")
            .text("Hello")
            .build()
        )
        
        assert msg["message_info"]["platform"] == "test"
        assert msg["message_info"]["user_info"]["user_id"] == "user_1"
        assert msg["message_segment"]["type"] == "text"
        assert msg["message_segment"]["data"] == "Hello"

    def test_build_requires_segment(self):
        """测试构建消息需要至少一个段落"""
        builder = MessageBuilder().platform("test").from_user("user_1")
        
        with pytest.raises(ValueError, match="需要至少添加一个消息段"):
            builder.build()

    def test_default_direction_is_outgoing(self):
        """测试默认方向是 outgoing"""
        msg = (
            MessageBuilder()
            .platform("test")
            .from_user("user_1")
            .text("Hello")
            .build()
        )
        assert msg["direction"] == "outgoing"

    def test_auto_generate_message_id(self):
        """测试自动生成消息 ID"""
        msg = (
            MessageBuilder()
            .platform("test")
            .from_user("user_1")
            .text("Hello")
            .build()
        )
        
        message_id = msg["message_info"]["message_id"]
        assert message_id is not None
        # 验证是有效的 UUID
        uuid.UUID(message_id)

    def test_auto_generate_time(self):
        """测试自动生成时间戳"""
        before = time.time()
        msg = (
            MessageBuilder()
            .platform("test")
            .from_user("user_1")
            .text("Hello")
            .build()
        )
        after = time.time()
        
        msg_time = msg["message_info"]["time"]
        assert before <= msg_time <= after


class TestMessageBuilderDirection:
    """测试消息方向设置"""

    def test_set_incoming_direction(self):
        """测试设置 incoming 方向"""
        msg = (
            MessageBuilder()
            .direction("incoming")
            .platform("test")
            .from_user("user_1")
            .text("Hello")
            .build()
        )
        assert msg["direction"] == "incoming"

    def test_set_outgoing_direction(self):
        """测试设置 outgoing 方向"""
        msg = (
            MessageBuilder()
            .direction("outgoing")
            .platform("test")
            .from_user("user_1")
            .text("Hello")
            .build()
        )
        assert msg["direction"] == "outgoing"


class TestMessageBuilderUserInfo:
    """测试用户信息设置"""

    def test_from_user_minimal(self):
        """测试最小用户信息"""
        msg = (
            MessageBuilder()
            .platform("test")
            .from_user("user_123")
            .text("Hello")
            .build()
        )
        
        user_info = msg["message_info"]["user_info"]
        assert user_info["user_id"] == "user_123"

    def test_from_user_with_nickname(self):
        """测试带昵称的用户信息"""
        msg = (
            MessageBuilder()
            .from_user("user_123", platform="test", nickname="TestNick")
            .text("Hello")
            .build()
        )
        
        user_info = msg["message_info"]["user_info"]
        assert user_info["user_nickname"] == "TestNick"

    def test_from_user_with_all_fields(self):
        """测试完整用户信息"""
        msg = (
            MessageBuilder()
            .from_user(
                "user_123",
                platform="test",
                nickname="TestNick",
                cardname="CardName",
                user_avatar="https://example.com/avatar.png",
            )
            .text("Hello")
            .build()
        )
        
        user_info = msg["message_info"]["user_info"]
        assert user_info["user_id"] == "user_123"
        assert user_info["user_nickname"] == "TestNick"
        assert user_info["user_cardname"] == "CardName"
        assert user_info["user_avatar"] == "https://example.com/avatar.png"

    def test_from_user_sets_platform(self):
        """测试 from_user 可以设置平台"""
        msg = (
            MessageBuilder()
            .from_user("user_123", platform="qq")
            .text("Hello")
            .build()
        )
        assert msg["message_info"]["platform"] == "qq"


class TestMessageBuilderGroupInfo:
    """测试群组信息设置"""

    def test_from_group_minimal(self):
        """测试最小群组信息"""
        msg = (
            MessageBuilder()
            .platform("test")
            .from_user("user_1")
            .from_group("group_123")
            .text("Hello")
            .build()
        )
        
        group_info = msg["message_info"]["group_info"]
        assert group_info["group_id"] == "group_123"

    def test_from_group_with_name(self):
        """测试带名称的群组信息"""
        msg = (
            MessageBuilder()
            .platform("test")
            .from_user("user_1")
            .from_group("group_123", name="Test Group")
            .text("Hello")
            .build()
        )
        
        group_info = msg["message_info"]["group_info"]
        assert group_info["group_name"] == "Test Group"

    def test_from_group_sets_platform(self):
        """测试 from_group 可以设置平台"""
        msg = (
            MessageBuilder()
            .from_user("user_1")
            .from_group("group_123", platform="discord")
            .text("Hello")
            .build()
        )
        assert msg["message_info"]["platform"] == "discord"


class TestMessageBuilderSegments:
    """测试消息段构建"""

    def test_text_segment(self):
        """测试文本段"""
        msg = (
            MessageBuilder()
            .platform("test")
            .from_user("user_1")
            .text("Hello, World!")
            .build()
        )
        
        assert msg["message_segment"]["type"] == "text"
        assert msg["message_segment"]["data"] == "Hello, World!"

    def test_image_segment(self):
        """测试图片段"""
        msg = (
            MessageBuilder()
            .platform("test")
            .from_user("user_1")
            .image("https://example.com/image.png")
            .build()
        )
        
        assert msg["message_segment"]["type"] == "image"
        assert msg["message_segment"]["data"] == "https://example.com/image.png"

    def test_reply_segment(self):
        """测试回复段"""
        msg = (
            MessageBuilder()
            .platform("test")
            .from_user("user_1")
            .reply("target_msg_123")
            .text("Reply content")
            .build()
        )
        
        segments = msg["message_segment"]
        assert isinstance(segments, list)
        assert segments[0]["type"] == "reply"
        assert segments[0]["data"] == "target_msg_123"

    def test_custom_segment(self):
        """测试自定义段"""
        msg = (
            MessageBuilder()
            .platform("test")
            .from_user("user_1")
            .seg("custom_type", {"key": "value"})
            .build()
        )
        
        assert msg["message_segment"]["type"] == "custom_type"
        assert msg["message_segment"]["data"] == {"key": "value"}

    def test_raw_segment(self):
        """测试原始段"""
        raw_seg = {"type": "at", "data": "user_456"}
        msg = (
            MessageBuilder()
            .platform("test")
            .from_user("user_1")
            .raw_segment(raw_seg)
            .build()
        )
        
        assert msg["message_segment"]["type"] == "at"
        assert msg["message_segment"]["data"] == "user_456"

    def test_multiple_segments(self):
        """测试多个段"""
        msg = (
            MessageBuilder()
            .platform("test")
            .from_user("user_1")
            .text("Hello")
            .image("https://example.com/1.png")
            .text("Goodbye")
            .build()
        )
        
        segments = msg["message_segment"]
        assert isinstance(segments, list)
        assert len(segments) == 3
        assert segments[0]["type"] == "text"
        assert segments[1]["type"] == "image"
        assert segments[2]["type"] == "text"

    def test_single_segment_not_list(self):
        """测试单个段不是列表"""
        msg = (
            MessageBuilder()
            .platform("test")
            .from_user("user_1")
            .text("Single")
            .build()
        )
        
        # 单个段应该是字典而不是列表
        assert isinstance(msg["message_segment"], dict)


class TestMessageBuilderMetadata:
    """测试元数据设置"""

    def test_set_message_id(self):
        """测试设置消息 ID"""
        msg = (
            MessageBuilder()
            .platform("test")
            .from_user("user_1")
            .message_id("custom_id_123")
            .text("Hello")
            .build()
        )
        assert msg["message_info"]["message_id"] == "custom_id_123"

    def test_set_timestamp_ms(self):
        """测试设置毫秒时间戳"""
        msg = (
            MessageBuilder()
            .platform("test")
            .from_user("user_1")
            .timestamp_ms(1700000000000)
            .text("Hello")
            .build()
        )
        assert msg["timestamp_ms"] == 1700000000000

    def test_set_timestamp_ms_auto(self):
        """测试自动设置毫秒时间戳"""
        before_ms = int(time.time() * 1000)
        msg = (
            MessageBuilder()
            .platform("test")
            .from_user("user_1")
            .timestamp_ms()  # 不传参数，自动生成
            .text("Hello")
            .build()
        )
        after_ms = int(time.time() * 1000)
        
        assert before_ms <= msg["timestamp_ms"] <= after_ms

    def test_set_metadata(self):
        """测试设置元数据"""
        metadata = {"trace_id": "trace_123", "custom": "value"}
        msg = (
            MessageBuilder()
            .platform("test")
            .from_user("user_1")
            .metadata(metadata)
            .text("Hello")
            .build()
        )
        assert msg["metadata"] == metadata


class TestMessageBuilderFormatInfo:
    """测试格式信息设置"""

    def test_set_format_info(self):
        """测试设置格式信息"""
        msg = (
            MessageBuilder()
            .platform("test")
            .from_user("user_1")
            .format_info(
                content_format=["text", "image"],
                accept_format=["text", "image", "video"],
            )
            .text("Hello")
            .build()
        )
        
        format_info = msg["message_info"]["format_info"]
        assert format_info["content_format"] == ["text", "image"]
        assert format_info["accept_format"] == ["text", "image", "video"]


class TestMessageBuilderChaining:
    """测试链式调用"""

    def test_method_chaining(self):
        """测试方法链式调用"""
        msg = (
            MessageBuilder()
            .direction("incoming")
            .platform("qq")
            .from_user("user_123", nickname="Test")
            .from_group("group_456", name="TestGroup")
            .message_id("msg_789")
            .timestamp_ms(1700000000000)
            .metadata({"key": "value"})
            .text("Hello")
            .image("https://example.com/1.png")
            .build()
        )
        
        assert msg["direction"] == "incoming"
        assert msg["message_info"]["platform"] == "qq"
        assert msg["message_info"]["user_info"]["user_id"] == "user_123"
        assert msg["message_info"]["group_info"]["group_id"] == "group_456"
        assert msg["message_info"]["message_id"] == "msg_789"
        assert msg["timestamp_ms"] == 1700000000000
        assert msg["metadata"]["key"] == "value"
        assert len(msg["message_segment"]) == 2

    def test_builder_reuse(self):
        """测试构建器不能重用（每次构建独立）"""
        builder = MessageBuilder().platform("test").from_user("user_1")
        
        msg1 = builder.text("Message 1").build()
        
        # 创建新的构建器
        builder2 = MessageBuilder().platform("test").from_user("user_2")
        msg2 = builder2.text("Message 2").build()
        
        assert msg1["message_info"]["user_info"]["user_id"] == "user_1"
        assert msg2["message_info"]["user_info"]["user_id"] == "user_2"
