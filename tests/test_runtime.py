"""
测试 runtime 模块：消息运行时路由和处理
"""
from __future__ import annotations

import asyncio
from typing import List
from unittest.mock import AsyncMock, MagicMock

import pytest

from mofox_wire import MessageBuilder, MessageEnvelope, MessageRuntime
from mofox_wire.runtime import (
    MessageProcessingError,
    MessageRoute,
    Middleware,
    _extract_segment_type,
    _looks_like_method,
)


# ============================================================
# 辅助函数
# ============================================================

def make_message(msg_type: str = "text", platform: str = "test") -> MessageEnvelope:
    """创建测试消息"""
    return (
        MessageBuilder()
        .platform(platform)
        .from_user("user_1")
        .seg(msg_type, "test data")
        .build()
    )


# ============================================================
# 测试 MessageRoute
# ============================================================

class TestMessageRoute:
    """测试消息路由配置"""

    def test_create_route(self):
        """测试创建路由"""
        async def predicate(msg):
            return True
        async def handler(msg):
            return msg
        
        route = MessageRoute(
            predicate=predicate,
            handler=handler,
            name="test_route",
            message_type="text",
        )

        # 严格验证路由的所有属性
        assert route.name == "test_route"
        assert route.message_type == "text"
        assert route.predicate is predicate
        assert route.handler is handler

    def test_route_with_multiple_types(self):
        """测试多类型路由"""
        async def predicate(msg):
            return True
        async def handler(msg):
            return msg
        
        route = MessageRoute(
            predicate=predicate,
            handler=handler,
            message_types={"text", "image"},
        )

        # 严格验证多类型路由的属性
        assert route.message_types == {"text", "image"}
        assert route.predicate is predicate
        assert route.handler is handler
        assert route.name is None

    def test_route_with_event_types(self):
        """测试事件类型路由"""
        async def predicate(msg):
            return True
        async def handler(msg):
            return msg
        
        route = MessageRoute(
            predicate=predicate,
            handler=handler,
            event_types={"message.receive", "message.send"},
        )

        # 严格验证事件类型包含所有预期事件且无多余事件
        expected_event_types = {"message.receive", "message.send"}
        assert route.event_types == expected_event_types
        assert route.predicate is predicate
        assert route.handler is handler


# ============================================================
# 测试 MessageRuntime 基本功能
# ============================================================

class TestMessageRuntimeBasic:
    """测试消息运行时基本功能"""

    @pytest.fixture
    def runtime(self) -> MessageRuntime:
        return MessageRuntime()

    @pytest.mark.asyncio
    async def test_add_route(self, runtime: MessageRuntime):
        """测试添加路由"""
        handler = AsyncMock(return_value=None)
        
        runtime.add_route(
            predicate=lambda msg: True,
            handler=handler,
            name="test_route",
        )

        # 严格验证路由数量和路由属性
        assert len(runtime._routes) == 1
        added_route = runtime._routes[0]
        assert added_route.name == "test_route"
        assert added_route.handler is handler

    @pytest.mark.asyncio
    async def test_handle_message_matches_route(self, runtime: MessageRuntime):
        """测试消息匹配路由并处理"""
        handler = AsyncMock(return_value=None)
        runtime.add_route(
            predicate=lambda msg: True,
            handler=handler,
        )
        
        msg = make_message()
        result = await runtime.handle_message(msg)

        # 严格验证处理器被调用且参数完全匹配
        handler.assert_called_once_with(msg)
        assert handler.call_count == 1
        assert result is None  # 处理器返回 None

    @pytest.mark.asyncio
    async def test_handle_message_no_match(self, runtime: MessageRuntime):
        """测试消息不匹配任何路由"""
        handler = AsyncMock(return_value=None)
        runtime.add_route(
            predicate=lambda msg: False,
            handler=handler,
        )
        
        msg = make_message()
        result = await runtime.handle_message(msg)

        # 严格验证处理器未被调用且返回结果为 None
        handler.assert_not_called()
        assert handler.call_count == 0
        assert result is None

    @pytest.mark.asyncio
    async def test_handle_message_returns_response(self, runtime: MessageRuntime):
        """测试处理器返回响应"""
        response_msg = make_message("text", "test")
        handler = AsyncMock(return_value=response_msg)
        runtime.add_route(
            predicate=lambda msg: True,
            handler=handler,
        )
        
        msg = make_message()
        result = await runtime.handle_message(msg)

        # 严格验证返回结果与预期响应完全一致
        assert result is response_msg
        assert result == response_msg
        handler.assert_called_once_with(msg)


# ============================================================
# 测试消息类型路由
# ============================================================

class TestMessageTypeRouting:
    """测试消息类型路由"""

    @pytest.fixture
    def runtime(self) -> MessageRuntime:
        return MessageRuntime()

    @pytest.mark.asyncio
    async def test_route_by_message_type(self, runtime: MessageRuntime):
        """测试按消息类型路由"""
        text_handler = AsyncMock(return_value=None)
        image_handler = AsyncMock(return_value=None)
        
        runtime.add_route(
            predicate=lambda msg: True,
            handler=text_handler,
            message_type="text",
        )
        runtime.add_route(
            predicate=lambda msg: True,
            handler=image_handler,
            message_type="image",
        )
        
        text_msg = make_message("text")
        await runtime.handle_message(text_msg)
        text_handler.assert_called_once()
        image_handler.assert_not_called()
        
        text_handler.reset_mock()
        image_msg = make_message("image")
        await runtime.handle_message(image_msg)
        image_handler.assert_called_once()

    @pytest.mark.asyncio
    async def test_route_by_multiple_types(self, runtime: MessageRuntime):
        """测试多类型路由"""
        handler = AsyncMock(return_value=None)
        
        runtime.add_route(
            predicate=lambda msg: True,
            handler=handler,
            message_type=["text", "image"],
        )
        
        text_msg = make_message("text")
        await runtime.handle_message(text_msg)
        handler.assert_called_once()
        
        handler.reset_mock()
        image_msg = make_message("image")
        await runtime.handle_message(image_msg)
        handler.assert_called_once()

    @pytest.mark.asyncio
    async def test_duplicate_type_registration_raises(self, runtime: MessageRuntime):
        """测试重复注册同一类型抛出异常"""
        runtime.add_route(
            predicate=lambda msg: True,
            handler=AsyncMock(),
            name="handler1",
            message_type="text",
        )
        
        with pytest.raises(ValueError, match="消息类型 'text' 已被处理器"):
            runtime.add_route(
                predicate=lambda msg: True,
                handler=AsyncMock(),
                name="handler2",
                message_type="text",
            )


# ============================================================
# 测试装饰器
# ============================================================

class TestDecorators:
    """测试装饰器"""

    @pytest.fixture
    def runtime(self) -> MessageRuntime:
        return MessageRuntime()

    @pytest.mark.asyncio
    async def test_route_decorator(self, runtime: MessageRuntime):
        """测试 @route 装饰器"""
        @runtime.route(lambda msg: True, name="test_route")
        async def handler(msg):
            return msg
        
        assert len(runtime._routes) == 1
        assert runtime._routes[0].name == "test_route"

    @pytest.mark.asyncio
    async def test_on_message_decorator(self, runtime: MessageRuntime):
        """测试 @on_message 装饰器"""
        @runtime.on_message(message_type="text")
        async def text_handler(msg):
            return msg
        
        assert len(runtime._routes) == 1

    @pytest.mark.asyncio
    async def test_on_message_with_platform(self, runtime: MessageRuntime):
        """测试带平台过滤的 @on_message"""
        handler = AsyncMock(return_value=None)
        
        @runtime.on_message(message_type="text", platform="qq")
        async def qq_handler(msg):
            await handler(msg)
        
        qq_msg = make_message("text", "qq")
        await runtime.handle_message(qq_msg)
        handler.assert_called_once()
        
        handler.reset_mock()
        discord_msg = make_message("text", "discord")
        await runtime.handle_message(discord_msg)
        handler.assert_not_called()

    @pytest.mark.asyncio
    async def test_on_message_without_args(self, runtime: MessageRuntime):
        """测试不带参数的 @on_message"""
        @runtime.on_message
        async def handler(msg):
            return msg
        
        assert len(runtime._routes) == 1


# ============================================================
# 测试钩子
# ============================================================

class TestHooks:
    """测试钩子函数"""

    @pytest.fixture
    def runtime(self) -> MessageRuntime:
        return MessageRuntime()

    @pytest.mark.asyncio
    async def test_before_hook(self, runtime: MessageRuntime):
        """测试前置钩子"""
        before_hook = AsyncMock()
        runtime.register_before_hook(before_hook)
        runtime.add_route(lambda msg: True, AsyncMock())
        
        msg = make_message()
        await runtime.handle_message(msg)
        
        before_hook.assert_called_once_with(msg)

    @pytest.mark.asyncio
    async def test_after_hook(self, runtime: MessageRuntime):
        """测试后置钩子"""
        after_hook = AsyncMock()
        runtime.register_after_hook(after_hook)
        runtime.add_route(lambda msg: True, AsyncMock())
        
        msg = make_message()
        await runtime.handle_message(msg)
        
        after_hook.assert_called_once_with(msg)

    @pytest.mark.asyncio
    async def test_error_hook(self, runtime: MessageRuntime):
        """测试错误钩子"""
        error_hook = AsyncMock()
        runtime.register_error_hook(error_hook)
        
        error = ValueError("test error")
        handler = AsyncMock(side_effect=error)
        runtime.add_route(lambda msg: True, handler)
        
        msg = make_message()
        with pytest.raises(MessageProcessingError):
            await runtime.handle_message(msg)
        
        error_hook.assert_called_once()
        call_args = error_hook.call_args[0]
        assert call_args[0] == msg
        assert call_args[1] == error

    @pytest.mark.asyncio
    async def test_multiple_hooks(self, runtime: MessageRuntime):
        """测试多个钩子"""
        hook1 = AsyncMock()
        hook2 = AsyncMock()
        runtime.register_before_hook(hook1)
        runtime.register_before_hook(hook2)
        runtime.add_route(lambda msg: True, AsyncMock())
        
        msg = make_message()
        await runtime.handle_message(msg)
        
        hook1.assert_called_once()
        hook2.assert_called_once()


# ============================================================
# 测试中间件
# ============================================================

class TestMiddleware:
    """测试中间件"""

    @pytest.fixture
    def runtime(self) -> MessageRuntime:
        return MessageRuntime()

    @pytest.mark.asyncio
    async def test_middleware_wraps_handler(self, runtime: MessageRuntime):
        """测试中间件包裹处理器"""
        call_order = []
        
        async def middleware(msg, handler):
            call_order.append("before_middleware")
            result = await handler(msg)
            call_order.append("after_middleware")
            return result
        
        async def handler(msg):
            call_order.append("handler")
            return msg
        
        runtime.register_middleware(middleware)
        runtime.add_route(lambda msg: True, handler)
        
        msg = make_message()
        await runtime.handle_message(msg)
        
        assert call_order == ["before_middleware", "handler", "after_middleware"]

    @pytest.mark.asyncio
    async def test_multiple_middlewares(self, runtime: MessageRuntime):
        """测试多个中间件（洋葱模型）"""
        call_order = []
        
        async def middleware1(msg, handler):
            call_order.append("m1_before")
            result = await handler(msg)
            call_order.append("m1_after")
            return result
        
        async def middleware2(msg, handler):
            call_order.append("m2_before")
            result = await handler(msg)
            call_order.append("m2_after")
            return result
        
        async def handler(msg):
            call_order.append("handler")
            return msg
        
        runtime.register_middleware(middleware1)
        runtime.register_middleware(middleware2)
        runtime.add_route(lambda msg: True, handler)
        
        msg = make_message()
        await runtime.handle_message(msg)
        
        # 洋葱模型：m1 -> m2 -> handler -> m2 -> m1
        assert call_order == ["m1_before", "m2_before", "handler", "m2_after", "m1_after"]

    @pytest.mark.asyncio
    async def test_middleware_can_modify_message(self, runtime: MessageRuntime):
        """测试中间件可以修改消息"""
        async def middleware(msg, handler):
            # 修改消息
            modified = dict(msg)
            modified["metadata"] = {"modified": True}
            return await handler(modified)
        
        received_msg = None
        async def handler(msg):
            nonlocal received_msg
            received_msg = msg
            return msg
        
        runtime.register_middleware(middleware)
        runtime.add_route(lambda msg: True, handler)
        
        msg = make_message()
        await runtime.handle_message(msg)
        
        assert received_msg["metadata"]["modified"] is True


# ============================================================
# 测试批量处理
# ============================================================

class TestBatchProcessing:
    """测试批量消息处理"""

    @pytest.fixture
    def runtime(self) -> MessageRuntime:
        return MessageRuntime()

    @pytest.mark.asyncio
    async def test_handle_batch_default(self, runtime: MessageRuntime):
        """测试默认批量处理（逐条处理）"""
        processed = []
        
        async def handler(msg):
            processed.append(msg)
            return msg
        
        runtime.add_route(lambda msg: True, handler)
        
        messages = [make_message() for _ in range(3)]
        responses = await runtime.handle_batch(messages)
        
        assert len(processed) == 3
        assert len(responses) == 3

    @pytest.mark.asyncio
    async def test_handle_batch_custom_handler(self, runtime: MessageRuntime):
        """测试自定义批量处理器"""
        async def batch_handler(messages: List[MessageEnvelope]):
            return [msg for msg in messages]
        
        runtime.set_batch_handler(batch_handler)
        
        messages = [make_message() for _ in range(3)]
        responses = await runtime.handle_batch(messages)
        
        assert len(responses) == 3

    @pytest.mark.asyncio
    async def test_handle_batch_empty(self, runtime: MessageRuntime):
        """测试处理空批次"""
        responses = await runtime.handle_batch([])
        assert responses == []


# ============================================================
# 测试错误处理
# ============================================================

class TestErrorHandling:
    """测试错误处理"""

    @pytest.fixture
    def runtime(self) -> MessageRuntime:
        return MessageRuntime()

    @pytest.mark.asyncio
    async def test_handler_exception_wrapped(self, runtime: MessageRuntime):
        """测试处理器异常被包装"""
        error = ValueError("test error")
        handler = AsyncMock(side_effect=error)
        runtime.add_route(lambda msg: True, handler)
        
        msg = make_message()
        with pytest.raises(MessageProcessingError) as exc_info:
            await runtime.handle_message(msg)
        
        assert exc_info.value.original == error
        assert exc_info.value.message_envelope == msg

    @pytest.mark.asyncio
    async def test_error_message_contains_id(self, runtime: MessageRuntime):
        """测试错误消息包含消息 ID"""
        handler = AsyncMock(side_effect=ValueError("test"))
        runtime.add_route(lambda msg: True, handler)
        
        msg = make_message()
        msg["id"] = "test_id_123"
        
        with pytest.raises(MessageProcessingError) as exc_info:
            await runtime.handle_message(msg)
        
        assert "test_id_123" in str(exc_info.value)


# ============================================================
# 测试辅助函数
# ============================================================

class TestHelperFunctions:
    """测试辅助函数"""

    def test_extract_segment_type_from_dict(self):
        """测试从字典提取段类型"""
        msg = make_message("text")
        assert _extract_segment_type(msg) == "text"

    def test_extract_segment_type_from_list(self):
        """测试从列表提取段类型"""
        msg = (
            MessageBuilder()
            .platform("test")
            .from_user("user_1")
            .text("hello")
            .image("url")
            .build()
        )
        # 第一个段的类型
        assert _extract_segment_type(msg) == "text"

    def test_extract_segment_type_from_message_chain(self):
        """测试从 message_chain 提取段类型"""
        msg: MessageEnvelope = {
            "message_info": {"platform": "test", "message_id": "1"},
            "message_segment": {"type": "text", "data": "hello"},
            "message_chain": [{"type": "image", "data": "url"}],
        }
        # 优先使用 message_segment
        assert _extract_segment_type(msg) == "text"

    def test_extract_segment_type_none(self):
        """测试无法提取段类型返回 None"""
        msg: MessageEnvelope = {
            "message_info": {"platform": "test", "message_id": "1"},
            "message_segment": {},  # type: ignore
        }
        assert _extract_segment_type(msg) is None

    def test_looks_like_method_function(self):
        """测试普通函数不是方法"""
        def func(msg):
            pass
        assert _looks_like_method(func) is False

    def test_looks_like_method_with_self(self):
        """测试带 self 参数的函数被识别为方法"""
        def method(self, msg):
            pass
        assert _looks_like_method(method) is True

    def test_looks_like_method_lambda(self):
        """测试 lambda 不是方法"""
        assert _looks_like_method(lambda msg: msg) is False


# ============================================================
# 测试实例方法路由
# ============================================================

class TestInstanceMethodRouting:
    """测试实例方法路由"""

    @pytest.mark.asyncio
    async def test_instance_method_route(self):
        """测试实例方法作为路由处理器"""
        runtime = MessageRuntime()
        received = []
        
        class Handler:
            @runtime.on_message(message_type="text")
            async def handle_text(self, msg):
                received.append(msg)
                return msg
        
        handler = Handler()
        
        msg = make_message("text")
        await runtime.handle_message(msg)
        
        assert len(received) == 1
        assert received[0] == msg

    @pytest.mark.asyncio
    async def test_multiple_instances(self):
        """测试多个实例"""
        runtime = MessageRuntime()
        received1 = []
        received2 = []
        
        class Handler:
            def __init__(self, store):
                self.store = store
            
            @runtime.route(lambda msg: True)
            async def handle(self, msg):
                self.store.append(msg)
                return msg
        
        # 由于路由冲突，这里每个实例会分别注册
        # 但由于 predicate 相同，只有第一个会匹配
        handler1 = Handler(received1)
        handler2 = Handler(received2)
        
        msg = make_message()
        await runtime.handle_message(msg)
        
        # 至少有一个处理器收到消息
        assert len(received1) + len(received2) >= 1
