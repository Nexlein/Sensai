import os
from pathlib import Path

import pytest

from sensai.tools.fs import ListDirTool, ReadFileTool


@pytest.fixture
def fs_sandbox(tmp_path: Path):
    allowed_root = tmp_path / "sandbox"
    allowed_root.mkdir()
    (allowed_root / "test.txt").write_text("hello world")
    (allowed_root / "subdir").mkdir()
    (allowed_root / "subdir" / "file.txt").write_text("sub file")

    outside_root = tmp_path / "outside"
    outside_root.mkdir()
    (outside_root / "secret.txt").write_text("secret")

    # Create a symlink in sandbox pointing outside
    symlink_path = allowed_root / "link"
    try:
        os.symlink(outside_root, symlink_path)
    except OSError:
        pass  # Handle OS where symlinks need admin rights

    return allowed_root


@pytest.mark.asyncio
async def test_read_file_allowed(fs_sandbox):
    tool = ReadFileTool(fs_sandbox)
    content = await tool.execute("test.txt")
    assert content == "hello world"


@pytest.mark.asyncio
async def test_list_dir_allowed(fs_sandbox):
    tool = ListDirTool(fs_sandbox)
    content = await tool.execute(".")
    assert "test.txt" in content
    assert "subdir" in content


@pytest.mark.asyncio
async def test_read_file_missing(fs_sandbox):
    tool = ReadFileTool(fs_sandbox)
    content = await tool.execute("missing.txt")
    assert "Error" in content
    assert "missing.txt" in content


@pytest.mark.asyncio
async def test_read_file_traversal_relative(fs_sandbox):
    tool = ReadFileTool(fs_sandbox)
    content = await tool.execute("../outside/secret.txt")
    assert "Error" in content
    assert "Path traversal rejected" in content


@pytest.mark.asyncio
async def test_read_file_traversal_absolute(fs_sandbox):
    tool = ReadFileTool(fs_sandbox)
    outside_file = fs_sandbox.parent / "outside" / "secret.txt"
    content = await tool.execute(str(outside_file.resolve()))
    assert "Error" in content
    assert "Path traversal rejected" in content


@pytest.mark.asyncio
async def test_read_file_traversal_symlink(fs_sandbox):
    symlink_path = fs_sandbox / "link"
    if not symlink_path.exists():
        pytest.skip("Symlink creation not supported on this OS")

    tool = ReadFileTool(fs_sandbox)
    content = await tool.execute("link/secret.txt")
    assert "Error" in content
    assert "Path traversal rejected" in content
