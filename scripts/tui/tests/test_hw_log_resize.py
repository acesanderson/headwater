from __future__ import annotations
import hw_log


def test_compute_row_cap_normal():
    cap = hw_log.compute_row_cap(40, hw_log.HEADER_HEIGHT)
    assert cap > 0
    assert cap == 40 - hw_log.HEADER_HEIGHT - 2


def test_compute_row_cap_minimum_is_one():
    cap = hw_log.compute_row_cap(5, hw_log.HEADER_HEIGHT)
    assert cap == 1


def test_compute_row_cap_exact_boundary():
    cap = hw_log.compute_row_cap(hw_log.HEADER_HEIGHT + 3, hw_log.HEADER_HEIGHT)
    assert cap == 1
