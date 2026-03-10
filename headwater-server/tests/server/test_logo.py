from __future__ import annotations

from headwater_server.server.logo import print_logo, print_bywater_logo


def test_bywater_logo_function_exists():
    """AC-10: print_bywater_logo() is importable from logo.py."""
    assert callable(print_bywater_logo)


def test_bywater_logo_uses_green(capsys):
    """AC-10: Bywater uses green (\\033[92m); not Headwater's blue (\\033[94m)."""
    print_bywater_logo()
    captured = capsys.readouterr()
    assert "\033[92m" in captured.out
    assert "\033[94m" not in captured.out
    assert "\033[0m" in captured.out


def test_bywater_logo_is_distinct_from_headwater_logo(capsys):
    """AC-10: The byte output of print_bywater_logo() != print_logo().
    Catches the case where HEADWATER banner is accidentally shipped in green.
    """
    print_logo()
    headwater_out = capsys.readouterr().out

    print_bywater_logo()
    bywater_out = capsys.readouterr().out

    assert bywater_out != headwater_out, (
        "Bywater and Headwater logos are identical — "
        "print_bywater_logo() must have distinct ASCII art"
    )
