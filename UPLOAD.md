# PyPI Upload Instructions

This document provides instructions for uploading the mofox-bus package to PyPI.

## Prerequisites

1. **PyPI Account**: You need an account on [PyPI](https://pypi.org/)
2. **API Token**: Generate an API token from your PyPI account settings
3. **Install Required Tools**:
   ```bash
   pip install build twine
   ```

## Upload Process

### 1. Test Upload to TestPyPI (Recommended)

First, upload to TestPyPI to verify everything works correctly:

```bash
# Upload to TestPyPI
python -m twine upload --repository testpypi dist/*
```

To test installation from TestPyPI:
```bash
pip install --index-url https://test.pypi.org/simple/ mofox-bus
```

### 2. Upload to Production PyPI

Once verified, upload to the production PyPI:

```bash
# Upload to PyPI (this is permanent!)
python -m twine upload dist/*
```

## Important Notes

- **Version Management**: Update the version in `mofox_bus/__init__.py` before each release
- **Check Changes**: Run `python -m twine check dist/*` to validate packages before upload
- **Git Tags**: Consider creating a git tag for each release:
  ```bash
  git tag v0.1.0
  git push origin v0.1.0
  ```

## File Structure After Build

```
dist/
├── mofox_bus-0.1.0-py3-none-any.whl  # Wheel distribution
└── mofox_bus-0.1.0.tar.gz            # Source distribution
```

## Post-Upload Verification

After uploading, verify the package:

1. Check the [PyPI page](https://pypi.org/project/mofox-bus/)
2. Test installation:
   ```bash
   pip install mofox-bus
   ```
3. Test import:
   ```python
   import mofox_bus
   print(f"Version: {mofox_bus.__version__}")
   ```

## Troubleshooting

### Common Issues

1. **Version Already Exists**: Increment the version number in `__init__.py`
2. **Invalid Distribution**: Run `python -m twine check dist/*` to identify issues
3. **Upload Failures**: Check your internet connection and PyPI API token

### Rebuilding Packages

If you need to rebuild after making changes:

```bash
# Clean previous builds
rm -rf dist/ build/ *.egg-info/

# Rebuild
python -m build
```