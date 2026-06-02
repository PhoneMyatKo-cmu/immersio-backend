from fastapi import BackgroundTasks, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from services.caption_services import save_tokenized_captions
from services.context_sentence_services import save_context_sentence
from services.video_background_service import process_video_vocab_background
from services.video_services import (
    check_video_exists,
    get_video_by_youtube_video_id,
    save_video,
)
from services.vocab_services import save_vocabularies
from utils.captions_helpers import (
    fetch_raw_captions,
    get_line_level_captions,
    process_captions,
)
from utils.sentence_reconstruction import (
    reconstruct_sentence_for_auto_generate,
    reconstruct_sentence_for_manual,
)
from utils.video_validation_helpers import validate_video


class SubmissionResult(BaseModel):
    message: str
    video_id: int
    video_title: str


def submit_video_for_processing(
    youtube_url: str, db: Session, background_tasks: BackgroundTasks
):
    """ "
    Validate a YouTube URL, ingest its Japanese captions, and persist the
    video-learning data needed by the app.

    This function orchestrates the full video submission flow:
    - validates that the URL points to a suitable Japanese YouTube video
    - returns the existing video if it has already been saved
    - fetches and processes captions
    - reconstructs context sentences
    - saves video metadata, processed captions, vocabulary, and sentences
    - queues background processing for video vocabulary profile and difficulty

    Raises:
        HTTPException: 400 when the video is invalid or unsuitable.
        HTTPException: 500 when caption fetching or database persistence fails.

    Returns:
        SubmissionResult: The submission status, saved video id, and video title.
    """

    validation_result = validate_video(youtube_url)
    if not validation_result["valid"]:
        raise HTTPException(400, validation_result["error"])

    youtube_video_id = validation_result["video_id"]
    video_existing = check_video_exists(youtube_video_id, db)
    if video_existing:
        return SubmissionResult(
            message="Video already exists.",
            video_id=video_existing.id,
            video_title=video_existing.title,
        )

    raw_captions = []
    try:
        raw_captions = fetch_raw_captions(youtube_video_id)
    except Exception as e:
        print(e)
        raise HTTPException(500, "Server Error")

    line_level_captions = get_line_level_captions(raw_captions)
    processed_captions = process_captions(line_level_captions)
    flattened_token = [
        (t["surface"], t["base_form"])
        for caption in processed_captions
        for t in caption["tokens"]
    ]
    surface_form_list = [token[0] for token in flattened_token]

    context_sentences = reconstruct_context_sentences(
        validation_result=validation_result,
        raw_captions=raw_captions,
        processed_captions=processed_captions,
    )

    try:
        video = save_video(
            meta_data=validation_result["meta_data"],
            suitability=validation_result["suitablity"],
            db=db,
        )

        saved_video_id = get_video_by_youtube_video_id(youtube_video_id, db).id

        save_tokenized_captions(processed_captions, saved_video_id, db)

        save_vocabularies(flattened_token, db)

        save_context_sentence(context_sentences, saved_video_id, db)

        background_tasks.add_task(
            process_video_vocab_background,
            saved_video_id,
            surface_form_list,
        )

    except Exception as e:
        print(f"Db error:{e}")
        raise HTTPException(500, "Server Error , Please Try again later.")

    return SubmissionResult(
        message="Successful", video_id=saved_video_id, video_title=video["title"]
    )


def reconstruct_context_sentences(
    validation_result: dict,
    raw_captions: dict,
    processed_captions: list[dict],
) -> list[dict]:
    available_captions = validation_result["suitablity"]["available_captions"]

    is_standard = any(
        track.get("snippet", {}).get("trackKind") == "standard"
        for track in available_captions
    )

    if is_standard:
        return reconstruct_sentence_for_manual(processed_captions)

    return reconstruct_sentence_for_auto_generate(raw_captions)
