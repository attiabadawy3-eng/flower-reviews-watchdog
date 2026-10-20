#!/usr/bin/env python3
from __future__ import annotations

import datetime as dt
import json
import os
import pathlib
import re
import shutil
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
import zipfile

from bs4 import BeautifulSoup
from flower_v16 import install_hero
from flower_apple_v17 import apply_apple_v17, PAGE_PATHS as APPLE_PAGES
from flower_apple_motion import install_motion
from flower_apple_cinema import install_cinema, SCENES
from flower_apple_premium import apply_premium
from flower_interactive_v17_4 import install_flower_interactive
from flower_signature_v18 import apply_signature

BASE = "https://flower-serviced-apartments-sa.onrender.com"
ROOT = pathlib.Path(os.environ.get("FLOWER_BUILD_ROOT", "/tmp/flower-site"))
VARIANT = os.environ.get("FLOWER_BUILD_VARIANT", "").strip().lower()
# V17 is the accepted production baseline. Keep staging artifacts separate.
# Explicit "editorial" retains the historical V16 A/B candidate for reference only.
if VARIANT not in ("", "production", "apple", "editorial", "apple-motion", "apple-cinematic", "apple-premium", "flower-interactive", "flower-signature"):
    raise SystemExit(f"unsupported FLOWER_BUILD_VARIANT: {VARIANT!r}")
IS_APPLE_STAGING = VARIANT == "apple"
IS_MOTION_STAGING = VARIANT == "apple-motion"
IS_CINEMATIC_STAGING = VARIANT == "apple-cinematic"
IS_PREMIUM_STAGING = VARIANT == "apple-premium"
INTERACTIVE = VARIANT == "flower-interactive"
LUXURY = VARIANT == "flower-signature"
# Accepted production baseline: premium V17.3, with image-first Flower 4 hero.
CINEMATIC = VARIANT in ("", "production", "apple-cinematic", "apple-premium", "flower-interactive", "flower-signature")
PREMIUM = VARIANT in ("", "production", "apple-premium", "flower-interactive", "flower-signature")
APPLE = VARIANT != "editorial"
MOTION = IS_MOTION_STAGING or CINEMATIC
EDITORIAL = True
OUT_ZIP = pathlib.Path(
    "deploy-assets/flower-signature-v18-staging.zip" if LUXURY else
    "deploy-assets/flower-interactive-v17-4-staging.zip" if INTERACTIVE else
    "deploy-assets/flower-site-apple-premium-staging.zip" if IS_PREMIUM_STAGING else
    "deploy-assets/flower-site-apple-cinematic-staging.zip" if IS_CINEMATIC_STAGING else
    "deploy-assets/flower-site-apple-motion-staging.zip" if IS_MOTION_STAGING else
    "deploy-assets/flower-site-apple-staging.zip" if IS_APPLE_STAGING else
    "deploy-assets/flower-site-editorial-staging.zip" if VARIANT == "editorial" else
    "deploy-assets/flower-site-production.zip"
)
MANIFEST = pathlib.Path(
    "deploy-assets/flower-signature-v18-manifest.json" if LUXURY else
    "deploy-assets/flower-interactive-v17-4-manifest.json" if INTERACTIVE else
    "deploy-assets/flower-apple-premium-staging-manifest.json" if IS_PREMIUM_STAGING else
    "deploy-assets/flower-apple-cinematic-staging-manifest.json" if IS_CINEMATIC_STAGING else
    "deploy-assets/flower-apple-motion-staging-manifest.json" if IS_MOTION_STAGING else
    "deploy-assets/flower-apple-staging-manifest.json" if IS_APPLE_STAGING else
    "deploy-assets/flower-editorial-staging-manifest.json" if VARIANT == "editorial" else
    "deploy-assets/flower-site-manifest.json"
)
BUILD_DATE = dt.datetime.now(dt.timezone.utc)
BUILD_DAY = BUILD_DATE.date().isoformat()
FEED_URL = "https://raw.githubusercontent.com/attiabadawy3-eng/flower-reviews-watchdog/main/public/reviews-summary.json"

BRANCHES = {
    "flower-1": {
        "path": "/dammam-al-anoud/",
        "rating": 4.83,
        "count": 117,
        "ar": "العنود",
        "en": "Al Anoud",
    },
    "flower-2": {
        "path": "/dammam-al-salam/",
        "rating": 4.5,
        "count": 263,
        "ar": "السلام",
        "en": "Al Salam",
    },
    "flower-3": {
        "path": "/al-qaisumah/",
        "rating": 4.63,
        "count": 57,
        "ar": "القيصومة",
        "en": "Al Qaisumah",
    },
    "flower-4": {
        "path": "/al-majmaah-harmah/",
        "rating": 4.6,
        "count": 142,
        "ar": "حرمة",
        "en": "Harmah",
    },
}

PATH_TO_BRANCH = {v["path"]: k for k, v in BRANCHES.items()}
PATH_TO_BRANCH.update({"/en" + v["path"]: k for k, v in BRANCHES.items()})


def request(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "FLOWER-Site-Builder/1.0"})
    with urllib.request.urlopen(req, timeout=45) as r:
        return r.read()


def local_path_for(url: str, content_type_hint: str = "") -> pathlib.Path:
    p = urllib.parse.urlsplit(url).path
    if not p or p.endswith("/"):
        p = p + "index.html"
    return ROOT / p.lstrip("/")


def same_origin_asset(url: str, base_url: str) -> str | None:
    if not url or url.startswith(("#", "mailto:", "tel:", "javascript:", "data:")):
        return None
    absolute = urllib.parse.urljoin(base_url, url)
    parts = urllib.parse.urlsplit(absolute)
    if parts.scheme not in ("http", "https") or parts.netloc != urllib.parse.urlsplit(BASE).netloc:
        return None
    return urllib.parse.urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))


def save_url(url: str) -> pathlib.Path:
    data = request(url)
    path = local_path_for(url)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


def collect_assets_from_html(html: str, page_url: str) -> set[str]:
    soup = BeautifulSoup(html, "html.parser")
    urls: set[str] = set()
    for tag, attr in [
        ("img", "src"), ("script", "src"), ("link", "href"), ("source", "src"),
        ("video", "poster"), ("iframe", "src")
    ]:
        for node in soup.find_all(tag):
            value = node.get(attr)
            asset = same_origin_asset(value, page_url) if value else None
            if asset:
                urls.add(asset)
    for node in soup.find_all(srcset=True):
        for item in str(node.get("srcset") or "").split(","):
            raw = item.strip().split(" ")[0]
            asset = same_origin_asset(raw, page_url)
            if asset:
                urls.add(asset)
    return urls


def collect_assets_from_css(css: str, css_url: str) -> set[str]:
    urls: set[str] = set()
    for match in re.finditer(r"url\(([^)]+)\)", css, flags=re.I):
        raw = match.group(1).strip().strip("\"'")
        asset = same_origin_asset(raw, css_url)
        if asset:
            urls.add(asset)
    return urls


def mirror_live_site() -> list[str]:
    if ROOT.exists():
        shutil.rmtree(ROOT)
    ROOT.mkdir(parents=True)

    sitemap_url = BASE + "/sitemap.xml"
    sitemap = request(sitemap_url)
    (ROOT / "sitemap.xml").write_bytes(sitemap)
    try:
        (ROOT / "robots.txt").write_bytes(request(BASE + "/robots.txt"))
    except Exception:
        pass

    xml = ET.fromstring(sitemap)
    ns = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    pages = [loc.text.strip() for loc in xml.findall(".//s:loc", ns) if loc.text]
    if BASE + "/" not in pages:
        pages.insert(0, BASE + "/")

    assets: set[str] = set()
    for url in pages:
        html = request(url).decode("utf-8", errors="replace")
        path = local_path_for(url)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(html, encoding="utf-8")
        assets |= collect_assets_from_html(html, url)

    queue = list(assets)
    seen: set[str] = set()
    while queue:
        url = queue.pop()
        if url in seen:
            continue
        seen.add(url)
        try:
            data = request(url)
        except Exception as exc:
            print(f"WARN asset fetch failed {url}: {exc}", file=sys.stderr)
            continue
        path = local_path_for(url)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        if path.suffix.lower() == ".css":
            text = data.decode("utf-8", errors="replace")
            for extra in collect_assets_from_css(text, url):
                if extra not in seen:
                    queue.append(extra)
    return pages


def ensure_asset_tags(soup: BeautifulSoup) -> None:
    head = soup.head
    body = soup.body
    if head and not soup.find("link", href="/assets/css/site-v14-live.css"):
        tag = soup.new_tag("link", rel="stylesheet", href="/assets/css/site-v14-live.css")
        head.append(tag)
    if body and not soup.find("script", src="/assets/js/google-reviews-live.js"):
        tag = soup.new_tag("script", src="/assets/js/google-reviews-live.js", defer=True)
        body.append(tag)


def format_rating(value: float) -> str:
    return f"{value:.1f}"


def patch_branch_cards(soup: BeautifulSoup, lang: str) -> None:
    for card in soup.select(".v7-branch-card"):
        media = card.select_one(".v7-branch-media[href]")
        if not media:
            continue
        href = urllib.parse.urlsplit(media.get("href") or "").path
        normalized = href[3:] if href.startswith("/en/") else href
        branch_id = PATH_TO_BRANCH.get(normalized)
        if not branch_id:
            continue
        span = media.find("span")
        if span:
            info = BRANCHES[branch_id]
            span["data-google-card"] = branch_id
            span.string = f"★ {format_rating(info['rating'])} · {info['count']} Google"


def patch_branch_page(soup: BeautifulSoup, branch_id: str, lang: str) -> None:
    info = BRANCHES[branch_id]
    rating = format_rating(info["rating"])
    count = str(info["count"])

    hero_meta = soup.select_one(".v10-meta")
    if hero_meta:
        star = next((x for x in hero_meta.find_all("span") if "★" in x.get_text(" ", strip=True) or "&#9733;" in str(x)), None)
        if star:
            star.clear()
            star.append("★ ")
            b = soup.new_tag("b")
            b["data-google-rating"] = branch_id
            b.string = rating
            star.append(b)
            star.append(" / 5")

    reviews = soup.find(id="reviews")
    if reviews:
        strong = reviews.find("strong")
        if strong:
            strong["data-google-rating"] = branch_id
            strong.string = rating
        candidates = [
            p for p in reviews.find_all("p")
            if ("Google" in p.get_text(" ", strip=True) and
                ("تقييم" in p.get_text(" ", strip=True) or "review" in p.get_text(" ", strip=True).lower()))
        ]
        if candidates:
            p = candidates[0]
            p["data-google-review-summary"] = branch_id
            p.clear()
            n = soup.new_tag("span")
            n["data-google-review-count"] = branch_id
            n.string = count
            p.append(n)
            if lang == "en":
                p.append(" Google reviews for this branch. Last verified: ")
            else:
                p.append(" مراجعة على Google لهذا الفرع. آخر تحقق: ")
            tm = soup.new_tag("time")
            tm["data-google-verified"] = ""
            tm.string = "17 أكتوبر 2026" if lang != "en" else "17 October 2026"
            p.append(tm)
            p.append(".")
        head = reviews.find("h2")
        if head and not reviews.select_one(".v14-review-auto"):
            note = soup.new_tag("small")
            note["class"] = ["v14-review-auto"]
            note["data-google-status"] = ""
            note.string = "تُحدّث بيانات Google تلقائيًا" if lang != "en" else "Google data updates automatically"
            head.insert_after(note)


def patch_home(soup: BeautifulSoup, lang: str) -> None:
    # Branch image overlays.
    for card in soup.select(".v7-branch-card"):
        link = card.find("a", href=True)
        if not link:
            continue
        href = urllib.parse.urlsplit(link["href"]).path
        if lang == "en" and href.startswith("/en/"):
            href = href[3:]
        branch_id = PATH_TO_BRANCH.get(href)
        if not branch_id:
            continue
        span = link.find("span")
        if span:
            info = BRANCHES[branch_id]
            span["data-google-card"] = branch_id
            span.string = f"★ {format_rating(info['rating'])} · {info['count']} Google"

    # Review cards are mapped by their Google Maps links / place order.
    review_cards = soup.select(".v7-review-card")
    for idx, card in enumerate(review_cards[:4], start=1):
        branch_id = f"flower-{idx}"
        info = BRANCHES[branch_id]
        strong = card.find("strong")
        if strong:
            strong["data-google-rating"] = branch_id
            strong.string = format_rating(info["rating"])
        p = next((x for x in card.find_all("p") if "Google" in x.get_text(" ", strip=True)), None)
        if p:
            p["data-google-review-summary"] = branch_id
            p.clear()
            n = soup.new_tag("span")
            n["data-google-review-count"] = branch_id
            n.string = str(info["count"])
            p.append(n)
            p.append(" Google reviews" if lang == "en" else " تقييمًا على Google")

    reviews = soup.find(id="reviews")
    if reviews:
        intro = next((p for p in reviews.find_all("p") if "2026-" in p.get_text(" ", strip=True) or "آخر تحديث" in p.get_text(" ", strip=True) or "Last update" in p.get_text(" ", strip=True)), None)
        if intro:
            intro["data-google-updated-summary"] = ""
            intro.string = (
                "يعرض كل فرع تقييمه وعدد مراجعاته على Google بصورة مستقلة. البيانات تُحدّث تلقائيًا؛ آخر تحقق: "
                if lang != "en"
                else "Each branch shows its own Google rating and review count. Data updates automatically; last verified: "
            )
            tm = soup.new_tag("time")
            tm["data-google-verified"] = ""
            tm.string = "17 أكتوبر 2026" if lang != "en" else "17 October 2026"
            intro.append(tm)
            intro.append(".")


def chip(soup: BeautifulSoup, text: str):
    span = soup.new_tag("span")
    span["class"] = ["v10-amenity-chip", "v14-confirmed-chip"]
    b = soup.new_tag("b")
    b.string = text
    span.append(b)
    return span


def patch_flower4_units(soup: BeautifulSoup, lang: str) -> None:
    stay = soup.find(id="stay")
    if not stay:
        return

    if lang == "en":
        head_text = "Choose the right unit type. Extra in-unit amenities vary by unit type and the specific available unit; the branch confirms them when you enquire."
        expected = [
            ("Room + Private Bathroom", ["Private bathroom"], "A private room with its own bathroom, suited to a practical and comfortable stay."),
            ("One Bedroom + Living Room", ["One bedroom", "Separate living room"], "One bedroom with a separate living room for extra space. Additional amenities are confirmed for the available unit."),
            ("Two Bedrooms + Living Room", ["Two bedrooms", "Separate living room"], "Two bedrooms with a separate living room for a more spacious stay. Additional amenities are confirmed for the available unit."),
        ]
    else:
        head_text = "اختر نوع الوحدة المناسب. التجهيزات الإضافية داخل الوحدة تختلف حسب النوع والوحدة المتاحة ويؤكدها الفرع عند الاستفسار."
        expected = [
            ("غرفة وحمام", ["حمام خاص"], "غرفة مستقلة مع حمام خاص، خيار عملي لإقامة مريحة."),
            ("غرفة وصالة", ["غرفة نوم", "صالة مستقلة"], "غرفة نوم مع صالة مستقلة لمساحة معيشة إضافية. التجهيزات الإضافية تُؤكد حسب الوحدة المتاحة."),
            ("غرفتان وصالة", ["غرفتا نوم", "صالة مستقلة"], "غرفتا نوم مع صالة مستقلة لإقامة أوسع. التجهيزات الإضافية تُؤكد حسب الوحدة المتاحة."),
        ]

    head_p = stay.select_one(".v7-section-head p")
    if head_p:
        head_p.string = head_text

    cards = stay.select("article.v7-unit")
    for card, (name, features, desc) in zip(cards, expected):
        h3 = card.find("h3")
        if h3:
            h3.string = name
        chips = card.select_one(".v10-amenity-chips")
        if chips:
            chips.clear()
            for feature in features:
                chips.append(chip(soup, feature))
        copy = card.select_one(".v7-unit-copy")
        if copy:
            direct_ps = [p for p in copy.find_all("p", recursive=False)]
            if direct_ps:
                direct_ps[-1].string = desc
        enquiry = card.select_one(".v7-unit-enquire")
        if enquiry:
            enquiry["data-unit-value"] = name

    select = soup.find(id="book-unit")
    if select:
        first = select.find("option")
        if first:
            first["value"] = expected[0][0]
            first.string = expected[0][0]

    dialogs = soup.select("dialog")
    marker = "FLOWER" if lang == "en" else "فلور"
    unit_dialogs = [d for d in dialogs if d.find(["h2", "h3"]) and marker in d.get_text(" ", strip=True)]
    for idx, dialog in enumerate(unit_dialogs[:3]):
        name, features, desc = expected[idx]
        title = dialog.find("h2")
        if title:
            title.string = name
        chips = dialog.select_one(".v10-amenity-chips")
        if chips:
            chips.clear()
            for feature in features:
                chips.append(chip(soup, feature))
        h4 = next((x for x in dialog.find_all("h4") if ("Unit amenities" in x.get_text(strip=True) if lang == "en" else "مزايا" in x.get_text(strip=True))), None)
        if h4:
            amenity_p = h4.find_next("p")
            if amenity_p:
                amenity_p.string = ", ".join(features) if lang == "en" else "، ".join(features)
            desc_p = h4.find_previous("p")
            if desc_p:
                desc_p.string = desc

    for details in soup.find_all("details"):
        summary = details.find("summary")
        if not summary:
            continue
        q = summary.get_text(" ", strip=True).lower()
        if (lang == "en" and "unit types" in q) or (lang != "en" and "أنواع الوحدات" in q):
            p = details.find("p")
            if p:
                p.string = ", ".join(x[0] for x in expected) if lang == "en" else "، ".join(x[0] for x in expected)
            break

    # Update meta copy so the first unit type is not described ambiguously.
    if soup.head:
        if lang == "en":
            meta_text = "FLOWER 4 offers serviced apartments in Harmah, Al Majmaah, with a room + private bathroom, one-bedroom + living room and two-bedroom + living room options, 24-hour reception, free Wi-Fi and parking."
        else:
            meta_text = "فلور 4 في حرمة بالمجمعة. شقق مخدومة ومفروشة بخيارات غرفة وحمام، غرفة وصالة، وغرفتين وصالة، مع استقبال 24 ساعة وواي فاي مجاني ومواقف سيارات."
        meta = soup.head.find("meta", attrs={"name": "description"})
        if meta:
            meta["content"] = meta_text
        og = soup.head.find("meta", attrs={"property": "og:description"})
        if og:
            og["content"] = meta_text

    # LodgingBusiness schema: keep property/service amenities only; do not imply unit appliances.
    for node in soup.find_all("script", attrs={"type": "application/ld+json"}):
        try:
            data = json.loads(node.string or "")
        except Exception:
            continue
        if data.get("@type") != "LodgingBusiness":
            continue
        if lang == "en":
            data["description"] = "FLOWER 4 serviced apartments in Harmah, Al Majmaah, with room + private bathroom, one-bedroom + living room and two-bedroom + living room options."
        else:
            data["description"] = "فلور 4 في حرمة بالمجمعة بخيارات غرفة وحمام، غرفة وصالة، وغرفتين وصالة."
        blocked = {"مطبخ", "غسالة", "ثلاجة", "ميكروويف", "Kitchen", "Washing machine", "Refrigerator", "Microwave"}
        feats = data.get("amenityFeature")
        if isinstance(feats, list):
            data["amenityFeature"] = [f for f in feats if str((f or {}).get("name")) not in blocked]
        node.string = json.dumps(data, ensure_ascii=False, separators=(",", ":"))


def install_editorial_layer(soup: BeautifulSoup, url_path: str) -> None:
    if not EDITORIAL or url_path not in ("/", "/en/", "/al-majmaah-harmah/", "/en/al-majmaah-harmah/"):
        return
    if soup.html:
        soup.html["data-flower-design"] = "editorial"
    if soup.body:
        classes = list(soup.body.get("class") or [])
        if "v15-editorial" not in classes:
            classes.append("v15-editorial")
        soup.body["class"] = classes
    if soup.head:
        bootstrap_source = '(function(){if(new URLSearchParams(location.search).get("design")==="classic"){document.documentElement.dataset.flowerDesign="classic"}})();'
        if not any(bootstrap_source == (x.string or "") for x in soup.head.find_all("script")):
            bootstrap = soup.new_tag("script")
            bootstrap.string = bootstrap_source
            soup.head.insert(0, bootstrap)
        for href in ("/assets/css/flower-editorial-v15.css", "/assets/css/flower-editorial-v16.css"):
            if not soup.head.find("link", href=href):
                soup.head.append(soup.new_tag("link", rel="stylesheet", href=href))
    if soup.body:
        if not soup.body.find("script", src="/assets/js/flower-editorial-v15.js"):
            soup.body.append(soup.new_tag("script", src="/assets/js/flower-editorial-v15.js", defer=True))
        install_hero(soup, url_path, "en" if url_path.startswith("/en/") else "ar")

def patch_page(path: pathlib.Path, url_path: str) -> None:
    html = path.read_text(encoding="utf-8")
    soup = BeautifulSoup(html, "html.parser")
    lang = "en" if (soup.html and str(soup.html.get("lang", "")).lower().startswith("en")) else "ar"
    ensure_asset_tags(soup)
    patch_branch_cards(soup, lang)

    branch_id = PATH_TO_BRANCH.get(url_path)
    if branch_id:
        patch_branch_page(soup, branch_id, lang)
    if url_path in ("/", "/en/"):
        patch_home(soup, lang)
    if url_path in ("/al-majmaah-harmah/", "/en/al-majmaah-harmah/"):
        patch_flower4_units(soup, lang)
    install_editorial_layer(soup, url_path)
    if APPLE:
        apply_apple_v17(soup, url_path)
    if MOTION:
        install_motion(soup, url_path)
    if CINEMATIC:
        install_cinema(soup, url_path)
    if PREMIUM:
        apply_premium(soup, url_path)
    if INTERACTIVE:
        install_flower_interactive(soup, url_path)
    if LUXURY:
        apply_signature(soup, url_path)

    path.write_text(str(soup), encoding="utf-8")


LIVE_JS = r'''(() => {
  const FEED = "''' + FEED_URL + r'''";
  const ids = ["flower-1", "flower-2", "flower-3", "flower-4"];
  const lang = (document.documentElement.lang || "").toLowerCase().startsWith("en") ? "en" : "ar";

  const formatNumber = (n) => new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 }).format(n);
  const formatRating = (n) => Number(n).toFixed(1);
  const formatVerified = (iso) => {
    try {
      return new Intl.DateTimeFormat(lang === "en" ? "en-GB" : "ar-EG-u-nu-latn", {
        timeZone: "Asia/Riyadh",
        day: "numeric",
        month: "long",
        year: "numeric",
        hour: "numeric",
        minute: "2-digit"
      }).format(new Date(iso));
    } catch {
      return iso;
    }
  };
  const setText = (selector, value) => document.querySelectorAll(selector).forEach((el) => { el.textContent = value; });

  function apply(doc) {
    if (!doc || doc.schemaVersion !== 1 || !doc.branches || !doc.verifiedAt) throw new Error("invalid review feed");
    for (const id of ids) {
      const b = doc.branches[id];
      if (!b || !Number.isFinite(Number(b.rating)) || !Number.isInteger(Number(b.reviewCount))) continue;
      const rating = formatRating(b.rating);
      const count = formatNumber(b.reviewCount);
      setText('[data-google-rating="' + id + '"]', rating);
      setText('[data-google-review-count="' + id + '"]', count);
      setText('[data-google-card="' + id + '"]', "★ " + rating + " · " + count + " Google");
      document.querySelectorAll('[data-google-review-summary="' + id + '"]').forEach((el) => {
        el.textContent = lang === "en"
          ? count + " Google reviews for this branch. Last verified: "
          : count + " مراجعة على Google لهذا الفرع. آخر تحقق: ";
        const time = document.createElement("time");
        time.setAttribute("data-google-verified", "");
        time.textContent = formatVerified(doc.verifiedAt);
        el.appendChild(time);
        el.append(".");
      });
    }
    setText("[data-google-verified]", formatVerified(doc.verifiedAt));

    const ageMs = Date.now() - new Date(doc.verifiedAt).getTime();
    const fresh = Number.isFinite(ageMs) && ageMs >= 0 && ageMs <= 36 * 60 * 60 * 1000;
    document.documentElement.dataset.googleReviews = fresh ? "fresh" : "stale";
    document.querySelectorAll("[data-google-status]").forEach((el) => {
      el.textContent = fresh
        ? (lang === "en" ? "Google data updates automatically" : "تُحدّث بيانات Google تلقائيًا")
        : (lang === "en" ? "Showing the last verified Google data" : "نعرض آخر بيانات Google تم التحقق منها");
    });
  }

  async function load() {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 5000);
    try {
      const bucket = Math.floor(Date.now() / 300000);
      const res = await fetch(FEED + "?v=" + bucket, { cache: "no-store", mode: "cors", signal: controller.signal });
      if (!res.ok) throw new Error("review feed " + res.status);
      apply(await res.json());
    } catch (err) {
      document.documentElement.dataset.googleReviews = "fallback";
      console.warn("[FLOWER] Google review feed fallback", err);
    } finally {
      clearTimeout(timeout);
    }
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", load, { once: true });
  else load();
})();'''

LIVE_CSS = r''':root{--f14-wine:#7A314D;--f14-wine-dark:#5B2038;--f14-gold:#B79862}
.v10-hero-card,.v7-unit,.v7-review-card,.v7-branch-card{transition:transform .35s cubic-bezier(.2,.8,.2,1),box-shadow .35s ease,border-color .35s ease}
.v10-hero-card{position:relative;isolation:isolate}
.v10-hero-card:before{content:"";position:absolute;inset:-1px;z-index:-1;border-radius:inherit;background:radial-gradient(circle at 78% 18%,rgba(183,152,98,.16),transparent 34%),radial-gradient(circle at 12% 80%,rgba(122,49,77,.08),transparent 30%);pointer-events:none}
.v10-photo-main img,.v10-photo-row img,.v7-unit-media img,.v7-home-gallery-item img{transition:transform .55s cubic-bezier(.2,.8,.2,1),filter .45s ease}
.v10-direct-btn,.v7-btn-primary{transition:transform .2s ease,box-shadow .25s ease,filter .25s ease}
.v14-review-auto{display:inline-flex;align-items:center;gap:.45rem;margin:.35rem 0 1rem;padding:.42rem .72rem;border:1px solid rgba(183,152,98,.34);border-radius:999px;color:var(--f14-wine-dark);background:rgba(183,152,98,.08);font-size:.78rem;font-weight:600}
.v14-review-auto:before{content:"";width:.48rem;height:.48rem;border-radius:50%;background:#2f8f5b;box-shadow:0 0 0 .22rem rgba(47,143,91,.11)}
html[data-google-reviews="stale"] .v14-review-auto:before,html[data-google-reviews="fallback"] .v14-review-auto:before{background:var(--f14-gold);box-shadow:0 0 0 .22rem rgba(183,152,98,.12)}
.v14-confirmed-chip{background:linear-gradient(135deg,rgba(122,49,77,.06),rgba(183,152,98,.10));border-color:rgba(122,49,77,.14)}
@media (hover:hover) and (pointer:fine){
  .v7-unit:hover,.v7-review-card:hover,.v7-branch-card:hover{transform:translateY(-4px);box-shadow:0 20px 44px rgba(50,24,34,.10)}
  .v10-photo-main:hover img,.v10-photo-row a:hover img,.v7-home-gallery-item:hover img{transform:scale(1.025);filter:saturate(1.03) contrast(1.01)}
  .v10-direct-btn:hover,.v7-btn-primary:hover{transform:translateY(-2px);box-shadow:0 12px 26px rgba(91,32,56,.18)}
  .v10-direct-btn:active,.v7-btn-primary:active{transform:translateY(0) scale(.985)}
}
@media (prefers-reduced-motion:reduce){
  .v10-hero-card,.v7-unit,.v7-review-card,.v7-branch-card,.v10-photo-main img,.v10-photo-row img,.v7-unit-media img,.v7-home-gallery-item img,.v10-direct-btn,.v7-btn-primary{transition:none!important;transform:none!important}
}
'''


def write_live_assets() -> None:
    js = ROOT / "assets/js/google-reviews-live.js"
    css = ROOT / "assets/css/site-v14-live.css"
    js.parent.mkdir(parents=True, exist_ok=True)
    css.parent.mkdir(parents=True, exist_ok=True)
    js.write_text(LIVE_JS, encoding="utf-8")
    css.write_text(LIVE_CSS, encoding="utf-8")
    if EDITORIAL:
        base = pathlib.Path(__file__).resolve().parent
        files = [
            (base / "flower-editorial-v15.css", ROOT / "assets/css/flower-editorial-v15.css"),
            (base / "flower-editorial-v15.js", ROOT / "assets/js/flower-editorial-v15.js"),
            (base / "flower-editorial-v16.css", ROOT / "assets/css/flower-editorial-v16.css"),
        ]
        for src, target in files:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, target)
    if APPLE:
        src = pathlib.Path(__file__).resolve().parent / "flower-apple-v17.css"
        dst = ROOT / "assets/css/flower-apple-v17.css"
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dst)
    if MOTION:
        base = pathlib.Path(__file__).resolve().parent
        for filename, destination in (
            ("flower-apple-motion.css", ROOT / "assets/css/flower-apple-motion.css"),
            ("flower-apple-motion.js", ROOT / "assets/js/flower-apple-motion.js")
        ):
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(base / filename, destination)
    if CINEMATIC:
        base = pathlib.Path(__file__).resolve().parent
        for filename, destination in (
            ("flower-apple-cinema.css", ROOT / "assets/css/flower-apple-cinema.css"),
            ("flower-apple-cinema.js", ROOT / "assets/js/flower-apple-cinema.js")
        ):
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(base / filename, destination)
    if PREMIUM:
        src = pathlib.Path(__file__).resolve().parent / "flower-apple-premium-v17-3.css"
        dst = ROOT / "assets/css/flower-apple-premium-v17-3.css"
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dst)
    if INTERACTIVE:
        base = pathlib.Path(__file__).resolve().parent
        for src_file, target_file in (
            ("flower-interactive-v17-4.css", "assets/css/flower-interactive-v17-4.css"),
            ("flower-interactive-v17-4.js", "assets/js/flower-interactive-v17-4.js"),
        ):
            target=ROOT / target_file
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(base / src_file, target)
    if LUXURY:
        base = pathlib.Path(__file__).resolve().parent
        for src_file, dest in (
            ("flower-signature-v18.css", "assets/css/flower-signature-v18.css"),
            ("flower-signature-v18.js", "assets/js/flower-signature-v18.js"),
        ):
            target=ROOT / dest
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(base/src_file,target)


def update_sitemap() -> None:
    path = ROOT / "sitemap.xml"
    tree = ET.parse(path)
    root = tree.getroot()
    ns = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    important = {BASE + "/", BASE + "/al-majmaah-harmah/", BASE + "/en/", BASE + "/en/al-majmaah-harmah/"}
    for url in root.findall("s:url", ns):
        loc = url.find("s:loc", ns)
        if loc is None or loc.text not in important:
            continue
        mod = url.find("s:lastmod", ns)
        if mod is None:
            mod = ET.SubElement(url, "{http://www.sitemaps.org/schemas/sitemap/0.9}lastmod")
        mod.text = BUILD_DAY
    tree.write(path, encoding="utf-8", xml_declaration=True)


def tests() -> dict:
    result = {}
    f4 = (ROOT / "al-majmaah-harmah/index.html").read_text(encoding="utf-8")
    f4_en = (ROOT / "en/al-majmaah-harmah/index.html").read_text(encoding="utf-8")
    home = (ROOT / "index.html").read_text(encoding="utf-8")
    js = (ROOT / "assets/js/google-reviews-live.js").read_text(encoding="utf-8")

    result["f4_review_fallback_142"] = "142" in f4 and 'data-google-review-summary="flower-4"' in f4
    result["home_review_fallbacks"] = all(str(BRANCHES[f"flower-{i}"]["count"]) in home for i in range(1,5))
    result["all_branch_cards_current"] = all(f"· {BRANCHES[f'flower-{i}']['count']} Google" in home for i in range(1,5)) and all(f"· {BRANCHES[f'flower-{i}']['count']} Google" in f4 for i in range(1,4))
    result["dynamic_feed_hook"] = FEED_URL in js and "data-google-rating" in js
    result["f4_no_room_appliance_generalization"] = all(x not in BeautifulSoup(f4, "html.parser").select_one("#stay").get_text(" ", strip=True) for x in ["غسالة", "ميكروويف"])
    result["f4_en_no_room_appliance_generalization"] = all(x not in BeautifulSoup(f4_en, "html.parser").select_one("#stay").get_text(" ", strip=True) for x in ["Washing machine", "Microwave"])
    result["f4_unit_label_consistent"] = "غرفة وحمام" in f4 and "Room + Private Bathroom" in f4_en
    result["canonical_kept"] = 'rel="canonical"' in f4 and "/al-majmaah-harmah/" in f4
    result["booking_link_kept"] = "booking.com/hotel/sa/flwr-llshqq-lmkhdwm-lmjm-h.ar.html" in f4
    result["whatsapp_kept"] = "+966566374274" in f4 or "966566374274" in f4
    result["motion_reduced_supported"] = "prefers-reduced-motion" in LIVE_CSS
    if EDITORIAL:
        new_css = (ROOT / "assets/css/flower-editorial-v15.css").read_text(encoding="utf-8")
        new_js = (ROOT / "assets/js/flower-editorial-v15.js").read_text(encoding="utf-8")
        home_en = (ROOT / "en/index.html").read_text(encoding="utf-8")
        result["editorial_home_ar_en"] = all(
            'data-flower-design="editorial"' in page and "flower-editorial-v15.css" in page
            for page in (home, home_en))
        result["editorial_f4_ar_en"] = all(
            'data-flower-design="editorial"' in page and "flower-editorial-v15.css" in page
            for page in (f4, f4_en))
        result["design_switcher_staging_only"] = 'flower-unified-staging.onrender.com' in new_js
        result["original_images_only"] = ("/assets/images/dammam-al-anoud/" in home
            and "/assets/images/al-majmaah-harmah/" in f4
            and "threeui.com" not in new_css and "https://" not in new_css)
        result["no_threejs_dependency"] = "WebGL" not in new_js and "THREE" not in new_js
        result["editorial_reduced_motion"] = "prefers-reduced-motion" in new_css
        result["editorial_focus_visible"] = "focus-visible" in new_css
        v16_css = (ROOT / "assets/css/flower-editorial-v16.css").read_text(encoding="utf-8")
        result["v16_new_immersive_hero"] = 'class="flower-v16-home-hero"' in home and 'class="flower-v16-property-hero"' in f4
        result["v16_ar_en_both_pages"] = all("flower-editorial-v16.css" in p and "v16-hero-actions" in p for p in [home, home_en, f4, f4_en])
        result["v16_switcher_preserves_classic"] = APPLE or (all("v13-group-hero" in p for p in [home, home_en]) and all("v10-property-hero" in p for p in [f4, f4_en]))
        result["v16_original_photos_only"] = all("/assets/images/" in p for p in [home, home_en, f4, f4_en]) and "threeui.com" not in v16_css
        result["v16_mobile_breakpoint"] = "@media(max-width:700px)" in v16_css and "scroll-snap-type:x mandatory" in v16_css
        result["v16_unchanged_booking_forms"] = all('id="book-whatsapp"' in p and 'id="book-arrival"' in p and 'id="book-departure"' in p for p in [home, home_en, f4, f4_en])
        result["v16_review_live_hook"] = all('data-google-review-count="flower-4"' in p for p in [f4, f4_en])

    if APPLE:
        good = []
        for url_path in sorted(APPLE_PAGES):
            local = ROOT / (url_path.lstrip("/") + "index.html")
            if url_path == "/":
                local = ROOT / "index.html"
            if not local.exists():
                good.append(False)
                continue
            page_soup = BeautifulSoup(local.read_text(encoding="utf-8"), "html.parser")
            good.append(
                page_soup.html.get("data-flower-apple") == "v17"
                and bool(page_soup.head.find("link", href="/assets/css/flower-apple-v17.css"))
                and bool(page_soup.find("a", href=lambda h: bool(h) and ("#booking" in h or "booking.com" in h)))
            )
        result["apple_all_ten_pages"] = len(good) == 10 and all(good)
        result["apple_h1_single"] = all(
            len(BeautifulSoup((ROOT / rel).read_text(encoding="utf-8"), "html.parser").find_all("h1")) == 1
            for rel in ("index.html", "en/index.html", "al-majmaah-harmah/index.html", "en/al-majmaah-harmah/index.html")
        )
        result["apple_no_preview_switcher"] = not any(
            "flower-design-compare" in (ROOT / rel).read_text(encoding="utf-8")
            for rel in ("index.html", "al-majmaah-harmah/index.html")
        )
        css_text = (ROOT / "assets/css/flower-apple-v17.css").read_text(encoding="utf-8")
        result["apple_brand_and_reduced_motion"] = all(
            token in css_text for token in ("#7A314D", "#5B2038", "#B79862", "prefers-reduced-motion")
        )
        result["apple_no_external_media"] = not any(
            token in css_text for token in ("url(http", "@import", "three.js", "WebGL")
        )

    if MOTION:
        import re
        pages = (
            "index.html","en/index.html","al-majmaah-harmah/index.html",
            "en/al-majmaah-harmah/index.html", "dammam-al-anoud/index.html",
            "en/dammam-al-anoud/index.html", "dammam-al-salam/index.html",
            "en/dammam-al-salam/index.html", "al-qaisumah/index.html",
            "en/al-qaisumah/index.html",
        )
        result["motion_isolation_ten_pages"] = all(
            '/assets/css/flower-apple-motion.css' in (ROOT / p).read_text(encoding="utf-8")
            and '/assets/js/flower-apple-motion.js' in (ROOT / p).read_text(encoding="utf-8")
            for p in pages
        )
        motion_js = (ROOT / "assets/js/flower-apple-motion.js").read_text(encoding="utf-8")
        motion_css = (ROOT / "assets/css/flower-apple-motion.css").read_text(encoding="utf-8")
        result["motion_accessibility"] = all(
            x in motion_js + motion_css for x in
            ("prefers-reduced-motion", "aria-label", "aria-live", "IntersectionObserver")
        )
        result["motion_no_network_or_external_packages"] = all(
            x not in motion_js + motion_css for x in
            ("fetch(", "XMLHttpRequest", "@import", "https://", "three.js")
        )
        result["motion_no_new_images"] = all(
            x not in motion_js for x in ("new Image(", "createElement(\"img\")")
        )
    if CINEMATIC and not LUXURY:
        f4_soup = BeautifulSoup(f4, "html.parser")
        f4_en_soup = BeautifulSoup(f4_en, "html.parser")
        sections = [f4_soup.select_one("#flower-cinema"), f4_en_soup.select_one("#flower-cinema")]
        result["cinema_three_verified_images"] = all(
            sec is not None and len(sec.select("[data-cinema-scene]")) == 3
            and [node.get("src") for node in sec.select("[data-cinema-scene] img")] == [scene["photo"] for scene in SCENES]
            for sec in sections
        )
        result["cinema_bookings_unchanged"] = all(
            sec is not None and sec.select_one('a[href="#booking"]') is not None
            for sec in sections
        ) and all(k in f4 for k in ('id="book-branch"', 'id="book-unit"', 'id="book-whatsapp"'))
        result["cinema_en_ar"] = all(
            len(sec.select("figcaption h3")) == 3 and len(sec.select(".flower-cinema-copy p")) == 3
            for sec in sections if sec is not None
        ) and all(sec is not None for sec in sections)
        result["cinema_css_js_loaded"] = all(
            '/assets/css/flower-apple-cinema.css' in txt and '/assets/js/flower-apple-cinema.js' in txt
            for txt in (f4, f4_en)
        )
        result["cinema_only_flower4"] = all(
            '/assets/js/flower-apple-cinema.js' not in (ROOT / rel).read_text(encoding="utf-8")
            for rel in ("index.html", "en/index.html", "al-qaisumah/index.html")
        )
        motion_js = (ROOT / "assets/js/flower-apple-cinema.js").read_text(encoding="utf-8")
        motion_css = (ROOT / "assets/css/flower-apple-cinema.css").read_text(encoding="utf-8")
        result["cinema_accessible_and_throttled"] = all(
            token in motion_js + motion_css
            for token in ("prefers-reduced-motion", "requestAnimationFrame", "IntersectionObserver", "aria-hidden", "data-flower-cinema")
        ) and all(no not in motion_js for no in ("fetch(", "XMLHttpRequest", "https://"))
    if PREMIUM and not LUXURY:
        ar = BeautifulSoup(f4, "html.parser")
        en = BeautifulSoup(f4_en, "html.parser")
        result["premium_ar_en_cinema"] = all(
            len(q.select('#flower-cinema[data-flower-story="premium"] [data-cinema-scene]')) == 3
            for q in (ar,en)
        )
        result["premium_css_last"] = all(
            bool(q.head.find("link",href="/assets/css/flower-apple-premium-v17-3.css"))
            and (
                INTERACTIVE and
                q.head.find_all("link",rel="stylesheet")[-2].get("href") == "/assets/css/flower-apple-premium-v17-3.css"
                and q.head.find_all("link",rel="stylesheet")[-1].get("href") == "/assets/css/flower-interactive-v17-4.css"
                or not INTERACTIVE and
                q.head.find_all("link",rel="stylesheet")[-1].get("href") == "/assets/css/flower-apple-premium-v17-3.css"
            )
            for q in (ar,en)
        )
        result["premium_first_image_preloaded"] = all(
            (q.select_one(".flower-v16-hero-bg") or {}).get("fetchpriority") == "high"
            and (q.select_one(".flower-v16-hero-bg") or {}).get("loading") == "eager"
            for q in (ar,en)
        )
        result["premium_legacy_content_preserved"] = all(
            q.select_one('#book-branch') and q.select_one('#book-unit')
            and q.select_one('#book-whatsapp') and q.select_one('a[href*="booking.com"]')
            and len(q.select('h1')) == 1
            for q in (ar,en)
        )
        result["premium_no_unverified_images"] = all(
            image.get('src','').startswith('/assets/images/al-majmaah-harmah/')
            for q in (ar,en) for image in q.select('#flower-cinema img')
        )
        result["premium_mobile_and_reduced_motion"] = all(
            word in (ROOT / "assets/css/flower-apple-premium-v17-3.css").read_text(encoding="utf-8")
            for word in ('@media(max-width:700px)', 'prefers-reduced-motion', 'flower-cinema-stage')
        )
    if INTERACTIVE:
        docs = [BeautifulSoup(f4,"html.parser"), BeautifulSoup(f4_en,"html.parser")]
        result["interactive_bilingual_sections"] = all(
            len(q.select("#flower-interactive")) == 1 and
            len(q.select("#flower-interactive [data-fi-floor]")) == 4 and
            len(q.select("#flower-interactive [data-fi-choose]")) == 4 and
            len(q.select("#flower-interactive [data-fi-unit]")) == 3
            for q in docs
        )
        result["interactive_original_images_match_units"] = all(
            [i["src"] for i in q.select("#flower-interactive .fi-unit-card img")]
            == [i["src"] for i in q.select("#stay .v7-unit-media img")][:3]
            for q in docs
        )
        result["interactive_real_unit_detail_anchors"] = all(
            all(q.select_one("#flower-unit-choice-"+str(i)) for i in range(3))
            for q in docs
        )
        result["interactive_booking_google_untouched"] = all(
            q.select_one("#book-whatsapp") and q.select_one("#book-branch")
            and q.select_one('a[href*="booking.com"]') and
            q.select_one('[data-google-rating="flower-4"]')
            for q in docs
        )
        result["interactive_staging_only"] = all(
            "/assets/js/flower-interactive-v17-4.js" not in
            (ROOT / loc).read_text(encoding="utf-8")
            for loc in ("index.html","en/index.html","al-qaisumah/index.html")
        )
        result["interactive_accessible"] = all(
            p in (ROOT/"assets/js/flower-interactive-v17-4.js").read_text(encoding="utf-8")+
                 (ROOT/"assets/css/flower-interactive-v17-4.css").read_text(encoding="utf-8")
            for p in ("prefers-reduced-motion","aria-pressed","ArrowLeft","pointermove")
        )
    if LUXURY:
        ar = BeautifulSoup(f4,"html.parser")
        en = BeautifulSoup(f4_en,"html.parser")
        result["signature_two_languages"] = all(
            q.html.get("data-flower-signature") == "v18" and
            q.select_one(".lx-hero") and q.select_one(".lx-media img.flower-v16-hero-bg") and
            q.select_one("#flower-signature")
            for q in (ar,en)
        )
        result["signature_three_real_scenes"] = all(
            [node["src"] for node in q.select("#flower-signature .lx-chapter-photo")]
            == [scene["photo"] for scene in SCENES]
            for q in (ar,en)
        )
        result["signature_no_rejected_graphics_or_old_cinema"] = all(
            not q.select("#flower-interactive,#flower-cinema") and
            not q.find("script",src="/assets/js/flower-apple-cinema.js") and
            not q.find("script",src="/assets/js/flower-interactive-v17-4.js")
            for q in (ar,en)
        )
        result["signature_three_original_unit_cards"] = all(
            len(q.select("#stay .v7-unit.lx-unit")) == 3 and
            all(i.get("src","").startswith("/assets/images/al-majmaah-harmah/")
                for i in q.select("#stay .v7-unit-media img"))
            for q in (ar,en)
        )
        result["signature_booking_unmodified"] = all(
            q.select_one("#book-whatsapp") and q.select_one("#book-branch") and
            q.select_one("#book-unit") and q.select_one("#book-arrival") and
            q.select_one("#book-departure") and q.select_one('a[href*="booking.com"]')
            for q in (ar,en)
        )
        result["signature_logo_google_seo_preserved"] = all(
            q.select_one(".v7-logo img") and q.select_one('[data-google-rating="flower-4"]') and
            q.head.find("link", rel="canonical") and len(q.select("h1")) == 1
            for q in (ar,en)
        )
        result["signature_design_assets_last"] = all(
            q.head.find_all("link",rel="stylesheet")[-1].get("href") == "/assets/css/flower-signature-v18.css"
            and q.body.find("script",src="/assets/js/flower-signature-v18.js")
            for q in (ar,en)
        )
        style = (ROOT/"assets/css/flower-signature-v18.css").read_text(encoding="utf-8")
        result["signature_mobile_and_accessibility"] = all(
            token in style for token in (
                "#7A314D","#5B2038","#B79862","max-width:700px","prefers-reduced-motion"
            )
        )
        result["signature_home_and_other_branches_unchanged"] = all(
            'flower-signature-v18.css' not in (ROOT / p).read_text(encoding="utf-8")
            for p in ("index.html","en/index.html","al-qaisumah/index.html")
        )
    if not all(result.values()):
        raise SystemExit("build tests failed: " + json.dumps(result, ensure_ascii=False))
    return result


def build_zip() -> None:
    OUT_ZIP.parent.mkdir(parents=True, exist_ok=True)
    if OUT_ZIP.exists():
        OUT_ZIP.unlink()
    with zipfile.ZipFile(OUT_ZIP, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for path in sorted(ROOT.rglob("*")):
            if path.is_file():
                z.write(path, path.relative_to(ROOT).as_posix())


def main() -> None:
    pages = mirror_live_site()
    for url in pages:
        parsed = urllib.parse.urlsplit(url)
        path = local_path_for(url)
        patch_page(path, parsed.path or "/")
    write_live_assets()
    update_sitemap()
    test_result = tests()
    build_zip()
    manifest = {
        "schemaVersion": 1,
        "source": BASE,
        "variant": "flower-signature-v18-staging" if LUXURY else "flower-interactive-v17.4-staging" if INTERACTIVE else "apple-v17.3-premium-staging" if IS_PREMIUM_STAGING else "apple-v17.3-premium-production" if PREMIUM else "apple-v17.2-cinematic-staging" if IS_CINEMATIC_STAGING else "apple-v17.2-cinematic-production" if CINEMATIC else "apple-v17.1-motion-staging" if MOTION else "apple-v17" if APPLE else "editorial-v16-legacy",
        "builtAt": BUILD_DATE.isoformat(),
        "fileCount": sum(1 for p in ROOT.rglob("*") if p.is_file()),
        "zipBytes": OUT_ZIP.stat().st_size,
        "changes": [
            "automatic Google review metrics feed",
            "verified fallback Google counts for all four branches",
            "Flower 4 unit amenity de-generalization",
            "ThreeUI-inspired native CSS micro-interactions without React/WebGL",
            "sitemap lastmod refresh for home and Flower 4",
            *(['Apple-inspired FLOWER V17: 10 bilingual pages, photo-first heroes, booking UX, no preview toolbar, and single H1'] if APPLE else
              ['Legacy ThreeUI-inspired editorial preview for comparison only'])
        ],
        "tests": test_result,
    }
    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
