from __future__ import annotations

from pathlib import Path

import pytest

from app.shared.html_templates import RawHTML, _read_template, render_template


@pytest.fixture
def template_file(tmp_path: Path) -> Path:
    path = tmp_path / "sample.html"
    path.write_text("<h1>{{title}}</h1><div>{{body}}</div><p>{{missing}}</p>", encoding="utf-8")
    return path


def test_render_template_replaces_placeholders(template_file: Path) -> None:
    result = render_template(template_file, title="Hola", body="mundo")

    assert "<h1>Hola</h1>" in result
    assert "<div>mundo</div>" in result


def test_render_template_escapes_plain_values(template_file: Path) -> None:
    result = render_template(template_file, title="<script>alert(1)</script>", body="x")

    assert "<script>" not in result
    assert "&lt;script&gt;" in result


def test_render_template_does_not_escape_raw_html(template_file: Path) -> None:
    result = render_template(template_file, title=RawHTML("<b>negrita</b>"), body="x")

    assert "<b>negrita</b>" in result


def test_render_template_leaves_unmatched_placeholder(template_file: Path) -> None:
    result = render_template(template_file, title="t", body="b")

    assert "{{missing}}" in result


def test_read_template_is_cached(template_file: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _read_template.cache_clear()
    render_template(template_file, title="t", body="b")

    template_file.write_text("changed", encoding="utf-8")
    result = render_template(template_file, title="t", body="b")

    assert "changed" not in result
