"""FLOWER V17.3 editorial refinement — Apple-inspired presentation, actual hotel media.

Private staging candidate. Pure BeautifulSoup pass on existing V17.2 DOM.
"""
from __future__ import annotations
from bs4 import BeautifulSoup

SCENES = {
 "ar": [
   ("إقامة تبدأ بالراحة", "غرف نوم حقيقية من فلور 4."),
   ("مساحة للراحة واللقاء", "صالة معيشة في فرع حرمة."),
   ("تفاصيل تكمّل يومك", "استكشف الخيارات ثم استفسر عن التوفر."),
 ],
 "en": [
   ("A restful welcome", "Real guest rooms at FLOWER 4."),
   ("A place to unwind", "A living space in Harmah."),
   ("Every detail matters", "Explore the stay, then enquire."),
 ],
}


def apply_premium(soup: BeautifulSoup, path: str) -> None:
    if path not in ("/al-majmaah-harmah/", "/en/al-majmaah-harmah/"):
        return
    if not soup.html or not soup.head or not soup.body:
        raise RuntimeError("missing Flower document structure")
    is_en=path.startswith("/en/")
    lang="en" if is_en else "ar"
    root=soup.select_one("#flower-cinema")
    hero=soup.select_one("section.flower-v16-property-hero")
    if not root or not hero or not soup.select_one(".flower-v16-hero-bg"):
        raise RuntimeError(f"V17.2 base unexpectedly missing for {path}")
    # Short, product-focused story; only authentic hotel photography is reused.
    intro=root.select_one(".flower-cinema-intro")
    if intro:
        intro_h2=intro.find("h2")
        intro_p=intro.find_all("p")
        if intro_h2:
            intro_h2.string=("Explore FLOWER 4." if is_en else "تجربة فلور 4، عن قرب.")
        if len(intro_p)>=2:
            intro_p[-1].string=("Real spaces. Three moments from your stay." if is_en else "ثلاث لقطات حقيقية، تحكي تفاصيل إقامتك.")
    for index,fig in enumerate(root.select("[data-cinema-scene]")):
        h3=fig.select_one(".flower-cinema-copy h3")
        p=fig.select_one(".flower-cinema-copy p")
        if h3:h3.string=SCENES[lang][index][0]
        if p:p.string=SCENES[lang][index][1]
    # Keep a single inquiry CTA in the cinematic presentation; show after chapter 3
    # when motion runs and immediately in static/reduced-motion fallback.
    cta=root.select_one(".flower-cinema-link")
    if cta:
        cta.string="استفسر عن التوفر" if not is_en else "Check availability"
    root["data-flower-story"]="premium"
    # Preserve the canonical property hero photo, single H1 and all real booking links.
    img=hero.select_one("img.flower-v16-hero-bg")
    if img:
        img["loading"]="eager"
        img["fetchpriority"]="high"
        img["decoding"]="async"
    stylesheet="/assets/css/flower-apple-premium-v17-3.css"
    if not soup.head.find("link",href=stylesheet):
        soup.head.append(soup.new_tag("link",rel="stylesheet",href=stylesheet))
