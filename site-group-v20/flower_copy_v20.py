"""FLOWER V20 copy layer: hospitality-led wording for AR/EN pages.

Only exact, whole text nodes are rewritten. Facts (phones, addresses, times,
links, ratings and policies' meaning) are never changed here.
"""
from __future__ import annotations
from bs4 import BeautifulSoup, NavigableString

AR_LEDE = "اكتشف صور الوحدات الحقيقية والتجهيزات المتاحة، واستفسر مباشرة عن تفاصيل إقامتك."

REPLACE = {
 # Branch names instead of numbers.
 "فلور 1  ·  العنود": "فلور العنود", "فلور 2  ·  السلام": "فلور السلام",
 "فلور 3  ·  القيصومة": "فلور القيصومة", "فلور 4  ·  حرمة": "فلور حرمة",
 "فلور 1": "فلور العنود", "فلور 2": "فلور السلام", "فلور 3": "فلور القيصومة", "فلور 4": "فلور حرمة",
 "FLOWER 01  ·  Al Anoud": "FLOWER Al Anoud", "FLOWER 02  ·  Al Salam": "FLOWER Al Salam",
 "FLOWER 03  ·  Al Qaisumah": "FLOWER Al Qaisumah", "FLOWER 04  ·  Harmah": "FLOWER Harmah",
 "FLOWER 01": "FLOWER Al Anoud", "FLOWER 02": "FLOWER Al Salam",
 "FLOWER 03": "FLOWER Al Qaisumah", "FLOWER 04": "FLOWER Harmah",
 # Hero ledes.
 "أربع وجهات للإقامة في الدمام والقيصومة والمجمعة. صور حقيقية لشققنا، وتجربة تبدأ من اختيار المكان الذي يناسبك.":
  "أربع وجهات في الدمام والقيصومة والمجمعة، تجمع راحة الشقق المخدومة بأناقة الضيافة الفندقية.",
 f"شقق مخدومة في الدمام. {AR_LEDE}":
  "شقق مخدومة في قلب الدمام، بضيافة على مدار الساعة وتفاصيل تجمع دفء البيت بأناقة الفندق.",
 f"شقق مخدومة في القيصومة. {AR_LEDE}":
  "شقق مخدومة على طريق الملك عبدالعزيز في القيصومة، بضيافة على مدار الساعة وراحة تليق بكل رحلة.",
 f"شقق مخدومة في المجمعة. {AR_LEDE}":
  "شقق مخدومة في حرمة بالمجمعة، بضيافة على مدار الساعة وتفاصيل تمنح إقامتك طابعًا خاصًا.",
 "Four distinctive locations in Dammam, Al Qaisumah and Al Majmaah. Discover our actual apartments and plan your stay with confidence.":
  "Four distinctive addresses in Dammam, Al Qaisumah and Al Majmaah, pairing serviced-apartment comfort with hotel-style hospitality.",
 "Serviced apartments in Dammam. Explore actual rooms, compare unit types, and enquire directly about your preferred stay.":
  "Serviced apartments in the heart of Dammam, with round-the-clock hospitality, the warmth of home and the polish of a hotel.",
 "Serviced apartments in Al Qaisumah. Explore actual rooms, compare unit types, and enquire directly about your preferred stay.":
  "Serviced apartments on King Abdulaziz Road in Al Qaisumah, with round-the-clock hospitality for every journey.",
 "Serviced apartments in Al Majmaah. Explore actual rooms, compare unit types, and enquire directly about your preferred stay.":
  "Serviced apartments in Harmah, Al Majmaah, with round-the-clock hospitality and thoughtful details for a stay of your own.",
 # Confident tone instead of "real photos" reassurance.
 "صور حقيقية": "ضيافة 24 ساعة", "REAL PHOTOGRAPHY": "24-HOUR HOSPITALITY",
 "مساحات من الواقع، وصور من فروعنا الفعلية، لتختار إقامتك بثقة.":
  "مساحات صُمّمت للراحة، وتفاصيل تمنح كل إقامة طابعها الخاص.",
 "Real apartments, carefully presented — discover more before making your enquiry.":
  "Spaces designed for comfort, with details that give every stay its own character.",
 "خيار عملي لإقامة مريحة مع التجهيزات المتوفرة في الفرع.": "غرفة أنيقة بتجهيزات متكاملة لإقامة مريحة.",
 "خدمات الاستقبال والاتصال والمرافق المتاحة في فروع فلور.": "ضيافة على مدار الساعة ومرافق مختارة في جميع فروع فلور.",
 "خدمات الفرع التي تسهّل إقامتك، بشكل منفصل عن التجهيزات الموجودة داخل كل وحدة.": "ضيافة متكاملة ترافقك طوال إقامتك.",
 "Branch services that make your stay easier, separate from the amenities included inside each unit.":
  "Complete hospitality throughout your stay.",
 # Enquiry flow: WhatsApp or Booking.com, confirmed by the team.
 "اختر الفرع والوحدة وتواريخ الإقامة والضيوف، ثم انتقل لقناة الحجز المتاحة. الاستفسار ليس تأكيدًا فوريًا للحجز.":
  "اختر الفرع والوحدة وتواريخ إقامتك، ثم أرسل طلبك عبر واتساب أو Booking.com ليؤكد لك فريقنا التوفر.",
 "Choose a property, your dates and guests. We will connect you with the existing reservation channels; this is an enquiry, not an instant confirmation.":
  "Choose your property, dates and guests, then send your request via WhatsApp or Booking.com and our team will confirm availability.",
 # FAQ answers.
 "نعم، الواي فاي المجاني مؤكد في هذا الفرع.": "نعم، الإنترنت اللاسلكي مجاني لجميع الضيوف.",
 "نعم، المواقف متوفرة بحسب البيانات المعتمدة للفرع.": "نعم، تتوفر مواقف سيارات للضيوف.",
 "Yes. Free Wi-Fi is confirmed for this branch.": "Yes. Complimentary Wi-Fi is available to all guests.",
 "Yes. Parking is confirmed for this branch.": "Yes. Guest parking is available.",
 # Approved refund wording (same policy, softer presentation).
 "لا يوجد استرداد": "الحجز غير قابل للاسترداد — تواصل معنا قبل الحجز لتأكيد التفاصيل",
 "No refund": "Non-refundable — contact us before booking to confirm details",
 # Gallery labels on the home page.
 "العنود · عرض الفرع": "فلور العنود", "السلام · عرض الفرع": "فلور السلام",
 "القيصومة · عرض الفرع": "فلور القيصومة", "حرمة · عرض الفرع": "فلور حرمة",
 "Al Anoud · View branch": "FLOWER Al Anoud", "Al Salam · View branch": "FLOWER Al Salam",
 "Al Qaisumah · View branch": "FLOWER Al Qaisumah", "Harmah · View branch": "FLOWER Harmah",
 # Harmah story and captions.
 "من غرف فلور 4": "من غرف فلور حرمة", "من صور فلور 4 الحقيقية": "لمسات من فلور حرمة",
 "اكتشف فلور 4 في حرمة من خلال صور حقيقية لغرفنا ومساحات المعيشة.":
  "اكتشف فلور حرمة: غرف هادئة ومساحات معيشة صُمّمت لراحتك.",
 "تفاصيل تبقى معاك": "تفاصيل تبقى معك", "صور حقيقية من فرع حرمة، كما هي.": "لمسات مدروسة في كل زاوية من فلور حرمة.",
 "FLOWER 4 · Guest room": "FLOWER Harmah · Guest room", "FLOWER 4 · Harmah": "FLOWER Harmah · Details",
 "FLOWER 4 · Authentic interiors": "FLOWER Harmah · Interiors",
 "A closer look at FLOWER 4 in Harmah, through photographs of our actual property.":
  "Discover FLOWER Harmah: calm rooms and living spaces designed for your comfort.",
 "An authentic look at our Harmah interiors.": "Thoughtful touches in every corner of FLOWER Harmah.",
 "FLOWER in Al Salam, Dammam, at the verified 8202 18th Street address. 24-hour reception, free Wi-Fi and parking.":
  "FLOWER in Al Salam, Dammam, at 8202 18th Street. 24-hour reception, free Wi-Fi and parking.",
 "FLOWER in Harmah, Al Majmaah, at the verified LMPA9275, 9275 2306 address. 24-hour reception, free Wi-Fi and parking.":
  "FLOWER in Harmah, Al Majmaah, at LMPA9275, 9275 2306. 24-hour reception, free Wi-Fi and parking.",
}
REMOVE = {"لا نعرض أزمنة وصول لأنها تختلف حسب حركة المرور.",
          "No travel times are shown because they vary with traffic."}

def apply_copy(soup: BeautifulSoup) -> dict[str, int]:
    """Rewrite matching visible text nodes; return how often each key was hit."""
    hits: dict[str, int] = {}
    for node in list(soup.body.find_all(string=True)):
        if node.parent is None or node.parent.name in ("script", "style", "option"):
            continue
        text = node.strip()
        if text in REMOVE and node.parent.get_text(strip=True) == text:
            node.parent.decompose()
            hits[text] = hits.get(text, 0) + 1
        elif text in REPLACE:
            lead = node[:len(node) - len(node.lstrip())]
            tail = node[len(node.rstrip()):]
            node.replace_with(NavigableString(lead + REPLACE[text] + tail))
            hits[text] = hits.get(text, 0) + 1
    return hits
