from __future__ import annotations

from app.shared.staff_nav import staff_fab_html


def test_staff_fab_hides_admin_link_for_non_admin() -> None:
    html = staff_fab_html(active="home", is_admin=False)

    assert 'href="/"' in html
    assert 'href="/interno/nuevo-lead"' in html
    assert 'href="/admin"' not in html


def test_staff_fab_shows_admin_link_for_admin() -> None:
    html = staff_fab_html(active="admin", is_admin=True)

    assert 'href="/admin"' in html


def test_staff_fab_marks_active_link() -> None:
    html = staff_fab_html(active="lead", is_admin=False)

    assert 'staff-fab__link--active" href="/interno/nuevo-lead"' in html
