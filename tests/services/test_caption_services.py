"""
Tests for services/caption/caption_services.py
Covers: docs/test_plan.md
  §5.2 DBS-05/06  save_tokenized_captions, get_captions_by_video_id  [integration]
  §7.2 GCT-01..04 get_caption_translation (cache hit/miss/fallback/KeyError)
[integration — db_session; mock google_translate at this module's path]
"""

import pytest

pytestmark = [pytest.mark.integration]


@pytest.mark.video_submission
@pytest.mark.skip(reason="TODO DBS-05/06: save_tokenized_captions + get_captions_by_video_id")
def test_dbs_captions(db_session):
    ...


@pytest.mark.word_lookup
@pytest.mark.skip(reason="TODO GCT-01..04: get_caption_translation cache/translate/fallback")
def test_gct_caption_translation(db_session):
    ...
