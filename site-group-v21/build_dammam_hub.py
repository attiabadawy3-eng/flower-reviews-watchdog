"""FLOWER V21.1: Dammam hub page (/dammam/ and /en/dammam/).

Built on top of the live V21 zip. The hub targets the generic searches where
the two Dammam branches currently split Google's attention ("شقق مفروشة الدمام",
"شقق مخدومة الدمام", "... شهري"), and links both branches. It reuses the home
page template (same CSS/JS bundles), keeping only Dammam photos, branches,
booking options and ratings. Every other page only gains a footer link.
"""
import copy
import hashlib
import json
import re
import sys
import zipfile
from pathlib import Path

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "deploy-assets/flower-group-v21-seo.zip"
SRC_SHA = "06d9877f"
OUT = ROOT / "deploy-assets/flower-group-v21-1-dammam.zip"
MANIFEST = ROOT / "deploy-assets/flower-group-v21-1-dammam-manifest.json"
BASE = "https://flower-serviced-apartments-sa.onrender.com"
TODAY = "2026-11-12"
IMG = "/assets/images/{}/enhanced/{}-enhanced.webp"
DAMMAM = ("dammam-al-anoud", "dammam-al-salam")

T = {
    "ar": {
        "path": "/dammam/", "home": "/", "other": "/en/dammam/", "other_label": "English",
        "title": "شقق مفروشة في الدمام | شقق مخدومة يومي وشهري – فلور العنود والسلام",
        "desc": "شقق مفروشة ومخدومة في الدمام للإيجار اليومي والشهري: فرعا فلور في حي العنود وحي السلام. غرفة، غرفة وصالة، وغرفتان وصالة، استقبال 24 ساعة، واي فاي مجاني ومواقف.",
        "h1": "شقق مفروشة في الدمام", "em": "مخدومة يوميًا وشهريًا في العنود والسلام.",
        "lead": "فرعان لفلور في الدمام: حي العنود وحي السلام. شقق مفروشة بالكامل مع خدمة فندقية واستقبال على مدار الساعة، للإقامة القصيرة أو الطويلة.",
        "facts": ["فرعان في الدمام", "استقبال 24 ساعة", "يومي وشهري"],
        "captions": ["العنود · الدمام", "السلام · الدمام", "العنود · الدمام", "السلام · الدمام"],
        "alt": "صورة حقيقية من فلور: {}",
        "ed_kicker": "فلور في الدمام", "ed_h2": "شقتك في الدمام جاهزة.",
        "ed_p": "صور حقيقية من فرعي العنود والسلام.",
        "br_kicker": "فروع الدمام", "br_h2": "اختر بين العنود والسلام",
        "br_p": "الفرعان يقدمان نفس أنواع الوحدات والخدمات؛ الفرق في الموقع داخل الدمام.",
        "card": {
            "dammam-al-anoud": "شارع الملك سعود بن عبدالعزيز بجوار محطة ساسكو، حي العنود. هادئ وقريب من الطرق الرئيسية.",
            "dammam-al-salam": "8202 شارع الثامن عشر، حي السلام. قريب من كورنيش وسط الدمام والخدمات اليومية.",
        },
        "about_kicker": "الإيجار الشهري", "about_h2": "شقق مفروشة في الدمام للإيجار الشهري",
        "about_lead": "لو إقامتك في الدمام أسبوع أو شهر أو أكثر، شقق فلور مناسبة للإقامة الممتدة: مطبخ مجهز، غسالة، تكييف، واي فاي مجاني، وتنظيف.",
        "about_p": "للأسعار الشهرية والعروض، تواصل مع الفرع مباشرة عبر واتساب: العنود {} · السلام {}.",
        "pills": ["حي العنود، الدمام 32426", "حي السلام، الدمام 32416", "الدخول 4:00 م · الخروج 2:00 م"],
        "faq_h2": "أسئلة شائعة عن شقق فلور في الدمام",
        "faq": [
            ("كم فرع لفلور في الدمام؟", "فرعان: فلور العنود في حي العنود على شارع الملك سعود بن عبدالعزيز، وفلور السلام في حي السلام على شارع الثامن عشر."),
            ("هل يتوفر إيجار شهري في الدمام؟", "نعم، الشقق مناسبة للإقامة اليومية والإقامة الممتدة. للأسعار الشهرية تواصل مع الفرع عبر واتساب."),
            ("ما أنواع الشقق المتاحة؟", "غرفة، غرفة وصالة، وغرفتان وصالة في الفرعين."),
            ("ما الخدمات المتاحة؟", "استقبال 24 ساعة، واي فاي مجاني، مواقف سيارات، مطبخ، غسالة، تكييف، مصعد، وخدمة تنظيف."),
            ("ما مواعيد الدخول والخروج؟", "تسجيل الدخول من الساعة 4 عصرًا، وتسجيل الخروج حتى الساعة 2 ظهرًا."),
            ("كيف أحجز؟", "اختر الفرع ونوع الوحدة والتواريخ في نموذج الاستفسار أعلى الصفحة، ثم أرسل طلبك عبر واتساب أو افتح صفحة الفرع على Booking.com."),
        ],
        "rev_h2": "تقييمات فروع فلور في الدمام على Google",
        "crumbs": ["فلور", "شقق مفروشة في الدمام"],
        "footer": "شقق مفروشة في الدمام",
        "footer_anchor": '<a href="/dammam-al-anoud/">الدمام · العنود</a>',
    },
    "en": {
        "path": "/en/dammam/", "home": "/en/", "other": "/dammam/", "other_label": "العربية",
        "title": "Furnished Apartments in Dammam | Daily & Monthly Serviced Apartments – FLOWER",
        "desc": "Furnished serviced apartments in Dammam for daily and monthly stays: FLOWER Al Anoud and FLOWER Al Salam. Room, one- and two-bedroom units, 24-hour reception, free Wi-Fi and parking.",
        "h1": "Furnished Apartments in Dammam", "em": "Serviced daily and monthly in Al Anoud and Al Salam.",
        "lead": "Two FLOWER branches in Dammam, Al Anoud and Al Salam. Fully furnished apartments with hotel-style service and 24-hour reception, for short or extended stays.",
        "facts": ["2 DAMMAM BRANCHES", "24-HOUR RECEPTION", "DAILY & MONTHLY"],
        "captions": ["Al Anoud · Dammam", "Al Salam · Dammam", "Al Anoud · Dammam", "Al Salam · Dammam"],
        "alt": "Real photo from FLOWER: {}",
        "ed_kicker": "FLOWER IN DAMMAM", "ed_h2": "Your Dammam apartment, ready.",
        "ed_p": "Real photos from the Al Anoud and Al Salam branches.",
        "br_kicker": "DAMMAM BRANCHES", "br_h2": "Choose Al Anoud or Al Salam",
        "br_p": "Both branches offer the same unit types and services; the difference is where you stay in Dammam.",
        "card": {
            "dammam-al-anoud": "King Saud bin Abdulaziz St, next to SASCO station, Al Anoud. Quiet and close to main roads.",
            "dammam-al-salam": "8202 Eighteenth St, Al Salam. Close to the central Dammam Corniche and daily services.",
        },
        "about_kicker": "MONTHLY STAYS", "about_h2": "Monthly furnished apartments in Dammam",
        "about_lead": "Staying in Dammam for a week, a month or longer? FLOWER apartments suit extended stays: equipped kitchen, washing machine, air conditioning, free Wi-Fi and housekeeping.",
        "about_p": "For monthly rates and offers, contact the branch on WhatsApp: Al Anoud {} · Al Salam {}.",
        "pills": ["Al Anoud, Dammam 32426", "Al Salam, Dammam 32416", "Check-in 4:00 PM · Check-out 2:00 PM"],
        "faq_h2": "FAQ: FLOWER apartments in Dammam",
        "faq": [
            ("How many FLOWER branches are in Dammam?", "Two: FLOWER Al Anoud on King Saud bin Abdulaziz St, and FLOWER Al Salam on Eighteenth St."),
            ("Do you offer monthly stays in Dammam?", "Yes. The apartments suit daily and extended stays. Contact the branch on WhatsApp for monthly rates."),
            ("What unit types are available?", "Room, one bedroom + living room, and two bedrooms + living room at both branches."),
            ("What services are included?", "24-hour reception, free Wi-Fi, parking, kitchen, washing machine, air conditioning, lift and housekeeping."),
            ("What are the check-in and check-out times?", "Check-in from 4:00 PM, check-out until 2:00 PM."),
            ("How do I book?", "Choose the branch, unit type and dates in the enquiry form above, then send it on WhatsApp or open the branch's Booking.com page."),
        ],
        "rev_h2": "Google ratings for FLOWER in Dammam",
        "crumbs": ["FLOWER", "Furnished apartments in Dammam"],
        "footer": "Furnished apartments in Dammam",
        "footer_anchor": '<a href="/en/dammam-al-anoud/">Dammam · Al Anoud</a>',
    },
}
PHONES = {"dammam-al-anoud": "+966559366744", "dammam-al-salam": "+966567780349"}
def wa(n):
    return f'<a dir="ltr" href="https://wa.me/{n.lstrip("+")}" rel="noopener" target="_blank">0{n[4:]}</a>'


SLIDES = [("dammam-al-anoud", "06"), ("dammam-al-salam", "05"), ("dammam-al-anoud", "03"), ("dammam-al-salam", "03")]


def tag(soup, name, attrs=None, text=None):
    t = soup.new_tag(name, attrs=attrs or {})
    if text is not None:
        t.string = text
    return t


def one(soup, sel):
    r = soup.select(sel)
    if len(r) != 1:
        sys.exit(f"FAIL selector {sel}: {len(r)} matches")
    return r[0]


def build(lang, home_html):
    t = T[lang]
    url = BASE + t["path"]
    soup = BeautifulSoup(home_html, "html.parser")
    head = soup.head

    one(soup, "title").string = t["title"]
    for sel, val in (('meta[name="description"]', t["desc"]), ('meta[property="og:description"]', t["desc"]),
                     ('meta[property="og:title"]', t["title"]), ('meta[property="og:url"]', url)):
        one(soup, sel)["content"] = val
    one(soup, 'link[rel="canonical"]')["href"] = url
    hl = {"ar": BASE + "/dammam/", "en": BASE + "/en/dammam/", "x-default": BASE + "/dammam/"}
    for l in soup.select("link[hreflang]"):
        l["href"] = hl[l["hreflang"]]
    hero_img = IMG.format("dammam-al-salam", "05")
    one(soup, 'link[rel="preload"][as="image"]')["href"] = hero_img
    for sel in ('meta[property="og:image"]', 'meta[name="twitter:image"]'):
        one(soup, sel)["content"] = BASE + hero_img

    # Structured data: replace the home graph
    ld = one(soup, 'script[type="application/ld+json"]')
    graph = {"@context": "https://schema.org", "@graph": [
        {"@type": "CollectionPage", "@id": url + "#page", "url": url, "name": t["title"],
         "description": t["desc"], "inLanguage": "ar-SA" if lang == "ar" else "en",
         "isPartOf": {"@id": BASE + "/#website"}, "about": {"@type": "City", "name": "Dammam" if lang == "en" else "الدمام"},
         "mainEntity": {"@type": "ItemList", "numberOfItems": 2, "itemListElement": [
             {"@type": "ListItem", "position": i + 1, "url": f"{BASE}/{s}/", "item": {"@id": f"{BASE}/{s}/#business"}}
             for i, s in enumerate(DAMMAM)]}},
        {"@type": "BreadcrumbList", "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": t["crumbs"][0], "item": BASE + t["home"]},
            {"@type": "ListItem", "position": 2, "name": t["crumbs"][1], "item": url}]},
        {"@type": "FAQPage", "@id": url + "#faq", "mainEntity": [
            {"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in t["faq"]]},
    ]}
    ld.string = json.dumps(graph, ensure_ascii=False, separators=(",", ":"))

    one(soup, "a.v7-lang")["href"] = t["other"]
    one(soup, "a.v7-lang").string = t["other_label"]

    # Hero
    h1 = one(soup, "h1")
    h1.span.string = t["h1"]
    h1.em.string = t["em"]
    one(soup, "p.fx19-hero-description").string = t["lead"]
    for s, txt in zip(one(soup, "div.fx19-hero-facts").find_all("span"), t["facts"]):
        s.string = txt
    figs = soup.select("figure.flv-slide")
    assert len(figs) == 4
    for f, (b, n), cap in zip(figs, SLIDES, t["captions"]):
        f.img["src"] = IMG.format(b, n)
        f.img["alt"] = t["alt"].format(cap)
        f.figcaption.string = cap
    one(soup, "div.flv-preview img")["src"] = IMG.format("dammam-al-anoud", "06")
    one(soup, "p.flv-active-caption").string = t["captions"][0]

    # Booking: Dammam branches only
    for o in one(soup, "#book-branch").find_all("option"):
        if o["value"] not in DAMMAM:
            o.decompose()

    # Editorial photo strip
    ed = one(soup, "section.fx19-editorial")
    ed.select_one(".fx19-overline-dark").string = t["ed_kicker"]
    ed.h2.string = t["ed_h2"]
    ed.select_one(".fx19-editorial-head p").string = t["ed_p"]
    for f, (b, n), cap in zip(ed.find_all("figure"), [("dammam-al-anoud", "06"), ("dammam-al-salam", "05"), ("dammam-al-anoud", "04")], t["captions"][:2] + [t["captions"][0]]):
        f.img["src"] = IMG.format(b, n)
        f.img["alt"] = cap
        f.figcaption.string = cap

    # Branch cards
    br = one(soup, "#branches")
    br.select_one(".v7-kicker").string = t["br_kicker"]
    br.h2.string = t["br_h2"]
    br.select_one(".v7-section-head p").string = t["br_p"]
    for card in br.select("article.branch-card"):
        href = card.a["href"].strip("/").split("/")[-1]
        if href not in DAMMAM:
            card.decompose()
        else:
            card.select_one(".v7-branch-copy p").string = t["card"][href]

    # New sections after branches: monthly stays + FAQ
    about = BeautifulSoup(
        f'<section class="v7-section v8-about" id="monthly"><div class="wrap v8-about-grid"><div>'
        f'<span class="v7-kicker">{t["about_kicker"]}</span><h2>{t["about_h2"]}</h2></div><div>'
        f'<p class="v7-lead">{t["about_lead"]}</p><p>{t["about_p"].format(*(wa(PHONES[k]) for k in DAMMAM))}</p>'
        f'<div class="v7-pills">{"".join(f"<span>{p}</span>" for p in t["pills"])}</div></div></div></section>'
        f'<section class="v7-section v7-policy" id="faq"><div class="wrap"><div class="faq">'
        f'<span class="v7-kicker">FAQ</span><h2>{t["faq_h2"]}</h2>'
        + "".join(f"<details><summary>{q}</summary><p>{a}</p></details>" for q, a in t["faq"])
        + "</div></div></section>", "html.parser")
    br.insert_after(about)

    # Units: swap the non-Dammam photo
    for img in soup.select("#stay img"):
        if "dammam" not in img["src"]:
            img["src"] = IMG.format("dammam-al-anoud", "04")
            img["alt"] = "فلور العنود - صالة معيشة" if lang == "ar" else "FLOWER Al Anoud - living room"

    # Gallery mixes all branches: drop it on the Dammam page
    one(soup, "#gallery").decompose()

    # Reviews: Dammam only
    rv = one(soup, "#reviews")
    rv.h2.string = t["rev_h2"]
    for card in rv.select("article.v7-review-card"):
        key = card.select_one("[data-google-rating]")["data-google-rating"]
        if key not in ("flower-1", "flower-2"):
            card.decompose()

    out = str(soup)
    assert "al-qaisumah/enhanced" not in out and "harmah" not in out.split("<footer")[0].split("</head>")[1], "non-Dammam leftovers"
    return out


def add_footer_link(html, lang):
    t = T[lang]
    a = t["footer_anchor"]
    if html.count(a) < 1 or f'href="{t["path"]}"' in html.split("<footer")[-1]:
        return html, False
    i = html.rfind(a)
    if html.rfind("<footer", 0, i) == -1:
        return html, False
    return html[:i] + f'<a href="{t["path"]}">{t["footer"]}</a>' + html[i:], True


def main():
    sha = hashlib.sha256(SRC.read_bytes()).hexdigest()
    if not sha.startswith(SRC_SHA):
        sys.exit(f"FAIL source {sha}")
    zin = zipfile.ZipFile(SRC)
    files = {i.filename: zin.read(i.filename) for i in zin.infolist() if not i.is_dir()}
    changed = []

    files["dammam/index.html"] = build("ar", files["index.html"].decode("utf-8")).encode("utf-8")
    files["en/dammam/index.html"] = build("en", files["en/index.html"].decode("utf-8")).encode("utf-8")
    changed += ["dammam/index.html", "en/dammam/index.html"]

    for p in list(files):
        if not p.endswith("index.html") or p.startswith("dammam/") or p.startswith("en/dammam/"):
            continue
        lang = "en" if p.startswith("en/") else "ar"
        html, ok = add_footer_link(files[p].decode("utf-8"), lang)
        if ok:
            files[p] = html.encode("utf-8")
            changed.append(p)

    # Home pages: link the hub from the branches intro
    for p, txt, path in (("index.html", "كل شقق فلور في الدمام ←", "/dammam/"), ("en/index.html", "All FLOWER apartments in Dammam →", "/en/dammam/")):
        s = files[p].decode("utf-8")
        old = '</p></div><div class="v7-branch-grid">'
        assert s.count(old) == 1, p
        s = s.replace(old, f' <a class="v7-text-link" href="{path}">{txt}</a></p></div><div class="v7-branch-grid">')
        files[p] = s.encode("utf-8")

    sm = files["sitemap.xml"].decode("utf-8")
    add = "".join(f"<url><loc>{BASE}{p}</loc><lastmod>{TODAY}</lastmod></url>" for p in ("/dammam/", "/en/dammam/"))
    sm = sm.replace("</urlset>", add + "</urlset>")
    files["sitemap.xml"] = sm.encode("utf-8")
    llms = files["llms.txt"].decode("utf-8")
    llms = llms.replace("## Branches (Arabic pages)\n",
                        f"## Branches (Arabic pages)\n\n- [شقق مفروشة في الدمام – فرعا العنود والسلام]({BASE}/dammam/): overview of both Dammam branches, monthly stays and FAQ.\n")
    llms = llms.replace("## English pages\n", f"## English pages\n\n- [Furnished apartments in Dammam]({BASE}/en/dammam/)\n")
    # Ratings from public/reviews-summary.json on main (verifiedAt 2026-11-04)
    for a, b in (("4.8 (117 reviews)", "4.8 (125 reviews)"), ("4.5 (263 reviews)", "4.5 (286 reviews)"),
                 ("4.6 (57 reviews)", "4.6 (58 reviews)"), ("4.6 (142 reviews)", "4.6 (166 reviews)"),
                 ("Ratings above were checked on Google on 2026-11-12.", "Ratings above come from the branches' Google Business Profiles, verified 2026-11-04; the live site shows the latest values.")):
        assert llms.count(a) == 1, a
        llms = llms.replace(a, b)
    files["llms.txt"] = llms.encode("utf-8")
    changed += ["sitemap.xml", "llms.txt"]

    for p in files:
        if p.endswith(".html"):
            b = files[p].decode("utf-8")
            for blk in re.findall(r'<script type="application/ld\+json">(.*?)</script>', b, re.S):
                json.loads(blk)
            assert b.count("<h1") == 1, p
    for src in re.findall(r'src="(/assets/[^"]+)"', files["dammam/index.html"].decode() + files["en/dammam/index.html"].decode()):
        assert src.lstrip("/") in files, "missing asset " + src

    with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as z:
        for name in sorted(files):
            zi = zipfile.ZipInfo(name, date_time=(2026, 11, 12, 0, 0, 0))
            zi.compress_type = zipfile.ZIP_DEFLATED
            zi.external_attr = 0o644 << 16
            z.writestr(zi, files[name])
    out_sha = hashlib.sha256(OUT.read_bytes()).hexdigest()
    MANIFEST.write_text(json.dumps({
        "release": "FLOWER V21.1 Dammam hub", "builtFrom": SRC.name, "builtFromSha256": sha,
        "zip": OUT.name, "sha256": out_sha, "fileCount": len(files), "changedFiles": sorted(set(changed)),
        "newPages": ["/dammam/", "/en/dammam/"], "rollbackZip": SRC.name, "checksPassed": True,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("FLOWER V21.1 DAMMAM HUB BUILD PASS", out_sha, len(set(changed)), "files changed")


if __name__ == "__main__":
    main()
