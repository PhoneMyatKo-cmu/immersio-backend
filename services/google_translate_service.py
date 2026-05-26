from pathlib import Path

from google.cloud import translate

BASE_DIR = Path(__file__).resolve().parent.parent
key_path = BASE_DIR / "gct_key.json"
client = translate.TranslationServiceClient.from_service_account_json(key_path)

parent = "projects/nlp-image-ocr/locations/global"


def fall_back_google_translate(japanese_form: str):
    print("Google Translation Running!")
    response = client.translate_text(
        contents=[japanese_form],
        target_language_code="en",
        parent=parent,
        mime_type="text/plain",
    )
    # print(response.translations)

    return [t.translated_text for t in response.translations]
