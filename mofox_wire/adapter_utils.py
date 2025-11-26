from __future__ import annotations

import asyncio
import contextlib
import logging
import multiprocessing as mp
from dataclasses import dataclass
from typing import Any, AsyncIterator, Awaitable, Callable, Protocol

import orjson
from aiohttp import web as aiohttp_web
import websockets

from .types import MessageEnvelope

logger = logging.getLogger("mofox_bus.adapter")


OutgoingHandler = Callable[[MessageEnvelope], Awaitable[None]]


class CoreMessageSink(Protocol):
    async def send(self, message: MessageEnvelope) -> None: ...

    async def send_many(self, messages: list[MessageEnvelope]) -> None: ...  # pragma: no cover - optional


class CoreSink(CoreMessageSink, Protocol):
    """
    双向 CoreSink 协议：
    - send/send_many: 适配器 → 核心（incoming）
    - push_outgoing: 核心 → 适配器（outgoing）
    """

    def set_outgoing_handler(self, handler: OutgoingHandler | None) -> None: ...

    def remove_outgoing_handler(self, handler: OutgoingHandler) -> None: ...

    async def push_outgoing(self, envelope: MessageEnvelope) -> None: ...

    async def close(self) -> None: ...  # pragma: no cover - lifecycle hook


class WebSocketLike(Protocol):
    def __aiter__(self) -> AsyncIterator[str | bytes]: ...

    @property
    def closed(self) -> bool: ...

    async def send(self, data: str | bytes) -> None: ...

    async def close(self) -> None: ...


@dataclass
class WebSocketAdapterOptions:
    url: str
    headers: dict[str, str] | None = None
    incoming_parser: Callable[[str | bytes], Any] | None = None
    outgoing_encoder: Callable[[MessageEnvelope], str | bytes] | None = None
    reconnect_interval: float = 5.0  # 重连间隔（秒）
    max_reconnect_attempts: int | None = None  # 最大重连次数，None 表示无限重连


@dataclass
class HttpAdapterOptions:
    host: str = "0.0.0.0"
    port: int = 8089
    path: str = "/adapter/messages"
    app: aiohttp_web.Application | None = None


AdapterTransportOptions = WebSocketAdapterOptions | HttpAdapterOptions | None


class AdapterBase:
    """
    适配器基类：负责平台原始消息与 MessageEnvelope 之间的互转。
    子类需要实现平台入站解析与出站发送逻辑。
    """

    platform: str = "unknown"

    def __init__(self, core_sink: CoreSink, transport: AdapterTransportOptions = None):
        """
        Args:
            core_sink: 核心消息入口，通常是 InProcessCoreSink 或自定义客户端。
            transport: 传入 WebSocketAdapterOptions / HttpAdapterOptions 即可自动管理监听逻辑。
        """
        self.core_sink = core_sink
        self._transport_config = transport
        self._ws: WebSocketLike | None = None
        self._ws_task: asyncio.Task | None = None
        self._http_runner: aiohttp_web.AppRunner | None = None
        self._http_site: aiohttp_web.BaseSite | None = None
        self._closed = False  # 标记适配器是否已关闭
        self._reconnect_attempts = 0  # 当前重连尝试次数

    async def start(self) -> None:
        """启动适配器的传输层监听（如果配置了传输选项）。"""
        self._closed = False
        self._reconnect_attempts = 0
        if hasattr(self.core_sink, "set_outgoing_handler"):
            try:
                self.core_sink.set_outgoing_handler(self._on_outgoing_from_core)
            except Exception:
                logger.exception("注册 outgoing 处理程序到核心接收器失败")
        if isinstance(self._transport_config, WebSocketAdapterOptions):
            await self._start_ws_transport(self._transport_config)
        elif isinstance(self._transport_config, HttpAdapterOptions):
            await self._start_http_transport(self._transport_config)


    async def stop(self) -> None:
        """停止适配器的传输层监听（如果配置了传输选项）。"""
        self._closed = True  # 标记为已关闭，阻止重连
        remove = getattr(self.core_sink, "remove_outgoing_handler", None)
        if callable(remove):
            try:
                remove(self._on_outgoing_from_core)
            except Exception:
                logger.exception("从核心接收器分离 outgoing 处理程序失败")
        elif hasattr(self.core_sink, "set_outgoing_handler"):
            try:
                self.core_sink.set_outgoing_handler(None)  # type: ignore[arg-type]
            except Exception:
                logger.exception("从核心接收器分离 outgoing 处理程序失败")
        if self._ws_task:
            self._ws_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._ws_task
            self._ws_task = None
        if self._ws:
            try:
                await self._ws.close()
            except Exception:
                pass  # 忽略关闭时的错误
            self._ws = None
        if self._http_site:
            await self._http_site.stop()
            self._http_site = None
        if self._http_runner:
            await self._http_runner.cleanup()
            self._http_runner = None

    def is_connected(self) -> bool:
        """检查 WebSocket 是否已连接。"""
        if isinstance(self._transport_config, WebSocketAdapterOptions):
            return self._ws is not None and not self._ws.closed
        elif isinstance(self._transport_config, HttpAdapterOptions):
            return self._http_site is not None
        return False

    async def wait_connected(self, timeout: float = 10.0) -> bool:
        """
        等待 WebSocket 连接建立。
        
        Args:
            timeout: 超时时间（秒）
            
        Returns:
            是否成功连接
        """
        if not isinstance(self._transport_config, WebSocketAdapterOptions):
            return True  # HTTP 模式不需要等待
        
        start = asyncio.get_event_loop().time()
        while not self._closed:
            if self._ws is not None and not self._ws.closed:
                return True
            if asyncio.get_event_loop().time() - start > timeout:
                return False
            await asyncio.sleep(0.1)
        return False

    async def on_platform_message(self, raw: Any) -> None:
        """处理平台下发的单条消息并交给核心。"""
        envelope = await self.from_platform_message(raw)
        await self.core_sink.send(envelope)

    async def on_platform_messages(self, raw_messages: list[Any]) -> None:
        """批量推送入口，内部自动批量或逐条送入核心。"""
        envelopes = [await self.from_platform_message(raw) for raw in raw_messages]
        await _send_many(self.core_sink, envelopes)

    async def send_to_platform(self, envelope: MessageEnvelope) -> None:
        """核心生成单条消息时调用，由子类或自动传输层发送。"""
        await self._send_platform_message(envelope)

    async def send_batch_to_platform(self, envelopes: list[MessageEnvelope]) -> None:
        """默认串行发送整批消息，子类可根据平台特性重写。"""
        for env in envelopes:
            await self._send_platform_message(env)

    async def _on_outgoing_from_core(self, envelope: MessageEnvelope) -> None:
        """核心生成 outgoing envelope 时的内部处理逻辑"""
        platform = envelope.get("platform") or envelope.get("message_info", {}).get("platform")
        if platform and platform != getattr(self, "platform", None):
            return
        await self._send_platform_message(envelope)

    async def from_platform_message(self, raw: Any) -> MessageEnvelope:
        """子类必须实现：将平台原始结构转换为统一 MessageEnvelope。"""
        raise NotImplementedError

    async def _send_platform_message(self, envelope: MessageEnvelope) -> None:
        """子类必须实现：把 MessageEnvelope 转为平台格式并发送出去。"""
        if isinstance(self._transport_config, WebSocketAdapterOptions):
            await self._send_via_ws(envelope)
            return
        raise NotImplementedError

    async def _start_ws_transport(self, options: WebSocketAdapterOptions) -> None:
        """启动 WebSocket 传输，包含自动重连逻辑。"""
        self._ws_task = asyncio.create_task(self._ws_connect_loop(options))

    async def _ws_connect_loop(self, options: WebSocketAdapterOptions) -> None:
        """WebSocket 连接循环，自动处理重连。"""
        while not self._closed:
            try:
                self._ws = await websockets.connect(options.url, extra_headers=options.headers)
                self._reconnect_attempts = 0  # 重置重连计数
                logger.info(f"WebSocket 已连接到 {options.url}")
                await self._ws_listen_loop(options)
            except asyncio.CancelledError:
                break
            except Exception as e:
                if self._closed:
                    break
                self._reconnect_attempts += 1
                max_attempts = options.max_reconnect_attempts
                if max_attempts is not None and self._reconnect_attempts > max_attempts:
                    logger.error(f"WebSocket 重连失败，已达最大尝试次数 {max_attempts}")
                    break
                logger.warning(
                    f"WebSocket 连接断开或失败: {e}，"
                    f"将在 {options.reconnect_interval:.1f} 秒后重连 "
                    f"(尝试 {self._reconnect_attempts}"
                    f"{f'/{max_attempts}' if max_attempts else ''})"
                )
                await asyncio.sleep(options.reconnect_interval)
            finally:
                if self._ws and not self._ws.closed:
                    try:
                        await self._ws.close()
                    except Exception:
                        pass
                self._ws = None

    async def _ws_listen_loop(self, options: WebSocketAdapterOptions) -> None:
        """WebSocket 消息监听循环。"""
        assert self._ws is not None
        parser = options.incoming_parser or self._default_ws_parser
        async for raw in self._ws:
            if self._closed:
                break
            try:
                payload = parser(raw)
                await self.on_platform_message(payload)
            except Exception:
                logger.exception("处理 WebSocket 消息失败")

    async def _send_via_ws(self, envelope: MessageEnvelope) -> None:
        """通过 WebSocket 发送消息。"""
        if self._ws is None or self._ws.closed:
            logger.warning("WebSocket 未连接，消息发送失败")
            raise RuntimeError("WebSocket transport is not active")
        encoder = None
        if isinstance(self._transport_config, WebSocketAdapterOptions):
            encoder = self._transport_config.outgoing_encoder
        data = encoder(envelope) if encoder else self._default_ws_encoder(envelope)
        try:
            await self._ws.send(data)
        except Exception as e:
            logger.warning(f"WebSocket 发送消息失败: {e}")
            raise

    async def _start_http_transport(self, options: HttpAdapterOptions) -> None:
        app = options.app or aiohttp_web.Application()
        app.add_routes([aiohttp_web.post(options.path, self._handle_http_request)])
        self._http_runner = aiohttp_web.AppRunner(app)
        await self._http_runner.setup()
        self._http_site = aiohttp_web.TCPSite(self._http_runner, options.host, options.port)
        await self._http_site.start()

    async def _handle_http_request(self, request: aiohttp_web.Request) -> aiohttp_web.Response:
        raw = await request.read()
        data = orjson.loads(raw) if raw else {}
        if isinstance(data, list):
            await self.on_platform_messages(data)
        else:
            await self.on_platform_message(data)
        return aiohttp_web.json_response({"status": "ok"})

    @staticmethod
    def _default_ws_parser(raw: str | bytes) -> Any:
        data = orjson.loads(raw)
        if isinstance(data, dict) and data.get("type") == "message" and "payload" in data:
            return data["payload"]
        return data

    @staticmethod
    def _default_ws_encoder(envelope: MessageEnvelope) -> bytes:
        return orjson.dumps({"type": "send", "payload": envelope})


class InProcessCoreSink(CoreSink):
    """
    进程内核心消息 sink，实现 CoreSink 协议。
    """

    def __init__(self, handler: Callable[[MessageEnvelope], Awaitable[None]]):
        self._handler = handler
        self._outgoing_handlers: set[OutgoingHandler] = set()

    def set_outgoing_handler(self, handler: OutgoingHandler | None) -> None:
        if handler is None:
            return
        self._outgoing_handlers.add(handler)

    def remove_outgoing_handler(self, handler: OutgoingHandler) -> None:
        self._outgoing_handlers.discard(handler)

    async def send(self, message: MessageEnvelope) -> None:
        await self._handler(message)

    async def send_many(self, messages: list[MessageEnvelope]) -> None:
        for message in messages:
            await self._handler(message)

    async def push_outgoing(self, envelope: MessageEnvelope) -> None:
        if not self._outgoing_handlers:
            logger.debug("Outgoing envelope dropped: no handler registered")
            return
        for callback in list(self._outgoing_handlers):
            await callback(envelope)

    async def close(self) -> None:  # pragma: no cover - symmetry
        self._outgoing_handlers.clear()


class ProcessCoreSink(CoreSink):
    """
    进程间核心消息 sink，实现 CoreSink 协议，使用 multiprocessing.Queue 初始化
    """

    _CONTROL_STOP = {"__core_sink_control__": "stop"}

    def __init__(self, *, to_core_queue: mp.Queue, from_core_queue: mp.Queue) -> None:
        self._to_core_queue = to_core_queue
        self._from_core_queue = from_core_queue
        self._outgoing_handler: OutgoingHandler | None = None
        self._closed = False
        self._listener_task: asyncio.Task | None = None
        self._loop = asyncio.get_event_loop()

    def set_outgoing_handler(self, handler: OutgoingHandler | None) -> None:
        self._outgoing_handler = handler
        if handler is not None and (self._listener_task is None or self._listener_task.done()):
            self._listener_task = self._loop.create_task(self._listen_from_core())

    def remove_outgoing_handler(self, handler: OutgoingHandler) -> None:
        if self._outgoing_handler is handler:
            self._outgoing_handler = None
            if self._listener_task and not self._listener_task.done():
                self._listener_task.cancel()

    async def send(self, message: MessageEnvelope) -> None:
        await asyncio.to_thread(self._to_core_queue.put, {"kind": "incoming", "payload": message})

    async def send_many(self, messages: list[MessageEnvelope]) -> None:
        for message in messages:
            await self.send(message)

    async def push_outgoing(self, envelope: MessageEnvelope) -> None:
        logger.debug("ProcessCoreSink.push_outgoing 在子进程中调用; 被忽略")

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        await asyncio.to_thread(self._from_core_queue.put, self._CONTROL_STOP)
        if self._listener_task:
            self._listener_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._listener_task
            self._listener_task = None

    async def _listen_from_core(self) -> None:
        while not self._closed:
            try:
                item = await asyncio.to_thread(self._from_core_queue.get)
            except asyncio.CancelledError:
                break
            if item == self._CONTROL_STOP:
                break
            if isinstance(item, dict) and item.get("kind") == "outgoing":
                envelope = item.get("payload")
                if self._outgoing_handler:
                    try:
                        await self._outgoing_handler(envelope)
                    except Exception:  # pragma: no cover
                        logger.exception("处理 ProcessCoreSink 中的 outgoing 信封失败")
            else:
                logger.debug(f"ProcessCoreSink 接受到未知负载: {item}")


class ProcessCoreSinkServer:
    """
    进程间核心消息 sink 服务器，实现 CoreSink 协议，使用 multiprocessing.Queue 初始化。
    - 将传入的 incoming 消息转发给指定的 handler
    - 将接收到的 outgoing 消息放入 outgoing 队列
    """

    def __init__(
        self,
        *,
        incoming_queue: mp.Queue,
        outgoing_queue: mp.Queue,
        core_handler: Callable[[MessageEnvelope], Awaitable[None]],
        name: str | None = None,
    ) -> None:
        self._incoming_queue = incoming_queue
        self._outgoing_queue = outgoing_queue
        self._core_handler = core_handler
        self._task: asyncio.Task | None = None
        self._closed = False
        self._name = name or "adapter"

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._consume_incoming())

    async def _consume_incoming(self) -> None:
        while not self._closed:
            try:
                item = await asyncio.to_thread(self._incoming_queue.get)
            except asyncio.CancelledError:
                break
            if isinstance(item, dict) and item.get("__core_sink_control__") == "stop":
                break
            if isinstance(item, dict) and item.get("kind") == "incoming":
                envelope = item.get("payload")
                try:
                    await self._core_handler(envelope)
                except Exception:  # pragma: no cover
                    logger.exception(f"处理来自 {self._name} 的 incoming 信封时失败")
            else:
                logger.debug(f"ProcessCoreSinkServer 忽略来自 {self._name} 的未知负载: {item}")

    async def push_outgoing(self, envelope: MessageEnvelope) -> None:
        await asyncio.to_thread(self._outgoing_queue.put, {"kind": "outgoing", "payload": envelope})

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        await asyncio.to_thread(self._incoming_queue.put, {"__core_sink_control__": "stop"})
        await asyncio.to_thread(self._outgoing_queue.put, ProcessCoreSink._CONTROL_STOP)
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None

async def _send_many(sink: CoreMessageSink, envelopes: list[MessageEnvelope]) -> None:
    send_many = getattr(sink, "send_many", None)
    if callable(send_many):
        await send_many(envelopes)
        return
    for env in envelopes:
        await sink.send(env)


__all__ = [
    "AdapterTransportOptions",
    "AdapterBase",
    "CoreSink",
    "CoreMessageSink",
    "HttpAdapterOptions",
    "InProcessCoreSink",
    "ProcessCoreSink",
    "ProcessCoreSinkServer",
    "WebSocketLike",
    "WebSocketAdapterOptions",
]
