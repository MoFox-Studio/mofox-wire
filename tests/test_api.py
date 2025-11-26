"""
测试 api 模块：MessageServer 和 MessageClient
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from mofox_wire import MessageBuilder, MessageEnvelope
from mofox_wire.api import (
    BaseMessageHandler,
    MessageClient,
    MessageServer,
    _attach_raw_bytes,
    _encode_for_ws_send,
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
# 测试辅助函数
# ============================================================

class TestHelperFunctions:
    """测试辅助函数"""

    def test_attach_raw_bytes_to_dict(self):
        """测试附加 raw_bytes 到字典"""
        payload = {"type": "text", "data": "hello"}
        raw = b"raw data"
        
        result = _attach_raw_bytes(payload, raw)
        
        assert result["raw_bytes"] == raw

    def test_attach_raw_bytes_preserves_existing(self):
        """测试不覆盖已存在的 raw_bytes"""
        existing = b"existing"
        payload = {"type": "text", "raw_bytes": existing}
        raw = b"new data"
        
        result = _attach_raw_bytes(payload, raw)
        
        assert result["raw_bytes"] == existing

    def test_attach_raw_bytes_to_list(self):
        """测试附加 raw_bytes 到列表"""
        payload = [{"type": "text"}, {"type": "image"}]
        raw = b"raw data"
        
        result = _attach_raw_bytes(payload, raw)
        
        assert result[0]["raw_bytes"] == raw
        assert result[1]["raw_bytes"] == raw

    def test_encode_for_ws_send_dict(self):
        """测试编码字典消息"""
        msg = {"type": "text", "data": "hello"}
        
        data, is_binary = _encode_for_ws_send(msg)
        
        assert isinstance(data, str)
        assert is_binary is False
        assert "hello" in data

    def test_encode_for_ws_send_bytes(self):
        """测试编码字节消息"""
        msg = b"binary data"
        
        data, is_binary = _encode_for_ws_send(msg)
        
        assert data == msg
        assert is_binary is True

    def test_encode_for_ws_send_use_raw_bytes(self):
        """测试使用 raw_bytes 编码"""
        raw = b"raw binary"
        msg = {"type": "text", "raw_bytes": raw}
        
        data, is_binary = _encode_for_ws_send(msg, use_raw_bytes=True)
        
        assert data == raw
        assert is_binary is True

    def test_encode_for_ws_send_strips_raw_bytes(self):
        """测试编码时移除 raw_bytes"""
        msg = {"type": "text", "data": "hello", "raw_bytes": b"raw"}
        
        data, is_binary = _encode_for_ws_send(msg, use_raw_bytes=False)
        
        assert b"raw_bytes" not in data.encode() if isinstance(data, str) else b"raw_bytes" not in data


# ============================================================
# 测试 BaseMessageHandler
# ============================================================

class TestBaseMessageHandler:
    """测试基础消息处理器"""

    @pytest.fixture
    def handler(self) -> BaseMessageHandler:
        return BaseMessageHandler()

    def test_register_message_handler(self, handler: BaseMessageHandler):
        """测试注册消息处理器"""
        callback = AsyncMock()
        handler.register_message_handler(callback)
        
        assert callback in handler.message_handlers

    def test_register_duplicate_handler(self, handler: BaseMessageHandler):
        """测试不重复注册相同处理器"""
        callback = AsyncMock()
        handler.register_message_handler(callback)
        handler.register_message_handler(callback)
        
        assert handler.message_handlers.count(callback) == 1

    @pytest.mark.asyncio
    async def test_process_message(self, handler: BaseMessageHandler):
        """测试处理消息"""
        callback = AsyncMock()
        handler.register_message_handler(callback)
        
        msg = make_message()
        await handler.process_message(msg)
        
        callback.assert_called_once_with(msg)

    @pytest.mark.asyncio
    async def test_process_message_multiple_handlers(self, handler: BaseMessageHandler):
        """测试多个处理器并发执行"""
        callback1 = AsyncMock()
        callback2 = AsyncMock()
        handler.register_message_handler(callback1)
        handler.register_message_handler(callback2)
        
        msg = make_message()
        await handler.process_message(msg)
        
        callback1.assert_called_once()
        callback2.assert_called_once()


# ============================================================
# 测试 MessageServer
# ============================================================

class TestMessageServer:
    """测试消息服务器"""

    def test_create_server_default(self):
        """测试创建默认服务器"""
        server = MessageServer()
        
        assert server.host == "0.0.0.0"
        assert server.port == 18000
        assert server._path == "/ws"

    def test_create_server_custom(self):
        """测试创建自定义服务器"""
        server = MessageServer(
            host="127.0.0.1",
            port=9000,
            path="/custom/ws",
        )
        
        assert server.host == "127.0.0.1"
        assert server.port == 9000
        assert server._path == "/custom/ws"

    def test_create_server_tcp_not_supported(self):
        """测试 TCP 模式不支持"""
        with pytest.raises(NotImplementedError, match="Only WebSocket mode"):
            MessageServer(mode="tcp")

    def test_add_valid_token(self):
        """测试添加有效 token"""
        server = MessageServer(enable_token=True)
        server.add_valid_token("secret_token")
        
        assert "secret_token" in server._valid_tokens

    def test_remove_valid_token(self):
        """测试移除有效 token"""
        server = MessageServer(enable_token=True)
        server.add_valid_token("token1")
        server.remove_valid_token("token1")
        
        assert "token1" not in server._valid_tokens

    @pytest.mark.asyncio
    async def test_verify_token_disabled(self):
        """测试禁用 token 验证"""
        server = MessageServer(enable_token=False)
        
        result = await server.verify_token(None)
        assert result is True

    @pytest.mark.asyncio
    async def test_verify_token_valid(self):
        """测试验证有效 token"""
        server = MessageServer(enable_token=True)
        server.add_valid_token("valid_token")
        
        result = await server.verify_token("valid_token")
        assert result is True

    @pytest.mark.asyncio
    async def test_verify_token_invalid(self):
        """测试验证无效 token"""
        server = MessageServer(enable_token=True)
        
        result = await server.verify_token("invalid_token")
        assert result is False

    @pytest.mark.asyncio
    async def test_stop_clears_connections(self):
        """测试停止清除连接"""
        server = MessageServer()
        server._running = True
        
        await server.stop()
        
        assert len(server._connections) == 0
        assert len(server._platform_connections) == 0


# ============================================================
# 测试 MessageClient
# ============================================================

class TestMessageClient:
    """测试消息客户端"""

    def test_create_client_default(self):
        """测试创建默认客户端"""
        client = MessageClient()
        
        assert client._mode == "ws"
        assert client._reconnect_interval == 5.0

    def test_create_client_custom(self):
        """测试创建自定义客户端"""
        client = MessageClient(reconnect_interval=10.0)
        
        assert client._reconnect_interval == 10.0

    def test_create_client_tcp_not_supported(self):
        """测试 TCP 模式不支持"""
        with pytest.raises(NotImplementedError, match="Only WebSocket mode"):
            MessageClient(mode="tcp")

    def test_is_connected_no_ws(self):
        """测试未连接状态"""
        client = MessageClient()
        
        assert client.is_connected() is False

    def test_set_disconnect_callback(self):
        """测试设置断开回调"""
        client = MessageClient()
        callback = AsyncMock()
        
        client.set_disconnect_callback(callback)
        
        assert client._on_disconnect is callback

    @pytest.mark.asyncio
    async def test_stop_closes_session(self):
        """测试停止关闭会话"""
        client = MessageClient()
        
        # Mock session
        mock_session = AsyncMock()
        client._session = mock_session
        
        await client.stop()
        
        mock_session.close.assert_called_once()
        assert client._session is None

    @pytest.mark.asyncio
    async def test_context_manager_requires_connect(self):
        """测试上下文管理器需要先连接"""
        client = MessageClient()
        
        with pytest.raises(RuntimeError, match="connect\\(\\) must be called"):
            async with client:
                pass


# ============================================================
# 测试消息队列处理
# ============================================================

class TestMessageQueueProcessing:
    """测试消息队列处理"""

    @pytest.mark.asyncio
    async def test_enqueue_message(self):
        """测试入队消息"""
        server = MessageServer(queue_maxsize=10)
        server._running = True
        server._worker_tasks = [AsyncMock()]  # 模拟工作线程
        
        msg = {"type": "text", "data": "hello"}
        await server._enqueue_message(msg)
        
        assert not server._message_queue.empty()

    @pytest.mark.asyncio
    async def test_start_workers(self):
        """测试启动工作线程"""
        server = MessageServer(worker_count=2)
        
        server._start_workers()
        
        assert len(server._worker_tasks) == 2
        assert server._running is True
        
        await server._stop_workers()

    @pytest.mark.asyncio
    async def test_stop_workers(self):
        """测试停止工作线程"""
        server = MessageServer(worker_count=2)
        server._start_workers()
        
        await server._stop_workers()
        
        assert len(server._worker_tasks) == 0
        assert server._running is False


# ============================================================
# 测试广播功能
# ============================================================

class TestBroadcasting:
    """测试广播功能"""

    @pytest.mark.asyncio
    async def test_broadcast_to_platform_no_connection(self):
        """测试广播到无连接平台抛出异常"""
        server = MessageServer()
        
        msg = make_message(platform="test")
        
        with pytest.raises(RuntimeError, match="没有活跃的连接"):
            await server.broadcast_to_platform("test", msg)

    @pytest.mark.asyncio
    async def test_send_message_no_platform_raises(self):
        """测试发送消息无平台信息抛出异常"""
        server = MessageServer()
        
        msg: MessageEnvelope = {
            "message_info": {"message_id": "1"},  # 缺少 platform
            "message_segment": {"type": "text", "data": "hello"},
        }
        
        with pytest.raises(ValueError, match="message_info.platform is required"):
            await server.send_message(msg)
