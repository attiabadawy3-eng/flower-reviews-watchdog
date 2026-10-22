#!/usr/bin/env python3
"""Create isolated FLOWER V19 staging archive from LIVE staging, retaining V18 assets.

Only two injected assets change HTML. Production is never read as a build target
and neither existing Render service is modified by this script.
"""
from __future__ import annotations

import hashlib
import json
import pathlib
import re
import shutil
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from collections import deque

from bs4 import BeautifulSoup
from flower_editorial_v19_1 import apply_editorial, PAGES as EDITORIAL_PAGES, IMAGES as EDITORIAL_IMAGES

STAGE = "https://flower-unified-staging.onrender.com"
ROOT = pathlib.Path("/tmp/flower-motion-v19-snapshot")
ZIP_PATH = pathlib.Path("deploy-assets/flower-motion-v19-staging.zip")
MANIFEST = pathlib.Path("deploy-assets/flower-motion-v19-manifest.json")
V18_ARCHIVE = ("https://raw.githubusercontent.com/attiabadawy3-eng/"
              "flower-reviews-watchdog/0eea80a6d12d4fdcd07f5b194077e227c2bd48c2/"
              "deploy-assets/flower-signature-v18-staging.zip")
STYLES = "site-motion-v19/flower-motion-v19.css"
SCRIPTS = "site-motion-v19/flower-motion-v19.js"
STYLE_TAG = '<link rel="stylesheet" href="/assets/css/flower-motion-v19.css" data-flower-motion-v19="css">'
SCRIPT_TAG = '<script defer src="/assets/js/flower-motion-v19.js" data-flower-motion-v19="js"></script>'
PATHS = [
    "/", "/en/",
    "/dammam-al-anoud/", "/en/dammam-al-anoud/",
    "/dammam-al-salam/", "/en/dammam-al-salam/",
    "/al-qaisumah/", "/en/al-qaisumah/",
    "/al-majmaah-harmah/", "/en/al-majmaah-harmah/"
]

def read(url: str, timeout: int = 45) -> bytes:
    q = urllib.request.Request(url, headers={"User-Agent": "FLOWER-Motion-V19-Staging/1.0"})
    with urllib.request.urlopen(q, timeout=timeout) as response:
        data = response.read()
        if not data:
            raise RuntimeError(f"Empty response: {url}")
        return data

def html_output(path: str) -> pathlib.Path:
    return ROOT / path.lstrip("/") / "index.html"

def asset_path(value: str, base: str) -> str | None:
    if not value or value.startswith(("data:", "#", "javascript:", "mailto:", "tel:")):
        return None
    target = urllib.parse.urlsplit(urllib.parse.urljoin(base, value))
    if target.scheme != "https" or target.netloc != urllib.parse.urlsplit(STAGE).netloc:
        return None
    path = urllib.parse.unquote(target.path)
    if not path.startswith("/assets/") or ".." in pathlib.PurePosixPath(path).parts:
        return None
    return path

def referenced_assets(html: str, page_url: str) -> set[str]:
    result: set[str] = set()
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup.find_all(True):
        for key in ("src", "href", "poster", "data-src", "data-background"):
            if tag.has_attr(key):
                p = asset_path(str(tag.get(key)), page_url)
                if p:
                    result.add(p)
        for key in ("srcset", "data-srcset"):
            if tag.has_attr(key):
                for entry in str(tag[key]).split(","):
                    p = asset_path(entry.strip().split(" ")[0], page_url)
                    if p:
                        result.add(p)
    result.update(extract_asset_literals(html, page_url))
    return result

def extract_asset_literals(text: str, base: str) -> set[str]:
    out: set[str] = set()
    # Capture CSS url(...) references and explicit /assets/... strings.
    for hit in re.findall(r"url\(\s*['\"]?([^)'\"\s]+)", text, flags=re.I):
        p = asset_path(hit, base)
        if p:
            out.add(p)
    for hit in re.findall(r"/assets/[A-Za-z0-9_./%+~-]+", text):
        p = asset_path(hit, base)
        if p:
            out.add(p)
    return out

def inject(raw: str) -> str:
    # Never rewrite or normalize existing markup, forms, links, copy or metadata.
    cleaned = raw.replace(STYLE_TAG, "").replace(SCRIPT_TAG, "")
    if cleaned.count("</head>") != 1 or cleaned.count("</body>") != 1:
        raise AssertionError("Unexpected HTML layout; refusing destructive patch")
    if 'data-flower-motion-v19="css"' in cleaned:
        raise AssertionError("Existing incompatible motion layer")
    out = cleaned.replace("</head>", STYLE_TAG + "\n</head>", 1)
    out = out.replace("</body>", SCRIPT_TAG + "\n</body>", 1)
    assert out.replace(STYLE_TAG + "\n", "").replace(SCRIPT_TAG + "\n", "") == cleaned
    return out

def build() -> None:
    if ROOT.exists():
        shutil.rmtree(ROOT)
    ROOT.mkdir(parents=True)
    data = read(V18_ARCHIVE)
    baseline_sha = hashlib.sha256(data).hexdigest()
    local_base = ROOT.parent / "flower-motion-v19-baseline.zip"
    local_base.write_bytes(data)
    with zipfile.ZipFile(local_base) as archive:
        if archive.testzip() is not None:
            raise RuntimeError("Corrupt V18 source archive")
        archive.extractall(ROOT)

    # Mirror latest staging page HTML, avoiding reversion to the older V18 page copy.
    queued: set[str] = set()
    original_stage_html: dict[str, str] = {}
    for p in PATHS:
        url = STAGE + p
        source = read(url).decode("utf-8")
        original_stage_html[p.lstrip("/") + "index.html"] = source
        soup = BeautifulSoup(source, "html.parser")
        if not soup.head or not soup.body or not soup.find("h1"):
            raise AssertionError(f"Unexpected live staging HTML at {p}")
        if "book" not in source.lower() and "booking" not in source.lower():
            raise AssertionError(f"Missing booking affordance in {p}")
        if p.endswith("/al-majmaah-harmah/"):
            expected = "2:00 PM" if p.startswith("/en/") else "2:00 م"
            if expected not in source:
                raise AssertionError(f"Changed checkout policy in {p}")
        output = inject(source)
        if p in EDITORIAL_PAGES:
            design_soup = BeautifulSoup(output, "html.parser")
            assert apply_editorial(design_soup, p)
            output = str(design_soup)
        target = html_output(p)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(output, encoding="utf-8")
        queued.update(referenced_assets(source, url))

    # Keep the current staging sitemap and robots instead of rewriting SEO.
    for p in ("/sitemap.xml", "/robots.txt"):
        (ROOT / p[1:]).write_bytes(read(STAGE + p))

    # Overlay currently referenced staging assets, preserving all V18 archive assets
    # even when referenced indirectly by interactive galleries.
    pending = deque(sorted(queued))
    visited: set[str] = set()
    failed: dict[str, str] = {}
    while pending:
        path = pending.popleft()
        if path in visited:
            continue
        visited.add(path)
        dest = ROOT / path[1:]
        try:
            data = read(STAGE + urllib.parse.quote(path, safe="/"), timeout=25)
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(data)
            if path.endswith((".css", ".js")):
                text = data.decode("utf-8", errors="replace")
                for extra in extract_asset_literals(text, STAGE + path):
                    if extra not in visited:
                        pending.append(extra)
        except Exception as exc:
            if dest.is_file():
                continue  # Exact original V18 asset still present.
            failed[path] = str(exc)
    if failed:
        # The existing site's legacy fallback registry includes four 01.jpg
        # aliases already returning 404. They are not used as visible photos.
        ignored = {
            "/assets/images/al-majmaah-harmah/01.jpg",
            "/assets/images/al-qaisumah/01.jpg",
            "/assets/images/dammam-al-anoud/01.jpg",
            "/assets/images/dammam-al-salam/01.jpg",
        }
        unexpected = {p: error for p, error in failed.items() if p not in ignored}
        if unexpected:
            raise RuntimeError("Missing referenced assets: " + json.dumps(unexpected, ensure_ascii=False))
        print("Legacy fallback images unavailable on base staging; preserved unchanged:", sorted(failed))

    (ROOT / "assets/css").mkdir(parents=True, exist_ok=True)
    (ROOT / "assets/js").mkdir(parents=True, exist_ok=True)
    shutil.copyfile(STYLES, ROOT / "assets/css/flower-motion-v19.css")
    shutil.copyfile(SCRIPTS, ROOT / "assets/js/flower-motion-v19.js")
    shutil.copyfile("site-motion-v19/flower-editorial-v19-1.css", ROOT / "assets/css/flower-editorial-v19-1.css")
    shutil.copyfile("site-motion-v19/flower-editorial-v19-1.js", ROOT / "assets/js/flower-editorial-v19-1.js")

    # Structural regression checks on both languages and all four branches.
    for path in PATHS:
        soup = BeautifulSoup(html_output(path).read_text("utf-8"), "html.parser")
        assert len(soup.select('[data-flower-motion-v19="css"]')) == 1
        assert len(soup.select('[data-flower-motion-v19="js"]')) == 1
        assert len(soup.select("h1")) == 1, path
        assert soup.find(id="booking"), path
        assert soup.find("link", rel="canonical"), path
        if path in EDITORIAL_PAGES:
            hero = soup.select_one(".fx19-hero.flv-editorial-hero")
            assert hero and hero.get("data-fl-editorial") == "v19-1", path
            assert len(hero.select(".flv-slide")) == len(EDITORIAL_IMAGES["home" if path in ("/", "/en/") else "property"]), path
            assert len(hero.select("button.flv-arrow")) == 2, path
            assert soup.select_one('link[href="/assets/css/flower-editorial-v19-1.css"]'), path
            assert soup.select_one('script[src="/assets/js/flower-editorial-v19-1.js"]'), path
            assert len(hero.select(".fx19-hero-actions a")) >= 2, path
        if "al-majmaah-harmah" in path:
            assert soup.find(id="stay"), path
            assert soup.select("a[href*='booking.com']"), path
            assert soup.select("a[href*='wa.me/']"), path

    ZIP_PATH.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(ZIP_PATH, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for file in sorted(ROOT.rglob("*")):
            if file.is_file():
                archive.write(file, file.relative_to(ROOT).as_posix())

    with zipfile.ZipFile(ZIP_PATH) as archive:
        assert archive.testzip() is None
        listing = set(archive.namelist())
        assert len(listing) >= 62, len(listing)
        for needed in ("assets/css/flower-motion-v19.css", "assets/js/flower-motion-v19.js",
                       "index.html", "en/index.html", "al-majmaah-harmah/index.html",
                       "en/al-majmaah-harmah/index.html"):
            assert needed in listing, needed
    # Exact HTML rollback snapshot of the currently live staging release;
    # the new editorial layer can be removed without losing earlier V19.
    rollback = pathlib.Path("deploy-assets/flower-motion-v19-rollback.zip")
    visual_files = {"assets/css/flower-editorial-v19-1.css",
                    "assets/js/flower-editorial-v19-1.js"}
    with zipfile.ZipFile(ZIP_PATH) as source_archive, zipfile.ZipFile(
            rollback, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as backup:
        for member in source_archive.infolist():
            if member.filename in visual_files:
                continue
            payload = (original_stage_html[member.filename].encode("utf-8")
                       if member.filename in original_stage_html
                       else source_archive.read(member.filename))
            backup.writestr(member.filename, payload)
    with zipfile.ZipFile(rollback) as backup:
        assert backup.testzip() is None
        assert len(backup.namelist()) >= 62
        assert "data-fl-editorial" not in backup.read("index.html").decode("utf-8")
        assert backup.read("index.html") == original_stage_html["index.html"].encode("utf-8")
    pathlib.Path("deploy-assets/flower-motion-v19-rollback-manifest.json").write_text(
        json.dumps({"source": STAGE, "pages": len(PATHS),
                    "files": len(listing) - 2, "checksPassed": True,
                    "reason": "exact pre-visual V19 staging HTML snapshot"}, indent=2) + "\n", "utf-8")

    manifest = {"variant": "FLOWER Editorial V19.1 staging candidate",
                "source": STAGE, "originalV18Sha256": baseline_sha,
                "pages": len(PATHS), "files": len(listing),
                "zipBytes": ZIP_PATH.stat().st_size,
                "effects": ["high-contrast split hospitality hero on home and Harmah",
                            "bilingual accessible hotel-photo carousel",
                            "genuine hotel photography only",
                            "no changes to reservations, other six pages or production",
                            "reduced-motion safety"],
                "productionUntouched": True, "checksPassed": True}
    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", "utf-8")
    print("FLOWER V19 STAGING ARCHIVE PASS", json.dumps(manifest, ensure_ascii=False))

if __name__ == "__main__":
    build()
