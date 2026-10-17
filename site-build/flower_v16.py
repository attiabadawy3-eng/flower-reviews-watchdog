"""V16 staged immersive FLOWER heroes, preserving the existing hero for A/B."""
from bs4 import BeautifulSoup


def install_hero(soup, url_path, lang):
    en = lang == "en"
    prefix = "/en" if en else ""
    if url_path in ("/", "/en/"):
        original = soup.select_one("section.v13-group-hero")
        if original is None:
            raise RuntimeError("Source homepage hero not found")
        branches = [
            ("dammam-al-anoud", "DAMMAM", "Al Anoud" if en else "العنود",
             "/assets/images/dammam-al-anoud/enhanced/06-enhanced.webp"),
            ("dammam-al-salam", "DAMMAM", "Al Salam" if en else "السلام",
             "/assets/images/dammam-al-salam/enhanced/05-enhanced.webp"),
            ("al-qaisumah", "AL QAISUMAH", "Al Qaisumah" if en else "القيصومة",
             "/assets/images/al-qaisumah/enhanced/05-enhanced.webp"),
            ("al-majmaah-harmah", "AL MAJMAAH", "Harmah" if en else "حرمة",
             "/assets/images/al-majmaah-harmah/enhanced/IMG_1362-enhanced.webp"),
        ]
        tiles = "".join(
            f'<a class="v16-branch-tile" href="{prefix}/{slug}/">'
            f'<img src="{photo}" alt="{label}" loading="lazy" decoding="async">'
            f'<small>{city}</small><strong>{label}</strong>'
            f'<span class="v16-arrow" aria-hidden="true">↗</span></a>'
            for slug, city, label, photo in branches
        )
        overline = "FLOWER | SERVICED APARTMENTS" if en else "فلور | للشقق المخدومة"
        main = "FLOWER Serviced Apartments" if en else "فلور للشقق المخدومة"
        second = "A better stay begins here" if en else "تفاصيل تليق بإقامتك"
        lead = (
            "Four serviced-apartment locations in Dammam, Al Qaisumah and Al Majmaah. "
            "Explore real rooms and enquire directly with your chosen branch."
            if en else
            "أربع وجهات للإقامة في الدمام والقيصومة والمجمعة. استكشف صور وحدات فلور الحقيقية وتواصل مباشرة مع الفرع المناسب لك."
        )
        cta1 = "Explore our locations" if en else "اكتشف فروع فلور"
        cta2 = "Enquire about availability" if en else "استفسر عن التوفر"
        trust = (
            "4 locations <span></span> Direct branch contact <span></span> Real photos"
            if en else
            "4 فروع <span></span> تواصل مباشر <span></span> صور حقيقية"
        )
        markup = f"""<section class="flower-v16-home-hero" aria-label="{overline}">
        <img class="flower-v16-hero-bg"
             src="/assets/images/dammam-al-anoud/enhanced/06-enhanced.webp"
             alt="" fetchpriority="high" decoding="async">
        <div class="v16-content">
          <div class="v16-overline">{overline}</div>
          <h1>{main}<span class="v16-headline-sub">{second}</span></h1>
          <p class="v16-hero-intro">{lead}</p>
          <div class="v16-hero-actions">
            <a class="v16-primary" href="#branches">{cta1}</a>
            <a class="v16-secondary" href="#booking">{cta2}</a>
          </div>
          <div class="v16-trustline">{trust}</div>
        </div>
        <nav class="v16-branch-rail" aria-label="{'FLOWER locations' if en else 'فروع فلور'}">{tiles}</nav>
        </section>"""
    elif url_path in ("/al-majmaah-harmah/", "/en/al-majmaah-harmah/"):
        original = soup.select_one("section.v10-property-hero")
        if original is None:
            raise RuntimeError("Source Flower 4 hero not found")
        overline = "FLOWER STAY / 04" if en else "فلور | إقامة في حرمة"
        label = "FLOWER 4 · Harmah" if en else "فلور 4 · حرمة"
        second = "Serviced apartments in Al Majmaah" if en else "إقامتك في المجمعة بصورة مختلفة"
        lead = (
            "Private room and apartment options, with direct access to the branch team. "
            "Browse our real accommodation photos before enquiring."
            if en else
            "غرفة وحمام، غرفة وصالة، وغرفتان وصالة. تصفّح صور فلور الحقيقية ثم استفسر مباشرة عن الوحدة المناسبة لإقامتك."
        )
        cta1 = "Enquire now" if en else "استفسر عن التوفر"
        cta2 = "See room photos" if en else "شاهد صور الوحدات"
        google = "Google reviews" if en else "مراجعات Google"
        home = "Home" if en else "الرئيسية"
        photos = [
            ("/assets/images/al-majmaah-harmah/enhanced/IMG_1362-enhanced.webp",
             "FLOWER 4" if en else "فلور 4"),
            ("/assets/images/al-majmaah-harmah/enhanced/IMG_1280-enhanced.webp",
             "Rooms" if en else "الغرف"),
            ("/assets/images/al-majmaah-harmah/enhanced/IMG_1223-enhanced.webp",
             "Living space" if en else "الصالات"),
        ]
        tiles = "".join(
            f'<a class="v16-photo-thumb" href="#gallery">'
            f'<img src="{photo}" alt="{caption}" loading="lazy" decoding="async">'
            f'<span>{caption}</span></a>'
            for photo, caption in photos
        )
        markup = f"""<section class="flower-v16-property-hero" aria-label="{label}">
        <img class="flower-v16-hero-bg"
             src="/assets/images/al-majmaah-harmah/polished/harmah-twin-polished.webp"
             alt="" fetchpriority="high" decoding="async">
        <div class="v16-content">
          <div class="v16-breadcrumb"><a href="{prefix}/">{home}</a> &lsaquo; {label}</div>
          <div class="v16-overline">{overline}</div>
          <h1>{label}<span class="v16-headline-sub">{second}</span></h1>
          <p class="v16-branch-intro">{lead}</p>
          <div class="v16-property-proof">
            <a class="v16-review-link"
               href="https://www.google.com/maps/search/?api=1&amp;query=FLOWER&amp;query_place_id=ChIJYVDYYgDJKj4RayfDdSuhdF8"
               target="_blank" rel="noopener noreferrer">
              ★ <b data-google-rating="flower-4">4.6</b> / 5 ·
              <b data-google-review-count="flower-4">142</b> {google}
            </a>
          </div>
          <div class="v16-hero-actions">
            <a class="v16-primary" href="#booking">{cta1}</a>
            <a class="v16-secondary" href="#gallery">{cta2}</a>
          </div>
        </div>
        <div class="v16-property-hero-thumbs">{tiles}</div>
        </section>"""
    else:
        return
    fragment = BeautifulSoup(markup, "html.parser").section
    original.insert_before(fragment)
