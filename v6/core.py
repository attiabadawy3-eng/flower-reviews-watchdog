"""Domain logic. No network access or credentials here."""
from dataclasses import dataclass
from typing import Any
import base64
import json
import re


class InvalidNotification(ValueError):
    pass


@dataclass(frozen=True)
class ReviewEvent:
    review_name: str
    location_name: str
    event_type: str
    message_id: str


REVIEW_PATTERN = re.compile(r'^accounts/\d+/locations/\d+/reviews/[A-Za-z0-9_-]+$')
LOCATION_PATTERN = re.compile(r'^accounts/\d+/locations/\d+$')


def parse_pubsub(envelope: dict[str, Any], location_aliases: dict[str, str] | None = None) -> ReviewEvent | None:
    """Accept actual Pub/Sub envelope and both documented naming variants.

    No reviewer identity, rating or comment is inferred from the notification.
    Those must be fetched from the official Reviews API.
    """
    if not isinstance(envelope, dict):
        raise InvalidNotification('invalid Pub/Sub envelope')
    message = envelope.get('message')
    if not isinstance(message, dict) or not isinstance(message.get('data'), str):
        raise InvalidNotification('missing Pub/Sub message.data')
    try:
        data = json.loads(base64.b64decode(message['data'], validate=True))
    except (ValueError, TypeError, UnicodeError) as exc:
        raise InvalidNotification('invalid notification encoding') from exc
    if not isinstance(data, dict):
        raise InvalidNotification('invalid notification JSON')
    typ = str(data.get('type') or data.get('notificationType') or '').upper()
    if typ not in ('NEW_REVIEW', 'UPDATED_REVIEW'):
        return None
    review = data.get('reviewName') or data.get('review_name') or data.get('review')
    location = data.get('locationName') or data.get('location_name') or data.get('location')
    if isinstance(review, dict):
        review = review.get('name')
    if isinstance(location, dict):
        location = location.get('name')
    review, location = str(review or ''), str(location or '')
    if location.startswith('locations/'):
        location = (location_aliases or {}).get(location, location)
    if review.startswith('locations/') and location.startswith('accounts/'):
        # Location-scoped review names must retain parent account.
        review = location.split('/locations/')[0] + '/' + review
    if not REVIEW_PATTERN.fullmatch(review):
        raise InvalidNotification('notification does not contain a valid review resource')
    if not location:
        location = review.rsplit('/reviews/', 1)[0]
    if not LOCATION_PATTERN.fullmatch(location) or not review.startswith(location + '/reviews/'):
        raise InvalidNotification('mismatched location and review resources')
    return ReviewEvent(review, location, typ, str(message.get('messageId') or message.get('message_id') or ''))


def as_star_count(value: str | int | None) -> int:
    mapping = {'ONE': 1, 'TWO': 2, 'THREE': 3, 'FOUR': 4, 'FIVE': 5}
    if isinstance(value, int):
        return value if 1 <= value <= 5 else 0
    return mapping.get(str(value or '').upper(), 0)


def needs_owner_review(stars: int, comment: str, minimum_autopost_stars: int) -> bool:
    # Owner may allow replies at all star levels, but higher-risk complaints
    # remain subject to extra review to avoid admitting unverified wrongdoing.
    high_risk = ('تحرش', 'اعتداء', 'سرقة', 'نصب', 'احتيال', 'تسمم', 'عنصرية', 'خصوصية',
                 'sexual assault', 'theft', 'fraud', 'discrimination', 'poisoning')
    return stars < minimum_autopost_stars or any(word in (comment or '').lower() for word in high_risk)


def reply_prompt(*, branch: str, stars: int, review_text: str, previous_replies: list[str]) -> str:
    """Generate a human-sounding Saudi hospitality reply without making up facts."""
    return '\n'.join([
        'أنت مسؤول علاقات النزلاء في مجموعة فلور للشقق المخدومة في السعودية.',
        'اكتب ردًا عامًا واحدًا للنشر على تقييم Google لهذا الفرع، بأسلوب سعودي مهني طبيعي ومختصر،',
        'كأن موظف استقبال سعودي ذو خبرة كتبه بعناية. لا تذكر أنك روبوت ولا تدّعِ اسم شخص أو تواصلًا لم يحدث.',
        'اقرأ المعنى الفعلي للتعليق؛ لا تكرر كلمات عامة ولا تنسخ تقييم النزيل حرفيًا.',
        'للشكر: 1–3 جمل ودودة متنوعة. للشكوى: اعتذار عن التجربة دون اعتراف بواقعة لم تُثبت،',
        'تفهّم محدد لملاحظة العميل، ودعوة للتواصل مع الإدارة عبر القنوات الرسمية عند الحاجة.',
        'الشكوى تظل رواية العميل لحين التحقق. لا تقر بأن المكيف تعطل أو تأخر الموظف ولا تنسب للإدارة خطأ مؤكدًا.',
        'في الشكوى قل «نأسف إن تجربتك ما كانت بالمستوى المطلوب» أو «نتفهم انزعاجك من موضوع التكييف» لا «مشكلة التكييف تسببت في الإزعاج» أو «تأخرنا في الاستجابة».',
        'لا تعد باسترجاع أموال أو خصومات أو إجراءات داخلية لم تُنفذ، ولا تكشف بيانات شخصية.',
        'لا تستخدم مبالغة دعائية أو رموزًا تعبيرية أو وسومًا أو توقيعًا ثابتًا.',
        'لا تستخدم اللهجة المصرية أو الفصحى المتكلّفة؛ الصياغة السعودية طبيعية ومحترمة.',
        'اسم المنشأة في نص الرد هو فلور فقط؛ لا تذكر كلمة الخليجية ولا الاسم القانوني الطويل ولا رقم الفرع.',
        'استخدم أسلوبًا سعوديًا طبيعيًا مثل حياك الله أو شاكرين لك عند ملاءمة السياق، ولا تجمع عدة عبارات ترحيب متكررة.',
        'اجعل الرد مرتبطًا بتعليق العميل تحديدًا: للنظافة اشكر على ملاحظته عن النظافة، وللاستقبال اذكر التعامل الطيب دون مبالغة.',
        'امنع التركيبات المصطنعة أو المتناقضة مثل «تنال إعراضك» و«ترقى لرضاك»، ولا تكتب «قدمنا تجربة تنال...»؛ قل ببساطة «يسعدنا إن إقامتك كانت مريحة».',
        'عدد النجوم موجود لفهم طبيعة التقييم فقط؛ لا تذكر النجوم أو عددها أو تصفها في الرد.',
        f'الفرع: {branch}',
        f'النجوم: {stars}',
        f'نص التقييم: {review_text.strip() if review_text.strip() else "تقييم بالنجوم فقط دون نص"}',
        'تجنب العبارات المتكررة من هذه الردود المنشورة مؤخرًا: ' + json.dumps(previous_replies[-6:], ensure_ascii=False),
        'أرجع نص الرد فقط بلا عنوان أو علامات اقتباس، بطول لا يتجاوز 350 حرفًا.'
    ])


def validate_reply(text: str) -> str:
    text = re.sub(r'\s+', ' ', str(text or '')).strip().strip('"“”')
    if not (16 <= len(text) <= 350):
        raise ValueError('reply length outside approved range')
    if any(x in text.lower() for x in ('كذكاء اصطناعي', 'انا روبوت', 'as an ai')):
        raise ValueError('generated reply reveals model instructions')
    if re.search(r'(?<!\d)(?:05\d{8}|\+966\d{9})(?!\d)', text):
        raise ValueError('unapproved phone number in generated reply')
    if re.search(r'الخليجي(?:ة|ه)?|الخليجية|al[-_ ]?khaleej|gulf serviced', text, re.IGNORECASE):
        raise ValueError('non-approved property name in generated reply')
    if re.search(r'نجوم|نجمة|نجمتين|نجمات|[★☆⭐🌟]', text):
        raise ValueError('star rating reference in generated reply')
    if re.search(r'فلور\s*[0-9٠-٩]', text):
        raise ValueError('non-approved branch number in public reply')
    if re.search(r'[اإأ]عراض(?:ك|كم|هم|ه|ها)?', text):
        raise ValueError('unintended negative sentiment or mistranslation')
    if re.search(r'ترق[ىيا] لرضاك|قد[ّ]?منا تجربة تنال', text):
        raise ValueError('unnatural hospitality sales script')
    if re.search(r'(?:تسببت|تسبب|تسبّب)(?:\s+فيه|\s+لك|\s+لكم)?\s+(?:مشكلة|عطل|خلل)', text):
        raise ValueError('unverified causal admission in customer complaint')
    if re.search(r'تأخرنا\s+(?:في|عن)\s+(?:الرد|الاستجابة|التجاوب)', text):
        raise ValueError('unverified admission of staff delay')
    return text
