"""
集成测试：平台-适配器-核心 端到端通讯
模拟实际的消息流转场景
"""
from __future__ import annotations

import asyncio
from typing import Any, List
from unittest.mock import AsyncMock

import pytest
from aiohttp import web

from mofox_wire import (
    MessageBuilder,
    MessageEnvelope,
    MessageRuntime,
    MessageServer,
    MessageClient,
)
from mofox_wire.adapter_utils import (
    AdapterBase,
    InProcessCoreSink,
    WebSocketAdapterOptions,
)
from mofox_wire.router import RouteConfig, Router, TargetConfig


# ============================================================
# 辅助函数
# ============================================================

def make_message(
    platform: str = "test",
    text: str = "hello",
    direction: str = "incoming",
) -> MessageEnvelope:
    """创建测试消息"""
    return (
        MessageBuilder()
        .platform(platform)
        .from_user("user_1")
        .text(text)
        .direction(direction)
        .build()
    )


# ============================================================
# 模拟适配器
# ============================================================

class MockPlatformAdapter(AdapterBase):
    """模拟平台适配器"""
    
    def __init__(self, platform: str, core_sink, transport=None):
        super().__init__(core_sink, transport)
        self.platform = platform
        self.sent_to_platform: List[MessageEnvelope] = []
        self.received_from_platform: List[Any] = []
    
    async def from_platform_message(self, raw: Any) -> MessageEnvelope:
        """将平台原始消息转换为 MessageEnvelope"""
        self.received_from_platform.append(raw)
        
        return (
            MessageBuilder()
            .platform(self.platform)
            .from_user(raw.get("user_id", "unknown"))
            .text(raw.get("content", ""))
            .direction("incoming")
            .build()
        )
    
    async def _send_platform_message(self, envelope: MessageEnvelope) -> None:
        """发送消息到平台"""
        self.sent_to_platform.append(envelope)


# ============================================================
# 测试进程内通讯
# ============================================================

@pytest.mark.integration
class TestInProcessCommunication:
    """测试进程内通讯"""

    @pytest.mark.asyncio
    async def test_adapter_to_core_message_flow(self):
        """测试适配器到核心的消息流转"""
        received_by_core = []
        
        async def core_handler(msg: MessageEnvelope):
            received_by_core.append(msg)
        
        # 创建进程内 sink
        sink = InProcessCoreSink(handler=core_handler)
        
        # 创建适配器
        adapter = MockPlatformAdapter(platform="test_platform", core_sink=sink)
        
        await adapter.start()
        
        try:
            # 模拟平台消息
            raw_message = {"user_id": "user_123", "content": "Hello from platform"}
            await adapter.on_platform_message(raw_message)
            
            # 验证核心收到消息
            assert len(received_by_core) == 1
            msg = received_by_core[0]
            assert msg["message_info"]["platform"] == "test_platform"
            assert msg["message_segment"]["data"] == "Hello from platform"
        finally:
            await adapter.stop()
            await sink.close()

    @pytest.mark.asyncio
    async def test_core_to_adapter_message_flow(self):
        """测试核心到适配器的消息流转"""
        async def core_handler(msg):
            pass
        
        sink = InProcessCoreSink(handler=core_handler)
        adapter = MockPlatformAdapter(platform="test_platform", core_sink=sink)
        
        await adapter.start()
        
        try:
            # 核心推送 outgoing 消息
            outgoing_msg = make_message(
                platform="test_platform",
                text="Response from core",
                direction="outgoing",
            )
            await sink.push_outgoing(outgoing_msg)
            
            # 验证适配器收到消息
            assert len(adapter.sent_to_platform) == 1
            assert adapter.sent_to_platform[0]["message_segment"]["data"] == "Response from core"
        finally:
            await adapter.stop()
            await sink.close()

    @pytest.mark.asyncio
    async def test_bidirectional_communication(self):
        """测试双向通讯"""
        core_received = []
        
        async def core_handler(msg: MessageEnvelope):
            core_received.append(msg)
            # 核心处理后返回响应
            if msg["direction"] == "incoming":
                response = make_message(
                    platform=msg["message_info"]["platform"],
                    text=f"Echo: {msg['message_segment']['data']}",
                    direction="outgoing",
                )
                await sink.push_outgoing(response)
        
        sink = InProcessCoreSink(handler=core_handler)
        adapter = MockPlatformAdapter(platform="echo_platform", core_sink=sink)
        
        await adapter.start()
        
        try:
            # 发送入站消息
            raw_message = {"user_id": "user_1", "content": "Test message"}
            await adapter.on_platform_message(raw_message)
            
            # 等待处理
            await asyncio.sleep(0.1)
            
            # 验证核心收到消息
            assert len(core_received) == 1
            
            # 验证适配器收到响应
            assert len(adapter.sent_to_platform) == 1
            assert "Echo:" in adapter.sent_to_platform[0]["message_segment"]["data"]
        finally:
            await adapter.stop()
            await sink.close()


# ============================================================
# 测试带 Runtime 的完整流程
# ============================================================

@pytest.mark.integration
class TestRuntimeIntegration:
    """测试带 MessageRuntime 的完整流程"""

    @pytest.mark.asyncio
    async def test_runtime_routes_messages(self):
        """测试 Runtime 路由消息"""
        text_handled = []
        image_handled = []
        
        runtime = MessageRuntime()
        
        @runtime.on_message(message_type="text")
        async def handle_text(msg):
            text_handled.append(msg)
            return msg
        
        @runtime.on_message(message_type="image")
        async def handle_image(msg):
            image_handled.append(msg)
            return msg
        
        # 创建 sink，使用 runtime 处理消息
        sink = InProcessCoreSink(handler=runtime.handle_message)
        adapter = MockPlatformAdapter(platform="test", core_sink=sink)
        
        await adapter.start()
        
        try:
            # 发送文本消息
            text_raw = {"user_id": "u1", "content": "Hello"}
            await adapter.on_platform_message(text_raw)
            
            await asyncio.sleep(0.1)
            
            assert len(text_handled) == 1
            assert len(image_handled) == 0
        finally:
            await adapter.stop()
            await sink.close()

    @pytest.mark.asyncio
    async def test_runtime_with_middleware(self):
        """测试 Runtime 中间件"""
        middleware_calls = []
        
        runtime = MessageRuntime()
        
        async def logging_middleware(msg, handler):
            middleware_calls.append(("before", msg))
            result = await handler(msg)
            middleware_calls.append(("after", result))
            return result
        
        runtime.register_middleware(logging_middleware)
        
        @runtime.on_message
        async def handle_all(msg):
            return msg
        
        sink = InProcessCoreSink(handler=runtime.handle_message)
        adapter = MockPlatformAdapter(platform="test", core_sink=sink)
        
        await adapter.start()
        
        try:
            raw = {"user_id": "u1", "content": "Test"}
            await adapter.on_platform_message(raw)
            
            await asyncio.sleep(0.1)
            
            assert len(middleware_calls) == 2
            assert middleware_calls[0][0] == "before"
            assert middleware_calls[1][0] == "after"
        finally:
            await adapter.stop()
            await sink.close()

    @pytest.mark.asyncio
    async def test_runtime_error_handling(self):
        """测试 Runtime 错误处理"""
        errors_caught = []
        
        runtime = MessageRuntime()
        
        async def error_hook(msg, exc):
            errors_caught.append((msg, exc))
        
        runtime.register_error_hook(error_hook)
        
        @runtime.on_message
        async def failing_handler(msg):
            raise ValueError("Intentional error")
        
        sink = InProcessCoreSink(handler=runtime.handle_message)
        adapter = MockPlatformAdapter(platform="test", core_sink=sink)
        
        await adapter.start()
        
        try:
            raw = {"user_id": "u1", "content": "Test"}
            
            # 处理应该捕获错误
            try:
                await adapter.on_platform_message(raw)
            except Exception:
                pass
            
            await asyncio.sleep(0.1)
            
            assert len(errors_caught) == 1
            assert isinstance(errors_caught[0][1], ValueError)
        finally:
            await adapter.stop()
            await sink.close()


# ============================================================
# 测试多平台路由
# ============================================================

@pytest.mark.integration
class TestMultiPlatformRouting:
    """测试多平台路由"""

    @pytest.fixture
    def free_port(self):
        """获取可用端口"""
        import socket
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(('', 0))
            return s.getsockname()[1]

    @pytest.mark.asyncio
    async def test_router_routes_to_correct_platform(self, free_port: int):
        """测试路由器路由到正确的平台"""
        platform_a_received = []
        platform_b_received = []
        
        def handler_a(msg):
            platform_a_received.append(msg)
        
        def handler_b(msg):
            platform_b_received.append(msg)
        
        # 创建两个模拟服务器
        server_a = MessageServer(host="127.0.0.1", port=free_port)
        server_a.register_message_handler(handler_a)
        
        server_b = MessageServer(host="127.0.0.1", port=free_port + 1)
        server_b.register_message_handler(handler_b)
        
        server_a_task = asyncio.create_task(server_a.run())
        server_b_task = asyncio.create_task(server_b.run())
        
        await asyncio.sleep(0.3)
        
        try:
            # 创建路由配置
            config = RouteConfig(
                route_config={
                    "platform_a": TargetConfig(url=f"ws://127.0.0.1:{free_port}/ws"),
                    "platform_b": TargetConfig(url=f"ws://127.0.0.1:{free_port + 1}/ws"),
                }
            )
            
            router = Router(config=config)
            
            # 连接所有平台
            await router.connect("platform_a")
            await router.connect("platform_b")
            
            # 等待连接建立
            await asyncio.sleep(0.2)
            
            # 发送消息到 platform_a
            msg_a = make_message(platform="platform_a", text="Message for A")
            await router.send_message(msg_a)
            
            # 发送消息到 platform_b
            msg_b = make_message(platform="platform_b", text="Message for B")
            await router.send_message(msg_b)
            
            await asyncio.sleep(0.2)
            
            # 验证消息路由正确
            assert len(platform_a_received) == 1
            assert platform_a_received[0]["message_segment"]["data"] == "Message for A"
            
            assert len(platform_b_received) == 1
            assert platform_b_received[0]["message_segment"]["data"] == "Message for B"
            
            await router.stop()
        finally:
            await server_a.stop()
            await server_b.stop()
            server_a_task.cancel()
            server_b_task.cancel()
            try:
                await server_a_task
            except asyncio.CancelledError:
                pass
            try:
                await server_b_task
            except asyncio.CancelledError:
                pass


# ============================================================
# 测试完整的消息生命周期
# ============================================================

@pytest.mark.integration
class TestFullMessageLifecycle:
    """测试完整的消息生命周期"""

    @pytest.fixture
    def free_port(self):
        """获取可用端口"""
        import socket
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(('', 0))
            return s.getsockname()[1]

    @pytest.mark.asyncio
    async def test_message_roundtrip(self, free_port: int):
        """测试消息往返：平台 -> 适配器 -> 核心 -> 适配器 -> 平台"""
        lifecycle_events = []
        
        # 核心处理逻辑
        runtime = MessageRuntime()
        
        @runtime.on_message(message_type="text")
        async def echo_handler(msg):
            lifecycle_events.append(("core_received", msg))
            
            # 生成响应
            response = (
                MessageBuilder()
                .platform(msg["message_info"]["platform"])
                .from_user("bot")
                .text(f"Echo: {msg['message_segment']['data']}")
                .direction("outgoing")
                .build()
            )
            
            lifecycle_events.append(("core_response", response))
            return response
        
        # 创建核心服务器
        server = MessageServer(host="127.0.0.1", port=free_port)
        server.register_message_handler(lambda msg: asyncio.create_task(runtime.handle_message(msg)))
        
        server_task = asyncio.create_task(server.run())
        await asyncio.sleep(0.3)
        
        try:
            # 模拟适配器连接
            adapter_received = []
            
            async def adapter_handler(msg):
                lifecycle_events.append(("adapter_received", msg))
                adapter_received.append(msg)
            
            client = MessageClient()
            client.register_message_handler(adapter_handler)
            
            await client.connect(
                url=f"ws://127.0.0.1:{free_port}/ws",
                platform="test_platform",
            )
            
            # 模拟平台发送消息
            platform_msg = make_message(
                platform="test_platform",
                text="Hello from platform",
                direction="incoming",
            )
            lifecycle_events.append(("platform_send", platform_msg))
            
            await client.send_message(platform_msg)
            
            # 等待完整处理
            await asyncio.sleep(0.5)
            
            # 验证生命周期事件
            event_types = [e[0] for e in lifecycle_events]
            
            assert "platform_send" in event_types
            assert "core_received" in event_types
            assert "core_response" in event_types
            
            await client.stop()
        finally:
            await server.stop()
            server_task.cancel()
            try:
                await server_task
            except asyncio.CancelledError:
                pass

    @pytest.mark.asyncio
    async def test_batch_message_processing(self, free_port: int):
        """测试批量消息处理"""
        processed_count = {"count": 0}
        
        runtime = MessageRuntime()
        
        @runtime.on_message
        async def count_handler(msg):
            processed_count["count"] += 1
            return msg
        
        server = MessageServer(host="127.0.0.1", port=free_port)
        server.register_message_handler(lambda msg: asyncio.create_task(runtime.handle_message(msg)))
        
        server_task = asyncio.create_task(server.run())
        await asyncio.sleep(0.3)
        
        try:
            client = MessageClient()
            await client.connect(
                url=f"ws://127.0.0.1:{free_port}/ws",
                platform="batch_test",
            )
            
            # 快速发送多条消息
            for i in range(20):
                msg = make_message(platform="batch_test", text=f"Message {i}")
                await client.send_message(msg)
            
            # 等待处理
            await asyncio.sleep(1.0)
            
            # 验证所有消息都被处理
            assert processed_count["count"] == 20
            
            await client.stop()
        finally:
            await server.stop()
            server_task.cancel()
            try:
                await server_task
            except asyncio.CancelledError:
                pass
