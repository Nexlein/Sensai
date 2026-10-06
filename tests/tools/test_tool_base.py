from pathlib import Path

import pytest

from sensai.tools.base import PermissionBoundary


def test_permission_boundary_accepts_paths_inside_root(tmp_path: Path):
    root = tmp_path / "root"
    root.mkdir()

    assert PermissionBoundary(root)._validate_path("nested/file.txt") == (
        root / "nested/file.txt"
    )


def test_permission_boundary_rejects_paths_outside_root(tmp_path: Path):
    root = tmp_path / "root"
    root.mkdir()

    with pytest.raises(ValueError, match="Path traversal rejected"):
        PermissionBoundary(root)._validate_path("../secret.txt")
