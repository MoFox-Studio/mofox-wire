"""
MoFox 内部通用消息线路实现。

该模块导出 TypedDict 消息模型、序列化工具、传输层封装以及适配器辅助工具，
供核心进程与各类平台适配器共享。
"""

__version__ = "0.1.3"

from . import codec, types
from .adapter_utils import (
    AdapterTransportOptions,
    AdapterBase,
    CoreSink,
    CoreMessageSink,
    HttpAdapterOptions,
    InProcessCoreSink,
    ProcessCoreSink,
    ProcessCoreSinkServer,
    WebSocketLike,
    WebSocketAdapterOptions,
)
from .api import MessageClient, MessageServer
from .codec import dumps_message, dumps_messages, loads_message, loads_messages
from .builder import MessageBuilder
from .router import RouteConfig, Router, TargetConfig, HandlerEntry
from .runtime import DEFAULT_PRIORITY, MessageProcessingError, MessageRoute, MessageRuntime, Middleware
from .types import (
    FormatInfoPayload,
    GroupInfoPayload,
    MessageDirection,
    MessageEnvelope,
    MessageInfoPayload,
    SegPayload,

    TemplateInfoPayload,
    UserInfoPayload,
)

__all__ = [
    # TypedDict model
    "MessageDirection",
    "MessageEnvelope",
    "SegPayload",
    "UserInfoPayload",
    "GroupInfoPayload",
    "FormatInfoPayload",
    "TemplateInfoPayload",
    "MessageInfoPayload",
    # Codec helpers
    "codec",
    "dumps_message",
    "dumps_messages",
    "loads_message",
    "loads_messages",
    "MessageBuilder",
    # Runtime / routing
    "MessageRoute",
    "MessageRuntime",
    "MessageProcessingError",
    "Middleware",
    # Server/client/router
    "MessageServer",
    "MessageClient",
    "Router",
    "RouteConfig",
    "TargetConfig",
    "HandlerEntry",
    "DEFAULT_PRIORITY",
    # Adapter helpers
    "AdapterTransportOptions",
    "AdapterBase",
    "CoreSink",
    "CoreMessageSink",
    "InProcessCoreSink",
    "ProcessCoreSink",
    "ProcessCoreSinkServer",
    "WebSocketLike",
    "WebSocketAdapterOptions",
    "HttpAdapterOptions",
]
