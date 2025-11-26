"""
集成测试：子进程通讯
测试 ProcessCoreSink 和 ProcessCoreSinkServer 的进程间通讯
"""
from __future__ import annotations

import asyncio
import multiprocessing as mp
from typing import List
from unittest.mock import AsyncMock

import pytest

from mofox_wire import MessageBuilder, MessageEnvelope
from mofox_wire.adapter_utils import (
    ProcessCoreSink,
    ProcessCoreSinkServer,
)


# ============================================================
# 辅助函数
# ============================================================

def make_message(platform: str = "test", text: str = "hello") -> MessageEnvelope:
    """创建测试消息"""
    return (
        MessageBuilder()
        .platform(platform)
        .from_user("user_1")
        .text(text)
        .build()
    )


# ============================================================
# 测试 ProcessCoreSink 和 ProcessCoreSinkServer 配对
# ============================================================

@pytest.mark.integration
class TestProcessCommunication:
    """测试进程间通讯"""

    @pytest.fixture
    def queues(self):
        """创建进程间队列"""
        # adapter -> core
        to_core = mp.Queue()
        # core -> adapter
        from_core = mp.Queue()
        yield to_core, from_core
        # 清理
        try:
            while not to_core.empty():
                to_core.get_nowait()
            while not from_core.empty():
                from_core.get_nowait()
        except Exception:
            pass

    @pytest.mark.asyncio
    async def test_adapter_sends_to_core(self, queues):
        """测试适配器发送消息到核心"""
        to_core, from_core = queues
        received_by_core = []
        
        async def core_handler(msg):
            received_by_core.append(msg)
        
        # 模拟核心端（使用 ProcessCoreSinkServer）
        core_server = ProcessCoreSinkServer(
            incoming_queue=to_core,
            outgoing_queue=from_core,
            core_handler=core_handler,
            name="test_adapter",
        )
        core_server.start()
        
        # 模拟适配器端（使用 ProcessCoreSink）
        adapter_sink = ProcessCoreSink(
            to_core_queue=to_core,
            from_core_queue=from_core,
        )
        
        try:
            # 适配器发送消息
            msg = make_message(text="Hello from adapter")
            await adapter_sink.send(msg)
            
            # 等待核心处理
            await asyncio.sleep(0.3)
            
            # 验证核心收到消息
            assert len(received_by_core) == 1
            assert received_by_core[0]["message_segment"]["data"] == "Hello from adapter"
        finally:
            await adapter_sink.close()
            await core_server.close()

    @pytest.mark.asyncio
    async def test_core_sends_to_adapter(self, queues):
        """测试核心发送消息到适配器"""
        to_core, from_core = queues
        received_by_adapter = []
        
        async def adapter_handler(msg):
            received_by_adapter.append(msg)
        
        async def core_handler(msg):
            pass
        
        # 核心端
        core_server = ProcessCoreSinkServer(
            incoming_queue=to_core,
            outgoing_queue=from_core,
            core_handler=core_handler,
        )
        core_server.start()
        
        # 适配器端
        adapter_sink = ProcessCoreSink(
            to_core_queue=to_core,
            from_core_queue=from_core,
        )
        adapter_sink.set_outgoing_handler(adapter_handler)
        
        try:
            # 核心发送 outgoing 消息
            outgoing_msg = make_message(text="Hello from core")
            await core_server.push_outgoing(outgoing_msg)
            
            # 等待适配器接收
            await asyncio.sleep(0.3)
            
            # 验证适配器收到消息
            assert len(received_by_adapter) == 1
            assert received_by_adapter[0]["message_segment"]["data"] == "Hello from core"
        finally:
            await adapter_sink.close()
            await core_server.close()

    @pytest.mark.asyncio
    async def test_bidirectional_process_communication(self, queues):
        """测试双向进程间通讯"""
        to_core, from_core = queues
        
        core_received = []
        adapter_received = []
        
        async def core_handler(msg):
            core_received.append(msg)
            # 核心处理后发送响应
            response = make_message(
                platform=msg["message_info"]["platform"],
                text=f"Echo: {msg['message_segment']['data']}",
            )
            await core_server.push_outgoing(response)
        
        async def adapter_handler(msg):
            adapter_received.append(msg)
        
        # 核心端
        core_server = ProcessCoreSinkServer(
            incoming_queue=to_core,
            outgoing_queue=from_core,
            core_handler=core_handler,
        )
        core_server.start()
        
        # 适配器端
        adapter_sink = ProcessCoreSink(
            to_core_queue=to_core,
            from_core_queue=from_core,
        )
        adapter_sink.set_outgoing_handler(adapter_handler)
        
        try:
            # 适配器发送消息
            msg = make_message(text="Test message")
            await adapter_sink.send(msg)
            
            # 等待双向处理
            await asyncio.sleep(0.5)
            
            # 验证
            assert len(core_received) == 1
            assert len(adapter_received) == 1
            assert "Echo:" in adapter_received[0]["message_segment"]["data"]
        finally:
            await adapter_sink.close()
            await core_server.close()

    @pytest.mark.asyncio
    async def test_batch_messages_through_process(self, queues):
        """测试批量消息通过进程间通讯"""
        to_core, from_core = queues
        core_received = []
        
        async def core_handler(msg):
            core_received.append(msg)
        
        core_server = ProcessCoreSinkServer(
            incoming_queue=to_core,
            outgoing_queue=from_core,
            core_handler=core_handler,
        )
        core_server.start()
        
        adapter_sink = ProcessCoreSink(
            to_core_queue=to_core,
            from_core_queue=from_core,
        )
        
        try:
            # 发送批量消息
            messages = [make_message(text=f"Message {i}") for i in range(10)]
            await adapter_sink.send_many(messages)
            
            # 等待处理
            await asyncio.sleep(0.5)
            
            # 验证
            assert len(core_received) == 10
        finally:
            await adapter_sink.close()
            await core_server.close()


# ============================================================
# 测试错误处理和边界情况
# ============================================================

@pytest.mark.integration
class TestProcessCommunicationEdgeCases:
    """测试进程间通讯边界情况"""

    @pytest.fixture
    def queues(self):
        """创建进程间队列"""
        to_core = mp.Queue()
        from_core = mp.Queue()
        yield to_core, from_core
        try:
            while not to_core.empty():
                to_core.get_nowait()
            while not from_core.empty():
                from_core.get_nowait()
        except Exception:
            pass

    @pytest.mark.asyncio
    async def test_close_sends_stop_signal(self, queues):
        """测试关闭发送停止信号"""
        to_core, from_core = queues
        
        adapter_sink = ProcessCoreSink(
            to_core_queue=to_core,
            from_core_queue=from_core,
        )
        
        await adapter_sink.close()
        
        # 验证停止信号被发送
        item = from_core.get(timeout=1)
        assert item.get("__core_sink_control__") == "stop"

    @pytest.mark.asyncio
    async def test_double_close_is_safe(self, queues):
        """测试重复关闭是安全的"""
        to_core, from_core = queues
        
        adapter_sink = ProcessCoreSink(
            to_core_queue=to_core,
            from_core_queue=from_core,
        )
        
        # 第一次关闭
        await adapter_sink.close()
        
        # 第二次关闭不应抛出异常
        await adapter_sink.close()

    @pytest.mark.asyncio
    async def test_no_outgoing_handler(self, queues):
        """测试无 outgoing 处理器时不会崩溃"""
        to_core, from_core = queues
        
        async def core_handler(msg):
            pass
        
        core_server = ProcessCoreSinkServer(
            incoming_queue=to_core,
            outgoing_queue=from_core,
            core_handler=core_handler,
        )
        core_server.start()
        
        adapter_sink = ProcessCoreSink(
            to_core_queue=to_core,
            from_core_queue=from_core,
        )
        # 不设置 outgoing handler
        
        try:
            # 核心发送 outgoing 消息
            outgoing_msg = make_message(text="No handler")
            await core_server.push_outgoing(outgoing_msg)
            
            # 等待一下，确保不会崩溃
            await asyncio.sleep(0.2)
        finally:
            await adapter_sink.close()
            await core_server.close()

    @pytest.mark.asyncio
    async def test_remove_outgoing_handler(self, queues):
        """测试移除 outgoing 处理器"""
        to_core, from_core = queues
        received = []
        
        async def handler(msg):
            received.append(msg)
        
        async def core_handler(msg):
            pass
        
        core_server = ProcessCoreSinkServer(
            incoming_queue=to_core,
            outgoing_queue=from_core,
            core_handler=core_handler,
        )
        core_server.start()
        
        adapter_sink = ProcessCoreSink(
            to_core_queue=to_core,
            from_core_queue=from_core,
        )
        adapter_sink.set_outgoing_handler(handler)
        
        try:
            # 发送第一条消息
            msg1 = make_message(text="Message 1")
            await core_server.push_outgoing(msg1)
            await asyncio.sleep(0.2)
            
            assert len(received) == 1
            
            # 移除处理器
            adapter_sink.remove_outgoing_handler(handler)
            
            # 发送第二条消息（应该不会被接收）
            msg2 = make_message(text="Message 2")
            await core_server.push_outgoing(msg2)
            await asyncio.sleep(0.2)
            
            # 仍然只有一条消息
            assert len(received) == 1
        finally:
            await adapter_sink.close()
            await core_server.close()


# ============================================================
# 测试高负载情况
# ============================================================

@pytest.mark.integration
@pytest.mark.slow
class TestProcessCommunicationLoad:
    """测试进程间通讯高负载情况"""

    @pytest.fixture
    def queues(self):
        """创建进程间队列"""
        to_core = mp.Queue()
        from_core = mp.Queue()
        yield to_core, from_core
        try:
            while not to_core.empty():
                to_core.get_nowait()
            while not from_core.empty():
                from_core.get_nowait()
        except Exception:
            pass

    @pytest.mark.asyncio
    async def test_high_message_volume(self, queues):
        """测试高消息量"""
        to_core, from_core = queues
        core_received = []
        
        async def core_handler(msg):
            core_received.append(msg)
        
        core_server = ProcessCoreSinkServer(
            incoming_queue=to_core,
            outgoing_queue=from_core,
            core_handler=core_handler,
        )
        core_server.start()
        
        adapter_sink = ProcessCoreSink(
            to_core_queue=to_core,
            from_core_queue=from_core,
        )
        
        try:
            # 发送大量消息
            message_count = 100
            for i in range(message_count):
                msg = make_message(text=f"High volume message {i}")
                await adapter_sink.send(msg)
            
            # 等待处理
            await asyncio.sleep(2.0)
            
            # 验证所有消息都被处理
            assert len(core_received) == message_count
        finally:
            await adapter_sink.close()
            await core_server.close()

    @pytest.mark.asyncio
    async def test_concurrent_bidirectional(self, queues):
        """测试并发双向通讯"""
        to_core, from_core = queues
        core_received = []
        adapter_received = []
        
        async def core_handler(msg):
            core_received.append(msg)
        
        async def adapter_handler(msg):
            adapter_received.append(msg)
        
        core_server = ProcessCoreSinkServer(
            incoming_queue=to_core,
            outgoing_queue=from_core,
            core_handler=core_handler,
        )
        core_server.start()
        
        adapter_sink = ProcessCoreSink(
            to_core_queue=to_core,
            from_core_queue=from_core,
        )
        adapter_sink.set_outgoing_handler(adapter_handler)
        
        try:
            # 并发发送消息
            async def send_to_core():
                for i in range(50):
                    msg = make_message(text=f"To core {i}")
                    await adapter_sink.send(msg)
            
            async def send_to_adapter():
                for i in range(50):
                    msg = make_message(text=f"To adapter {i}")
                    await core_server.push_outgoing(msg)
            
            await asyncio.gather(send_to_core(), send_to_adapter())
            
            # 等待处理
            await asyncio.sleep(2.0)
            
            # 验证
            assert len(core_received) == 50
            assert len(adapter_received) == 50
        finally:
            await adapter_sink.close()
            await core_server.close()
