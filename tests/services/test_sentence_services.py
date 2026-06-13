"""
Tests for services/sentence/sentence_services.py
Covers: docs/test_plan.md §5.2 (DBS-07/08): save_sentence, get_sentence_by_video_id.
[integration — db_session]
"""

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.video_submission]


@pytest.mark.skip(reason="TODO DBS-07: save_sentence persists + returns {number_of_sentences}")
def test_dbs_07_save_sentence(db_session):
    ...


@pytest.mark.skip(reason="TODO DBS-08: get_sentence_by_video_id returns the video's sentences")
def test_dbs_08_get_sentence_by_video_id(db_session):
    ...
