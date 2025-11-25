#!/usr/bin/env python3
"""
Setup script for mofox-bus package.
"""

from setuptools import setup, find_packages
import os

# Read the README file
def read_readme():
    with open("README.md", "r", encoding="utf-8") as fh:
        return fh.read()

# Read the license file
def read_license():
    with open("LICENSE", "r", encoding="utf-8") as fh:
        return fh.read()

# Get version from __init__.py
def get_version():
    with open("mofox_bus/__init__.py", "r", encoding="utf-8") as f:
        for line in f:
            if line.startswith("__version__"):
                return line.split("=")[1].strip().strip('"').strip("'")
    return "0.1.0"  # fallback version

setup(
    name="mofox-bus",
    version=get_version(),
    author="MoFox Team",
    author_email="",
    description="Messaging bus for MoFox Bot with HTTP/WebSocket transports and routing helpers",
    long_description=read_readme(),
    long_description_content_type="text/markdown",
    url="https://github.com/mofox-bot/mofox-bus",
    project_urls={
        "Bug Tracker": "https://github.com/mofox-bot/mofox-bus/issues",
        "Documentation": "https://github.com/mofox-bot/mofox-bus/wiki",
        "Source Code": "https://github.com/mofox-bot/mofox-bus",
    },
    packages=find_packages(exclude=["tests*", "docs*", "examples*"]),
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "Topic :: Software Development :: Libraries :: Python Modules",
        "Topic :: System :: Networking",
        "Topic :: Internet :: WWW/HTTP",
        "License :: OSI Approved :: GNU General Public License v3 (GPLv3)",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Programming Language :: Python :: 3.13",
        "Programming Language :: Python :: 3 :: Only",
        "Operating System :: OS Independent",
        "Framework :: AsyncIO",
        "Typing :: Typed",
    ],
    python_requires=">=3.11",
    install_requires=[
        "aiohttp>=3.12.0",
        "fastapi>=0.116.0",
        "orjson>=3.10.0",
        "uvicorn>=0.35.0",
        "websockets>=15.0.1",
    ],
    extras_require={
        "dev": [
            "pytest>=7.0.0",
            "pytest-asyncio>=0.21.0",
            "black>=23.0.0",
            "isort>=5.12.0",
            "mypy>=1.0.0",
            "ruff>=0.1.0",
        ],
        "docs": [
            "mkdocs>=1.5.0",
            "mkdocs-material>=9.0.0",
            "mkdocstrings[python]>=0.20.0",
        ],
    },
    keywords=[
        "messaging",
        "bus",
        "asyncio",
        "websocket",
        "http",
        "routing",
        "bot",
        "chatbot",
        "message-handler",
    ],
    include_package_data=True,
    zip_safe=False,
    license="GPL-3.0",
    platforms=["any"],
)