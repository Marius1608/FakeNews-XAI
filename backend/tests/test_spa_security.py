"""Regression tests for the SPA catch-all path traversal (backend/main.py → safe_build_path)."""

from pathlib import Path

import pytest

from backend.spa import safe_build_path


@pytest.fixture()
def build(tmp_path: Path) -> Path:
    root = tmp_path / "frontend" / "build"
    (root / "assets").mkdir(parents=True)
    (root / "index.html").write_text("<html></html>")
    (root / "assets" / "index-abc.js").write_text("console.log(1)")
    (tmp_path / ".env").write_text("NEO4J_PASSWORD=secret")
    return root


def test_serves_files_inside_build(build: Path) -> None:
    assert safe_build_path(build, "assets/index-abc.js") == (build / "assets" / "index-abc.js").resolve()
    assert safe_build_path(build, "index.html") == (build / "index.html").resolve()


@pytest.mark.parametrize(
    "requested",
    [
        "../../.env",           # what "/..%2f..%2f.env" decodes to
        "assets/../../../.env",
        "/etc/passwd",          # absolute path replaces the base on join
        "..",
        "assets",               # directory, not a file
        "missing.js",
    ],
)
def test_rejects_traversal_and_non_files(build: Path, requested: str) -> None:
    assert safe_build_path(build, requested) is None


def test_rejects_symlink_escaping_build(build: Path, tmp_path: Path) -> None:
    link = build / "leak"
    try:
        link.symlink_to(tmp_path / ".env")
    except OSError:
        pytest.skip("symlinks not permitted on this system")
    assert safe_build_path(build, "leak") is None
