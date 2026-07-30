
from datetime import datetime, timedelta

from models.user_vocab_library import UserSavedVocabulary


def update_ease_factor(vocab_card: UserSavedVocabulary, grade: int) -> float:
    """
    Update the new ease factor based on the user's review grade.
    """
    # Ensure the grade is between 0 and 5
    if grade < 0 or grade > 5:
        raise ValueError("Grade must be between 0 and 5.")

    # Calculate the new ease factor
    new_ease_factor = vocab_card.ease_factor + (0.1 - (5 - grade) * (0.08 + (5 - grade) * 0.02))

    # Ensure the ease factor doesn't drop below 1.3
    if new_ease_factor < 1.3:
        new_ease_factor = 1.3

    vocab_card.ease_factor = new_ease_factor
    return new_ease_factor

def update_review_stats(vocab_card: UserSavedVocabulary, grade: int):
    """
    Update the interval, repetitions, and lapses based on the user's review grade.
    """
    if grade < 3:
        vocab_card.lapses += 1
        vocab_card.repetitions = 0  # Reset repetitions on a lapse
        vocab_card.interval_days = 1  # Reset interval to 1 day on a lapse
    else:
        vocab_card.repetitions += 1
        if vocab_card.repetitions == 1:
            vocab_card.interval_days = 1
        elif vocab_card.repetitions == 2:
            vocab_card.interval_days = 6
        else:
            vocab_card.interval_days = round(vocab_card.interval_days * vocab_card.ease_factor)


def update_next_review_date(vocab_card: UserSavedVocabulary):
    """
    Update the next review date based on the current date and the interval.
    """
    vocab_card.last_review_date = datetime.now().date()
    vocab_card.next_review_date = vocab_card.last_review_date + timedelta(days=vocab_card.interval_days)

def update_srs_state(vocab_card: UserSavedVocabulary):
    """
    Update the SRS state based on the interval of the card.
    """

    if vocab_card.interval_days >= 180:
        vocab_card.srs_state = "mastered"
    else:
        vocab_card.srs_state = "studying"

def update_review_card(vocab_card: UserSavedVocabulary, grade: int):
    """
    Update the review card based on the user's review grade.
    """
    update_ease_factor(vocab_card, grade)
    update_review_stats(vocab_card, grade)
    update_next_review_date(vocab_card)
    update_srs_state(vocab_card)