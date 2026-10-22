"""FLOWER V19.1 visual revision: photo-led split-stage on isolated staging.
Only transforms bilingual home and Harmah hero, preserving actual content and links.
"""
from __future__ import annotations
from bs4 import BeautifulSoup

PAGES = {"/", "/en/", "/al-majmaah-harmah/", "/en/al-majmaah-harmah/"}
CSS_PATH = "/assets/css/flower-editorial-v19-1.css"
JS_PATH = "/assets/js/flower-editorial-v19-1.js"
IMAGES = {
 "home": [
  ("/assets/images/al-majmaah-harmah/polished/harmah-twin-polished.webp", "حرمة · المجمعة", "Harmah · Al Majmaah"),
  ("/assets/images/dammam-al-anoud/enhanced/06-enhanced.webp", "العنود · الدمام", "Al Anoud · Dammam"),
  ("/assets/images/dammam-al-salam/enhanced/05-enhanced.webp", "السلام · الدمام", "Al Salam · Dammam"),
  ("/assets/images/al-qaisumah/enhanced/05-enhanced.webp", "القيصومة", "Al Qaisumah")
 ],
 "property": [
  ("/assets/images/al-majmaah-harmah/polished/harmah-twin-polished.webp", "من غرف فلور 4", "FLOWER 4 · Guest room"),
  ("/assets/images/al-majmaah-harmah/enhanced/IMG_1623-enhanced.webp", "تفاصيل من فرع حرمة", "FLOWER 4 · Harmah"),
  ("/assets/images/al-majmaah-harmah/enhanced/IMG_1223-enhanced.webp", "من صور فلور 4 الحقيقية", "FLOWER 4 · Authentic interiors")
 ]
}

def element(soup, tag, text=None, klass=None, **attrs):
    node = soup.new_tag(tag)
    if klass:
        node["class"] = klass.split()
    for key, val in attrs.items():
        node[key.replace("_", "-")] = val
    if text is not None:
        node.string = text
    return node

def apply_editorial(soup: BeautifulSoup, path: str) -> bool:
    if path not in PAGES:
        return False
    hero = soup.select_one("main > section.fx19-hero")
    if not hero or not soup.head or not soup.body:
        raise RuntimeError(f"V19.1 requires current authentic V19 hotel hero: {path}")
    if hero.get("data-fl-editorial") == "v19-1":
        return True
    copy = hero.select_one(".fx19-hero-inner .fx19-hero-copy")
    main_media = hero.select_one(".fx19-hero-media img[src]")
    if not copy or not copy.find("h1") or not hero.select_one(".fx19-hero-actions a"):
        raise RuntimeError(f"Original headline and enquiry actions are required on {path}")
    if not main_media or not main_media["src"].startswith("/assets/images/"):
        raise RuntimeError("A genuine FLOWER cover photo is required")
    if soup.select_one(".flv-scene"):
        raise RuntimeError("Visual layer already exists without its marker")

    lang_en = path.startswith("/en/")
    home = path in ("/", "/en/")
    images = IMAGES["home" if home else "property"]
    scene = element(soup, "div", klass="flv-scene", role="region",
                    aria_label=("Photographs of FLOWER locations" if lang_en
                                else "صور حقيقية من فروع فلور"))
    scene["tabindex"] = "0"
    scene["data-flv-scene"] = "home" if home else "property"

    frame = element(soup, "div", klass="flv-stage")
    for i, (src, ar, en) in enumerate(images):
        slide = element(soup, "figure", klass=("flv-slide is-active" if i == 0 else "flv-slide"))
        slide["data-flv-number"] = str(i+1)
        slide["aria-hidden"] = "false" if i == 0 else "true"
        img = element(soup, "img", klass="flv-photo", src=src,
                      alt=(f"صورة حقيقية من فلور: {ar}" if not lang_en else f"Authentic FLOWER photo: {en}"),
                      decoding="async", width="1440", height="960",
                      loading="eager" if i == 0 else "lazy")
        if i == 0:
            img["fetchpriority"] = "high"
        slide.append(img)
        caption = element(soup, "figcaption", en if lang_en else ar, klass="flv-caption")
        slide.append(caption)
        frame.append(slide)
    scene.append(frame)

    corner = element(soup, "div", klass="flv-corner")
    corner.append(element(soup, "span", "FLOWER / SAUDI ARABIA", klass="flv-corner-brand"))
    corner.append(element(soup, "span", f"01 / {len(images):02d}", klass="flv-counter", aria_live="polite"))
    scene.append(corner)
    preview = element(soup, "div", klass="flv-preview", aria_hidden="true")
    preview.append(element(soup, "img", src=images[1][0], alt="", loading="lazy", decoding="async", width="220", height="280"))
    scene.append(preview)

    navigation = element(soup, "div", klass="flv-navigation")
    caption = element(soup, "p", images[0][2 if lang_en else 1], klass="flv-active-caption", aria_live="polite")
    navigation.append(caption)
    actions = element(soup, "div", klass="flv-arrows")
    for key, glyph, label in [
        ("prev", "‹", "Previous photo" if lang_en else "الصورة السابقة"),
        ("next", "›", "Next photo" if lang_en else "الصورة التالية")
    ]:
        button = element(soup, "button", glyph, klass="flv-arrow", type="button", aria_label=label)
        button["data-flv-move"] = key
        actions.append(button)
    navigation.append(actions)
    scene.append(navigation)

    hero["data-fl-editorial"] = "v19-1"
    hero["class"].append("flv-editorial-hero")
    # Existing photographic background becomes redundant; preserve all
    # original copy, CTAs, navigation and the independent reservation form.
    media = hero.select_one(":scope > .fx19-hero-media")
    if media:
        media.decompose()
    inset = hero.select_one(".fx19-hero-inset")
    if inset:
        inset.decompose()
    old_index = hero.select_one(":scope > .fx19-hero-index")
    if old_index:
        old_index.decompose()
    hero.append(scene)
    if not soup.head.find("link", href=CSS_PATH):
        soup.head.append(element(soup, "link", rel="stylesheet", href=CSS_PATH))
    if not soup.body.find("script", src=JS_PATH):
        soup.body.append(element(soup, "script", src=JS_PATH, defer=""))
    return True
