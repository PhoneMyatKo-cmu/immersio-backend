"""
Tests for services/vocab/vocab_services.py
Covers: docs/test_plan.md
  §5.3 SVOC-01..03  save_vocabularies   [integration; mock translate / lookup]
  §7.3 VDS-01       get_vocab_by_surface_form
"""

import pytest

pytestmark = [pytest.mark.integration]


@pytest.mark.video_submission
@pytest.mark.skip(reason="TODO SVOC-01..03: new rows, skip existing, input de-dup")
def test_svoc_save_vocabularies(db_session):
    ...


@pytest.mark.word_lookup
@pytest.mark.skip(reason="TODO VDS-01: get_vocab_by_surface_form returns row / None")
def test_vds_01_get_vocab_by_surface_form(db_session):
    ...
