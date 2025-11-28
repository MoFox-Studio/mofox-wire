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
    async def test_same_type_multiple_handlers_with_priority(self, runtime: MessageRuntime):
        """测试同一类型可以有多个处理器（通过优先度区分）"""
        handler1 = AsyncMock(return_value=None)
        handler2 = AsyncMock(return_value=None)
        
        runtime.add_route(
            predicate=lambda msg: True,
            handler=handler1,
            name="handler1",
            message_type="text",
            priority=10,
        )
        
        # 不再抛出异常，可以注册多个同类型处理器
        runtime.add_route(
            predicate=lambda msg: True,
            handler=handler2,
            name="handler2",
            message_type="text",
            priority=1,
        )
        
        msg = make_message(msg_type="text")
        await runtime.handle_message(msg)
        
        # 只有高优先度处理器被调用
        handler1.assert_called_once()
        handler2.assert_not_called()


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


# ============================================================
# 测试优先度功能
# ============================================================

class TestRoutePriority:
    """测试路由优先度功能"""

    @pytest.mark.asyncio
    async def test_add_route_with_priority(self):
        """测试添加带优先度的路由"""
        runtime = MessageRuntime()
        
        async def handler(msg):
            return msg
        
        runtime.add_route(lambda msg: True, handler, priority=10)
        
        assert len(runtime._routes) == 1
        assert runtime._routes[0].priority == 10

    @pytest.mark.asyncio
    async def test_routes_sorted_by_priority(self):
        """测试路由按优先度排序"""
        runtime = MessageRuntime()
        
        async def handler_low(msg):
            return msg
        async def handler_mid(msg):
            return msg
        async def handler_high(msg):
            return msg
        
        # 以乱序添加
        runtime.add_route(lambda msg: True, handler_mid, name="mid", priority=5)
        runtime.add_route(lambda msg: True, handler_low, name="low", priority=1)
        runtime.add_route(lambda msg: True, handler_high, name="high", priority=10)
        
        # 验证按优先度降序排列
        assert len(runtime._routes) == 3
        assert runtime._routes[0].priority == 10
        assert runtime._routes[0].name == "high"
        assert runtime._routes[1].priority == 5
        assert runtime._routes[1].name == "mid"
        assert runtime._routes[2].priority == 1
        assert runtime._routes[2].name == "low"

    @pytest.mark.asyncio
    async def test_only_highest_priority_handler_called(self):
        """测试只有最高优先度的处理器被调用"""
        runtime = MessageRuntime()
        
        results = []
        
        async def handler_low(msg):
            results.append("low")
            return msg
        
        async def handler_high(msg):
            results.append("high")
            return msg
        
        runtime.add_route(lambda msg: True, handler_low, priority=1)
        runtime.add_route(lambda msg: True, handler_high, priority=10)
        
        msg = make_message()
        await runtime.handle_message(msg)
        
        # 只有高优先度处理器被调用
        assert results == ["high"]

    @pytest.mark.asyncio
    async def test_same_priority_handlers_all_called(self):
        """测试相同优先度的处理器都被调用"""
        runtime = MessageRuntime()
        
        results = []
        
        async def handler1(msg):
            results.append("handler1")
            return msg
        
        async def handler2(msg):
            results.append("handler2")
            return None
        
        async def handler3(msg):
            results.append("handler3")
            return None
        
        async def handler_low(msg):
            results.append("low")
            return msg
        
        # 三个相同优先度的处理器
        runtime.add_route(lambda msg: True, handler1, priority=10)
        runtime.add_route(lambda msg: True, handler2, priority=10)
        runtime.add_route(lambda msg: True, handler3, priority=10)
        # 一个低优先度处理器
        runtime.add_route(lambda msg: True, handler_low, priority=1)
        
        msg = make_message()
        await runtime.handle_message(msg)
        
        # 所有高优先度处理器都被调用（顺序可能不确定）
        assert "handler1" in results
        assert "handler2" in results
        assert "handler3" in results
        # 低优先度处理器不被调用
        assert "low" not in results

    @pytest.mark.asyncio
    async def test_on_message_decorator_with_priority(self):
        """测试 on_message 装饰器支持优先度"""
        runtime = MessageRuntime()
        
        results = []
        
        @runtime.on_message(message_type="text", priority=10)
        async def high_handler(msg):
            results.append("high")
            return msg
        
        @runtime.on_message(message_type="text", priority=1)
        async def low_handler(msg):
            results.append("low")
            return msg
        
        msg = make_message(msg_type="text")
        await runtime.handle_message(msg)
        
        assert results == ["high"]

    @pytest.mark.asyncio
    async def test_route_decorator_with_priority(self):
        """测试 route 装饰器支持优先度"""
        runtime = MessageRuntime()
        
        results = []
        
        @runtime.route(lambda msg: True, priority=10)
        async def high_handler(msg):
            results.append("high")
            return msg
        
        @runtime.route(lambda msg: True, priority=1)
        async def low_handler(msg):
            results.append("low")
            return msg
        
        msg = make_message()
        await runtime.handle_message(msg)
        
        assert results == ["high"]

    @pytest.mark.asyncio
    async def test_negative_priority(self):
        """测试负优先度"""
        runtime = MessageRuntime()
        
        results = []
        
        async def handler_negative(msg):
            results.append("negative")
            return msg
        
        async def handler_zero(msg):
            results.append("zero")
            return msg
        
        runtime.add_route(lambda msg: True, handler_negative, priority=-5)
        runtime.add_route(lambda msg: True, handler_zero, priority=0)
        
        msg = make_message()
        await runtime.handle_message(msg)
        
        # 0 优先度更高
        assert results == ["zero"]

    @pytest.mark.asyncio
    async def test_priority_with_message_type_filter(self):
        """测试优先度与消息类型过滤器结合"""
        runtime = MessageRuntime()
        
        results = []
        
        @runtime.on_message(message_type="text", priority=10)
        async def high_text_handler(msg):
            results.append("high_text")
            return msg
        
        @runtime.on_message(message_type="text", priority=1)
        async def low_text_handler(msg):
            results.append("low_text")
            return msg
        
        @runtime.on_message(message_type="image", priority=10)
        async def high_image_handler(msg):
            results.append("high_image")
            return msg
        
        # 发送 text 消息
        text_msg = make_message(msg_type="text")
        await runtime.handle_message(text_msg)
        
        # 只有高优先度的 text 处理器被调用
        assert results == ["high_text"]

    @pytest.mark.asyncio
    async def test_same_priority_returns_first_non_none_result(self):
        """测试相同优先度时返回第一个非 None 结果"""
        runtime = MessageRuntime()
        
        async def handler1(msg):
            return None
        
        async def handler2(msg):
            return {"response": "from handler2"}
        
        async def handler3(msg):
            return {"response": "from handler3"}
        
        runtime.add_route(lambda msg: True, handler1, priority=10)
        runtime.add_route(lambda msg: True, handler2, priority=10)
        runtime.add_route(lambda msg: True, handler3, priority=10)
        
        msg = make_message()
        result = await runtime.handle_message(msg)
        
        # 返回第一个非 None 结果
        assert result is not None
        assert "response" in result

    @pytest.mark.asyncio
    async def test_no_matching_high_priority_falls_to_lower(self):
        """测试当高优先度不匹配时，低优先度被调用"""
        runtime = MessageRuntime()
        
        results = []
        
        # 高优先度但不匹配 text 类型
        @runtime.on_message(message_type="image", priority=10)
        async def high_image_handler(msg):
            results.append("high_image")
            return msg
        
        # 低优先度但匹配 text 类型
        @runtime.on_message(message_type="text", priority=1)
        async def low_text_handler(msg):
            results.append("low_text")
            return msg
        
        msg = make_message(msg_type="text")
        await runtime.handle_message(msg)
        
        # 高优先度不匹配，低优先度被调用
        assert results == ["low_text"]

    @pytest.mark.asyncio
    async def test_default_priority_is_zero(self):
        """测试默认优先度为 0"""
        runtime = MessageRuntime()
        
        async def handler(msg):
            return msg
        
        runtime.add_route(lambda msg: True, handler)
        
        assert runtime._routes[0].priority == 0
