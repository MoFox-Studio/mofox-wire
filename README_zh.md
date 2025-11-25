# MoFox Bus

[![PyPI version](https://badge.fury.io/py/mofox-bus.svg)](https://badge.fury.io/py/mofox-bus)
[![Python versions](https://img.shields.io/pypi/pyversions/mofox-bus.svg)](https://pypi.org/project/mofox-bus/)
[![License](https://img.shields.io/badge/License-GPL--3.0-blue.svg)](https://opensource.org/licenses/GPL-3.0)

MoFox Bus 是一个轻量级、高性能的消息总线，专为 MoFox Bot 及类似的聊天机器人应用而设计。它为构建消息驱动系统提供了坚实的基础，支持类型化消息信封、灵活的路由机制和多种传输协议。

## ✨ 特性

- **🏷️ 类型化消息**: 基于 TypedDict 的完整 TypeScript 风格类型安全
- **🚀 高性能**: 基于 async/await 构建，为高吞吐量场景优化
- **🌐 多种传输**: 开箱即用的 HTTP 和 WebSocket 协议支持
- **🔄 灵活路由**: 支持中间件的复杂消息路由
- **📦 JSON 序列化**: 基于 orjson 的高效 JSON 消息序列化
- **🛡️ 错误处理**: 全面的错误处理和处理保证
- **🎯 易于集成**: 简单的 API，便于与现有项目快速集成

## 🚀 安装

从 PyPI 安装（推荐）：

```bash
pip install mofox-bus
```

从源码安装：

```bash
git clone https://github.com/mofox-bot/mofox-bus.git
cd mofox-bus
pip install -e .
```

开发环境安装：

```bash
pip install -e ".[dev]"
```

## 📋 系统要求

- Python 3.11+
- aiohttp >= 3.12.0
- fastapi >= 0.116.0
- orjson >= 3.10.0
- uvicorn >= 0.35.0
- websockets >= 15.0.1

## 🏗️ 架构

MoFox Bus 采用分层架构：

```
┌─────────────────┐
│   应用程序      │
├─────────────────┤
│   运行时 API    │
├─────────────────┤
│     路由器      │
├─────────────────┤
│   编解码/类型   │
├─────────────────┤
│   传输层        │
└─────────────────┘
```

- **类型**: 消息和元数据的 TypedDict 模型
- **编解码**: JSON 序列化/反序列化工具
- **传输**: HTTP 和 WebSocket 客户端/服务器实现
- **路由器**: 消息路由和过滤功能
- **运行时**: 用于消息处理和中间件的高级 API

## 📖 快速开始

### 基础消息处理

```python
import asyncio
from mofox_bus import MessageRuntime, MessageBuilder, MessageEnvelope

async def handle_message(envelope: MessageEnvelope) -> MessageEnvelope | None:
    """处理传入消息的简单消息处理器"""
    print(f"处理消息: {envelope.get('content', '无内容')}")

    # 处理消息（修改、过滤等）
    if envelope.get('content') == 'hello':
        response = MessageBuilder.text_message('world')
        response['reply_to'] = envelope.get('id')
        return response

    return None

async def main():
    # 创建运行时
    runtime = MessageRuntime()

    # 注册处理器
    runtime.add_handler(handle_message)

    # 创建测试消息
    message = MessageBuilder.text_message('hello')
    message['id'] = 'msg-001'

    # 处理消息
    await runtime.process_message(message)

if __name__ == '__main__':
    asyncio.run(main())
```

### HTTP 服务器示例

```python
from mofox_bus import MessageServer
import uvicorn

async def main():
    # 创建 HTTP 服务器
    server = MessageServer()

    # 添加消息处理器
    server.add_handler(lambda env: print(f"收到: {env}"))

    # 启动服务器（将运行直到中断）
    config = uvicorn.Config(server.app, host="0.0.0.0", port=8000)
    server = uvicorn.Server(config)
    await server.serve()

if __name__ == '__main__':
    asyncio.run(main())
```

### WebSocket 客户端示例

```python
from mofox_bus.transport import WebSocketClient
from mofox_bus import MessageBuilder

async def main():
    # 创建 WebSocket 客户端
    client = WebSocketClient("ws://localhost:8000/ws")

    await client.connect()

    # 发送消息
    message = MessageBuilder.text_message("来自 WebSocket 客户端的问候！")
    await client.send_message(message)

    # 接收消息
    async for envelope in client.listen():
        print(f"收到: {envelope}")

if __name__ == '__main__':
    asyncio.run(main())
```

## 📚 API 参考

### 核心组件

#### MessageRuntime

处理消息的主要运行时，支持中间件。

```python
runtime = MessageRuntime()
runtime.add_handler(handler_func)
runtime.add_middleware(middleware_func)
await runtime.process_message(envelope)
```

#### MessageBuilder

用于创建类型化消息信封的工具。

```python
# 文本消息
msg = MessageBuilder.text_message("Hello world", user_id="user123")

# 图片消息
msg = MessageBuilder.image_message("https://example.com/image.jpg", user_id="user123")

# 自定义消息
msg = MessageBuilder.create_message(
    content="自定义内容",
    message_type="custom",
    user_id="user123",
    platform="discord"
)
```

#### Router

高级消息路由和过滤。

```python
router = Router()

# 添加带谓词的路由
router.add_route(
    predicate=lambda env: env.get('platform') == 'discord',
    handler=discord_handler
)

# 处理消息
await router.route(envelope)
```

### 消息类型

MoFox Bus 提供了几种内置的消息类型：

- **文本消息**: 标准文本内容
- **图片消息**: 图片 URL 和元数据
- **分段消息**: 结构化的分段内容
- **自定义消息**: 可扩展的消息格式

### 传输层

#### HTTP 传输

```python
# 服务器
server = MessageServer()
server.add_handler(handler)
await server.start(host="0.0.0.0", port=8000)

# 客户端
client = MessageClient("http://localhost:8000")
await client.send_message(envelope)
```

#### WebSocket 传输

```python
# 服务器
ws_server = WebSocketServer()
ws_server.add_handler(handler)
await ws_server.start(host="0.0.0.0", port=8001)

# 客户端
ws_client = WebSocketClient("ws://localhost:8001/ws")
await ws_client.connect()
await ws_client.send_message(envelope)
```

## 🔧 配置

### 环境变量

```bash
# 默认设置
MOFOX_BUS_HOST=0.0.0.0
MOFOX_BUS_PORT=8000
MOFOX_BUS_LOG_LEVEL=INFO
MOFOX_BUS_MAX_CONNECTIONS=1000
```

### 程序化配置

```python
from mofox_bus import MessageRuntime

runtime = MessageRuntime(
    max_workers=10,
    error_handler=custom_error_handler,
    middleware=[middleware1, middleware2]
)
```

## 🧪 开发

### 运行测试

```bash
# 安装开发依赖
pip install -e ".[dev]"

# 运行测试
pytest

# 运行带覆盖率的测试
pytest --cov=mofox_bus

# 运行类型检查
mypy mofox_bus
```

### 代码格式化

```bash
# 格式化代码
black mofox_bus
isort mofox_bus

# 检查代码
ruff check mofox_bus
```

### 构建文档

```bash
# 安装文档依赖
pip install -e ".[docs]"

# 构建文档
mkdocs build
```

## 📝 更新日志

### [0.1.0] - 2024-XX-XX

#### 新增
- MoFox Bus 初始版本
- 支持中间件的核心消息运行时
- HTTP 和 WebSocket 传输实现
- 基于 TypedDict 的类型化消息模型
- 消息路由和过滤功能
- 使用 orjson 优化的 JSON 序列化
- 全面的错误处理
- 完整的 async/await 支持

## 🤝 贡献

我们欢迎贡献！请参阅我们的[贡献指南](CONTRIBUTING.md)了解详情。

### 开发工作流程

1. Fork 仓库
2. 创建功能分支 (`git checkout -b feature/amazing-feature`)
3. 进行更改
4. 运行测试 (`pytest`)
5. 提交更改 (`git commit -m 'Add amazing feature'`)
6. 推送到分支 (`git push origin feature/amazing-feature`)
7. 打开 Pull Request

## 📄 许可证

本项目采用 GPL-3.0 许可证。详情请参见 [LICENSE](LICENSE) 文件。

## 🙏 致谢

- MoFox Bot 团队提供的原始概念和需求
- 帮助塑造本库的贡献者
- Python async 社区提供的灵感和最佳实践

## 📞 支持

- 📖 [文档](https://github.com/mofox-bot/mofox-bus/wiki)
- 🐛 [问题跟踪器](https://github.com/mofox-bot/mofox-bus/issues)
- 💬 [讨论](https://github.com/mofox-bot/mofox-bus/discussions)

## 🔗 相关项目

- [MoFox Bot](https://github.com/mofox-bot/mofox-bot) - 主要聊天机器人框架
- [maim_message](https://github.com/maimai-bot/maim_message) - 消息格式标准

---

**MoFox Bus** - 一次一条消息，构建消息基础设施的未来。🚀