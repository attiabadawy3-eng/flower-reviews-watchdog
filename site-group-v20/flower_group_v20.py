"""FLOWER V20 group unification: carry the approved V19.1 editorial hero to the
three remaining branches (AR/EN) using each branch's existing photographs.
Content, booking links, policies and SEO of each page are kept as-is.
"""
from __future__ import annotations
from bs4 import BeautifulSoup
import flower_editorial_v19_1 as editorial

BRANCH_IMAGES = {
 "dammam-al-anoud": [
  ("/assets/images/dammam-al-anoud/enhanced/06-enhanced.webp", "من غرف فلور العنود", "FLOWER Al Anoud · Guest room"),
  ("/assets/images/dammam-al-anoud/enhanced/02-enhanced.webp", "جناح بإطلالة هادئة", "FLOWER Al Anoud · Suite"),
  ("/assets/images/dammam-al-anoud/enhanced/05-enhanced.webp", "صالة المعيشة", "FLOWER Al Anoud · Living room")
 ],
 "dammam-al-salam": [
  ("/assets/images/dammam-al-salam/enhanced/03-enhanced.webp", "صالة فلور السلام", "FLOWER Al Salam · Living room"),
  ("/assets/images/dammam-al-salam/enhanced/02-enhanced.webp", "غرفة بسريرين", "FLOWER Al Salam · Twin room"),
  ("/assets/images/dammam-al-salam/enhanced/05-enhanced.webp", "تفاصيل الغرفة", "FLOWER Al Salam · Room details")
 ],
 "al-qaisumah": [
  ("/assets/images/al-qaisumah/enhanced/02-enhanced.webp", "من غرف فلور القيصومة", "FLOWER Al Qaisumah · Guest room"),
  ("/assets/images/al-qaisumah/enhanced/04-enhanced.webp", "صالة المعيشة", "FLOWER Al Qaisumah · Living room"),
  ("/assets/images/al-qaisumah/enhanced/06-enhanced.webp", "الاستقبال", "FLOWER Al Qaisumah · Reception")
 ]
}
PAGES = {f"/{b}/" for b in BRANCH_IMAGES} | {f"/en/{b}/" for b in BRANCH_IMAGES}

def branch_of(path: str) -> str:
    return path.strip("/").split("/")[-1]

def apply_group(soup: BeautifulSoup, path: str) -> bool:
    if path not in PAGES:
        return False
    # Reuse the approved V19.1 markup builder unchanged; it reads its module
    # globals at call time, so point the property gallery at this branch.
    saved_pages, saved_images = editorial.PAGES, editorial.IMAGES
    editorial.PAGES = saved_pages | {path}
    editorial.IMAGES = {**saved_images, "property": BRANCH_IMAGES[branch_of(path)]}
    try:
        return editorial.apply_editorial(soup, path)
    finally:
        editorial.PAGES, editorial.IMAGES = saved_pages, saved_images
