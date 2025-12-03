# MoFox Wire

[![PyPI version](https://badge.fury.io/py/mofox-wire.svg)](https://badge.fury.io/py/mofox-wire)
[![Python versions](https://img.shields.io/pypi/pyversions/mofox-wire.svg)](https://pypi.org/project/mofox-wire/)
[![License](https://img.shields.io/badge/License-GPL--3.0-blue.svg)](https://opensource.org/licenses/GPL-3.0)

MoFox Wire is a lightweight, high-performance messaging wire designed for MoFox Bot and similar chatbot applications. It provides a rowiret foundation for building message-driven systems with support for typed message envelopes, flexible routing, and multiple transport protocols.

## ✨ Features

- **🏷️ Typed Messages**: Full TypeScript-style type safety with TypedDict message models
- **🚀 High Performance**: Built with async/await and optimized for high-throughput scenarios
- **🌐 Multiple Transports**: Support for HTTP and WebSocket protocols out of the box
- **🔄 Flexible Routing**: Sophisticated message routing with middleware support
- **📦 JSON Serialization**: Efficient JSON-based message serialization with orjson
- **🛡️ Error Handling**: Comprehensive error handling and processing guarantees
- **🎯 Easy Integration**: Simple API for quick integration with existing projects

## 🚀 Installation

Install from PyPI (recommended):

```bash
pip install mofox-wire
```

Install from source:

```bash
git clone https://github.com/mofox-bot/mofox-wire.git
cd mofox-wire
pip install -e .
```

For development:

```bash
pip install -e ".[dev]"
```

## 📋 Requirements

- Python 3.11+
- aiohttp >= 3.12.0
- fastapi >= 0.116.0
- orjson >= 3.10.0
- uvicorn >= 0.35.0
- websockets >= 15.0.1

## 🏗️ Architecture

MoFox Wire follows a layered architecture:

```
┌─────────────────┐
│   Application   │
├─────────────────┤
│   Runtime API   │
├─────────────────┤
│     Router      │
├─────────────────┤
│   Codec/Types   │
├─────────────────┤
│   Transport     │
└─────────────────┘
```

- **Types**: TypedDict models for messages and metadata
- **Codec**: JSON serialization/deserialization utilities
- **Transport**: HTTP and WebSocket client/server implementations
- **Router**: Message routing and filtering capabilities
- **Runtime**: High-level API for message processing and middleware

## 📖 Quick Start

### Basic Message Handling

```python
import asyncio
from mofox_wire import MessageRuntime, MessageBuilder, MessageEnvelope

async def handle_message(envelope: MessageEnvelope) -> MessageEnvelope | None:
    """Simple message handler that processes incoming messages"""
    print(f"Processing message: {envelope.get('content', 'No content')}")

    # Process the message (modify, filter, etc.)
    if envelope.get('content') == 'hello':
        response = MessageBuilder.text_message('world')
        response['reply_to'] = envelope.get('id')
        return response

    return None

async def main():
    # Create runtime
    runtime = MessageRuntime()

    # Register handler
    runtime.add_handler(handle_message)

    # Create a test message
    message = MessageBuilder.text_message('hello')
    message['id'] = 'msg-001'

    # Process the message
    await runtime.process_message(message)

if __name__ == '__main__':
    asyncio.run(main())
```

### HTTP Server Example

```python
from mofox_wire import MessageServer
import uvicorn

async def main():
    # Create HTTP server
    server = MessageServer()

    # Add message handler
    server.add_handler(lambda env: print(f"Received: {env}"))

    # Start server (will run until interrupted)
    config = uvicorn.Config(server.app, host="0.0.0.0", port=8000)
    server = uvicorn.Server(config)
    await server.serve()

if __name__ == '__main__':
    asyncio.run(main())
```

### WebSocket Client Example

```python
from mofox_wire.transport import WebSocketClient
from mofox_wire import MessageBuilder

async def main():
    # Create WebSocket client
    client = WebSocketClient("ws://localhost:8000/ws")

    await client.connect()

    # Send a message
    message = MessageBuilder.text_message("Hello from WebSocket client!")
    await client.send_message(message)

    # Receive messages
    async for envelope in client.listen():
        print(f"Received: {envelope}")

if __name__ == '__main__':
    asyncio.run(main())
```

## 📚 API Reference

### Core Components

#### MessageRuntime

The main runtime for processing messages with middleware support.

```python
runtime = MessageRuntime()
runtime.add_handler(handler_func)
runtime.add_middleware(middleware_func)
await runtime.process_message(envelope)
```

#### MessageBuilder

Utility for creating typed message envelopes.

```python
# Text message
msg = MessageBuilder.text_message("Hello world", user_id="user123")

# Image message
msg = MessageBuilder.image_message("https://example.com/image.jpg", user_id="user123")

# Custom message
msg = MessageBuilder.create_message(
    content="Custom content",
    message_type="custom",
    user_id="user123",
    platform="discord"
)
```

#### Router

Advanced message routing and filtering.

```python
router = Router()

# Add route with predicate
router.add_route(
    predicate=lambda env: env.get('platform') == 'discord',
    handler=discord_handler
)

# Process messages
await router.route(envelope)
```

### Message Types

MoFox Wire provides several built-in message types:

- **Text Messages**: Standard text content
- **Image Messages**: Image URLs and metadata
- **Seg Messages**: Structured content with segments
- **Custom Messages**: Extensible message format

### Transport Layer

#### HTTP Transport

```python
# Server
server = MessageServer()
server.add_handler(handler)
await server.start(host="0.0.0.0", port=8000)

# Client
client = MessageClient("http://localhost:8000")
await client.send_message(envelope)
```

#### WebSocket Transport

```python
# Server
ws_server = WebSocketServer()
ws_server.add_handler(handler)
await ws_server.start(host="0.0.0.0", port=8001)

# Client
ws_client = WebSocketClient("ws://localhost:8001/ws")
await ws_client.connect()
await ws_client.send_message(envelope)
```

## 🔧 Configuration

### Environment Variables

```bash
# Default settings
mofox_wire_HOST=0.0.0.0
mofox_wire_PORT=8000
mofox_wire_LOG_LEVEL=INFO
mofox_wire_MAX_CONNECTIONS=1000
```

### Programmatic Configuration

```python
from mofox_wire import MessageRuntime

runtime = MessageRuntime(
    max_workers=10,
    error_handler=custom_error_handler,
    middleware=[middleware1, middleware2]
)
```

## 🧪 Development

### Running Tests

```bash
# Install development dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Run tests with coverage
pytest --cov=mofox_wire

# Run type checking
mypy mofox_wire
```

### Code Formatting

```bash
# Format code
black mofox_wire
isort mofox_wire

# Lint code
ruff check mofox_wire
```

### Building Documentation

```bash
# Install documentation dependencies
pip install -e ".[docs]"

# Build docs
mkdocs build
```

## 📝 Changelog

### [0.1.0] - 2024-XX-XX

#### Added
- Initial release of MoFox Wire
- Core message runtime with middleware support
- HTTP and WebSocket transport implementations
- Typed message models with TypedDict
- Message routing and filtering capabilities
- JSON serialization with orjson optimization
- Comprehensive error handling
- Full async/await support

## 🤝 Contributing

We welcome contributions! Please see our [Contributing Guide](CONTRIBUTING.md) for details.

### Development Workflow

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Make your changes
4. Run tests (`pytest`)
5. Commit your changes (`git commit -m 'Add amazing feature'`)
6. Push to the branch (`git push origin feature/amazing-feature`)
7. Open a Pull Request

## 📄 License

This project is licensed under the GPL-3.0 License. See the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- The MoFox Bot team for the original concept and requirements
- Contributors who have helped shape this library
- The Python async community for inspiration and best practices

## 📞 Support

- 📖 [Documentation](https://github.com/mofox-bot/mofox-wire/wiki)
- 🐛 [Issue Tracker](https://github.com/mofox-bot/mofox-wire/issues)
- 💬 [Discussions](https://github.com/mofox-bot/mofox-wire/discussions)

## 🔗 Related Projects

- [MoFox Bot](https://github.com/mofox-bot/mofox-bot) - The main chatbot framework
- [maim_message](https://github.com/maimai-bot/maim_message) - Message format standard

---

**MoFox Wire** - Building the future of messaging infrastructure, one message at a time. 🚀