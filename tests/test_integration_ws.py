"""
集成测试：WebSocket 连接
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest
import aiohttp
from aiohttp import web

from mofox_wire import MessageBuilder, MessageEnvelope, MessageServer, MessageClient
from mofox_wire.transport.ws_server import WsMessageServer
from mofox_wire.transport.ws_client import WsMessageClient
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
# 测试 WsMessageServer 和 WsMessageClient 集成
# ============================================================

@pytest.mark.integration
class TestWsIntegration:
    """WebSocket 服务器-客户端集成测试"""

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
        
        async def handler(msg: MessageEnvelope):
            received_messages.append(msg)
        
        # 创建服务器
        server = WsMessageServer(handler=handler, path="/ws")
        app = server.make_app()
        
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "127.0.0.1", free_port)
        await site.start()
        
        try:
            # 创建客户端并连接
            client = WsMessageClient(
                url=f"ws://127.0.0.1:{free_port}/ws",
                reconnect_interval=1.0,
            )
            await client.connect()
            
            # 发送消息
            msg = make_message(text="Hello from client")
            await client.send_message(msg)
            
            # 等待服务器处理
            await asyncio.sleep(0.2)
            
            # 验证服务器收到消息
            assert len(received_messages) == 1
            assert received_messages[0]["message_segment"]["data"] == "Hello from client"
            
            await client.close()
        finally:
            await runner.cleanup()

    @pytest.mark.asyncio
    async def test_server_broadcast_to_client(self, free_port: int):
        """测试服务器广播到客户端"""
        client_received = []
        
        async def client_handler(msg: MessageEnvelope):
            client_received.append(msg)
        
        async def server_handler(msg: MessageEnvelope):
            pass  # 服务器端处理
        
        # 创建服务器
        server = WsMessageServer(handler=server_handler, path="/ws")
        app = server.make_app()
        
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "127.0.0.1", free_port)
        await site.start()
        
        try:
            # 创建客户端
            client = WsMessageClient(
                url=f"ws://127.0.0.1:{free_port}/ws",
                handler=client_handler,
            )
            await client.connect()
            
            # 等待连接建立
            await asyncio.sleep(0.1)
            
            # 服务器广播消息
            broadcast_msg = make_message(text="Broadcast message")
            await server.broadcast([broadcast_msg])
            
            # 等待客户端接收
            await asyncio.sleep(0.2)
            
            # 验证客户端收到广播
            assert len(client_received) == 1
            assert client_received[0]["message_segment"]["data"] == "Broadcast message"
            
            await client.close()
        finally:
            await runner.cleanup()

    @pytest.mark.asyncio
    async def test_multiple_clients(self, free_port: int):
        """测试多个客户端连接"""
        received_count = {"count": 0}
        
        async def handler(msg: MessageEnvelope):
            received_count["count"] += 1
        
        # 创建服务器
        server = WsMessageServer(handler=handler, path="/ws")
        app = server.make_app()
        
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "127.0.0.1", free_port)
        await site.start()
        
        clients = []
        try:
            # 创建多个客户端
            for i in range(3):
                client = WsMessageClient(url=f"ws://127.0.0.1:{free_port}/ws")
                await client.connect()
                clients.append(client)
            
            # 每个客户端发送一条消息
            for i, client in enumerate(clients):
                msg = make_message(text=f"Message from client {i}")
                await client.send_message(msg)
            
            # 等待处理
            await asyncio.sleep(0.3)
            
            # 验证服务器收到所有消息
            assert received_count["count"] == 3
            
        finally:
            for client in clients:
                await client.close()
            await runner.cleanup()

    @pytest.mark.asyncio
    async def test_batch_messages(self, free_port: int):
        """测试批量消息"""
        received_messages = []
        
        async def handler(msg: MessageEnvelope):
            received_messages.append(msg)
        
        # 创建服务器
        server = WsMessageServer(handler=handler, path="/ws")
        app = server.make_app()
        
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "127.0.0.1", free_port)
        await site.start()
        
        try:
            # 创建客户端
            client = WsMessageClient(url=f"ws://127.0.0.1:{free_port}/ws")
            await client.connect()
            
            # 发送批量消息
            messages = [make_message(text=f"Batch message {i}") for i in range(5)]
            await client.send_messages(messages)
            
            # 等待处理
            await asyncio.sleep(0.3)
            
            # 验证服务器收到所有消息
            assert len(received_messages) == 5
            
            await client.close()
        finally:
            await runner.cleanup()


# ============================================================
# 测试 MessageServer 和 MessageClient 集成
# ============================================================

@pytest.mark.integration
class TestMessageServerClientIntegration:
    """MessageServer 和 MessageClient 集成测试"""

    @pytest.fixture
    def free_port(self):
        """获取可用端口"""
        import socket
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(('', 0))
            return s.getsockname()[1]

    @pytest.mark.asyncio
    async def test_basic_connection(self, free_port: int):
        """测试基本连接"""
        received_messages = []
        
        def handler(msg):
            received_messages.append(msg)
        
        # 创建服务器
        server = MessageServer(
            host="127.0.0.1",
            port=free_port,
            path="/ws",
        )
        server.register_message_handler(handler)
        
        # 启动服务器
        server_task = asyncio.create_task(server.run())
        await asyncio.sleep(0.3)  # 等待服务器启动
        
        try:
            # 创建客户端
            client = MessageClient(reconnect_interval=1.0)
            await client.connect(
                url=f"ws://127.0.0.1:{free_port}/ws",
                platform="test",
            )
            
            # 发送消息
            msg = make_message(platform="test", text="Hello")
            await client.send_message(msg)
            
            # 等待处理
            await asyncio.sleep(0.3)
            
            # 验证
            assert len(received_messages) == 1
            
            await client.stop()
        finally:
            await server.stop()
            server_task.cancel()
            try:
                await server_task
            except asyncio.CancelledError:
                pass

    @pytest.mark.asyncio
    async def test_token_authentication(self, free_port: int):
        """测试 token 认证"""
        # 创建启用 token 的服务器
        server = MessageServer(
            host="127.0.0.1",
            port=free_port,
            enable_token=True,
        )
        server.add_valid_token("valid_token")
        
        server_task = asyncio.create_task(server.run())
        await asyncio.sleep(0.3)
        
        try:
            # 使用有效 token 连接
            client = MessageClient()
            await client.connect(
                url=f"ws://127.0.0.1:{free_port}/ws",
                platform="test",
                token="valid_token",
            )
            
            assert client.is_connected()
            
            await client.stop()
        finally:
            await server.stop()
            server_task.cancel()
            try:
                await server_task
            except asyncio.CancelledError:
                pass

    @pytest.mark.asyncio
    async def test_platform_routing(self, free_port: int):
        """测试平台路由"""
        received_by_platform = {"qq": [], "discord": []}
        
        def handler(msg):
            platform = msg.get("message_info", {}).get("platform")
            if platform in received_by_platform:
                received_by_platform[platform].append(msg)
        
        server = MessageServer(
            host="127.0.0.1",
            port=free_port,
        )
        server.register_message_handler(handler)
        
        server_task = asyncio.create_task(server.run())
        await asyncio.sleep(0.3)
        
        try:
            # 创建两个不同平台的客户端
            qq_client = MessageClient()
            await qq_client.connect(
                url=f"ws://127.0.0.1:{free_port}/ws",
                platform="qq",
            )
            
            discord_client = MessageClient()
            await discord_client.connect(
                url=f"ws://127.0.0.1:{free_port}/ws",
                platform="discord",
            )
            
            # 发送消息
            qq_msg = make_message(platform="qq", text="QQ message")
            await qq_client.send_message(qq_msg)
            
            discord_msg = make_message(platform="discord", text="Discord message")
            await discord_client.send_message(discord_msg)
            
            await asyncio.sleep(0.3)
            
            # 验证
            assert len(received_by_platform["qq"]) == 1
            assert len(received_by_platform["discord"]) == 1
            
            await qq_client.stop()
            await discord_client.stop()
        finally:
            await server.stop()
            server_task.cancel()
            try:
                await server_task
            except asyncio.CancelledError:
                pass
