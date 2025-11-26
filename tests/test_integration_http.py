"""
集成测试：HTTP 连接
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest
from aiohttp import web

from mofox_wire import MessageBuilder, MessageEnvelope
from mofox_wire.transport.http_server import HttpMessageServer
from mofox_wire.transport.http_client import HttpMessageClient
from mofox_wire.codec import dumps_messages, loads_messages


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
# 测试 HttpMessageServer 和 HttpMessageClient 集成
# ============================================================

@pytest.mark.integration
class TestHttpIntegration:
    """HTTP 服务器-客户端集成测试"""

    @pytest.fixture
    def free_port(self):
        """获取可用端口"""
        import socket
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(('', 0))
            return s.getsockname()[1]

    @pytest.mark.asyncio
    async def test_client_server_message_exchange(self, free_port: int):
        """测试客户端-服务器消息交换"""
        received_messages = []
        
        async def handler(messages):
            received_messages.extend(messages)
            return None
        
        # 创建服务器
        server = HttpMessageServer(handler=handler, path="/messages")
        app = server.make_app()
        
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "127.0.0.1", free_port)
        await site.start()
        
        try:
            # 创建客户端
            async with HttpMessageClient(f"http://127.0.0.1:{free_port}") as client:
                # 发送消息
                msg = make_message(text="Hello from client")
                await client.send_messages([msg])
                
                # 验证服务器收到消息
                assert len(received_messages) == 1
                assert received_messages[0]["message_segment"]["data"] == "Hello from client"
        finally:
            await runner.cleanup()

    @pytest.mark.asyncio
    async def test_batch_messages(self, free_port: int):
        """测试批量消息"""
        received_messages = []
        
        async def handler(messages):
            received_messages.extend(messages)
            return None
        
        server = HttpMessageServer(handler=handler)
        app = server.make_app()
        
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "127.0.0.1", free_port)
        await site.start()
        
        try:
            async with HttpMessageClient(f"http://127.0.0.1:{free_port}") as client:
                # 发送批量消息
                messages = [make_message(text=f"Message {i}") for i in range(10)]
                await client.send_messages(messages)
                
                # 验证
                assert len(received_messages) == 10
        finally:
            await runner.cleanup()

    @pytest.mark.asyncio
    async def test_request_response(self, free_port: int):
        """测试请求-响应模式"""
        async def handler(messages):
            # 返回响应消息
            responses = []
            for msg in messages:
                response = make_message(
                    platform=msg["message_info"]["platform"],
                    text=f"Echo: {msg['message_segment']['data']}",
                )
                responses.append(response)
            return responses
        
        server = HttpMessageServer(handler=handler)
        app = server.make_app()
        
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "127.0.0.1", free_port)
        await site.start()
        
        try:
            async with HttpMessageClient(f"http://127.0.0.1:{free_port}") as client:
                # 发送消息并期望响应
                msg = make_message(text="Original message")
                responses = await client.send_messages([msg], expect_reply=True)
                
                # 验证响应
                assert responses is not None
                assert len(responses) == 1
                assert "Echo:" in responses[0]["message_segment"]["data"]
        finally:
            await runner.cleanup()

    @pytest.mark.asyncio
    async def test_custom_path(self, free_port: int):
        """测试自定义路径"""
        received = []
        
        async def handler(messages):
            received.extend(messages)
            return None
        
        server = HttpMessageServer(handler=handler, path="/api/v1/messages")
        app = server.make_app()
        
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "127.0.0.1", free_port)
        await site.start()
        
        try:
            async with HttpMessageClient(f"http://127.0.0.1:{free_port}") as client:
                msg = make_message()
                await client.send_messages([msg], path="/api/v1/messages")
                
                assert len(received) == 1
        finally:
            await runner.cleanup()

    @pytest.mark.asyncio
    async def test_add_to_existing_app(self, free_port: int):
        """测试添加到现有应用"""
        received = []
        
        async def handler(messages):
            received.extend(messages)
            return None
        
        # 创建主应用
        app = web.Application()
        
        # 添加自定义路由
        async def health_check(request):
            return web.json_response({"status": "ok"})
        
        app.router.add_get("/health", health_check)
        
        # 添加消息服务器
        server = HttpMessageServer(handler=handler, path="/messages")
        server.add_to_app(app)
        
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "127.0.0.1", free_port)
        await site.start()
        
        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                # 测试健康检查
                async with session.get(f"http://127.0.0.1:{free_port}/health") as resp:
                    assert resp.status == 200
                    data = await resp.json()
                    assert data["status"] == "ok"
            
            # 测试消息发送
            async with HttpMessageClient(f"http://127.0.0.1:{free_port}") as client:
                msg = make_message()
                await client.send_messages([msg])
                
                assert len(received) == 1
        finally:
            await runner.cleanup()

    @pytest.mark.asyncio
    async def test_concurrent_requests(self, free_port: int):
        """测试并发请求"""
        received = []
        lock = asyncio.Lock()
        
        async def handler(messages):
            async with lock:
                received.extend(messages)
            await asyncio.sleep(0.01)  # 模拟处理延迟
            return None
        
        server = HttpMessageServer(handler=handler)
        app = server.make_app()
        
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "127.0.0.1", free_port)
        await site.start()
        
        try:
            async with HttpMessageClient(f"http://127.0.0.1:{free_port}") as client:
                # 并发发送多个请求
                tasks = []
                for i in range(10):
                    msg = make_message(text=f"Concurrent message {i}")
                    task = asyncio.create_task(client.send_messages([msg]))
                    tasks.append(task)
                
                await asyncio.gather(*tasks)
                
                # 验证所有消息都被接收
                assert len(received) == 10
        finally:
            await runner.cleanup()

    @pytest.mark.asyncio
    async def test_large_message_batch(self, free_port: int):
        """测试大批量消息"""
        received = []
        
        async def handler(messages):
            received.extend(messages)
            return None
        
        server = HttpMessageServer(handler=handler)
        app = server.make_app()
        
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "127.0.0.1", free_port)
        await site.start()
        
        try:
            async with HttpMessageClient(f"http://127.0.0.1:{free_port}") as client:
                # 发送 100 条消息
                messages = [make_message(text=f"Large batch message {i}") for i in range(100)]
                await client.send_messages(messages)
                
                assert len(received) == 100
        finally:
            await runner.cleanup()
