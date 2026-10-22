#!/usr/bin/env python3
"""Produce a reviewed production release with only 4 approved V19.1 pages.

The other six existing production property pages keep their original HTML,
CSS/JS and images under an isolated asset namespace. Also archive a rollback
snapshot of all ten live production pages and their referenced public assets.
No access to private credentials or mutation of Render is performed here.
"""
from __future__ import annotations
import hashlib
import io
import json
import pathlib
import re
import urllib.request
import urllib.parse
import zipfile
from collections import deque
from bs4 import BeautifulSoup

REPO = "attiabadawy3-eng/flower-reviews-watchdog"
STAGE_SHA = "9f57812dd829264ea49fa7914cae3ccea372770c"
V18_SHA = "0eea80a6d12d4fdcd07f5b194077e227c2bd48c2"
PROD = "https://flower-serviced-apartments-sa.onrender.com"
STAGE_ARCHIVE = f"https://raw.githubusercontent.com/{REPO}/{STAGE_SHA}/deploy-assets/flower-motion-v19-staging.zip"
BASE_ARCHIVE = f"https://raw.githubusercontent.com/{REPO}/{V18_SHA}/deploy-assets/flower-signature-v18-staging.zip"
OUT = pathlib.Path("deploy-assets/flower-v19-1-production-approved.zip")
BACKUP = pathlib.Path("deploy-assets/flower-v18-production-snapshot-before-v19-1.zip")
MANIFEST = pathlib.Path("deploy-assets/flower-v19-1-production-approved-manifest.json")
PAGES = ["/", "/en/", "/dammam-al-anoud/", "/en/dammam-al-anoud/",
         "/dammam-al-salam/", "/en/dammam-al-salam/", "/al-qaisumah/",
         "/en/al-qaisumah/", "/al-majmaah-harmah/", "/en/al-majmaah-harmah/"]
DESIGN = {"/", "/en/", "/al-majmaah-harmah/", "/en/al-majmaah-harmah/"}
PRESERVED = set(PAGES) - DESIGN
PREFIX = "/flower-v18-preserved"
LEGACY_404 = {f"/assets/images/{v}/01.jpg" for v in
              ("al-majmaah-harmah", "al-qaisumah", "dammam-al-anoud", "dammam-al-salam")}

def fetch(url: str) -> bytes:
    req=urllib.request.Request(url,headers={"User-Agent":"FLOWER-Approved-Production-Release/1.0"})
    with urllib.request.urlopen(req, timeout=45) as resp:
        data=resp.read()
        if not data: raise RuntimeError("Empty download: "+url)
        return data

def relpage(urlpath: str) -> str:
    return urlpath.lstrip("/") + "index.html"

def files_from_zip(archive: zipfile.ZipFile) -> dict[str,bytes]:
    if archive.testzip() is not None: raise RuntimeError("Broken archive")
    return {n:archive.read(n) for n in archive.namelist() if not n.endswith("/")}

def referenced(text: str, base_path: str) -> set[str]:
    assets=set()
    # Absolute asset strings used by HTML, CSS and JS.
    for match in re.findall(r"/assets/[A-Za-z0-9_./%+~@-]+",text):
        path=urllib.parse.unquote(match)
        if ".." not in pathlib.PurePosixPath(path).parts: assets.add(path)
    # CSS url() may include relative paths (e.g. ../fonts/xyz.woff).
    for value in re.findall(r"url\(\s*['\"]?([^)'\"\s]+)", text, re.I):
        if value.startswith(("data:","http:","https:","#")): continue
        absolute=urllib.parse.urljoin(PROD+base_path,value)
        parsed=urllib.parse.urlsplit(absolute)
        if parsed.netloc==urllib.parse.urlsplit(PROD).netloc and parsed.path.startswith("/assets/"):
            assets.add(parsed.path)
    return assets

def collect_prod_assets(live: dict[str,bytes]) -> tuple[dict[str,bytes],list[str]]:
    queue=deque()
    for path,raw in live.items():
        queue.extend(sorted(referenced(raw.decode("utf-8","replace"),path)))
    found={}
    missing=[]
    while queue:
        path=queue.popleft()
        if path in found or path in missing:continue
        try:
            data=fetch(PROD+urllib.parse.quote(path,safe="/"))
        except Exception as exc:
            if path in LEGACY_404:
                missing.append(path)
                continue
            raise RuntimeError(f"Critical production asset could not be preserved: {path}: {exc}")
        found[path]=data
        if path.endswith((".css",".js")):
            refs=referenced(data.decode("utf-8","replace"),path)
            queue.extend(sorted(refs-set(found)-set(missing)))
    return found,missing

def pack(path: pathlib.Path, tree:dict[str,bytes]) -> None:
    path.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(path,"w",compression=zipfile.ZIP_DEFLATED,compresslevel=6) as dst:
        for name in sorted(tree):
            dst.writestr(name,tree[name])
    with zipfile.ZipFile(path) as z:
        if z.testzip():raise RuntimeError("Created invalid zip")

def run():
    stage_data=fetch(STAGE_ARCHIVE)
    base_data=fetch(BASE_ARCHIVE)
    with zipfile.ZipFile(io.BytesIO(stage_data)) as z: candidate=files_from_zip(z)
    with zipfile.ZipFile(io.BytesIO(base_data)) as z: baseline=files_from_zip(z)
    live={}
    for p in PAGES:
        raw=fetch(PROD+p)
        page=BeautifulSoup(raw,"html.parser")
        if not page.head or not page.body or len(page.select("h1"))!=1:
            raise AssertionError("Production page structure invalid: "+p)
        if not page.find(id="booking"):raise AssertionError("Missing production booking: "+p)
        live[relpage(p)]=raw
    assets,legacy=collect_prod_assets(live)
    # Actual old production (not guessed SOURCE_URL) is retained for rollback.
    snapshot=dict(baseline)
    snapshot.update(live)
    for path,content in assets.items():snapshot[path.lstrip("/")]=content
    snapshot["robots.txt"]=fetch(PROD+"/robots.txt")
    snapshot["sitemap.xml"]=fetch(PROD+"/sitemap.xml")
    pack(BACKUP,snapshot)

    # Exactly four visual pages from the tested V19.1 archive.
    release=dict(candidate)
    for p in DESIGN:
        name=relpage(p)
        if name not in release or b'flv-editorial-hero' not in release[name]:
            raise AssertionError("Approved visual page missing: "+p)
        if len(BeautifulSoup(release[name],"html.parser").select(".flv-slide")) < 3:
            raise AssertionError("Visual carousel missing: "+p)
    # Six non-target pages stay on the currently live V18 DOM.
    for p in PRESERVED:
        name=relpage(p)
        raw=live[name]
        altered=raw.replace(b"/assets/",(PREFIX+"/assets/").encode())
        # Check mechanically: every change to preserved HTML was ONLY the
        # asset namespace, preventing unwanted changes to policy/booking/copy.
        assert altered.replace((PREFIX+"/assets/").encode(),b"/assets/")==raw
        release[name]=altered
    # Preserve the actual original CSS/JS/photos in a dedicated namespace.
    for path,content in assets.items():
        if path.endswith((".css",".js")):
            # Absolute local references inside preserved CSS/JS must resolve
            # inside the preserved original namespace too.
            content=content.replace(b"/assets/",(PREFIX+"/assets/").encode())
        release[PREFIX.lstrip("/")+path]=content

    # In the rare case a legacy reference is broken in current production,
    # don't invent imagery; preserve existing fallback state.
    for path in legacy:
        name=path.lstrip("/")
        if name in baseline:
            release[PREFIX.lstrip("/")+path]=baseline[name]
    # Production site metadata lives at original canonical URLs (not staging).
    release["robots.txt"]=snapshot["robots.txt"]
    release["sitemap.xml"]=snapshot["sitemap.xml"]

    for p in PAGES:
        name=relpage(p)
        html=BeautifulSoup(release[name],"html.parser")
        if not html.find("link",rel="canonical") or not html.find(id="booking"):
            raise AssertionError("Page SEO/booking regression: "+p)
        if p in DESIGN:
            if b'flv-editorial-hero' not in release[name]:raise AssertionError(name)
        else:
            expected=live[name].replace(b"/assets/",(PREFIX+"/assets/").encode())
            if release[name]!=expected:raise AssertionError("Unauthorised change "+p)
        if p.endswith("al-majmaah-harmah/"):
            if ("2:00 PM" if p.startswith("/en/") else "2:00 م") not in release[name].decode("utf-8"):
                raise AssertionError("Check-out regression: "+p)
            if not html.select("a[href*='wa.me/']") or not html.select("a[href*='booking.com']"):
                raise AssertionError("Harmah booking links missing: "+p)
    pack(OUT,release)

    # Exact rollback and release artifacts are tested before any deployment.
    with zipfile.ZipFile(BACKUP) as z:
        for p in PAGES:
            if z.read(relpage(p))!=live[relpage(p)]:
                raise AssertionError("Rollback HTML differs from existing production "+p)
    with zipfile.ZipFile(OUT) as z:
        for p in DESIGN:
            if z.read(relpage(p))!=candidate[relpage(p)]:
                raise AssertionError("Design differs from approved staging "+p)
        if not z.read("assets/js/flower-editorial-v19-1.js"):
            raise AssertionError("No visual JS")
    manifest={"version":"FLOWER Signature V19.1 approved",
      "approvedStagingCommit":STAGE_SHA,
      "approvedStageZipSHA256":hashlib.sha256(stage_data).hexdigest(),
      "productionSnapshotSHA256":hashlib.sha256(BACKUP.read_bytes()).hexdigest(),
      "releaseSHA256":hashlib.sha256(OUT.read_bytes()).hexdigest(),
      "releaseBytes":OUT.stat().st_size,"snapshotBytes":BACKUP.stat().st_size,
      "designPages":sorted(DESIGN),"preservedV18Pages":sorted(PRESERVED),
      "preservedProductionPublicAssets":len(assets),
      "legacyAlreadyMissing":legacy,
      "productionPagesExactlySnapshot":True,"allChecksPassed":True}
    MANIFEST.write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+"\n","utf-8")
    print("APPROVED_RELEASE_VERIFIED",json.dumps(manifest,ensure_ascii=False))
if __name__=="__main__":
    run()
