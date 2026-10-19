"""FLOWER cinematic property reveal — three verified photos from the live Flower 4 gallery.

Only included in the dedicated apple-cinematic staging build.
Retains semantic, fully visible fallback in case JavaScript is off.
"""
from __future__ import annotations

from bs4 import BeautifulSoup

SCENES = [
    {
        "photo": "/assets/images/al-majmaah-harmah/polished/harmah-twin-polished.webp",
        "alt_ar": "غرفة نوم بسريرين في فلور 4 – حرمة",
        "alt_en": "Real FLOWER 4 Harmah guest room with twin beds",
        "ar": ("01 / 03", "إقامة تبدأ بالراحة", "غرف نوم من فلور 4، كما تبدو في الصور الأصلية."),
        "en": ("01 / 03", "A restful place to arrive", "Real guest room photography from FLOWER 4 in Harmah."),
    },
    {
        "photo": "/assets/images/al-majmaah-harmah/enhanced/IMG_1362-enhanced.webp",
        "alt_ar": "صالة معيشة وطاولة طعام في فلور 4 – حرمة",
        "alt_en": "Real FLOWER 4 Harmah living area with dining table",
        "ar": ("02 / 03", "مساحات للحظات أجمل", "لمحة من إحدى صالات المعيشة في فرع حرمة."),
        "en": ("02 / 03", "Room to make yourself at home", "A look at one of the living areas in Harmah."),
    },
    {
        "photo": "/assets/images/al-majmaah-harmah/enhanced/IMG_1623-enhanced.webp",
        "alt_ar": "غرفة بسرير مزدوج في فلور 4 – حرمة",
        "alt_en": "Real FLOWER 4 Harmah room with double bed",
        "ar": ("03 / 03", "تفاصيل تُكمل إقامتك", "صور حقيقية من فلور 4، وخيارات الإقامة يوضحها الفرع عند الاستفسار."),
        "en": ("03 / 03", "Comfort in the details", "Real imagery from FLOWER 4. Confirm available unit features when enquiring."),
    },
]

def install_cinema(soup: BeautifulSoup, path: str) -> None:
    if path not in ("/al-majmaah-harmah/", "/en/al-majmaah-harmah/"):
        return
    if not soup.html or not soup.head or not soup.body:
        raise ValueError("missing HTML scaffolding")
    if soup.select_one("#flower-cinema"):
        return
    hero = soup.select_one("section.flower-v16-property-hero")
    if not hero:
        raise RuntimeError("flower V17 hero missing; cinematic insert would be unsafe")
    is_en = path.startswith("/en/")
    localized = "en" if is_en else "ar"
    section = soup.new_tag("section", id="flower-cinema")
    section["class"] = ["flower-cinema"]
    section["aria-label"] = ("Explore real FLOWER 4 photographs" if is_en else "جولة بصرية في صور فلور 4 الأصلية")
    intro = soup.new_tag("div")
    intro["class"] = ["flower-cinema-intro"]
    eyebrow = soup.new_tag("p")
    eyebrow["class"] = ["flower-cinema-eyebrow"]
    eyebrow.string = "FLOWER 4 · HARMAH"
    intro.append(eyebrow)
    h2=soup.new_tag("h2")
    h2.string=("Discover the stay, one scene at a time." if is_en else "اكتشف الإقامة، مشهدًا بعد مشهد.")
    intro.append(h2)
    p=soup.new_tag("p")
    p.string=("Three original photographs from our Harmah property. Scroll to explore the spaces."
              if is_en else "ثلاث صور أصلية من فرع حرمة. مرّر لاستكشاف تفاصيل المكان.")
    intro.append(p)
    section.append(intro)
    track = soup.new_tag("div")
    track["class"] = ["flower-cinema-track"]
    track["data-cinema-track"] = ""
    stage = soup.new_tag("div")
    stage["class"] = ["flower-cinema-stage"]
    stage["data-cinema-stage"] = ""
    frame=soup.new_tag("div")
    frame["class"]=["flower-cinema-frame"]
    frame["data-cinema-frame"]=""
    for i, scene in enumerate(SCENES):
        fig=soup.new_tag("figure")
        fig["class"]=["flower-cinema-scene"]
        fig["data-cinema-scene"]=str(i)
        img=soup.new_tag("img")
        img["src"]=scene["photo"]
        img["alt"]=scene["alt_en" if is_en else "alt_ar"]
        img["loading"]="lazy"
        img["decoding"]="async"
        img["width"]="1280"
        img["height"]="840"
        fig.append(img)
        text=soup.new_tag("figcaption")
        text["class"]=["flower-cinema-copy"]
        k=soup.new_tag("span")
        k["class"]=["flower-cinema-index"]
        k.string=scene[localized][0]
        text.append(k)
        title=soup.new_tag("h3")
        title.string=scene[localized][1]
        text.append(title)
        details=soup.new_tag("p")
        details.string=scene[localized][2]
        text.append(details)
        fig.append(text)
        frame.append(fig)
    stage.append(frame)
    footer=soup.new_tag("div")
    footer["class"]=["flower-cinema-controls"]
    progress=soup.new_tag("div")
    progress["class"]=["flower-cinema-progress"]
    progress["aria-hidden"]="true"
    for i in range(3):
        seg=soup.new_tag("span")
        seg["data-cinema-segment"]=str(i)
        progress.append(seg)
    footer.append(progress)
    a=soup.new_tag("a", href="#booking")
    a["class"]=["flower-cinema-link"]
    a.string="استفسر عن التوفر" if not is_en else "Enquire about availability"
    footer.append(a)
    stage.append(footer)
    track.append(stage)
    section.append(track)
    hero.insert_after(section)
    for href in ("/assets/css/flower-apple-cinema.css",):
        if not soup.head.find("link", href=href):
            soup.head.append(soup.new_tag("link",rel="stylesheet",href=href))
    if not soup.body.find("script",src="/assets/js/flower-apple-cinema.js"):
        soup.body.append(soup.new_tag("script",src="/assets/js/flower-apple-cinema.js",defer=True))
