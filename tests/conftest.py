"""
Pytest 配置和共享 fixtures
"""
from __future__ import annotations

import asyncio
import multiprocessing as mp
from typing import Any, Dict, List
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio

from mofox_wire import MessageBuilder, MessageEnvelope
from mofox_wire.adapter_utils import InProcessCoreSink, ProcessCoreSink, ProcessCoreSinkServer


# ============================================================
# 通用 Fixtures
# ============================================================

@pytest.fixture(scope="session")
def event_loop_policy():
    """使用默认事件循环策略"""
    return asyncio.DefaultEventLoopPolicy()


@pytest.fixture
def sample_text_message() -> MessageEnvelope:
    """创建一个简单的文本消息示例"""
    return (
        MessageBuilder()
        .platform("test")
        .from_user("user_123", nickname="TestUser")
        .from_group("group_456", name="TestGroup")
        .text("Hello, World!")
        .build()
    )


@pytest.fixture
def sample_image_message() -> MessageEnvelope:
    """创建一个图片消息示例"""
    return (
        MessageBuilder()
        .platform("test")
        .from_user("user_123")
        .image("https://example.com/image.png")
        .build()
    )


@pytest.fixture
def sample_mixed_message() -> MessageEnvelope:
    """创建一个包含多个段落的消息示例"""
    return (
        MessageBuilder()
        .platform("test")
        .from_user("user_123")
        .text("Check out this image:")
        .image("https://example.com/image.png")
        .build()
    )


@pytest.fixture
def sample_messages_batch() -> List[MessageEnvelope]:
    """创建一批消息示例"""
    messages = []
    for i in range(5):
        msg = (
            MessageBuilder()
            .platform("test")
            .from_user(f"user_{i}")
            .text(f"Message {i}")
            .build()
        )
        messages.append(msg)
    return messages


@pytest.fixture
def mock_handler() -> AsyncMock:
    """创建一个模拟的异步消息处理器"""
    return AsyncMock(return_value=None)


@pytest_asyncio.fixture
async def in_process_sink(mock_handler: AsyncMock) -> InProcessCoreSink:
    """创建进程内 CoreSink"""
    sink = InProcessCoreSink(handler=mock_handler)
    yield sink
    await sink.close()


@pytest.fixture
def mp_queues():
    """创建多进程通信队列对"""
    to_core = mp.Queue()
    from_core = mp.Queue()
    yield to_core, from_core
    # 清理队列
    try:
        while not to_core.empty():
            to_core.get_nowait()
        while not from_core.empty():
            from_core.get_nowait()
    except Exception:
        pass


# ============================================================
# 服务器端口管理
# ============================================================

_port_counter = 19000


def get_free_port() -> int:
    """获取一个可用端口（简单递增策略）"""
    global _port_counter
    _port_counter += 1
    return _port_counter


@pytest.fixture
def free_port() -> int:
    """获取一个可用端口"""
    return get_free_port()


# ============================================================
# 辅助函数
# ============================================================

def make_envelope(
    platform: str = "test",
    user_id: str = "user_1",
    text: str = "hello",
    direction: str = "incoming",
) -> MessageEnvelope:
    """快速创建消息信封的辅助函数"""
    return (
        MessageBuilder()
        .platform(platform)
        .from_user(user_id)
        .text(text)
        .direction(direction)
        .build()
    )
