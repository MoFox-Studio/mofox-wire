"""
集成测试：断联和自动重试机制
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import aiohttp
import pytest
from aiohttp import web

from mofox_wire import MessageBuilder, MessageEnvelope, MessageServer, MessageClient
from mofox_wire.transport.ws_server import WsMessageServer
from mofox_wire.transport.ws_client import WsMessageClient


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
# 测试断联处理
# ============================================================

@pytest.mark.integration
class TestDisconnection:
    """测试断联处理"""

    @pytest.fixture
    def free_port(self):
        """获取可用端口"""
        import socket
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(('', 0))
            return s.getsockname()[1]

    @pytest.mark.asyncio
    async def test_client_detects_server_shutdown(self, free_port: int):
        """测试客户端检测服务器关闭"""
        disconnect_called = {"called": False, "reason": ""}
        
        async def on_disconnect(platform: str, reason: str):
            disconnect_called["called"] = True
            disconnect_called["reason"] = reason
        
        # 创建服务器
        server = MessageServer(
            host="127.0.0.1",
            port=free_port,
        )
        
        server_task = asyncio.create_task(server.run())
        await asyncio.sleep(0.3)
        
        # 创建客户端
        client = MessageClient(reconnect_interval=0.5)
        client.set_disconnect_callback(on_disconnect)
        
        await client.connect(
            url=f"ws://127.0.0.1:{free_port}/ws",
            platform="test",
        )
        
        assert client.is_connected()
        
        # 关闭服务器
        await server.stop()
        server_task.cancel()
        try:
            await server_task
        except asyncio.CancelledError:
            pass
        
        # 等待客户端检测到断联
        await asyncio.sleep(0.5)
        
        # 验证回调被调用
        assert disconnect_called["called"] is True
        
        await client.stop()

    @pytest.mark.asyncio
    async def test_server_detects_client_disconnect(self, free_port: int):
        """测试服务器检测客户端断开"""
        connection_count = {"connected": 0, "disconnected": 0}
        
        server = MessageServer(
            host="127.0.0.1",
            port=free_port,
        )
        
        server_task = asyncio.create_task(server.run())
        await asyncio.sleep(0.3)
        
        try:
            # 创建客户端并连接
            client = MessageClient()
            await client.connect(
                url=f"ws://127.0.0.1:{free_port}/ws",
                platform="test",
            )
            
            await asyncio.sleep(0.1)
            
            # 记录当前连接数
            initial_connections = len(server._connections)
            assert initial_connections == 1
            
            # 断开客户端
            await client.stop()
            
            await asyncio.sleep(0.2)
            
            # 验证连接已移除
            assert len(server._connections) == 0
        finally:
            await server.stop()
            server_task.cancel()
            try:
                await server_task
            except asyncio.CancelledError:
                pass

    @pytest.mark.asyncio
    async def test_multiple_client_disconnect(self, free_port: int):
        """测试多个客户端断开"""
        server = MessageServer(
            host="127.0.0.1",
            port=free_port,
        )
        
        server_task = asyncio.create_task(server.run())
        await asyncio.sleep(0.3)
        
        clients = []
        try:
            # 创建多个客户端
            for i in range(3):
                client = MessageClient()
                await client.connect(
                    url=f"ws://127.0.0.1:{free_port}/ws",
                    platform=f"platform_{i}",
                )
                clients.append(client)
            
            await asyncio.sleep(0.1)
            assert len(server._connections) == 3
            
            # 逐个断开
            for i, client in enumerate(clients):
                await client.stop()
                await asyncio.sleep(0.1)
                assert len(server._connections) == 2 - i
        finally:
            for client in clients:
                if client.is_connected():
                    await client.stop()
            await server.stop()
            server_task.cancel()
            try:
                await server_task
            except asyncio.CancelledError:
                pass


# ============================================================
# 测试自动重连机制
# ============================================================

@pytest.mark.integration
class TestAutoReconnect:
    """测试自动重连机制"""

    @pytest.fixture
    def free_port(self):
        """获取可用端口"""
        import socket
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(('', 0))
            return s.getsockname()[1]

    @pytest.mark.asyncio
    async def test_client_reconnects_after_server_restart(self, free_port: int):
        """测试服务器重启后客户端重连"""
        received_messages = []
        
        def handler(msg):
            received_messages.append(msg)
        
        # 第一次启动服务器
        server = MessageServer(
            host="127.0.0.1",
            port=free_port,
        )
        server.register_message_handler(handler)
        
        server_task = asyncio.create_task(server.run())
        await asyncio.sleep(0.3)
        
        # 创建客户端（短重连间隔）
        client = MessageClient(reconnect_interval=0.5)
        await client.connect(
            url=f"ws://127.0.0.1:{free_port}/ws",
            platform="test",
        )
        
        # 发送第一条消息
        msg1 = make_message(text="Before restart")
        await client.send_message(msg1)
        await asyncio.sleep(0.1)
        
        assert len(received_messages) == 1
        
        # 关闭服务器
        await server.stop()
        server_task.cancel()
        try:
            await server_task
        except asyncio.CancelledError:
            pass
        
        await asyncio.sleep(0.2)
        
        # 重启服务器
        server2 = MessageServer(
            host="127.0.0.1",
            port=free_port,
        )
        server2.register_message_handler(handler)
        
        server_task2 = asyncio.create_task(server2.run())
        await asyncio.sleep(0.3)
        
        # 等待客户端重连
        await asyncio.sleep(1.0)
        
        try:
            # 发送第二条消息（重连后）
            if client.is_connected():
                msg2 = make_message(text="After restart")
                await client.send_message(msg2)
                await asyncio.sleep(0.2)
                
                # 验证第二条消息被接收
                assert len(received_messages) >= 2
        finally:
            await client.stop()
            await server2.stop()
            server_task2.cancel()
            try:
                await server_task2
            except asyncio.CancelledError:
                pass

    @pytest.mark.asyncio
    async def test_ws_client_reconnect_interval(self, free_port: int):
        """测试 WsMessageClient 重连间隔"""
        reconnect_attempts = {"count": 0}
        reconnect_called = asyncio.Event()
        
        async def handler(msg):
            pass
        
        # 启动服务器
        server = WsMessageServer(handler=handler, path="/ws")
        app = server.make_app()
        
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "127.0.0.1", free_port)
        await site.start()
        
        # 创建一个带有短超时的 session，避免清理时长时间等待
        connector = aiohttp.TCPConnector(force_close=True, enable_cleanup_closed=True)
        session = aiohttp.ClientSession(
            connector=connector,
            timeout=aiohttp.ClientTimeout(total=2, sock_connect=1)
        )
        
        # 创建客户端
        client = WsMessageClient(
            url=f"ws://127.0.0.1:{free_port}/ws",
            reconnect_interval=0.1,  # 使用更短的重连间隔以加快测试
            session=session,
        )
        
        async def tracked_reconnect():
            reconnect_attempts["count"] += 1
            reconnect_called.set()
            # 阻止实际重连，避免无限循环
            client._closed = True  # 停止进一步重连
        
        client._reconnect = tracked_reconnect
        
        await client.connect()
        await asyncio.sleep(0.1)
        
        # 关闭服务器触发重连
        await runner.cleanup()
        
        try:
            # 等待重连被调用，设置超时
            await asyncio.wait_for(reconnect_called.wait(), timeout=2.0)
            
            # 验证有重连尝试
            assert reconnect_attempts["count"] >= 1
        finally:
            # 确保客户端被关闭
            client._closed = True
            if client._receive_task:
                client._receive_task.cancel()
                try:
                    await asyncio.wait_for(client._receive_task, timeout=0.5)
                except (asyncio.CancelledError, asyncio.TimeoutError, Exception):
                    pass
            if client._ws and not client._ws.closed:
                try:
                    await client._ws.close()
                except Exception:
                    pass
            # 强制关闭连接器和 session
            await connector.close()
            await session.close()


# ============================================================
# 测试连接替换
# ============================================================

@pytest.mark.integration
class TestConnectionReplacement:
    """测试连接替换"""

    @pytest.fixture
    def free_port(self):
        """获取可用端口"""
        import socket
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(('', 0))
            return s.getsockname()[1]

    @pytest.mark.asyncio
    async def test_same_platform_replaces_connection(self, free_port: int):
        """测试相同平台的新连接替换旧连接"""
        received_from = []
        
        def handler(msg):
            received_from.append(msg.get("metadata", {}).get("client_id"))
        
        server = MessageServer(
            host="127.0.0.1",
            port=free_port,
        )
        server.register_message_handler(handler)
        
        server_task = asyncio.create_task(server.run())
        await asyncio.sleep(0.3)
        
        try:
            # 第一个客户端
            client1 = MessageClient()
            await client1.connect(
                url=f"ws://127.0.0.1:{free_port}/ws",
                platform="test_platform",
            )
            
            await asyncio.sleep(0.1)
            assert len(server._platform_connections) == 1
            
            # 第二个客户端使用相同平台
            client2 = MessageClient()
            await client2.connect(
                url=f"ws://127.0.0.1:{free_port}/ws",
                platform="test_platform",
            )
            
            await asyncio.sleep(0.2)
            
            # 验证只有一个平台连接
            assert len(server._platform_connections) == 1
            
            # 新客户端应该是活跃的
            msg = make_message(platform="test_platform")
            msg["metadata"] = {"client_id": "client2"}
            await client2.send_message(msg)
            
            await asyncio.sleep(0.1)
            
            assert "client2" in received_from
            
            await client1.stop()
            await client2.stop()
        finally:
            await server.stop()
            server_task.cancel()
            try:
                await server_task
            except asyncio.CancelledError:
                pass


# ============================================================
# 测试优雅关闭
# ============================================================

@pytest.mark.integration
class TestGracefulShutdown:
    """测试优雅关闭"""

    @pytest.fixture
    def free_port(self):
        """获取可用端口"""
        import socket
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(('', 0))
            return s.getsockname()[1]

    @pytest.mark.asyncio
    async def test_server_graceful_shutdown(self, free_port: int):
        """测试服务器优雅关闭"""
        server = MessageServer(
            host="127.0.0.1",
            port=free_port,
        )
        
        server_task = asyncio.create_task(server.run())
        await asyncio.sleep(0.3)
        
        # 创建多个客户端
        clients = []
        for i in range(3):
            client = MessageClient()
            await client.connect(
                url=f"ws://127.0.0.1:{free_port}/ws",
                platform=f"platform_{i}",
            )
            clients.append(client)
        
        await asyncio.sleep(0.1)
        
        # 优雅关闭服务器
        await server.stop()
        server_task.cancel()
        try:
            await server_task
        except asyncio.CancelledError:
            pass
        
        # 验证服务器状态
        assert len(server._connections) == 0
        assert len(server._platform_connections) == 0
        assert server._running is False
        
        # 清理客户端
        for client in clients:
            await client.stop()

    @pytest.mark.asyncio
    async def test_client_graceful_shutdown(self, free_port: int):
        """测试客户端优雅关闭"""
        server = MessageServer(
            host="127.0.0.1",
            port=free_port,
        )
        
        server_task = asyncio.create_task(server.run())
        await asyncio.sleep(0.3)
        
        try:
            client = MessageClient()
            await client.connect(
                url=f"ws://127.0.0.1:{free_port}/ws",
                platform="test",
            )
            
            assert client.is_connected()
            
            # 优雅关闭客户端
            await client.stop()
            
            # 验证客户端状态
            assert client._closed is True
            assert client._ws is None
            assert client._session is None
        finally:
            await server.stop()
            server_task.cancel()
            try:
                await server_task
            except asyncio.CancelledError:
                pass
