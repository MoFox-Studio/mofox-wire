"""
测试 adapter_utils 模块：适配器工具类
"""
from __future__ import annotations

import asyncio
import multiprocessing as mp
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from mofox_wire import MessageBuilder, MessageEnvelope
from mofox_wire.adapter_utils import (
    AdapterBase,
    HttpAdapterOptions,
    InProcessCoreSink,
    ProcessCoreSink,
    ProcessCoreSinkServer,
    WebSocketAdapterOptions,
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
# 测试 InProcessCoreSink
# ============================================================

class TestInProcessCoreSink:
    """测试进程内 CoreSink"""

    @pytest.fixture
    def handler(self) -> AsyncMock:
        return AsyncMock(return_value=None)

    @pytest.fixture
    def sink(self, handler: AsyncMock) -> InProcessCoreSink:
        return InProcessCoreSink(handler=handler)

    @pytest.mark.asyncio
    async def test_send_message(self, sink: InProcessCoreSink, handler: AsyncMock):
        """测试发送单条消息"""
        msg = make_message()
        await sink.send(msg)

        # 严格验证处理器被调用且参数完全匹配
        handler.assert_called_once_with(msg)
        assert handler.call_count == 1

    @pytest.mark.asyncio
    async def test_send_many_messages(self, sink: InProcessCoreSink, handler: AsyncMock):
        """测试批量发送消息"""
        messages = [make_message(text=f"msg_{i}") for i in range(3)]
        await sink.send_many(messages)

        # 严格验证处理器被调用且每条消息都被正确处理
        assert handler.call_count == 3

        # 验证每次调用的参数
        for i, call in enumerate(handler.call_args_list):
            assert call[0][0] == messages[i]  # 验证第i条消息被正确传递

    @pytest.mark.asyncio
    async def test_set_outgoing_handler(self, sink: InProcessCoreSink):
        """测试设置 outgoing 处理器"""
        outgoing_handler = AsyncMock()
        sink.set_outgoing_handler(outgoing_handler)
        
        msg = make_message()
        await sink.push_outgoing(msg)
        
        outgoing_handler.assert_called_once_with(msg)

    @pytest.mark.asyncio
    async def test_multiple_outgoing_handlers(self, sink: InProcessCoreSink):
        """测试多个 outgoing 处理器"""
        handler1 = AsyncMock()
        handler2 = AsyncMock()
        sink.set_outgoing_handler(handler1)
        sink.set_outgoing_handler(handler2)
        
        msg = make_message()
        await sink.push_outgoing(msg)
        
        handler1.assert_called_once()
        handler2.assert_called_once()

    @pytest.mark.asyncio
    async def test_remove_outgoing_handler(self, sink: InProcessCoreSink):
        """测试移除 outgoing 处理器"""
        handler = AsyncMock()
        sink.set_outgoing_handler(handler)
        sink.remove_outgoing_handler(handler)
        
        msg = make_message()
        await sink.push_outgoing(msg)
        
        handler.assert_not_called()

    @pytest.mark.asyncio
    async def test_push_outgoing_no_handler(self, sink: InProcessCoreSink):
        """测试无处理器时推送不报错"""
        msg = make_message()
        # 不应抛出异常
        await sink.push_outgoing(msg)

    @pytest.mark.asyncio
    async def test_close(self, sink: InProcessCoreSink):
        """测试关闭清除处理器"""
        handler = AsyncMock()
        sink.set_outgoing_handler(handler)
        
        await sink.close()
        
        msg = make_message()
        await sink.push_outgoing(msg)
        handler.assert_not_called()


# ============================================================
# 测试 ProcessCoreSink（子进程通讯）
# ============================================================

class TestProcessCoreSink:
    """测试进程间 CoreSink"""

    @pytest.fixture
    def queues(self):
        """创建进程间队列"""
        to_core = mp.Queue()
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
    async def test_send_message_to_queue(self, queues):
        """测试发送消息到队列"""
        to_core, from_core = queues
        sink = ProcessCoreSink(to_core_queue=to_core, from_core_queue=from_core)
        
        msg = make_message()
        await sink.send(msg)
        
        # 检查队列中的消息
        item = to_core.get(timeout=1)

        # 严格验证队列消息的结构和内容
        assert isinstance(item, dict)
        assert item["kind"] == "incoming"
        assert "payload" in item
        assert item["payload"]["message_info"]["platform"] == "test"
        assert item["payload"]["message_segment"]["data"] == "hello"
        assert len(item.keys()) == 2  # 只有 kind 和 payload 字段
        
        await sink.close()

    @pytest.mark.asyncio
    async def test_send_many_messages(self, queues):
        """测试批量发送消息"""
        to_core, from_core = queues
        sink = ProcessCoreSink(to_core_queue=to_core, from_core_queue=from_core)
        
        messages = [make_message(text=f"msg_{i}") for i in range(3)]
        await sink.send_many(messages)
        
        # 检查队列中有 3 条消息
        for i in range(3):
            item = to_core.get(timeout=1)
            assert item["kind"] == "incoming"
        
        await sink.close()

    @pytest.mark.asyncio
    async def test_outgoing_handler(self, queues):
        """测试 outgoing 处理器"""
        to_core, from_core = queues
        sink = ProcessCoreSink(to_core_queue=to_core, from_core_queue=from_core)
        
        received = []
        async def handler(msg):
            received.append(msg)
        
        sink.set_outgoing_handler(handler)
        
        # 模拟核心发送 outgoing 消息
        outgoing_msg = make_message(text="outgoing")
        from_core.put({"kind": "outgoing", "payload": outgoing_msg})
        
        # 等待处理
        await asyncio.sleep(0.2)
        
        assert len(received) == 1
        
        await sink.close()

    @pytest.mark.asyncio
    async def test_close_sends_stop_signal(self, queues):
        """测试关闭发送停止信号"""
        to_core, from_core = queues
        sink = ProcessCoreSink(to_core_queue=to_core, from_core_queue=from_core)
        
        await sink.close()
        
        # 检查停止信号
        item = from_core.get(timeout=1)
        assert item.get("__core_sink_control__") == "stop"


# ============================================================
# 测试 ProcessCoreSinkServer
# ============================================================

class TestProcessCoreSinkServer:
    """测试进程间 CoreSink 服务器"""

    @pytest.fixture
    def queues(self):
        """创建进程间队列"""
        incoming = mp.Queue()
        outgoing = mp.Queue()
        yield incoming, outgoing
        # 清理
        try:
            while not incoming.empty():
                incoming.get_nowait()
            while not outgoing.empty():
                outgoing.get_nowait()
        except Exception:
            pass

    @pytest.mark.asyncio
    async def test_consume_incoming(self, queues):
        """测试消费 incoming 消息"""
        incoming, outgoing = queues
        received = []
        
        async def handler(msg):
            received.append(msg)
        
        server = ProcessCoreSinkServer(
            incoming_queue=incoming,
            outgoing_queue=outgoing,
            core_handler=handler,
            name="test_adapter",
        )
        
        server.start()
        
        # 发送 incoming 消息
        msg = make_message()
        incoming.put({"kind": "incoming", "payload": msg})
        
        # 等待处理
        await asyncio.sleep(0.2)
        
        assert len(received) == 1
        
        await server.close()

    @pytest.mark.asyncio
    async def test_push_outgoing(self, queues):
        """测试推送 outgoing 消息"""
        incoming, outgoing = queues
        
        server = ProcessCoreSinkServer(
            incoming_queue=incoming,
            outgoing_queue=outgoing,
            core_handler=AsyncMock(),
        )
        
        msg = make_message(text="outgoing")
        await server.push_outgoing(msg)
        
        # 检查 outgoing 队列
        item = outgoing.get(timeout=1)
        assert item["kind"] == "outgoing"
        assert item["payload"]["message_segment"]["data"] == "outgoing"
        
        await server.close()

    @pytest.mark.asyncio
    async def test_close_stops_consumer(self, queues):
        """测试关闭停止消费者"""
        incoming, outgoing = queues
        
        server = ProcessCoreSinkServer(
            incoming_queue=incoming,
            outgoing_queue=outgoing,
            core_handler=AsyncMock(),
        )
        
        server.start()
        await asyncio.sleep(0.1)
        
        await server.close()
        
        # 验证任务已取消
        assert server._task is None or server._task.done()


# ============================================================
# 测试 WebSocketAdapterOptions
# ============================================================

class TestWebSocketAdapterOptions:
    """测试 WebSocket 适配器选项"""

    def test_create_options(self):
        """测试创建选项"""
        options = WebSocketAdapterOptions(
            url="ws://localhost:8080/ws",
            headers={"Authorization": "Bearer token"},
        )
        
        assert options.url == "ws://localhost:8080/ws"
        assert options.headers["Authorization"] == "Bearer token"

    def test_default_values(self):
        """测试默认值"""
        options = WebSocketAdapterOptions(url="ws://localhost:8080")
        
        assert options.headers is None
        assert options.incoming_parser is None
        assert options.outgoing_encoder is None

    def test_custom_parser_encoder(self):
        """测试自定义解析器和编码器"""
        def parser(data):
            return {"parsed": data}
        
        def encoder(msg):
            return b"encoded"
        
        options = WebSocketAdapterOptions(
            url="ws://localhost:8080",
            incoming_parser=parser,
            outgoing_encoder=encoder,
        )
        
        assert options.incoming_parser is parser
        assert options.outgoing_encoder is encoder


# ============================================================
# 测试 HttpAdapterOptions
# ============================================================

class TestHttpAdapterOptions:
    """测试 HTTP 适配器选项"""

    def test_create_options(self):
        """测试创建选项"""
        options = HttpAdapterOptions(
            host="127.0.0.1",
            port=9000,
            path="/api/messages",
        )
        
        assert options.host == "127.0.0.1"
        assert options.port == 9000
        assert options.path == "/api/messages"

    def test_default_values(self):
        """测试默认值"""
        options = HttpAdapterOptions()
        
        assert options.host == "0.0.0.0"
        assert options.port == 8089
        assert options.path == "/adapter/messages"
        assert options.app is None


# ============================================================
# 测试 AdapterBase
# ============================================================

class TestAdapterBase:
    """测试适配器基类"""

    @pytest.fixture
    def mock_sink(self) -> AsyncMock:
        sink = AsyncMock()
        sink.send = AsyncMock()
        sink.send_many = AsyncMock()
        sink.set_outgoing_handler = MagicMock()
        sink.remove_outgoing_handler = MagicMock()
        return sink

    def test_create_adapter(self, mock_sink):
        """测试创建适配器"""
        adapter = AdapterBase(core_sink=mock_sink)
        
        assert adapter.core_sink is mock_sink
        assert adapter.platform == "unknown"

    @pytest.mark.asyncio
    async def test_on_platform_message_not_implemented(self, mock_sink):
        """测试 from_platform_message 未实现"""
        adapter = AdapterBase(core_sink=mock_sink)
        
        with pytest.raises(NotImplementedError):
            await adapter.on_platform_message({"raw": "data"})

    @pytest.mark.asyncio
    async def test_send_platform_message_not_implemented(self, mock_sink):
        """测试 _send_platform_message 未实现"""
        adapter = AdapterBase(core_sink=mock_sink)
        
        msg = make_message()
        with pytest.raises(NotImplementedError):
            await adapter._send_platform_message(msg)

    @pytest.mark.asyncio
    async def test_start_registers_outgoing_handler(self, mock_sink):
        """测试启动时注册 outgoing 处理器"""
        adapter = AdapterBase(core_sink=mock_sink)
        
        await adapter.start()
        
        mock_sink.set_outgoing_handler.assert_called_once()

    @pytest.mark.asyncio
    async def test_stop_removes_outgoing_handler(self, mock_sink):
        """测试停止时移除 outgoing 处理器"""
        adapter = AdapterBase(core_sink=mock_sink)
        
        await adapter.start()
        await adapter.stop()
        
        # 检查是否调用了移除处理器或设置为 None
        assert (
            mock_sink.remove_outgoing_handler.called or
            any(call[0] == (None,) for call in mock_sink.set_outgoing_handler.call_args_list)
        )


# ============================================================
# 测试自定义适配器
# ============================================================

class TestCustomAdapter:
    """测试自定义适配器实现"""

    class MockAdapter(AdapterBase):
        """测试用的模拟适配器"""
        platform = "mock"
        
        def __init__(self, core_sink, transport=None):
            super().__init__(core_sink, transport)
            self.sent_messages = []
        
        async def from_platform_message(self, raw):
            return (
                MessageBuilder()
                .platform("mock")
                .from_user("user_1")
                .text(raw.get("text", ""))
                .build()
            )
        
        async def _send_platform_message(self, envelope):
            self.sent_messages.append(envelope)

    @pytest.fixture
    def mock_sink(self) -> AsyncMock:
        sink = AsyncMock()
        sink.send = AsyncMock()
        sink.send_many = AsyncMock()
        sink.set_outgoing_handler = MagicMock()
        sink.remove_outgoing_handler = MagicMock()
        return sink

    @pytest.mark.asyncio
    async def test_custom_adapter_handles_message(self, mock_sink):
        """测试自定义适配器处理消息"""
        adapter = self.MockAdapter(core_sink=mock_sink)
        
        raw_message = {"text": "Hello from platform"}
        await adapter.on_platform_message(raw_message)
        
        mock_sink.send.assert_called_once()
        sent_msg = mock_sink.send.call_args[0][0]
        assert sent_msg["message_info"]["platform"] == "mock"
        assert sent_msg["message_segment"]["data"] == "Hello from platform"

    @pytest.mark.asyncio
    async def test_custom_adapter_handles_batch(self, mock_sink):
        """测试自定义适配器批量处理"""
        adapter = self.MockAdapter(core_sink=mock_sink)
        
        raw_messages = [
            {"text": "Message 1"},
            {"text": "Message 2"},
            {"text": "Message 3"},
        ]
        await adapter.on_platform_messages(raw_messages)
        
        # 检查 send_many 被调用
        assert mock_sink.send_many.called or mock_sink.send.call_count == 3

    @pytest.mark.asyncio
    async def test_custom_adapter_sends_to_platform(self, mock_sink):
        """测试自定义适配器发送到平台"""
        adapter = self.MockAdapter(core_sink=mock_sink)
        
        msg = make_message(platform="mock", text="Outgoing")
        await adapter.send_to_platform(msg)
        
        assert len(adapter.sent_messages) == 1
        assert adapter.sent_messages[0] == msg

    @pytest.mark.asyncio
    async def test_custom_adapter_batch_send(self, mock_sink):
        """测试自定义适配器批量发送"""
        adapter = self.MockAdapter(core_sink=mock_sink)
        
        messages = [make_message(text=f"msg_{i}") for i in range(3)]
        await adapter.send_batch_to_platform(messages)
        
        assert len(adapter.sent_messages) == 3

    @pytest.mark.asyncio
    async def test_outgoing_handler_filters_platform(self, mock_sink):
        """测试 outgoing 处理器按平台过滤"""
        adapter = self.MockAdapter(core_sink=mock_sink)
        
        # 模拟 outgoing 消息来自其他平台
        other_platform_msg = make_message(platform="other", text="other")
        await adapter._on_outgoing_from_core(other_platform_msg)
        
        # 不应发送到平台
        assert len(adapter.sent_messages) == 0
        
        # 相同平台的消息应该发送
        same_platform_msg = make_message(platform="mock", text="same")
        await adapter._on_outgoing_from_core(same_platform_msg)
        
        assert len(adapter.sent_messages) == 1
