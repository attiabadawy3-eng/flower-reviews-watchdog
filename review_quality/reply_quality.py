"""FLOWER Google Reviews: dependency-free draft quality gate (DEV only).

Only judges drafts. Never calls Google APIs, accesses credentials, or publishes.
"""
from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher
import re
import unicodedata

AR_MARKS = re.compile(r"[\u064b-\u065f\u0670\u0640]")
SPACES = re.compile(r"\s+")
EMOJI = re.compile(r"[\U0001F300-\U0001FAFF\u2764\ufe0f\u2600-\u27bf]")
UNVERIFIED_CLAIMS = (
    "تم اتخاذ الاجراءات اللازمه", "تم حل المشكله", "راجعنا الكاميرات",
    "تم التواصل معك", "نضمن عدم تكرار", "لن يتكرر ابدا",
)


def normalize(value: str) -> str:
    text = unicodedata.normalize("NFKC", value or "").lower()
    text = AR_MARKS.sub("", text).replace("أ", "ا").replace("إ", "ا").replace("آ", "ا")
    text = text.replace("ى", "ي").replace("ة", "ه")
    text = re.sub(r"[^\w\s]", " ", text, flags=re.UNICODE)
    return SPACES.sub(" ", text).strip()


def signature(value: str, *, from_end: bool = False, words: int = 3) -> str:
    parts = normalize(value).split()
    return " ".join(parts[-words:] if from_end else parts[:words])


@dataclass(frozen=True)
class Decision:
    accepted: bool
    reasons: tuple[str, ...]
    max_similarity: float


def review_draft(
    *, review_text: str, rating: int, reply: str,
    recent_replies: list[str] | tuple[str, ...] = (),
    allowed_staff_names: list[str] | tuple[str, ...] = (),
    max_similarity: float = 0.80,
) -> Decision:
    """Conservative deterministic checks before *human* approval.

    Rejecting a draft only requests regeneration or manual review. Positive
    results are NOT permission to publish. Staff names are supplied from the
    review/verified operational context by the caller; the gate does not infer.
    """
    errors: list[str] = []
    norm = normalize(reply)
    review = normalize(review_text)
    if rating not in (1, 2, 3, 4, 5):
        errors.append("invalid_rating")
    if not norm or len(reply.strip()) < 25 or len(reply.strip()) > 450:
        errors.append("reply_length_outside_25_450")
    if rating in (1, 2) and EMOJI.search(reply):
        errors.append("emoji_in_negative_reply")
    if rating in (1, 2) and not any(w in norm for w in ("نعتذر", "اعتذر", "اسفين", "نأسف", "ناسف", "ملاحظتك", "تجربتك")):
        errors.append("negative_reply_does_not_acknowledge_issue")
    if not review and any(p in norm for p in ("النظافه", "الاستقبال", "الموظف", "الغرفه", "الهدوء", "الفطور")):
        errors.append("specific_claim_without_review_text")
    if any(normalize(p) in norm for p in UNVERIFIED_CLAIMS):
        errors.append("unverified_corrective_action_claim")
    if len(EMOJI.findall(reply)) > (0 if rating in (1, 2) else 2):
        errors.append("excess_emojis")
    if allowed_staff_names:
        for staff_name in allowed_staff_names:
            if normalize(staff_name) in norm and normalize(staff_name) not in review:
                errors.append("staff_name_not_in_review:" + normalize(staff_name))
    previous = [normalize(s) for s in list(recent_replies)[-50:] if normalize(s)]
    similarity = max((SequenceMatcher(None, norm, p).ratio() for p in previous), default=0.0)
    if norm and norm in previous:
        errors.append("exact_duplicate_reply")
    elif similarity >= max_similarity:
        errors.append("near_duplicate_reply")
    recent10 = previous[-10:]
    if len(norm.split()) >= 3 and sum(signature(p) == signature(norm) for p in recent10) >= 3:
        errors.append("overused_opening")
    if len(norm.split()) >= 6 and sum(signature(p, from_end=True) == signature(norm, from_end=True) for p in recent10) >= 3:
        errors.append("overused_closing")
    return Decision(accepted=not errors, reasons=tuple(dict.fromkeys(errors)), max_similarity=round(similarity, 3))


def select_safe_draft(
    *, review_text: str, rating: int, candidates: list[str],
    recent_replies: list[str], allowed_staff_names: list[str] | tuple[str, ...] = (),
) -> tuple[str | None, list[Decision]]:
    """Choose a qualifying candidate, or require manual review. Never post."""
    checked = [review_draft(review_text=review_text, rating=rating, reply=x,
                            recent_replies=recent_replies, allowed_staff_names=allowed_staff_names)
               for x in candidates]
    valid = [(x, result) for x, result in zip(candidates, checked) if result.accepted]
    valid.sort(key=lambda pair: pair[1].max_similarity)
    return (valid[0][0] if valid else None), checked
