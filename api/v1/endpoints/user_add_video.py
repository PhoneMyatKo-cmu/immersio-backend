from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from db.base import get_db
from services.caption_services import save_tokenized_captions
from services.context_sentence_services import save_context_sentence
from services.video_services import (
    check_video_exists,
    get_video_by_youtube_video_id,
    save_video,
)
from services.video_vocab_service import (
    save_video_vocab_profile,
    save_video_vocab_profile_background,
)
from services.vocab_services import save_vocabularies
from utils.captions_helpers import (
    fetch_raw_captions,
    get_line_level_captions,
    process_captions,
    tokenize_captions,
)
from utils.sentence_reconstruction import (
    reconstruct_sentence_for_auto_generate,
    reconstruct_sentence_for_manual,
)
from utils.video_validation_helpers import validate_video

router = APIRouter(prefix="/add-video")


class VideoUrl(BaseModel):
    youtube_url: str


class SubmissionResponse(BaseModel):
    message: str
    video_id: int
    video_title: str


@router.post("/")
def add_video(
    data: VideoUrl, background_tasks: BackgroundTasks, db: Session = Depends(get_db)
) -> SubmissionResponse:

    validation_result = validate_video(data.youtube_url)
    if not validation_result["valid"]:
        # return {
        #     "status":"fail",
        #     "error":validation_result["error"]
        # }
        raise HTTPException(400, validation_result["error"])

    youtube_video_id = validation_result["video_id"]
    video_existing = check_video_exists(youtube_video_id, db)
    if video_existing:
        # return {
        #     "status":"fail",
        #     "error": "Already exists"
        # }
        return SubmissionResponse(
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
    caption_len = 0
    flattened_token = [
        (t["surface"], t["base_form"])
        for caption in processed_captions
        for t in caption["tokens"]
    ]
    surface_form_list = [token[0] for token in flattened_token]

    available_caption = validation_result["suitablity"]["available_captions"]
    print(f"Available captions:{available_caption}")
    is_standard = False
    for track in available_caption:
        if track.get("snippet", "").get("trackKind") == "standard":
            is_standard = True

    if is_standard:
        print("Manual Route")
        context_sentences = reconstruct_sentence_for_manual(processed_captions)

    else:
        context_sentences = reconstruct_sentence_for_auto_generate(raw_captions)

    try:
        video = save_video(
            meta_data=validation_result["meta_data"],
            suitability=validation_result["suitablity"],
            db=db,
        )

        saved_video_id = get_video_by_youtube_video_id(youtube_video_id, db).id
        # print(flattened_token[:5])

        caption_len = save_tokenized_captions(processed_captions, saved_video_id, db)

        save_vocabularies(flattened_token, db)

        saved_sentences = save_context_sentence(context_sentences, saved_video_id, db)

        background_tasks.add_task(
            save_video_vocab_profile_background,
            saved_video_id,
            surface_form_list,
        )

    except Exception as e:
        print(f"Db error:{e}")
        raise HTTPException(500, "Server Error , Please Try again later.")

    return SubmissionResponse(
        message="Successful", video_id=saved_video_id, video_title=video["title"]
    )
