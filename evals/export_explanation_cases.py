"""Export cached contextual-explanation cases for LLM-as-a-judge review.

Read-only. Joins each ContextualExplanation back to the Vocabulary and Caption
rows it was generated from, so every exported case carries BOTH:

  - the INPUT the generator saw   (surface_form, meanings, context_sentence)
  - the OUTPUT it produced        (explanation, examples, confidence, mismatch flag)

Caveat: the original `pos` (part of speech) passed at generation time is NOT
persisted anywhere (ContextualExplanation stores only vocab_id/caption_id, and
Vocabulary has no POS column), so it is exported as "NOT RECORDED". Everything
else is reconstructed faithfully.

Outputs (under evals/output/):
  - cases_all.jsonl     every exported row, machine-readable
  - handrate_cases.md   first N_HAND rows, for your own hand-rating
  - llm_cases.md        the remaining rows, to paste into the Claude Project

Usage:
  python -m evals.export_explanation_cases                 # 70 rows, 20 hand / 50 llm
  python -m evals.export_explanation_cases --limit 70 --hand 20
  python -m evals.export_explanation_cases --random        # random sample (not reproducible)
"""

import argparse
import json
import os

import importlib
import pkgutil

from sqlalchemy import func, select

import models as models_pkg
from db.base import SessionLocal
from models.ai_explanation_cache import ContextualExplanation
from models.processed_caption import Caption
from models.vocab import Vocabulary

# The ORM models use string-based relationships (e.g. Caption -> "Video" ->
# "User" -> ...). SQLAlchemy can only resolve those names if every referenced
# class has been imported. Import all model modules so the mapper registry is
# fully populated before any query is compiled.
for _module in pkgutil.iter_modules(models_pkg.__path__):
    importlib.import_module(f"{models_pkg.__name__}.{_module.name}")

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "output")


def fetch_cases(limit: int, randomize: bool) -> list[dict]:
    stmt = (
        select(ContextualExplanation, Vocabulary, Caption)
        .join(Vocabulary, ContextualExplanation.vocab_id == Vocabulary.id)
        .join(Caption, ContextualExplanation.caption_id == Caption.id)
    )
    stmt = stmt.order_by(func.random()) if randomize else stmt.order_by(ContextualExplanation.id)
    stmt = stmt.limit(limit)

    cases = []
    with SessionLocal() as db:
        for expl, vocab, caption in db.execute(stmt).all():
            cases.append(
                {
                    "explanation_id": expl.id,
                    "vocab_id": expl.vocab_id,
                    "caption_id": expl.caption_id,
                    # ---- INPUT (what the generator saw) ----
                    "surface_form": vocab.japanese_form,
                    "reading": vocab.reading,
                    "pos": "NOT RECORDED",  # not persisted at generation time
                    "meanings": vocab.meanings,
                    "context_sentence": caption.text,
                    "context_translation": caption.translation,
                    # ---- OUTPUT (what the generator produced) ----
                    "explanation": expl.explanation,
                    "examples": expl.examples,
                    "confidence": expl.confidence_level.value,
                    "dictionary_mismatch_detected": expl.dictionary_mismatch_detected,
                }
            )
    return cases


def render_case_md(case: dict, index: int) -> str:
    meanings = json.dumps(case["meanings"], ensure_ascii=False)
    examples_lines = []
    for i, ex in enumerate(case["examples"], 1):
        examples_lines.append(
            f"  {i}. {ex.get('japanese', '')}\n"
            f"     reading: {ex.get('reading', '')}\n"
            f"     english: {ex.get('english', '')}"
        )
    examples_block = "\n".join(examples_lines) if examples_lines else "  (none)"

    return f"""### Case {index}  (explanation_id={case['explanation_id']})

INPUT
- surface_form: {case['surface_form']}
- reading: {case['reading']}
- pos: {case['pos']}
- meanings: {meanings}
- context_sentence: {case['context_sentence']}
- context_translation: {case['context_translation']}

OUTPUT UNDER REVIEW
- explanation: {case['explanation']}
- examples:
{examples_block}
- confidence: {case['confidence']}
- dictionary_mismatch_detected: {case['dictionary_mismatch_detected']}

---
"""


def write_md(path: str, title: str, cases: list[dict], start_index: int) -> None:
    parts = [f"# {title}\n\n({len(cases)} cases)\n\n"]
    for offset, case in enumerate(cases):
        parts.append(render_case_md(case, start_index + offset))
    with open(path, "w", encoding="utf-8") as f:
        f.write("".join(parts))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=70, help="total rows to export")
    parser.add_argument("--hand", type=int, default=20, help="first N rows go to the hand-rate set")
    parser.add_argument("--random", action="store_true", help="random sample (not reproducible)")
    args = parser.parse_args()

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    cases = fetch_cases(args.limit, args.random)
    if not cases:
        print("No contextual-explanation rows found. Is DATABASE_URL pointing at a populated DB?")
        return
    if len(cases) < args.limit:
        print(f"WARNING: only {len(cases)} rows available (asked for {args.limit}).")

    hand_cases = cases[: args.hand]
    llm_cases = cases[args.hand :]

    jsonl_path = os.path.join(OUTPUT_DIR, "cases_all.jsonl")
    with open(jsonl_path, "w", encoding="utf-8") as f:
        for case in cases:
            f.write(json.dumps(case, ensure_ascii=False) + "\n")

    write_md(
        os.path.join(OUTPUT_DIR, "handrate_cases.md"),
        "Hand-rate cases (rate these yourself first)",
        hand_cases,
        start_index=1,
    )
    write_md(
        os.path.join(OUTPUT_DIR, "llm_cases.md"),
        "LLM judge cases (paste into the Claude Project)",
        llm_cases,
        start_index=len(hand_cases) + 1,
    )

    print(f"Exported {len(cases)} cases to {OUTPUT_DIR}/")
    print(f"  - cases_all.jsonl   ({len(cases)} rows)")
    print(f"  - handrate_cases.md ({len(hand_cases)} rows)")
    print(f"  - llm_cases.md      ({len(llm_cases)} rows)")


if __name__ == "__main__":
    main()
