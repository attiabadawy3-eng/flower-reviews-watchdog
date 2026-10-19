"""Flower V17 web adaptation of Apple's visual design principles.
Uses existing FLOWER assets and semantic HTML; no Apple trademarks, fonts or SDKs.
Apple Design Skill is advisory and focused on native apps, not a web template.
"""
from __future__ import annotations

from bs4 import BeautifulSoup

PAGE_PATHS = {
    "/", "/en/",
    "/dammam-al-anoud/", "/en/dammam-al-anoud/",
    "/dammam-al-salam/", "/en/dammam-al-salam/",
    "/al-qaisumah/", "/en/al-qaisumah/",
    "/al-majmaah-harmah/", "/en/al-majmaah-harmah/",
}


def apply_apple_v17(soup: BeautifulSoup, path: str) -> None:
    if path not in PAGE_PATHS:
        return
    if not soup.html or not soup.head or not soup.body:
        raise RuntimeError(f"missing semantic HTML structure: {path}")

    soup.html["data-flower-apple"] = "v17"
    # Existing V15/V16 markup is our baseline. CSS v17 is loaded LAST.
    href = "/assets/css/flower-apple-v17.css"
    if not soup.head.find("link", href=href):
        soup.head.append(soup.new_tag("link", rel="stylesheet", href=href))

    # Production preview controls are removed rather than visually hidden.
    for node in soup.find_all("script", src="/assets/js/flower-editorial-v15.js"):
        node.decompose()
    for node in soup.select(".flower-design-compare"):
        node.decompose()
    for node in soup.head.find_all("script"):
        if node.string and 'get("design")' in node.string and "flowerDesign" in node.string:
            node.decompose()

    if path in ("/", "/en/"):
        new_hero = soup.select_one("section.flower-v16-home-hero")
        if new_hero is None:
            raise RuntimeError(f"missing V16 homepage baseline: {path}")
        # Old hidden DOM held a SECOND H1 and unnecessary decorative markup.
        for old in soup.select("section.v13-group-hero"):
            old.decompose()
    elif path in ("/al-majmaah-harmah/", "/en/al-majmaah-harmah/"):
        new_hero = soup.select_one("section.flower-v16-property-hero")
        if new_hero is None:
            raise RuntimeError(f"missing V16 FLOWER 4 baseline: {path}")
        for old in soup.select("section.v10-property-hero"):
            old.decompose()

    # Meaningful, unaltered FLOWER room photography; avoid network fonts or stock media.
    hero_img = soup.select_one("section.flower-v16-home-hero img.flower-v16-hero-bg, section.flower-v16-property-hero img.flower-v16-hero-bg")
    if hero_img:
        hero_img["loading"] = "eager"
        hero_img["decoding"] = "async"
        hero_img["fetchpriority"] = "high"
        hero_img["alt"] = ("صورة أصلية من وحدات فلور للشقق المخدومة" if not path.startswith("/en/")
                           else "Original FLOWER serviced apartments interior photo")

    # Lazy-load only below-the-fold photographs. No image paths replaced.
    for img in soup.find_all("img", src=True):
        if img is hero_img:
            continue
        if not img.has_attr("loading") and "brand/" not in str(img["src"]):
            img["loading"] = "lazy"
            img["decoding"] = "async"

    # Keep every booking form, contact URL, Google review data hook, and structured data intact.
    if path in ("/", "/en/", "/al-majmaah-harmah/", "/en/al-majmaah-harmah/"):
        h1s = soup.select("h1")
        if len(h1s) != 1:
            raise RuntimeError(f"expected exactly one H1 after deduplication: {path}: {len(h1s)}")
