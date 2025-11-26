from __future__ import annotations

import asyncio
import functools
import inspect
import threading
import weakref
from dataclasses import dataclass
from typing import Awaitable, Callable, Dict, Iterable, List, Protocol

from .types import MessageEnvelope

Hook = Callable[[MessageEnvelope], Awaitable[None] | None]
ErrorHook = Callable[[MessageEnvelope, BaseException], Awaitable[None] | None]
Predicate = Callable[[MessageEnvelope], bool | Awaitable[bool]]
MessageHandler = Callable[[MessageEnvelope], Awaitable[MessageEnvelope | None] | MessageEnvelope | None]
BatchHandler = Callable[[List[MessageEnvelope]], Awaitable[List[MessageEnvelope] | None] | List[MessageEnvelope] | None]
MiddlewareCallable = Callable[[MessageEnvelope], Awaitable[MessageEnvelope | None]]


class Middleware(Protocol):
    async def __call__(self, message: MessageEnvelope, handler: MiddlewareCallable) -> MessageEnvelope | None: ...


class MessageProcessingError(RuntimeError):
    """封装处理链路中发生的异常。"""

    def __init__(self, message: MessageEnvelope, original: BaseException):
        detail = message.get("id", "<unknown>")
        super().__init__(f"处理消息 {detail} 时出错: {original}")
        self.message_envelope = message
        self.original = original


@dataclass
class MessageRoute:
    """消息路由配置，包含匹配条件和处理函数"""
    predicate: Predicate
    handler: MessageHandler
    name: str | None = None
    message_type: str | None = None
    message_types: set[str] | None = None  # 支持多个消息类型
    event_types: set[str] | None = None


class MessageRuntime:
    """
    消息运行时环境，负责调度消息路由、执行前后处理钩子以及批量处理消息
    """

    def __init__(self) -> None:
        self._routes: list[MessageRoute] = []
        self._before_hooks: list[Hook] = []
        self._after_hooks: list[Hook] = []
        self._error_hooks: list[ErrorHook] = []
        self._batch_handler: BatchHandler | None = None
        self._lock = threading.RLock()
        self._middlewares: list[Middleware] = []
        self._type_routes: Dict[str, list[MessageRoute]] = {}
        self._event_routes: Dict[str, list[MessageRoute]] = {}
        # 用于检测同一类型的重复注册
        self._explicit_type_handlers: Dict[str, str] = {}  # message_type -> handler_name

    def add_route(
        self,
        predicate: Predicate,
        handler: MessageHandler,
        name: str | None = None,
        *,
        message_type: str | list[str] | None = None,
        event_types: Iterable[str] | None = None,
    ) -> None:
        """
        添加消息路由

        Args:
            predicate: 路由匹配条件
            handler: 消息处理函数
            name: 路由名称（可选）
            message_type: 消息类型，可以是字符串或字符串列表（可选）
            event_types: 事件类型列表（可选）
        """
        with self._lock:
            # 处理 message_type 参数，支持字符串或列表
            message_types_set: set[str] | None = None
            single_message_type: str | None = None
            
            if message_type is not None:
                if isinstance(message_type, str):
                    message_types_set = {message_type}
                    single_message_type = message_type
                elif isinstance(message_type, list):
                    message_types_set = set(message_type)
                    if len(message_types_set) == 1:
                        single_message_type = next(iter(message_types_set))
                else:
                    raise TypeError(f"message_type must be str or list[str], got {type(message_type)}")
                
                # 检测重复注册：如果明确指定了某个类型，不允许重复
                handler_name = name or getattr(handler, "__name__", str(handler))
                for msg_type in message_types_set:
                    if msg_type in self._explicit_type_handlers:
                        existing_handler = self._explicit_type_handlers[msg_type]
                        raise ValueError(
                            f"消息类型 '{msg_type}' 已被处理器 '{existing_handler}' 明确注册，"
                            f"不能再由 '{handler_name}' 注册。同一消息类型只能有一个明确的处理器。"
                        )
                    self._explicit_type_handlers[msg_type] = handler_name
            
            route = MessageRoute(
                predicate=predicate,
                handler=handler,
                name=name,
                message_type=single_message_type,
                message_types=message_types_set,
                event_types=set(event_types) if event_types is not None else None,
            )
            self._routes.append(route)
            
            # 为每个消息类型建立索引
            if message_types_set:
                for msg_type in message_types_set:
                    self._type_routes.setdefault(msg_type, []).append(route)
            
            if route.event_types:
                for et in route.event_types:
                    self._event_routes.setdefault(et, []).append(route)

    def route(self, predicate: Predicate, name: str | None = None) -> Callable[[MessageHandler], MessageHandler]:
        """装饰器写法，便于在核心逻辑中声明式注册。
        
        支持普通函数和类方法。对于类方法，会在实例创建时自动绑定并注册路由。
        """

        def decorator(func: MessageHandler) -> MessageHandler:
            # Support decorating instance methods: defer binding until the object is created.
            if _looks_like_method(func):
                return _InstanceMethodRoute(
                    runtime=self,
                    func=func,
                    predicate=predicate,
                    name=name,
                    message_type=None,
                )
            
            self.add_route(predicate, func, name=name)
            return func

        return decorator

    def on_message(
        self,
        func: MessageHandler | None = None,
        *,
        message_type: str | list[str] | None = None,
        platform: str | None = None,
        predicate: Predicate | None = None,
        name: str | None = None,
    ) -> Callable[[MessageHandler], MessageHandler] | MessageHandler:
        """Sugar decorator with optional Seg.type/platform predicate matching.

        Args:
            func: 被装饰的函数
            message_type: 消息类型，可以是单个字符串或字符串列表
            platform: 平台名称
            predicate: 自定义匹配条件
            name: 路由名称

        Usages:
        - @runtime.on_message(...)
        - @runtime.on_message
        - @runtime.on_message(message_type="text")
        - @runtime.on_message(message_type=["text", "image"])

        If the target looks like an instance method (first arg is self), it will be
        auto-bound to the instance and registered when the object is constructed.
        """
        # 将 message_type 转换为集合以便统一处理
        message_types_set: set[str] | None = None
        if message_type is not None:
            if isinstance(message_type, str):
                message_types_set = {message_type}
            elif isinstance(message_type, list):
                message_types_set = set(message_type)
            else:
                raise TypeError(f"message_type must be str or list[str], got {type(message_type)}")

        async def combined_predicate(message: MessageEnvelope) -> bool:
            if message_types_set is not None:
                extracted_type = _extract_segment_type(message)
                if extracted_type not in message_types_set:
                    return False
            if platform is not None:
                info_platform = message.get("message_info", {}).get("platform")
                if message.get("platform") not in (None, platform) and info_platform is None:
                    return False
                if info_platform not in (None, platform):
                    return False
            if predicate is None:
                return True
            return await _invoke_callable(predicate, message, prefer_thread=False)

        def decorator(func: MessageHandler) -> MessageHandler:
            # Support decorating instance methods: defer binding until the object is created.
            if _looks_like_method(func):
                return _InstanceMethodRoute(
                    runtime=self,
                    func=func,
                    predicate=combined_predicate,
                    name=name,
                    message_type=message_type,
                )

            self.add_route(combined_predicate, func, name=name, message_type=message_type)
            return func

        if func is not None:
            return decorator(func)
        return decorator



    def set_batch_handler(self, handler: BatchHandler) -> None:
        self._batch_handler = handler

    def register_before_hook(self, hook: Hook) -> None:
        self._before_hooks.append(hook)

    def register_after_hook(self, hook: Hook) -> None:
        self._after_hooks.append(hook)

    def register_error_hook(self, hook: ErrorHook) -> None:
        self._error_hooks.append(hook)

    def register_middleware(self, middleware: Middleware) -> None:
        """注册洋葱模型中间件，围绕处理器执行。"""

        self._middlewares.append(middleware)

    async def handle_message(self, message: MessageEnvelope) -> MessageEnvelope | None:
        await self._run_hooks(self._before_hooks, message)
        try:
            route = await self._match_route(message)
            if route is None:
                return None
            handler = self._wrap_with_middlewares(route.handler)
            result = await handler(message)
        except Exception as exc:
            await self._run_error_hooks(message, exc)
            raise MessageProcessingError(message, exc) from exc
        await self._run_hooks(self._after_hooks, message)
        return result

    async def handle_batch(self, messages: Iterable[MessageEnvelope]) -> List[MessageEnvelope]:
        batch = list(messages)
        if not batch:
            return []
        if self._batch_handler is not None:
            result = await _invoke_callable(self._batch_handler, batch, prefer_thread=True)
            return result or []
        responses: list[MessageEnvelope] = []
        for message in batch:
            response = await self.handle_message(message)
            if response is not None:
                responses.append(response)
        return responses

    async def _match_route(self, message: MessageEnvelope) -> MessageRoute | None:
        """匹配消息路由，优先匹配明确指定了消息类型的处理器"""
        message_type = _extract_segment_type(message)
        event_type = (
            message.get("event_type")
            or message.get("message_info", {})
            .get("additional_config", {})
            .get("event_type")
        )
        
        # 分为两层候选：优先级和普通
        priority_candidates: list[MessageRoute] = []  # 明确指定了消息类型的
        normal_candidates: list[MessageRoute] = []    # 没有指定或通配的
        
        with self._lock:
            # 事件路由（优先级最高）
            if event_type and event_type in self._event_routes:
                priority_candidates.extend(self._event_routes[event_type])
            
            # 消息类型路由（明确指定的有优先级）
            if message_type and message_type in self._type_routes:
                priority_candidates.extend(self._type_routes[message_type])
            
            # 通用路由（没有明确指定类型的）
            for route in self._routes:
                # 如果路由没有指定 message_types，则是通用路由
                if route.message_types is None and route.event_types is None:
                    normal_candidates.append(route)

        # 先尝试优先级候选
        seen: set[int] = set()
        for route in priority_candidates:
            rid = id(route)
            if rid in seen:
                continue
            seen.add(rid)
            should_handle = await _invoke_callable(route.predicate, message, prefer_thread=False)
            if should_handle:
                return route
        
        # 如果没有匹配到优先级候选，再尝试普通候选
        for route in normal_candidates:
            rid = id(route)
            if rid in seen:
                continue
            seen.add(rid)
            should_handle = await _invoke_callable(route.predicate, message, prefer_thread=False)
            if should_handle:
                return route
        
        return None

    async def _run_hooks(self, hooks: Iterable[Hook], message: MessageEnvelope) -> None:
        coro_list = [self._call_hook(hook, message) for hook in hooks]
        if coro_list:
            await asyncio.gather(*coro_list)

    async def _call_hook(self, hook: Hook, message: MessageEnvelope) -> None:
        await _invoke_callable(hook, message, prefer_thread=True)

    async def _run_error_hooks(self, message: MessageEnvelope, exc: BaseException) -> None:
        coros = [self._call_error_hook(hook, message, exc) for hook in self._error_hooks]
        if coros:
            await asyncio.gather(*coros)

    async def _call_error_hook(self, hook: ErrorHook, message: MessageEnvelope, exc: BaseException) -> None:
        await _invoke_callable(hook, message, exc, prefer_thread=True)

    def _wrap_with_middlewares(self, handler: MessageHandler) -> MiddlewareCallable:
        async def base_handler(message: MessageEnvelope) -> MessageEnvelope | None:
            return await _invoke_callable(handler, message, prefer_thread=True)

        wrapped: MiddlewareCallable = base_handler
        for middleware in reversed(self._middlewares):
            current = wrapped

            async def wrapper(msg: MessageEnvelope, mw=middleware, nxt=current) -> MessageEnvelope | None:
                return await _invoke_callable(mw, msg, nxt, prefer_thread=False)

            wrapped = wrapper
        return wrapped


async def _invoke_callable(func: Callable[..., object], *args, prefer_thread: bool = False):
    """支持 sync/async 调用，并可选择在线程中执行。
    
    自动处理普通函数、类方法和绑定方法。
    """
    # 如果是绑定方法（bound method），直接使用，不需要额外处理
    # 因为绑定方法已经包含了 self 参数
    if inspect.ismethod(func):
        # 绑定方法可以直接调用，args 中不应包含 self
        if inspect.iscoroutinefunction(func):
            return await func(*args)
        if prefer_thread:
            result = await asyncio.to_thread(func, *args)
            if asyncio.iscoroutine(result) or isinstance(result, asyncio.Future):
                return await result
            return result
        result = func(*args)
        if asyncio.iscoroutine(result) or isinstance(result, asyncio.Future):
            return await result
        return result
    
    # 对于普通函数（未绑定的），按原有逻辑处理
    if inspect.iscoroutinefunction(func):
        return await func(*args)
    if prefer_thread:
        result = await asyncio.to_thread(func, *args)
        if asyncio.iscoroutine(result) or isinstance(result, asyncio.Future):
            return await result
        return result
    result = func(*args)
    if asyncio.iscoroutine(result) or isinstance(result, asyncio.Future):
        return await result
    return result


def _extract_segment_type(message: MessageEnvelope) -> str | None:
    seg = message.get("message_segment") or message.get("message_chain")
    if isinstance(seg, dict):
        return seg.get("type")
    if isinstance(seg, list) and seg:
        first = seg[0]
        if isinstance(first, dict):
            return first.get("type")
    return None


def _looks_like_method(func: Callable[..., object]) -> bool:
    """Return True if callable signature suggests an instance method (first arg named self)."""
    if inspect.ismethod(func):
        return True
    if not inspect.isfunction(func):
        return False
    params = inspect.signature(func).parameters
    if not params:
        return False
    first = next(iter(params.values()))
    return first.name == "self"


class _InstanceMethodRoute:
    """Descriptor that binds decorated instance methods and registers routes per-instance."""

    def __init__(
        self,
        runtime: MessageRuntime,
        func: MessageHandler,
        predicate: Predicate,
        name: str | None,
        message_type: str | None,
    ) -> None:
        self._runtime = runtime
        self._func = func
        self._predicate = predicate
        self._name = name
        self._message_type = message_type
        self._owner: type | None = None
        self._registered_instances: weakref.WeakSet[object] = weakref.WeakSet()

    def __set_name__(self, owner: type, name: str) -> None:
        self._owner = owner
        registry: list[_InstanceMethodRoute] | None = getattr(owner, "_mofox_instance_routes", None)
        if registry is None:
            registry = []
            setattr(owner, "_mofox_instance_routes", registry)
            original_init = owner.__init__

            @functools.wraps(original_init)
            def wrapped_init(inst, *args, **kwargs):
                original_init(inst, *args, **kwargs)
                for descriptor in getattr(inst.__class__, "_mofox_instance_routes", []):
                    descriptor._register_instance(inst)

            owner.__init__ = wrapped_init  # type: ignore[assignment]
        registry.append(self)

    def _register_instance(self, instance: object) -> None:
        if instance in self._registered_instances:
            return
        owner = self._owner or instance.__class__
        bound = self._func.__get__(instance, owner)  # type: ignore[arg-type]
        self._runtime.add_route(self._predicate, bound, name=self._name, message_type=self._message_type)
        self._registered_instances.add(instance)

    def __get__(self, instance: object | None, owner: type | None = None):
        if instance is None:
            return self._func
        self._register_instance(instance)
        return self._func.__get__(instance, owner)  # type: ignore[arg-type]


__all__ = [
    "BatchHandler",
    "Hook",
    "MessageHandler",
    "MessageProcessingError",
    "MessageRoute",
    "MessageRuntime",
    "Middleware",
    "Predicate",
]
