"""
Tests for utils/user_vocab_exposure_helper.py

Covers docs/test_case_specification.pdf MD-143:

  MD-143  isIntervalOverlapping()
    - Containment returns True, partial overlap does not
    - Tolerance buffer
    - Disjoint and identical intervals
"""

import pytest

from utils.user_vocab_exposure_helper import isIntervalOverlapping

pytestmark = [pytest.mark.unit]


def test_containment_true_partial_overlap_false():
    """A fully contained interval matches; one running past the end does not."""
    assert isIntervalOverlapping(5.0, 8.0, 4.0, 10.0) is True
    assert isIntervalOverlapping(5.0, 15.0, 4.0, 10.0) is False


def test_tolerance_buffer():
    """Endpoints just outside the window still match while the tolerance covers them."""
    assert isIntervalOverlapping(3.8, 10.2, 4.0, 10.0, tolerance=0.3) is True
    assert isIntervalOverlapping(3.5, 10.0, 4.0, 10.0, tolerance=0.3) is False


def test_disjoint_and_identical_intervals():
    """Disjoint intervals do not match; identical intervals do."""
    assert isIntervalOverlapping(20.0, 25.0, 4.0, 10.0) is False
    assert isIntervalOverlapping(4.0, 10.0, 4.0, 10.0) is True
