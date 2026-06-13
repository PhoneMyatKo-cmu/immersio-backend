"""
Tests for services/user_vocab/user_vocab_service.py
Covers: docs/test_plan.md §7.3 (VDS-02..04):
  save_vocab_to_library, duplicate-constraint behavior, check_duplicate_vocab.
[integration — db_session; VDS-03 needs a constraint-enforcing DB (Postgres)]
"""

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.word_lookup]


@pytest.mark.skip(reason="TODO VDS-02: save_vocab_to_library inserts row with default SRS values")
def test_vds_02_save(db_session, fx_user_save):
    ...


@pytest.mark.skip(reason="TODO VDS-03: duplicate (user, vocab) violates uq_user_vocab -> raises")
def test_vds_03_duplicate_raises(db_session, fx_user_save):
    ...


@pytest.mark.skip(reason="TODO VDS-04: check_duplicate_vocab scoped per user")
def test_vds_04_check_duplicate(db_session, fx_user_save):
    ...
