"""
测试 codec 模块：消息序列化和反序列化
"""
from __future__ import annotations

import pytest

from mofox_wire import (
    MessageBuilder,
    MessageEnvelope,
    dumps_message,
    dumps_messages,
    loads_message,
    loads_messages,
)
from mofox_wire.codec import DEFAULT_SCHEMA_VERSION, _strip_raw_bytes


class TestDumpsMessage:
    """测试单条消息序列化"""

    def test_dumps_simple_text_message(self, sample_text_message: MessageEnvelope):
        """测试序列化简单文本消息"""
        result = dumps_message(sample_text_message)
        assert isinstance(result, bytes)
        assert b"Hello, World!" in result
        assert b"schema_version" in result

    def test_dumps_adds_schema_version(self, sample_text_message: MessageEnvelope):
        """测试序列化时自动添加 schema_version"""
        # 确保原消息没有 schema_version
        msg = dict(sample_text_message)
        msg.pop("schema_version", None)
        
        result = dumps_message(msg)  # type: ignore
        loaded = loads_message(result)
        assert loaded.get("schema_version") == DEFAULT_SCHEMA_VERSION

    def test_dumps_preserves_existing_schema_version(self):
        """测试序列化时保留已有的 schema_version"""
        msg = (
            MessageBuilder()
            .platform("test")
            .from_user("user_1")
            .text("test")
            .build()
        )
        msg["schema_version"] = 1
        
        result = dumps_message(msg)
        loaded = loads_message(result)
        assert loaded.get("schema_version") == 1

    def test_dumps_strips_raw_bytes(self):
        """测试序列化时移除 raw_bytes 字段"""
        msg = (
            MessageBuilder()
            .platform("test")
            .from_user("user_1")
            .text("test")
            .build()
        )
        msg["raw_bytes"] = b"some raw data"
        
        result = dumps_message(msg)
        assert b"raw_bytes" not in result


class TestDumpsMessages:
    """测试批量消息序列化"""

    def test_dumps_empty_list(self):
        """测试序列化空消息列表"""
        result = dumps_messages([])
        loaded = loads_messages(result)
        assert loaded == []

    def test_dumps_multiple_messages(self, sample_messages_batch):
        """测试序列化多条消息"""
        result = dumps_messages(sample_messages_batch)
        assert isinstance(result, bytes)
        
        loaded = loads_messages(result)
        assert len(loaded) == len(sample_messages_batch)

    def test_dumps_messages_has_schema_version(self, sample_messages_batch):
        """测试批量序列化包含 schema_version"""
        result = dumps_messages(sample_messages_batch)
        assert b"schema_version" in result


class TestLoadsMessage:
    """测试单条消息反序列化"""

    def test_loads_from_bytes(self, sample_text_message: MessageEnvelope):
        """测试从 bytes 反序列化"""
        serialized = dumps_message(sample_text_message)
        loaded = loads_message(serialized)
        
        assert loaded["message_info"]["platform"] == "test"
        assert loaded["message_info"]["user_info"]["user_id"] == "user_123"

    def test_loads_from_string(self, sample_text_message: MessageEnvelope):
        """测试从字符串反序列化"""
        serialized = dumps_message(sample_text_message)
        loaded = loads_message(serialized.decode("utf-8"))
        
        assert loaded["message_info"]["platform"] == "test"

    def test_loads_invalid_schema_version_raises(self):
        """测试不支持的 schema_version 抛出异常"""
        import orjson
        invalid_data = orjson.dumps({"schema_version": 999, "message_info": {}})
        
        with pytest.raises(ValueError, match="不支持的 schema_version"):
            loads_message(invalid_data)


class TestLoadsMessages:
    """测试批量消息反序列化"""

    def test_loads_batch_messages(self, sample_messages_batch):
        """测试反序列化批量消息"""
        serialized = dumps_messages(sample_messages_batch)
        loaded = loads_messages(serialized)
        
        assert len(loaded) == len(sample_messages_batch)
        for i, msg in enumerate(loaded):
            assert msg["message_info"]["user_info"]["user_id"] == f"user_{i}"

    def test_loads_empty_batch(self):
        """测试反序列化空批次"""
        serialized = dumps_messages([])
        loaded = loads_messages(serialized)
        assert loaded == []

    def test_loads_from_string(self, sample_messages_batch):
        """测试从字符串反序列化批量消息"""
        serialized = dumps_messages(sample_messages_batch)
        loaded = loads_messages(serialized.decode("utf-8"))
        assert len(loaded) == len(sample_messages_batch)


class TestStripRawBytes:
    """测试 _strip_raw_bytes 辅助函数"""

    def test_strip_raw_bytes_from_dict(self):
        """测试从字典中移除 raw_bytes"""
        msg = {"type": "text", "data": "hello", "raw_bytes": b"data"}
        result = _strip_raw_bytes(msg)  # type: ignore
        assert "raw_bytes" not in result
        assert result["type"] == "text"

    def test_strip_raw_bytes_preserves_original(self):
        """测试不修改原始字典"""
        msg = {"type": "text", "data": "hello", "raw_bytes": b"data"}
        _strip_raw_bytes(msg)  # type: ignore
        assert "raw_bytes" in msg  # 原始字典不变

    def test_strip_raw_bytes_no_raw_bytes(self):
        """测试没有 raw_bytes 时返回原字典"""
        msg = {"type": "text", "data": "hello"}
        result = _strip_raw_bytes(msg)  # type: ignore
        assert result is msg  # 相同对象


class TestRoundTrip:
    """测试序列化和反序列化的往返一致性"""

    def test_single_message_roundtrip(self, sample_text_message: MessageEnvelope):
        """测试单条消息往返"""
        serialized = dumps_message(sample_text_message)
        loaded = loads_message(serialized)
        
        # 验证关键字段一致
        assert loaded["message_info"]["platform"] == sample_text_message["message_info"]["platform"]
        assert loaded["message_info"]["user_info"]["user_id"] == sample_text_message["message_info"]["user_info"]["user_id"]
        assert loaded["direction"] == sample_text_message["direction"]

    def test_batch_messages_roundtrip(self, sample_messages_batch):
        """测试批量消息往返"""
        serialized = dumps_messages(sample_messages_batch)
        loaded = loads_messages(serialized)
        
        assert len(loaded) == len(sample_messages_batch)
        for orig, new in zip(sample_messages_batch, loaded):
            assert orig["message_info"]["user_info"]["user_id"] == new["message_info"]["user_info"]["user_id"]

    def test_mixed_message_roundtrip(self, sample_mixed_message: MessageEnvelope):
        """测试混合消息往返"""
        serialized = dumps_message(sample_mixed_message)
        loaded = loads_message(serialized)
        
        # 验证消息段
        segments = loaded.get("message_segment")
        assert isinstance(segments, list)
        assert len(segments) == 2
        assert segments[0]["type"] == "text"
        assert segments[1]["type"] == "image"
