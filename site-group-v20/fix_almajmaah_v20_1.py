#!/usr/bin/env python3
"""FLOWER V20.1: market the Harmah property as FLOWER Al Majmaah.

The locality Harmah and real street address are preserved. Existing URLs,
booking channels, photographs, price/policy facts and all other branches remain
unchanged. The approved V20 archive is immutable input.
"""
from __future__ import annotations
import hashlib
import io
import json
from pathlib import Path
import zipfile
from bs4 import BeautifulSoup

SOURCE = Path("deploy-assets/flower-group-v20-staging.zip")
SOURCE_SHA = "9f216e1c4625e55bd3b40ab2fe49c3eedc7771a5a0554cdb5e9c934bf79aad66"
OUT = Path("deploy-assets/flower-group-v20-1-almajmaah.zip")
MANIFEST = Path("deploy-assets/flower-group-v20-1-almajmaah-manifest.json")
PAGES = [
 "/", "/en/", "/dammam-al-anoud/", "/en/dammam-al-anoud/",
 "/dammam-al-salam/", "/en/dammam-al-salam/", "/al-qaisumah/",
 "/en/al-qaisumah/", "/al-majmaah-harmah/", "/en/al-majmaah-harmah/"
]
MAIN = {"/al-majmaah-harmah/", "/en/al-majmaah-harmah/"}
NEW_TITLES = {
 "/al-majmaah-harmah/": "فلور المجمعة | شقق مخدومة ومفروشة في المجمعة – حرمة",
 "/en/al-majmaah-harmah/": "FLOWER Al Majmaah | Serviced Apartments in Al Majmaah – Harmah",
}
NEW_DESCRIPTIONS = {
 "/al-majmaah-harmah/": "فلور المجمعة للشقق المخدومة والمفروشة في حرمة – المجمعة. تعرف على الغرف والشقق والصور والخدمات، واستفسر عن تفاصيل الحجز مباشرة.",
 "/en/al-majmaah-harmah/": "FLOWER Al Majmaah serviced apartments in Harmah, Al Majmaah. Explore rooms, apartment types, real property photos and amenities, and enquire directly.",
}
# Keep the exact existing URL so links, ranking history and canonical continue.
CANONICAL = {
 "/al-majmaah-harmah/": "https://flower-serviced-apartments-sa.onrender.com/al-majmaah-harmah/",
 "/en/al-majmaah-harmah/": "https://flower-serviced-apartments-sa.onrender.com/en/al-majmaah-harmah/",
}

def pagename(path: str) -> str:
    return path.lstrip("/") + "index.html"

def links(soup):
    return sorted(a.get("href") for a in soup.find_all("a", href=True))

def resource_paths(soup):
    return sorted((tag.name, tag.get("src"), tag.get("href"))
      for tag in soup.find_all(["script","link","img"])
      if tag.get("src") or tag.get("href"))

def change_json(node, locale):
    """Only marketing hotel name; do not edit physical address or coordinates."""
    if isinstance(node, dict):
        typ=node.get("@type", "")
        if isinstance(typ, list): typ=" ".join(typ)
        if any(x in str(typ) for x in ("LodgingBusiness", "Hotel", "Accommodation", "LocalBusiness")):
            name=node.get("name")
            if isinstance(name, str) and any(x in name for x in (
                "Harmah","حرمة","فلور 4","FLOWER 04","فلور المجمعة","Al Majmaah"
            )):
                node["name"]="FLOWER Al Majmaah" if locale=="en" else "فلور المجمعة للشقق المخدومة"
        for v in node.values():
            change_json(v, locale)
    elif isinstance(node, list):
        for v in node:change_json(v, locale)

def main_page(soup, locale: str, path: str):
    title=soup.title
    if not title:raise AssertionError("Missing title "+path)
    title.string=NEW_TITLES[path]
    desc=NEW_DESCRIPTIONS[path]
    meta=soup.find("meta", attrs={"name":"description"})
    if not meta: raise AssertionError("Missing meta description "+path)
    meta["content"]=desc
    for attr, prop, value in (
        ("property", "og:title", NEW_TITLES[path]),
        ("property", "og:description", desc),
        ("name", "twitter:title", NEW_TITLES[path]),
        ("name", "twitter:description", desc),
    ):
        tag=soup.find("meta",attrs={attr:prop})
        if tag:tag["content"]=value

    # Keep the city visible as the primary heading, Harmah as precise location.
    h1=soup.find("h1")
    if not h1 or ("فلور المجمعة" if locale=="ar" else "FLOWER Al Majmaah") not in h1.get_text():
        raise AssertionError("H1 was not renamed "+path)

    for script in soup.find_all("script",attrs={"type":"application/ld+json"}):
        if not script.string:continue
        data=json.loads(script.string)
        change_json(data,locale)
        script.string=json.dumps(data,ensure_ascii=False,separators=(",",":"))
    canon=soup.find("link",rel="canonical")
    if not canon or canon.get("href")!=CANONICAL[path]:
        raise AssertionError("Canonical changed "+path)
    text=soup.get_text(" ",strip=True)
    if "حرمة" not in text and locale=="ar":
        raise AssertionError("True Harmah locality lost")
    if "Harmah" not in text and locale=="en":
        raise AssertionError("True Harmah locality lost")

def main():
    assert hashlib.sha256(SOURCE.read_bytes()).hexdigest()==SOURCE_SHA,"Source V20 archive changed"
    with zipfile.ZipFile(SOURCE) as archive:
        assert archive.testzip() is None,"Original ZIP invalid"
        original={n:archive.read(n) for n in archive.namelist() if not n.endswith("/")}
    release=dict(original)
    changed=[]
    for path in PAGES:
        name=pagename(path)
        before=original[name]
        text=before.decode("utf-8")
        # Marketing labels only; generic Harmah/حرمة addresses are deliberately kept.
        text=text.replace("فلور حرمة","فلور المجمعة").replace("FLOWER Harmah","FLOWER Al Majmaah")
        if path in MAIN:
            lang="en" if path.startswith("/en/") else "ar"
            # Keep location truth but lead with the city searchers use.
            if lang=="ar":
                text=text.replace("شقق مخدومة في حرمة بالمجمعة، بضيافة",
                    "شقق مخدومة في المجمعة، بموقعها في حرمة، وبضيافة")
            else:
                text=text.replace("Serviced apartments in Harmah, Al Majmaah, with",
                    "Serviced apartments in Al Majmaah, located in Harmah, with")
            soup=BeautifulSoup(text,"html.parser")
            main_page(soup,lang,path)
            text=str(soup)
        after=text.encode("utf-8")
        if before!=after:changed.append(path)
        old=BeautifulSoup(before,"html.parser")
        new=BeautifulSoup(after,"html.parser")
        assert links(old)==links(new),"Booking/contact hyperlink regression "+path
        assert resource_paths(old)==resource_paths(new),"Image/script/style resources changed "+path
        assert (old.find("link",rel="canonical") or {}).get("href")==(
            new.find("link",rel="canonical") or {}).get("href"),"Canonical regression "+path
        assert len(new.find_all("h1"))==1 and new.find(id="booking"),"HTML booking regression "+path
        assert len(new.select(".flv-slide"))==len(old.select(".flv-slide")),"Gallery regression "+path
        assert "2:00 م" in text if not path.startswith("/en/") else "2:00 PM" in text, "Checkout regression "+path
        if path in MAIN:
            assert NEW_TITLES[path] in text, "New SEO title missing"
            assert NEW_DESCRIPTIONS[path] in text, "New SEO description missing"
            assert len(new.select("article"))>=len(old.select("article")),"Unit cards lost"
        release[name]=after
    assert set(MAIN).issubset(changed),"Both languages must be updated"
    for name,data in original.items():
        if name not in {pagename(path) for path in PAGES}:
            assert release[name]==data,"Non-HTML asset modified "+name
    with zipfile.ZipFile(OUT,"w",compression=zipfile.ZIP_DEFLATED,compresslevel=6) as out:
        for key in sorted(release):
            out.writestr(key,release[key])
    with zipfile.ZipFile(OUT) as z:
        assert z.testzip() is None,"Release zip failed CRC"
        assert len(z.namelist())==len(original)
    manifest={
       "version":"FLOWER Group V20.1 — Al Majmaah marketing correction",
       "source":"FLOWER Group V20 (approved)",
       "sourceSHA256":SOURCE_SHA,
       "releaseSHA256":hashlib.sha256(OUT.read_bytes()).hexdigest(),
       "releaseBytes":OUT.stat().st_size,
       "pages":len(PAGES),"changedPages":changed,
       "primaryNameAr":"فلور المجمعة","primaryNameEn":"FLOWER Al Majmaah",
       "physicalLocationMaintained":"حرمة – المجمعة / Harmah, Al Majmaah",
       "canonicalURLsUnchanged":True,
       "bookingAndWhatsAppUnchanged":True,
       "photosAndScriptsUnchanged":True,
       "otherBranchIdentityUnchanged":True,
       "checksPassed":True
    }
    MANIFEST.write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print("FLOWER_V20_1_ALMAJMAAH_PASS",json.dumps(manifest,ensure_ascii=False))
if __name__=="__main__":
    main()
