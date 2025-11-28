"""
测试 router 模块：消息路由器
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from mofox_wire import MessageBuilder, MessageEnvelope
from mofox_wire.router import RouteConfig, Router, TargetConfig, HandlerEntry, DEFAULT_PRIORITY


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
# 测试 TargetConfig
# ============================================================

class TestTargetConfig:
    """测试路由目标配置"""

    def test_create_target_config(self):
        """测试创建目标配置"""
        config = TargetConfig(
            url="ws://localhost:8080/ws",
            token="secret_token",
            ssl_verify="/path/to/cert.pem",
        )
        
        assert config.url == "ws://localhost:8080/ws"
        assert config.token == "secret_token"
        assert config.ssl_verify == "/path/to/cert.pem"

    def test_default_values(self):
        """测试默认值"""
        config = TargetConfig(url="ws://localhost:8080")
        
        assert config.token is None
        assert config.ssl_verify is None

    def test_to_dict(self):
        """测试转换为字典"""
        config = TargetConfig(
            url="ws://localhost:8080",
            token="token123",
        )
        
        result = config.to_dict()
        
        assert result["url"] == "ws://localhost:8080"
        assert result["token"] == "token123"
        assert result["ssl_verify"] is None

    def test_from_dict(self):
        """测试从字典创建"""
        data = {
            "url": "ws://localhost:9000",
            "token": "my_token",
            "ssl_verify": None,
        }
        
        config = TargetConfig.from_dict(data)
        
        assert config.url == "ws://localhost:9000"
        assert config.token == "my_token"


# ============================================================
# 测试 RouteConfig
# ============================================================

class TestRouteConfig:
    """测试路由配置"""

    def test_create_route_config(self):
        """测试创建路由配置"""
        config = RouteConfig(
            route_config={
                "qq": TargetConfig(url="ws://qq-adapter:8080"),
                "discord": TargetConfig(url="ws://discord-adapter:8080"),
            }
        )
        
        assert "qq" in config.route_config
        assert "discord" in config.route_config
        assert config.route_config["qq"].url == "ws://qq-adapter:8080"

    def test_to_dict(self):
        """测试转换为字典"""
        config = RouteConfig(
            route_config={
                "qq": TargetConfig(url="ws://qq:8080", token="qq_token"),
            }
        )
        
        result = config.to_dict()
        
        assert "route_config" in result
        assert result["route_config"]["qq"]["url"] == "ws://qq:8080"
        assert result["route_config"]["qq"]["token"] == "qq_token"

    def test_from_dict(self):
        """测试从字典创建"""
        data = {
            "route_config": {
                "qq": {"url": "ws://qq:8080", "token": "token"},
                "discord": {"url": "ws://discord:8080"},
            }
        }
        
        config = RouteConfig.from_dict(data)
        
        assert len(config.route_config) == 2
        assert config.route_config["qq"].token == "token"
        assert config.route_config["discord"].token is None


# ============================================================
# 测试 Router 基本功能
# ============================================================

class TestRouterBasic:
    """测试路由器基本功能"""

    @pytest.fixture
    def route_config(self) -> RouteConfig:
        return RouteConfig(
            route_config={
                "test_platform": TargetConfig(url="ws://localhost:19001/ws"),
            }
        )

    def test_create_router(self, route_config: RouteConfig):
        """测试创建路由器"""
        router = Router(config=route_config)
        
        assert router.config is route_config
        assert len(router.clients) == 0
        assert router._running is False

    def test_register_class_handler(self, route_config: RouteConfig):
        """测试注册类处理器"""
        router = Router(config=route_config)
        handler = MagicMock()
        
        router.register_class_handler(handler)
        
        assert len(router.handlers) == 1
        assert router.handlers[0].handler is handler
        assert router.handlers[0].priority == DEFAULT_PRIORITY

    @pytest.mark.asyncio
    async def test_connect_unknown_platform_raises(self, route_config: RouteConfig):
        """测试连接未知平台抛出异常"""
        router = Router(config=route_config)
        
        with pytest.raises(ValueError, match="未知平台"):
            await router.connect("unknown_platform")

    @pytest.mark.asyncio
    async def test_connect_tcp_not_implemented(self):
        """测试 TCP 模式未实现"""
        config = RouteConfig(
            route_config={
                "test": TargetConfig(url="tcp://localhost:8080"),
            }
        )
        router = Router(config=config)
        
        with pytest.raises(NotImplementedError, match="TCP 模式暂未实现"):
            await router.connect("test")


# ============================================================
# 测试 Router 消息路由
# ============================================================

class TestRouterMessageRouting:
    """测试路由器消息路由"""

    @pytest.fixture
    def route_config(self) -> RouteConfig:
        return RouteConfig(
            route_config={
                "platform_a": TargetConfig(url="ws://a:8080"),
                "platform_b": TargetConfig(url="ws://b:8080"),
            }
        )

    def test_get_target_url(self, route_config: RouteConfig):
        """测试获取目标 URL"""
        router = Router(config=route_config)
        
        msg = make_message(platform="platform_a")
        url = router.get_target_url(msg)
        
        assert url == "ws://a:8080"

    def test_get_target_url_unknown_platform(self, route_config: RouteConfig):
        """测试获取未知平台的目标 URL"""
        router = Router(config=route_config)
        
        msg = make_message(platform="unknown")
        url = router.get_target_url(msg)
        
        assert url is None

    def test_get_target_url_no_platform(self, route_config: RouteConfig):
        """测试消息无平台信息"""
        router = Router(config=route_config)
        
        msg: MessageEnvelope = {
            "message_info": {"message_id": "1"},  # 缺少 platform
            "message_segment": {"type": "text", "data": "hello"},
        }
        url = router.get_target_url(msg)
        
        assert url is None

    @pytest.mark.asyncio
    async def test_send_message_no_platform_raises(self, route_config: RouteConfig):
        """测试发送消息无平台信息抛出异常"""
        router = Router(config=route_config)
        
        msg: MessageEnvelope = {
            "message_info": {"message_id": "1"},  # 缺少 platform
            "message_segment": {"type": "text", "data": "hello"},
        }
        
        with pytest.raises(ValueError, match="缺少必需的 message_info.platform 字段"):
            await router.send_message(msg)

    @pytest.mark.asyncio
    async def test_send_message_no_client_raises(self, route_config: RouteConfig):
        """测试发送消息无客户端抛出异常"""
        router = Router(config=route_config)
        
        msg = make_message(platform="platform_a")
        
        with pytest.raises(RuntimeError, match="没有已连接的客户端"):
            await router.send_message(msg)


# ============================================================
# 测试 Router 配置更新
# ============================================================

class TestRouterConfigUpdate:
    """测试路由器配置更新"""

    @pytest.fixture
    def route_config(self) -> RouteConfig:
        return RouteConfig(
            route_config={
                "platform_a": TargetConfig(url="ws://a:8080"),
            }
        )

    @pytest.mark.asyncio
    async def test_update_config_adds_platform(self, route_config: RouteConfig):
        """测试更新配置添加平台"""
        router = Router(config=route_config)
        
        new_config = {
            "route_config": {
                "platform_a": {"url": "ws://a:8080"},
                "platform_b": {"url": "ws://b:8080"},
            }
        }
        
        # Mock connect to avoid actual connection
        with patch.object(router, "connect", new_callable=AsyncMock) as mock_connect:
            await router.update_config(new_config)
            
            # 验证新平台被连接
            mock_connect.assert_called_with("platform_b")

    @pytest.mark.asyncio
    async def test_update_config_removes_platform(self, route_config: RouteConfig):
        """测试更新配置移除平台"""
        # 先添加多个平台
        config = RouteConfig(
            route_config={
                "platform_a": TargetConfig(url="ws://a:8080"),
                "platform_b": TargetConfig(url="ws://b:8080"),
            }
        )
        router = Router(config=config)
        
        new_config = {
            "route_config": {
                "platform_a": {"url": "ws://a:8080"},
                # platform_b 被移除
            }
        }
        
        with patch.object(router, "remove_platform", new_callable=AsyncMock) as mock_remove:
            await router.update_config(new_config)
            
            # 验证平台被移除
            mock_remove.assert_called_with("platform_b")

    @pytest.mark.asyncio
    async def test_update_config_changes_url(self, route_config: RouteConfig):
        """测试更新配置改变 URL"""
        router = Router(config=route_config)
        
        new_config = {
            "route_config": {
                "platform_a": {"url": "ws://new-a:9000"},  # URL 改变
            }
        }
        
        with patch.object(router, "remove_platform", new_callable=AsyncMock) as mock_remove:
            with patch.object(router, "connect", new_callable=AsyncMock) as mock_connect:
                await router.update_config(new_config)
                
                # 验证旧连接被移除，新连接被创建
                mock_remove.assert_called_with("platform_a")
                mock_connect.assert_called_with("platform_a")


# ============================================================
# 测试 Router 生命周期
# ============================================================

class TestRouterLifecycle:
    """测试路由器生命周期"""

    @pytest.fixture
    def route_config(self) -> RouteConfig:
        return RouteConfig(
            route_config={
                "test": TargetConfig(url="ws://localhost:19002/ws"),
            }
        )

    @pytest.mark.asyncio
    async def test_stop_clears_clients(self, route_config: RouteConfig):
        """测试停止清除客户端"""
        router = Router(config=route_config)
        
        # 模拟已连接的客户端
        mock_client = AsyncMock()
        router.clients["test"] = mock_client
        router._running = True
        
        await router.stop()
        
        assert len(router.clients) == 0
        assert router._running is False

    @pytest.mark.asyncio
    async def test_remove_platform(self, route_config: RouteConfig):
        """测试移除平台"""
        router = Router(config=route_config)
        
        # 模拟已连接的客户端
        mock_client = AsyncMock()
        router.clients["test"] = mock_client
        
        await router.remove_platform("test")
        
        assert "test" not in router.clients
        mock_client.stop.assert_called_once()

    @pytest.mark.asyncio
    async def test_remove_platform_cancels_task(self, route_config: RouteConfig):
        """测试移除平台取消任务"""
        router = Router(config=route_config)
        
        # 创建一个真实的可被取消的任务
        async def dummy_task():
            try:
                await asyncio.sleep(100)
            except asyncio.CancelledError:
                pass
        
        real_task = asyncio.create_task(dummy_task())
        router._client_tasks["test"] = real_task
        
        mock_client = AsyncMock()
        router.clients["test"] = mock_client
        
        await router.remove_platform("test")
        
        assert real_task.cancelled() or real_task.done()


# ============================================================
# 测试 Router 优先度功能
# ============================================================

class TestRouterPriority:
    """测试路由器优先度功能"""

    @pytest.fixture
    def route_config(self) -> RouteConfig:
        return RouteConfig(
            route_config={
                "test_platform": TargetConfig(url="ws://localhost:19003/ws"),
            }
        )

    def test_register_handler_with_priority(self, route_config: RouteConfig):
        """测试注册带优先度的处理器"""
        router = Router(config=route_config)
        handler = MagicMock()
        
        router.register_class_handler(handler, priority=10)
        
        assert len(router.handlers) == 1
        assert router.handlers[0].handler is handler
        assert router.handlers[0].priority == 10

    def test_handlers_sorted_by_priority(self, route_config: RouteConfig):
        """测试处理器按优先度排序"""
        router = Router(config=route_config)
        
        low_handler = MagicMock(name="low")
        mid_handler = MagicMock(name="mid")
        high_handler = MagicMock(name="high")
        
        # 以乱序注册
        router.register_class_handler(mid_handler, priority=5)
        router.register_class_handler(low_handler, priority=1)
        router.register_class_handler(high_handler, priority=10)
        
        # 验证按优先度降序排列
        assert len(router.handlers) == 3
        assert router.handlers[0].priority == 10
        assert router.handlers[0].handler is high_handler
        assert router.handlers[1].priority == 5
        assert router.handlers[1].handler is mid_handler
        assert router.handlers[2].priority == 1
        assert router.handlers[2].handler is low_handler

    @pytest.mark.asyncio
    async def test_priority_dispatch_only_highest(self, route_config: RouteConfig):
        """测试只有最高优先度的处理器被调用"""
        router = Router(config=route_config)
        
        low_handler = AsyncMock(name="low")
        high_handler = AsyncMock(name="high")
        
        router.register_class_handler(low_handler, priority=1)
        router.register_class_handler(high_handler, priority=10)
        
        message = make_message()
        await router._priority_dispatch(message)
        
        # 只有高优先度处理器被调用
        high_handler.assert_called_once_with(message)
        low_handler.assert_not_called()

    @pytest.mark.asyncio
    async def test_priority_dispatch_same_priority_all_called(self, route_config: RouteConfig):
        """测试相同优先度的处理器都被调用"""
        router = Router(config=route_config)
        
        handler1 = AsyncMock(name="handler1")
        handler2 = AsyncMock(name="handler2")
        handler3 = AsyncMock(name="handler3")
        low_handler = AsyncMock(name="low")
        
        # 三个相同优先度的处理器
        router.register_class_handler(handler1, priority=10)
        router.register_class_handler(handler2, priority=10)
        router.register_class_handler(handler3, priority=10)
        # 一个低优先度处理器
        router.register_class_handler(low_handler, priority=1)
        
        message = make_message()
        await router._priority_dispatch(message)
        
        # 所有高优先度处理器都被调用
        handler1.assert_called_once_with(message)
        handler2.assert_called_once_with(message)
        handler3.assert_called_once_with(message)
        # 低优先度处理器不被调用
        low_handler.assert_not_called()

    @pytest.mark.asyncio
    async def test_priority_dispatch_empty_handlers(self, route_config: RouteConfig):
        """测试无处理器时的分发"""
        router = Router(config=route_config)
        
        message = make_message()
        # 不应抛出异常
        await router._priority_dispatch(message)

    @pytest.mark.asyncio
    async def test_priority_dispatch_sync_handler(self, route_config: RouteConfig):
        """测试同步处理器的优先度分发"""
        router = Router(config=route_config)
        
        results = []
        
        def sync_high_handler(msg):
            results.append("high")
        
        def sync_low_handler(msg):
            results.append("low")
        
        router.register_class_handler(sync_low_handler, priority=1)
        router.register_class_handler(sync_high_handler, priority=10)
        
        message = make_message()
        await router._priority_dispatch(message)
        
        # 只有高优先度处理器被调用
        assert results == ["high"]

    @pytest.mark.asyncio
    async def test_priority_dispatch_handler_exception(self, route_config: RouteConfig):
        """测试处理器异常不影响其他处理器"""
        router = Router(config=route_config)
        
        results = []
        
        async def failing_handler(msg):
            raise ValueError("Test error")
        
        async def working_handler(msg):
            results.append("worked")
        
        # 两个相同优先度的处理器，一个会抛出异常
        router.register_class_handler(failing_handler, priority=10)
        router.register_class_handler(working_handler, priority=10)
        
        message = make_message()
        # 不应抛出异常
        await router._priority_dispatch(message)
        
        # 正常的处理器仍然被调用
        assert results == ["worked"]

    def test_negative_priority(self, route_config: RouteConfig):
        """测试负优先度"""
        router = Router(config=route_config)
        
        negative_handler = MagicMock(name="negative")
        zero_handler = MagicMock(name="zero")
        positive_handler = MagicMock(name="positive")
        
        router.register_class_handler(negative_handler, priority=-5)
        router.register_class_handler(zero_handler, priority=0)
        router.register_class_handler(positive_handler, priority=5)
        
        # 验证按优先度降序排列
        assert router.handlers[0].priority == 5
        assert router.handlers[1].priority == 0
        assert router.handlers[2].priority == -5

    @pytest.mark.asyncio
    async def test_priority_dispatch_with_negative_priority(self, route_config: RouteConfig):
        """测试负优先度时的分发"""
        router = Router(config=route_config)
        
        negative_handler = AsyncMock(name="negative")
        more_negative_handler = AsyncMock(name="more_negative")
        
        router.register_class_handler(negative_handler, priority=-1)
        router.register_class_handler(more_negative_handler, priority=-10)
        
        message = make_message()
        await router._priority_dispatch(message)
        
        # -1 优先度更高
        negative_handler.assert_called_once_with(message)
        more_negative_handler.assert_not_called()
