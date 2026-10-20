"""FLOWER Signature V18 • photo-led, original-property luxury editorial presentation.

An isolated staging-only successor to the rejected V17.4 experiment. Removes
the experimental SVG completely and replaces the scrolling image crossfade with
high-quality, static-first hospitality storytelling using original FLOWER photos.
"""
from __future__ import annotations
from bs4 import BeautifulSoup
from flower_apple_cinema import SCENES

PATHS={"/al-majmaah-harmah/","/en/al-majmaah-harmah/"}

def el(soup,tag,text=None,css=None,**attrs):
    node=soup.new_tag(tag)
    if css: node["class"]=css.split()
    for name,value in attrs.items():
        node[name.replace("_","-")]=value
    if text is not None: node.string=text
    return node

def apply_signature(soup:BeautifulSoup,path:str)->None:
    if path not in PATHS:return
    if not soup.html or not soup.head or not soup.body:
        raise RuntimeError("Invalid FLOWER HTML")
    en=path.startswith("/en/")
    # Checkout time is 2 PM. Avoid implying every booking lasts exactly one night.
    policy = soup.select_one(".v7-policy-list")
    if policy is None:
        raise RuntimeError("Missing existing check-out policy")
    for entry in policy.find_all("div", recursive=False):
        title = entry.find("span")
        value = entry.find("strong")
        if not title or not value:
            continue
        label = title.get_text(" ", strip=True).casefold()
        if label in ("وقت الخروج", "check-out"):
            original = value.get_text(" ", strip=True)
            expected = "2:00 PM the following day" if en else "2:00 م من اليوم التالي"
            if original != expected:
                raise RuntimeError(f"Unexpected check-out text: {original}")
            value.string = "2:00 PM" if en else "2:00 م"
            break
    else:
        raise RuntimeError("Check-out field not found")
    soup.html["data-flower-signature"]="v18"
    hero=soup.select_one("section.flower-v16-property-hero")
    mainimg=hero.select_one("img.flower-v16-hero-bg") if hero else None
    content=hero.select_one(".v16-content") if hero else None
    if not hero or not mainimg or not content:
        raise RuntimeError("Original hotel hero/photo is required")
    if not mainimg.get("src","").startswith("/assets/images/al-majmaah-harmah/"):
        raise RuntimeError("Hero must use original FLOWER 4 photography")
    # The photo remains the original, but is intentionally composed as a true cover.
    media=el(soup,"div",css="lx-media")
    mainimg.wrap(media)
    media.append(el(soup,"div","FLOWER 04  /  HARMAH" if en else "فلور 04  /  حرمة",css="lx-image-signature"))
    hero["class"].append("lx-hero")
    content["class"].append("lx-hero-content")
    label=el(soup,"p","FLOWER · SERVICED APARTMENTS" if en else "FLOWER · شقق مخدومة",css="lx-eyebrow")
    content.insert(0,label)
    # Existing hero thumbnails duplicate the gallery; gallery below remains untouched.
    for thumbs in hero.select(".v16-property-hero-thumbs"):thumbs.decompose()
    # Older V17.2 cinema becomes an entirely different editorial sequence.
    for old in soup.select("#flower-cinema,#flower-interactive"):
        old.decompose()
    for script in list(soup.body.find_all("script")):
        if script.get("src") in ("/assets/js/flower-apple-cinema.js","/assets/js/flower-interactive-v17-4.js"):
            script.decompose()
    for link in list(soup.head.find_all("link")):
        if link.get("href") in ("/assets/css/flower-apple-cinema.css",
                                "/assets/css/flower-interactive-v17-4.css"):
            link.decompose()
    # Curated story based exclusively on the three already verified hotel photos.
    story=el(soup,"section",css="lx-story",id="flower-signature")
    story["aria-label"]="A closer look at original Flower 4 rooms" if en else "اكتشف مساحات فلور 4 من الصور الحقيقية"
    opening=el(soup,"div",css="lx-story-heading")
    opening.append(el(soup,"span","THE FLOWER EXPERIENCE" if en else "تجربة فلور",css="lx-overline"))
    opening.append(el(soup,"h2","Every stay has its own atmosphere." if en else "لكل إقامة تفاصيلها."))
    opening.append(el(soup,"p","A closer look at FLOWER 4 in Harmah, through photographs of our actual property."
                     if en else "اكتشف فلور 4 في حرمة من خلال صور حقيقية لغرفنا ومساحات المعيشة."))
    story.append(opening)
    titles=[
      ("راحة تستحقها","A room to unwind"),
      ("مساحة للحياة","Space for your day"),
      ("تفاصيل تبقى معاك","The comfort of details"),
    ]
    subtitles=[
      ("مساحة هادئة تبدأ منها يومك.","A calm space to begin and end the day."),
      ("صالة تضيف إلى إقامتك إحساس البيت.","A living space designed for time together."),
      ("صور حقيقية من فرع حرمة، كما هي.","An authentic look at our Harmah interiors."),
    ]
    for i,scene in enumerate(SCENES):
        article=el(soup,"article",css="lx-chapter lx-reveal")
        article["data-lx-chapter"]=str(i+1)
        visual=el(soup,"div",css="lx-chapter-visual")
        im=el(soup,"img",css="lx-chapter-photo",src=scene["photo"],
              alt=scene["alt_en"] if en else scene["alt_ar"],
              loading="lazy",decoding="async",width="1280",height="840")
        visual.append(im)
        article.append(visual)
        copy=el(soup,"div",css="lx-chapter-copy")
        copy.append(el(soup,"span",f"0{i+1} / 03",css="lx-chapter-number"))
        copy.append(el(soup,"h3",titles[i][1] if en else titles[i][0]))
        copy.append(el(soup,"p",subtitles[i][1] if en else subtitles[i][0]))
        article.append(copy)
        story.append(article)
    statement=el(soup,"div",css="lx-statement")
    statement.append(el(soup,"span","FLOWER HOTEL",css="lx-statement-brand"))
    statement.append(el(soup,"p","A thoughtful stay, in every detail."
                        if en else "إقامة لها طابعها. وراحة تليق بتفاصيل يومك."))
    statement.append(el(soup,"a","Explore available apartments" if en else "استكشف أنواع الوحدات",
                        css="lx-statement-link",href="#stay"))
    story.append(statement)
    # Keep booking accessible near the top, after hero, before editorial.
    booking=soup.select_one("#booking")
    if not booking:
        raise RuntimeError("Existing booking form must remain available")
    booking.insert_after(story)
    # The cards beneath this story retain original genuine images, categories,
    # chip content (curated earlier), booking buttons and URLs.
    units=soup.select_one("#stay")
    if not units or len(units.select(".v7-unit"))!=3:
        raise RuntimeError("Expected three genuine unit categories")
    units["class"].append("lx-original-units")
    for i,unit in enumerate(units.select(".v7-unit")):
        unit["data-lx-unit"]=str(i+1)
        unit["class"].append("lx-unit")
        photo=unit.select_one(".v7-unit-media img")
        if not photo or not photo.get("src","").startswith("/assets/images/al-majmaah-harmah/"):
            raise RuntimeError("Unit card must preserve original genuine image")
    # Self-contained stylesheet after all historical CSS to avoid old overrides.
    css="/assets/css/flower-signature-v18.css"
    js="/assets/js/flower-signature-v18.js"
    if not soup.head.find("link",href=css):
        soup.head.append(el(soup,"link",rel="stylesheet",href=css))
    if not soup.body.find("script",src=js):
        soup.body.append(el(soup,"script",src=js,defer=True))
