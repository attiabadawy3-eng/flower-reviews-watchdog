#!/usr/bin/env python3
"""Build the FLOWER V20 group staging archive offline from pinned repo archives.

Base: approved V19.1 production release (home + Harmah, all assets).
Change: the six V18-preserved branch pages are replaced by their V19 staging
pages with the V19.1 editorial hero. Every business fact on those pages must
match current production exactly. Nothing is deployed by this script.
"""
from __future__ import annotations
import hashlib
import json
import pathlib
import re
import sys
import zipfile

from bs4 import BeautifulSoup

sys.path.insert(0, "site-motion-v19")
sys.path.insert(0, "site-group-v20")
from flower_group_v20 import apply_group, PAGES as GROUP_PAGES  # noqa: E402
from flower_copy_v20 import apply_copy, REPLACE, REMOVE  # noqa: E402

APPROVED = pathlib.Path("deploy-assets/flower-v19-1-production-approved.zip")
APPROVED_SHA = "ad21473053cbd217783656f76052eaee059affa816c860d7efe025b6fdfd9408"
V19_STAGE = pathlib.Path("deploy-assets/flower-motion-v19-staging.zip")
OUT = pathlib.Path("deploy-assets/flower-group-v20-staging.zip")
MANIFEST = pathlib.Path("deploy-assets/flower-group-v20-staging-manifest.json")
DESIGN_V19_1 = ["/", "/en/", "/al-majmaah-harmah/", "/en/al-majmaah-harmah/"]
ALL_PAGES = DESIGN_V19_1 + sorted(GROUP_PAGES)
JS_V19_1 = "/assets/js/flower-editorial-v19-1.js"
JS_V20 = "/assets/js/flower-editorial-v20.js"

def relpage(path: str) -> str:
    return path.lstrip("/") + "index.html"

def read_zip(path: pathlib.Path) -> dict[str, bytes]:
    with zipfile.ZipFile(path) as z:
        if z.testzip() is not None:
            raise RuntimeError(f"Broken archive {path}")
        return {n: z.read(n) for n in z.namelist() if not n.endswith("/")}

def facts(raw: bytes) -> dict:
    s = BeautifulSoup(raw, "html.parser")
    def hrefs(pattern):
        return sorted({a["href"].split("?")[0] for a in s.find_all("a", href=True) if re.search(pattern, a["href"])})
    policy = {}
    for row in s.select(".v7-policy-list > div"):
        if row.find("span") and row.find("strong"):
            policy[row.find("span").get_text(strip=True)] = row.find("strong").get_text(strip=True)
    return {"title": s.title.string if s.title else None,
            "canonical": (s.find("link", rel="canonical") or {}).get("href"),
            "description": (s.find("meta", attrs={"name": "description"}) or {}).get("content"),
            "tel": hrefs(r"^tel:"), "whatsapp": hrefs(r"wa\.me"), "booking": hrefs(r"booking\.com"),
            "maps": hrefs(r"google\.com/maps|search\.google"), "policy": policy,
            "ldjson": [t.string for t in s.find_all("script", type="application/ld+json")],
            "hreflang": sorted(l.get("href") for l in s.find_all("link", rel="alternate"))}

def assets_in(raw: bytes) -> set[str]:
    pattern = r"(?:/flower-v18-preserved)?/assets/[A-Za-z0-9_./%+~@-]+\.[a-z0-9]+"
    return {m.lstrip("/") for m in re.findall(pattern, raw.decode("utf-8", "replace"))}

def build() -> dict:
    if hashlib.sha256(APPROVED.read_bytes()).hexdigest() != APPROVED_SHA:
        raise AssertionError("Approved production archive changed; refusing to build")
    approved = read_zip(APPROVED)
    stage = read_zip(V19_STAGE)
    release = dict(approved)

    for path in sorted(GROUP_PAGES):
        name = relpage(path)
        soup = BeautifulSoup(stage[name], "html.parser")
        if not apply_group(soup, path):
            raise AssertionError(f"V20 layer not applied: {path}")
        # Keep production structured data verbatim (its image URLs point at the
        # preserved asset namespace that exists in this release).
        live_ld = BeautifulSoup(approved[name], "html.parser").find_all("script", type="application/ld+json")
        page_ld = soup.find_all("script", type="application/ld+json")
        if len(live_ld) != len(page_ld):
            raise AssertionError(f"Structured data block count differs: {path}")
        for target, source in zip(page_ld, live_ld):
            target.string = source.string
        release[name] = str(soup).encode("utf-8")

    # Copy layer and carousel script on all ten pages.
    hits: dict[str, int] = {}
    for path in ALL_PAGES:
        name = relpage(path)
        soup = BeautifulSoup(release[name], "html.parser")
        for key, n in apply_copy(soup).items():
            hits[key] = hits.get(key, 0) + n
        script = soup.find("script", src=JS_V19_1)
        if not script:
            raise AssertionError(f"Editorial script missing: {path}")
        script["src"] = JS_V20
        release[name] = str(soup).encode("utf-8")
    unused = sorted((set(REPLACE) | REMOVE) - set(hits))
    if unused:
        raise AssertionError(f"Copy entries never matched: {unused}")
    release[JS_V20.lstrip("/")] = pathlib.Path("site-group-v20/flower-editorial-v20.js").read_bytes()

    for path in ALL_PAGES:
        name = relpage(path)
        page = BeautifulSoup(release[name], "html.parser")
        expected = facts(approved[name])
        expected["policy"] = {k: REPLACE.get(v, v) for k, v in expected["policy"].items()}
        if facts(release[name]) != expected:
            raise AssertionError(f"Business facts differ from production: {path}")
        hero = page.select_one(".fx19-hero.flv-editorial-hero")
        assert hero and hero.get("data-fl-editorial") == "v19-1", path
        assert len(hero.select(".flv-slide")) == (4 if path in ("/", "/en/") else 3), path
        assert page.find("script", src=JS_V20) and not page.find("script", src=JS_V19_1), path
        assert len(page.select("h1")) == 1 and page.find(id="booking"), path
        # References already present on the approved production page are served
        # by the live service today; only new references must ship in the archive.
        missing = sorted(a for a in assets_in(release[name]) - assets_in(approved[name]) if a not in release)
        if missing:
            raise AssertionError(f"Missing assets on {path}: {missing}")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(OUT, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for name in sorted(release):
            z.writestr(name, release[name])
    with zipfile.ZipFile(OUT) as z:
        assert z.testzip() is None
    manifest = {"version": "FLOWER Group V20 staging candidate",
                "base": str(APPROVED), "baseSHA256": APPROVED_SHA,
                "unifiedPages": sorted(GROUP_PAGES), "copyLayerPages": ALL_PAGES,
                "copyEdits": sum(hits.values()), "businessFactsMatchProduction": True,
                "files": len(release), "zipBytes": OUT.stat().st_size,
                "zipSHA256": hashlib.sha256(OUT.read_bytes()).hexdigest(),
                "productionUntouched": True, "checksPassed": True}
    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", "utf-8")
    print("FLOWER GROUP V20 STAGING PASS", json.dumps(manifest, ensure_ascii=False))
    return manifest

if __name__ == "__main__":
    build()
