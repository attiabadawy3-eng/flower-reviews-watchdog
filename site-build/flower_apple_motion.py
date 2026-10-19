"""Apple-inspired FLOWER motion layer, staged and enabled only on apple-motion builds."""
from __future__ import annotations
from bs4 import BeautifulSoup

MOTION_PAGES = {
    "/", "/en/", "/al-majmaah-harmah/", "/en/al-majmaah-harmah/",
    "/dammam-al-anoud/", "/en/dammam-al-anoud/",
    "/dammam-al-salam/", "/en/dammam-al-salam/",
    "/al-qaisumah/", "/en/al-qaisumah/",
}

def install_motion(soup: BeautifulSoup, url_path: str) -> None:
    if url_path not in MOTION_PAGES:
        return
    if not soup.html or not soup.head or not soup.body:
        raise RuntimeError(f"missing document structure {url_path}")
    css = "/assets/css/flower-apple-motion.css"
    js = "/assets/js/flower-apple-motion.js"
    if not soup.head.find("link", href=css):
        soup.head.append(soup.new_tag("link", rel="stylesheet", href=css))
    if not soup.body.find("script", src=js):
        soup.body.append(soup.new_tag("script", src=js, defer=True))
    # Hero media and booking are never replaced; the JS only moves DOM state for
    # unobtrusive animation, and the original HTML works with JavaScript disabled.
