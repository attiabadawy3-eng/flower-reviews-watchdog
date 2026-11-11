"""FLOWER V21 search-visibility release.

Builds deploy-assets/flower-group-v21-seo.zip from the verified V20.1 production
zip (byte-identical to live on 2026-11-11). Only text/metadata changes:

- Arabic branch titles, meta descriptions and og:title target the queries
  people actually type (Search Console, Aug-Nov 2026): "فندق فلور ...",
  "شقق مخدومة/مفروشة ...", "يومي وشهري".
- H1 tagline (<em>) carries the main keyword; a space separates brand and
  tagline so the H1 text no longer reads "فلور السلامتفاصيل".
- Reviews heading names the branch ("آراء وتقييمات النزلاء ...").
- Three extra FAQ entries with facts already on the page (check-in/out,
  extended stays, location) + FAQPage JSON-LD for every FAQ (AR + EN).
- Organization JSON-LD gains description and links to the 4 branches.
- New /llms.txt for AI assistants; sitemap lastmod bumped and the ns0:
  prefix removed.

Photos, scripts, CSS, canonical URLs, booking and WhatsApp links are untouched.
"""
import hashlib
import json
import re
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "deploy-assets/flower-group-v20-1-almajmaah.zip"
OUT = ROOT / "deploy-assets/flower-group-v21-seo.zip"
MANIFEST = ROOT / "deploy-assets/flower-group-v21-seo-manifest.json"
SRC_SHA = "890f8ce2"  # prefix of the V20.1 zip that production serves
BASE = "https://flower-serviced-apartments-sa.onrender.com"
TODAY = "2026-11-12"

BRANCHES = {
    "dammam-al-anoud": {
        "title": "فلور العنود الدمام | شقق مخدومة ومفروشة يومي وشهري",
        "desc": "فلور العنود في حي العنود بالدمام: شقق مخدومة ومفروشة للإيجار اليومي والإقامة الطويلة. غرفة، غرفة وصالة، وغرفتان وصالة، استقبال 24 ساعة، واي فاي مجاني ومواقف.",
        "em_old": "مساحة هادئة في قلب الدمام.",
        "em_new": "شقق مخدومة ومفروشة في حي العنود بالدمام.",
        "reviews": "آراء وتقييمات النزلاء في فلور العنود",
        "place": "في حي العنود بالدمام، شارع الملك سعود بن عبدالعزيز بجوار محطة ساسكو",
    },
    "dammam-al-salam": {
        "title": "فندق فلور الدمام – حي السلام | شقق مخدومة ومفروشة يومي وشهري",
        "desc": "فلور السلام في حي السلام بالدمام: شقق مخدومة ومفروشة للإيجار اليومي والإقامة الطويلة، قريبة من كورنيش الدمام. غرفة، غرفة وصالة، وغرفتان وصالة، استقبال 24 ساعة ومواقف.",
        "em_old": "تفاصيل دافئة لإقامة أكثر راحة.",
        "em_new": "شقق مخدومة ومفروشة في حي السلام بالدمام.",
        "reviews": "آراء وتقييمات النزلاء في فلور السلام",
        "place": "في حي السلام بالدمام، 8202 شارع الثامن عشر، قريب من كورنيش وسط الدمام",
    },
    "al-qaisumah": {
        "title": "فندق فلور القيصومة | شقق مخدومة ومفروشة يومي وشهري",
        "desc": "فلور القيصومة على طريق الملك عبدالعزيز مقابل البلدية: شقق مخدومة ومفروشة للإيجار اليومي والإقامة الطويلة قرب حفر الباطن. استقبال 24 ساعة، واي فاي مجاني ومواقف.",
        "em_old": "اختيار مريح لكل تفاصيل الرحلة.",
        "em_new": "شقق مخدومة ومفروشة على طريق الملك عبدالعزيز.",
        "reviews": "آراء وتقييمات النزلاء في فلور القيصومة",
        "place": "في القيصومة على طريق الملك عبدالعزيز مقابل البلدية",
    },
    "al-majmaah-harmah": {
        "title": "فندق فلور المجمعة – حرمة | شقق مخدومة ومفروشة",
        "desc": "فندق فلور المجمعة في حرمة: شقق مخدومة ومفروشة للإيجار اليومي والإقامة الطويلة. غرفة، غرفة وصالة، وغرفتان وصالة، استقبال 24 ساعة. اقرأ تعليقات النزلاء وتقييمات Google.",
        "em_old": "إقامتك في حرمة بطابع مختلف.",
        "em_new": "شقق مخدومة ومفروشة في حرمة – المجمعة.",
        "reviews": "تعليقات وتقييمات النزلاء في فلور المجمعة",
        "place": "في حرمة بالمجمعة، LMPA9275، 9275 2306، حرمة 15363",
    },
}
REVIEWS_OLD_AR = "<h2>ثقة الضيوف على Google</h2>"


def once(s, old, new, label):
    n = s.count(old)
    if n != 1:
        sys.exit(f"FAIL {label}: expected 1 match, found {n}: {old[:80]!r}")
    return s.replace(old, new)


def html_text(x):
    return re.sub(r"<[^>]+>", "", x).replace("&amp;", "&").strip()


def faq_jsonld(s, page_url, lang):
    pairs = re.findall(r"<details><summary>(.*?)</summary><p>(.*?)</p></details>", s, re.S)
    assert len(pairs) >= 4, page_url
    data = {
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "@id": page_url + "#faq",
        "inLanguage": lang,
        "mainEntity": [
            {"@type": "Question", "name": html_text(q),
             "acceptedAnswer": {"@type": "Answer", "text": html_text(a)}}
            for q, a in pairs
        ],
    }
    tag = '<script type="application/ld+json">' + json.dumps(data, ensure_ascii=False, separators=(",", ":")) + "</script>"
    return once(s, "</head>", tag + "</head>", "faq-jsonld " + page_url), len(pairs)


def extra_faq_ar(info):
    items = [
        ("هل يتوفر إيجار يومي وشهري؟",
         "نعم، الشقق مناسبة للإقامة القصيرة باليوم وللإقامة الممتدة. للأسعار الشهرية تواصل مع الفرع مباشرة عبر واتساب."),
        ("ما مواعيد تسجيل الدخول والخروج؟",
         "تسجيل الدخول من الساعة 4 عصرًا، وتسجيل الخروج حتى الساعة 2 ظهرًا، والاستقبال متاح 24 ساعة."),
        ("أين يقع الفرع؟", "يقع الفرع " + info["place"] + "."),
    ]
    return "".join(f"<details><summary>{q}</summary><p>{a}</p></details>" for q, a in items)


EXTRA_FAQ_EN = (
    "<details><summary>Do you offer daily and monthly stays?</summary><p>Yes. The apartments suit short daily stays and extended stays. For monthly rates, contact the branch directly on WhatsApp.</p></details>"
    "<details><summary>What are the check-in and check-out times?</summary><p>Check-in is from 4:00 PM and check-out is until 2:00 PM. Reception is open 24 hours.</p></details>"
)

LAST_FAQ_AR = "<details><summary>كيف أتحقق من التوفر؟</summary>"
LAST_FAQ_EN = "<details><summary>How do I confirm availability?</summary>"

LLMS_TXT = f"""# FLOWER Serviced Apartments (فلور للشقق المخدومة)

> FLOWER (فلور، وتُعرف أيضًا بـ"فندق فلور" و"شقق فلور الخليجية للشقق المخدومة") is a group of serviced, furnished apartments in Saudi Arabia with four branches: Al Anoud and Al Salam in Dammam, Al Qaisumah, and Harmah in Al Majmaah. Every branch offers 24-hour reception, free Wi-Fi, parking, kitchens and housekeeping, for daily or extended (monthly) stays. Check-in 4:00 PM, check-out 2:00 PM.

## Branches (Arabic pages)

- [فلور العنود – الدمام]({BASE}/dammam-al-anoud/): Al Anoud district, King Saud bin Abdulaziz St, next to SASCO station, Dammam 32426. Phone/WhatsApp +966559366744. Google rating 4.8 (117 reviews).
- [فلور السلام – الدمام]({BASE}/dammam-al-salam/): Al Salam district, 8202 Eighteenth St, Dammam 32416, near the Dammam Corniche. Phone/WhatsApp +966567780349. Google rating 4.5 (263 reviews).
- [فلور القيصومة]({BASE}/al-qaisumah/): King Abdulaziz Road opposite the municipality, Al Qaisumah (Hafr Al-Batin area). Phone/WhatsApp +966573644047. Google rating 4.6 (57 reviews).
- [فلور المجمعة – حرمة]({BASE}/al-majmaah-harmah/): Harmah, Al Majmaah 15363. Phone/WhatsApp +966566374274. Google rating 4.6 (142 reviews).

## English pages

- [FLOWER home]({BASE}/en/)
- [FLOWER Al Anoud, Dammam]({BASE}/en/dammam-al-anoud/)
- [FLOWER Al Salam, Dammam]({BASE}/en/dammam-al-salam/)
- [FLOWER Al Qaisumah]({BASE}/en/al-qaisumah/)
- [FLOWER Al Majmaah – Harmah]({BASE}/en/al-majmaah-harmah/)

## Unit types

- Room (غرفة)
- One bedroom + living room (غرفة وصالة)
- Two bedrooms + living room (غرفتان وصالة)

## Booking

Availability and prices are confirmed directly with each branch on WhatsApp (links on each branch page) or through the branch's Booking.com page. Ratings above were checked on Google on {TODAY}.

## Optional

- [Privacy policy]({BASE}/privacy/)
"""


def main():
    src_bytes = SRC.read_bytes()
    src_sha = hashlib.sha256(src_bytes).hexdigest()
    if not src_sha.startswith(SRC_SHA):
        sys.exit(f"FAIL source zip sha {src_sha} does not match V20.1")
    zin = zipfile.ZipFile(SRC)
    files = {i.filename: zin.read(i.filename) for i in zin.infolist() if not i.is_dir()}
    changed, report = [], {}

    for slug, info in BRANCHES.items():
        p = f"{slug}/index.html"
        s = files[p].decode("utf-8")
        old_title = re.search(r"<title>(.*?)</title>", s).group(1)
        s = once(s, f"<title>{old_title}</title>", f"<title>{info['title']}</title>", p + " title")
        s = once(s, f'<meta content="{old_title}" property="og:title"/>',
                 f'<meta content="{info["title"]}" property="og:title"/>', p + " og:title")
        old_desc = re.search(r'<meta content="([^"]*)" name="description"/>', s).group(1)
        s = once(s, f'<meta content="{old_desc}" name="description"/>',
                 f'<meta content="{info["desc"]}" name="description"/>', p + " desc")
        s = once(s, f'<meta content="{old_desc}" property="og:description"/>',
                 f'<meta content="{info["desc"]}" property="og:description"/>', p + " og:desc")
        s = once(s, f"</span><em>{info['em_old']}</em></h1>",
                 f"</span> <em>{info['em_new']}</em></h1>", p + " h1")
        s = once(s, REVIEWS_OLD_AR, f"<h2>{info['reviews']}</h2>", p + " reviews h2")
        s = once(s, LAST_FAQ_AR, extra_faq_ar(info) + LAST_FAQ_AR, p + " faq")
        s, n = faq_jsonld(s, f"{BASE}/{slug}/", "ar")
        files[p] = s.encode("utf-8")
        changed.append(p)
        report[p] = {"title": info["title"], "faqCount": n}

        pe = f"en/{slug}/index.html"
        e = files[pe].decode("utf-8")
        e = once(e, "</span><em>", "</span> <em>", pe + " h1 space")
        e = once(e, LAST_FAQ_EN, EXTRA_FAQ_EN + LAST_FAQ_EN, pe + " faq")
        e, n = faq_jsonld(e, f"{BASE}/en/{slug}/", "en")
        files[pe] = e.encode("utf-8")
        changed.append(pe)
        report[pe] = {"faqCount": n}

    # Home pages: H1 spacing + richer Organization entity
    for p, lang in (("index.html", "ar"), ("en/index.html", "en")):
        s = files[p].decode("utf-8")
        s = once(s, "</span><em>", "</span> <em>", p + " h1 space")
        m = re.search(r'<script type="application/ld\+json">(\{"@context":"https://schema.org","@graph".*?)</script>', s, re.S)
        graph = json.loads(m.group(1))
        org = next(x for x in graph["@graph"] if x["@type"] == "Organization")
        org["description"] = (
            "فلور للشقق المخدومة: شقق مخدومة ومفروشة في الدمام (العنود والسلام) والقيصومة والمجمعة (حرمة)، للإيجار اليومي والإقامة الطويلة، مع استقبال 24 ساعة."
            if lang == "ar" else
            "FLOWER Serviced Apartments: furnished serviced apartments in Dammam (Al Anoud, Al Salam), Al Qaisumah and Al Majmaah (Harmah) for daily and extended stays, with 24-hour reception."
        )
        org["areaServed"] = ["Dammam", "Al Qaisumah", "Al Majmaah"]
        org["subOrganization"] = [{"@id": f"{BASE}/{slug}/#business"} for slug in BRANCHES]
        new = json.dumps(graph, ensure_ascii=False, separators=(",", ":"))
        s = once(s, m.group(1), new, p + " org")
        files[p] = s.encode("utf-8")
        changed.append(p)

    # Sitemap: default namespace + fresh lastmod for changed pages
    sm = files["sitemap.xml"].decode("utf-8").replace("ns0:", "").replace("xmlns:ns0=", "xmlns=")
    def bump(mo):
        loc = mo.group(1)
        return f"<url><loc>{loc}</loc><lastmod>{TODAY}</lastmod></url>"
    sm = re.sub(r"<url><loc>([^<]*)</loc>(?:<lastmod>[^<]*</lastmod>)?</url>",
                lambda mo: bump(mo) if "privacy" not in mo.group(1) else mo.group(0), sm)
    files["sitemap.xml"] = sm.encode("utf-8")
    changed.append("sitemap.xml")

    files["llms.txt"] = LLMS_TXT.encode("utf-8")
    changed.append("llms.txt")

    # Invariants: canonical, hreflang, links, scripts and images unchanged
    for p in files:
        if not p.endswith(".html"):
            continue
        a, b = zin.read(p).decode("utf-8"), files[p].decode("utf-8")
        for pat in (r'rel="canonical"[^>]*>', r'<link[^>]*hreflang[^>]*>', r'href="https://(?:wa\.me|api\.whatsapp|www\.booking)[^"]*"',
                    r"<img[^>]*>", r"<script src=[^>]*>", r'<link[^>]*stylesheet[^>]*>'):
            if re.findall(pat, a) != re.findall(pat, b):
                sys.exit(f"FAIL invariant {pat} changed in {p}")
        assert b.count("<h1") == 1, p
        for blk in re.findall(r'<script type="application/ld\+json">(.*?)</script>', b, re.S):
            json.loads(blk)

    with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as z:
        for name in sorted(files):
            info = zipfile.ZipInfo(name, date_time=(2026, 11, 12, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            z.writestr(info, files[name])

    out_sha = hashlib.sha256(OUT.read_bytes()).hexdigest()
    MANIFEST.write_text(json.dumps({
        "release": "FLOWER V21 search visibility",
        "builtFrom": SRC.name, "builtFromSha256": src_sha,
        "zip": OUT.name, "sha256": out_sha, "fileCount": len(files),
        "changedFiles": changed, "pages": report,
        "checksPassed": True, "canonicalURLsUnchanged": True,
        "bookingAndWhatsAppUnchanged": True, "photosAndScriptsUnchanged": True,
        "rollbackZip": SRC.name,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("FLOWER V21 SEO BUILD PASS", out_sha, len(changed), "files changed")


if __name__ == "__main__":
    main()
