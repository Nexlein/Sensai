import os
from pathlib import Path

import pytest

from sensai.tools.fs import ListDirTool, ReadFileTool, WriteFileTool


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


@pytest.mark.asyncio
async def test_list_dir_rejects_relative_traversal(fs_sandbox):
    tool = ListDirTool(fs_sandbox)
    content = await tool.execute("../outside")

    assert "Path traversal rejected" in content


@pytest.mark.asyncio
async def test_list_dir_rejects_symlink_escape(fs_sandbox):
    if not (fs_sandbox / "link").exists():
        pytest.skip("Symlink creation not supported on this OS")

    tool = ListDirTool(fs_sandbox)
    content = await tool.execute("link")

    assert "Path traversal rejected" in content


async def test_read_file_resolves_unique_filename_case(fs_sandbox):
    (fs_sandbox / "AGENTS.md").write_text("real instructions", encoding="utf-8")
    tool = ReadFileTool(fs_sandbox)
    assert await tool.execute("agents.md") == "real instructions"


async def test_read_file_refuses_ambiguous_case_match(fs_sandbox):
    (fs_sandbox / "NOTE.md").write_text("first", encoding="utf-8")
    (fs_sandbox / "Note.md").write_text("second", encoding="utf-8")
    tool = ReadFileTool(fs_sandbox)
    assert await tool.execute("note.md") == "Error: Ambiguous file name: note.md"


async def test_case_corrected_symlink_still_cannot_escape_root(fs_sandbox):
    outside_file = fs_sandbox.parent / "outside" / "secret.txt"
    (fs_sandbox / "SECRET.TXT").symlink_to(outside_file)
    tool = ReadFileTool(fs_sandbox)
    assert "Path traversal rejected" in await tool.execute("secret.txt")


def test_write_file_requires_confirmation(fs_sandbox):
    assert WriteFileTool(fs_sandbox).requires_confirmation is True


async def test_write_file_creates_new_file(fs_sandbox):
    tool = WriteFileTool(fs_sandbox)
    assert await tool.execute("new.txt", "fresh") == "Wrote 5 characters to new.txt"
    assert (fs_sandbox / "new.txt").read_text(encoding="utf-8") == "fresh"


async def test_write_file_overwrites_existing_file(fs_sandbox):
    tool = WriteFileTool(fs_sandbox)
    await tool.execute("test.txt", "replaced")
    assert (fs_sandbox / "test.txt").read_text(encoding="utf-8") == "replaced"


def test_write_file_preview_diffs_against_current_content(fs_sandbox):
    preview = WriteFileTool(fs_sandbox).preview("test.txt", "hello there")

    assert "-hello world" in preview
    assert "+hello there" in preview
    assert (fs_sandbox / "test.txt").read_text(encoding="utf-8") == "hello world"


def test_write_file_preview_new_file_is_all_additions(fs_sandbox):
    preview = WriteFileTool(fs_sandbox).preview("new.txt", "a\nb")

    assert preview.splitlines()[-2:] == ["+a", "+b"]
    assert not (fs_sandbox / "new.txt").exists()


def test_write_file_preview_none_when_write_would_be_refused(fs_sandbox):
    tool = WriteFileTool(fs_sandbox)

    assert tool.preview("../outside/secret.txt", "x") is None
    assert tool.preview("subdir", "x") is None


async def test_write_file_creates_missing_parents(fs_sandbox):
    tool = WriteFileTool(fs_sandbox)
    await tool.execute("a/b/c.txt", "deep")
    assert (fs_sandbox / "a" / "b" / "c.txt").read_text(encoding="utf-8") == "deep"


async def test_write_file_accepts_empty_content(fs_sandbox):
    tool = WriteFileTool(fs_sandbox)
    await tool.execute("empty.txt", "")
    assert (fs_sandbox / "empty.txt").read_text(encoding="utf-8") == ""


async def test_write_file_refuses_directory(fs_sandbox):
    tool = WriteFileTool(fs_sandbox)
    assert await tool.execute("subdir", "x") == "Error: Path is a directory: subdir"
    assert await tool.execute(".", "x") == "Error: Path is a directory: ."


async def test_write_file_rejects_relative_traversal(fs_sandbox):
    tool = WriteFileTool(fs_sandbox)
    assert "Path traversal rejected" in await tool.execute(
        "../outside/secret.txt", "pwned"
    )
    assert (fs_sandbox.parent / "outside" / "secret.txt").read_text() == "secret"


async def test_write_file_rejects_absolute_path(fs_sandbox):
    tool = WriteFileTool(fs_sandbox)
    target = fs_sandbox.parent / "outside" / "new.txt"
    assert "Path traversal rejected" in await tool.execute(str(target), "pwned")
    assert not target.exists()


async def test_write_file_rejects_traversal_without_creating_dirs(fs_sandbox):
    tool = WriteFileTool(fs_sandbox)
    assert "Path traversal rejected" in await tool.execute("../escape/x.txt", "pwned")
    assert not (fs_sandbox.parent / "escape").exists()


async def test_write_file_rejects_symlink_dir_escape(fs_sandbox):
    if not (fs_sandbox / "link").exists():
        pytest.skip("Symlink creation not supported on this OS")
    tool = WriteFileTool(fs_sandbox)
    assert "Path traversal rejected" in await tool.execute("link/secret.txt", "pwned")
    assert (fs_sandbox.parent / "outside" / "secret.txt").read_text() == "secret"


async def test_write_file_rejects_symlinked_file_escape(fs_sandbox):
    outside_file = fs_sandbox.parent / "outside" / "secret.txt"
    (fs_sandbox / "alias.txt").symlink_to(outside_file)
    tool = WriteFileTool(fs_sandbox)
    assert "Path traversal rejected" in await tool.execute("alias.txt", "pwned")
    assert outside_file.read_text() == "secret"
