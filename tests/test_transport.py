"""
测试 transport 模块：HTTP 和 WebSocket 传输层
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiohttp import web

from mofox_wire import MessageBuilder, MessageEnvelope, dumps_messages, loads_messages
from mofox_wire.transport.http_server import HttpMessageServer
from mofox_wire.transport.http_client import HttpMessageClient
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
# 测试 HttpMessageServer
# ============================================================

class TestHttpMessageServer:
    """测试 HTTP 消息服务器"""

    @pytest.fixture
    def handler(self) -> AsyncMock:
        return AsyncMock(return_value=None)

    @pytest.fixture
    def server(self, handler: AsyncMock) -> HttpMessageServer:
        return HttpMessageServer(handler=handler, path="/messages")

    def test_create_server(self, server: HttpMessageServer):
        """测试创建服务器"""
        assert server._path == "/messages"

    def test_make_app(self, server: HttpMessageServer):
        """测试获取 aiohttp 应用"""
        app = server.make_app()
        assert isinstance(app, web.Application)

    def test_add_to_app(self, handler: AsyncMock):
        """测试添加到现有应用"""
        server = HttpMessageServer(handler=handler, path="/custom")
        app = web.Application()
        
        server.add_to_app(app)
        
        # 验证路由被添加
        routes = [r.resource.canonical for r in app.router.routes()]
        assert "/custom" in routes

    @pytest.mark.asyncio
    async def test_handle_messages_success(self, server: HttpMessageServer, handler: AsyncMock):
        """测试处理消息成功"""
        messages = [make_message(text=f"msg_{i}") for i in range(3)]
        payload = dumps_messages(messages)
        
        # 创建模拟请求
        mock_request = AsyncMock()
        mock_request.read = AsyncMock(return_value=payload)
        
        response = await server._handle_messages(mock_request)
        
        assert response.status == 200
        handler.assert_called_once()
        
        # 验证处理器收到的消息
        call_args = handler.call_args[0][0]
        assert len(call_args) == 3

    @pytest.mark.asyncio
    async def test_handle_messages_with_response(self, handler: AsyncMock):
        """测试处理消息并返回响应"""
        response_msg = make_message(text="response")
        handler.return_value = [response_msg]
        
        server = HttpMessageServer(handler=handler)
        
        messages = [make_message()]
        payload = dumps_messages(messages)
        
        mock_request = AsyncMock()
        mock_request.read = AsyncMock(return_value=payload)
        
        response = await server._handle_messages(mock_request)
        
        assert response.status == 200
        # 验证响应包含消息
        result = loads_messages(response.body)
        assert len(result) == 1


# ============================================================
# 测试 HttpMessageClient
# ============================================================

class TestHttpMessageClient:
    """测试 HTTP 消息客户端"""

    def test_create_client(self):
        """测试创建客户端"""
        client = HttpMessageClient(base_url="http://localhost:8080")
        
        assert client._base_url == "http://localhost:8080"

    def test_create_client_strips_trailing_slash(self):
        """测试创建客户端时移除尾部斜杠"""
        client = HttpMessageClient(base_url="http://localhost:8080/")
        
        assert client._base_url == "http://localhost:8080"

    @pytest.mark.asyncio
    async def test_send_empty_messages(self):
        """测试发送空消息列表"""
        client = HttpMessageClient(base_url="http://localhost:8080")
        
        result = await client.send_messages([])
        
        assert result == []

    @pytest.mark.asyncio
    async def test_close(self):
        """测试关闭客户端"""
        client = HttpMessageClient(base_url="http://localhost:8080")
        
        # 模拟会话
        mock_session = AsyncMock()
        client._session = mock_session
        
        await client.close()
        
        mock_session.close.assert_called_once()
        assert client._session is None

    @pytest.mark.asyncio
    async def test_context_manager(self):
        """测试上下文管理器"""
        client = HttpMessageClient(base_url="http://localhost:8080")
        
        with patch.object(client, "_ensure_session", new_callable=AsyncMock):
            with patch.object(client, "close", new_callable=AsyncMock) as mock_close:
                async with client:
                    pass
                
                mock_close.assert_called_once()


# ============================================================
# 测试 WsMessageServer
# ============================================================

class TestWsMessageServer:
    """测试 WebSocket 消息服务器"""

    @pytest.fixture
    def handler(self) -> AsyncMock:
        return AsyncMock(return_value=None)

    @pytest.fixture
    def server(self, handler: AsyncMock) -> WsMessageServer:
        return WsMessageServer(handler=handler, path="/ws")

    def test_create_server(self, server: WsMessageServer):
        """测试创建服务器"""
        assert server._path == "/ws"

    def test_make_app(self, server: WsMessageServer):
        """测试获取 aiohttp 应用"""
        app = server.make_app()
        assert isinstance(app, web.Application)

    @pytest.mark.asyncio
    async def test_broadcast_no_connections(self, server: WsMessageServer):
        """测试无连接时广播"""
        messages = [make_message()]
        
        # 不应抛出异常
        await server.broadcast(messages)


# ============================================================
# 测试 WsMessageClient
# ============================================================

class TestWsMessageClient:
    """测试 WebSocket 消息客户端"""

    def test_create_client(self):
        """测试创建客户端"""
        client = WsMessageClient(url="ws://localhost:8080/ws")
        
        assert client._url == "ws://localhost:8080/ws"
        assert client._reconnect_interval == 5.0

    def test_create_client_custom_reconnect(self):
        """测试自定义重连间隔"""
        client = WsMessageClient(
            url="ws://localhost:8080/ws",
            reconnect_interval=10.0,
        )
        
        assert client._reconnect_interval == 10.0

    @pytest.mark.asyncio
    async def test_close(self):
        """测试关闭客户端"""
        client = WsMessageClient(url="ws://localhost:8080/ws")
        
        # 模拟 WebSocket 和会话
        mock_ws = AsyncMock()
        mock_session = AsyncMock()
        client._ws = mock_ws
        client._session = mock_session
        
        await client.close()
        
        mock_ws.close.assert_called_once()
        mock_session.close.assert_called_once()
        assert client._closed is True

    @pytest.mark.asyncio
    async def test_send_empty_messages(self):
        """测试发送空消息列表"""
        client = WsMessageClient(url="ws://localhost:8080/ws")
        
        # 不应抛出异常
        await client.send_messages([])

    @pytest.mark.asyncio
    async def test_context_manager(self):
        """测试上下文管理器"""
        client = WsMessageClient(url="ws://localhost:8080/ws")
        
        with patch.object(client, "connect", new_callable=AsyncMock):
            with patch.object(client, "close", new_callable=AsyncMock) as mock_close:
                async with client:
                    pass
                
                mock_close.assert_called_once()
