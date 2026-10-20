"""FLOWER Signature V19: transform the real V18 site archive on an isolated staging branch.
All existing booking wiring, original image assets, SEO metadata, and branch data remain.
No live availability, prices, or checkout transaction is represented or invented.
"""
from __future__ import annotations

import hashlib
import json
import pathlib
import zipfile
from bs4 import BeautifulSoup

HERE = pathlib.Path("deploy-assets")
SOURCE = HERE / "flower-signature-v18-unified-times.zip"
OUTPUT = HERE / "flower-signature-v19-staging.zip"
MANIFEST = HERE / "flower-signature-v19-manifest.json"
CSS_PATH = "assets/css/flower-signature-v19.css"
JS_PATH = "assets/js/flower-signature-v19.js"
BRANCHES = (
    ("dammam-al-anoud", "01", "العنود", "Al Anoud", "الدمام", "Dammam",
     "مساحة هادئة في قلب الدمام.", "A quieter place to land in Dammam."),
    ("dammam-al-salam", "02", "السلام", "Al Salam", "الدمام", "Dammam",
     "تفاصيل دافئة لإقامة أكثر راحة.", "Comfort that feels considered."),
    ("al-qaisumah", "03", "القيصومة", "Al Qaisumah", "القيصومة", "Al Qaisumah",
     "اختيار مريح لكل تفاصيل الرحلة.", "Room for a more comfortable journey."),
    ("al-majmaah-harmah", "04", "حرمة", "Harmah", "المجمعة", "Al Majmaah",
     "إقامتك في حرمة بطابع مختلف.", "Make your stay in Harmah your own."),
)
BRANCH_BY_SLUG = {x[0]: x for x in BRANCHES}

def new(s, name, text=None, **attrs):
    t = s.new_tag(name)
    for k,v in attrs.items(): t[k.replace("_","-")]=v
    if text is not None: t.string=text
    return t

def make_hero(s, branch, photo, en, available):
    home = branch is None
    data = BRANCH_BY_SLUG.get(branch)
    hero = new(s,"section", **{"class":"fx19-hero "+("fx19-home" if home else "fx19-property"),"aria-label":"FLOWER Signature V19"})
    media = new(s,"div",**{"class":"fx19-hero-media"})
    im = new(s,"img",**{"src":photo, "alt":("Original photograph of a FLOWER serviced apartment" if en else "صورة حقيقية من شقق فلور المخدومة"),
       "width":"1440","height":"900","fetchpriority":"high","decoding":"async"})
    media.append(im)
    media.append(new(s,"div",**{"class":"fx19-hero-overlay"}))
    hero.append(media)
    wrap = new(s,"div",**{"class":"fx19-hero-inner"})
    side = new(s,"div",**{"class":"fx19-hero-copy"})
    side.append(new(s,"p","FLOWER COLLECTION   /   SERVICED APARTMENTS" if en else "FLOWER COLLECTION   /   شقق فلور المخدومة",**{"class":"fx19-overline"}))
    h1 = new(s,"h1")
    if home:
        h1.append(new(s,"span","FLOWER Serviced Apartments" if en else "فلور للشقق المخدومة"))
        h1.append(new(s,"em","A better way to feel at home." if en else "مساحات تليق براحتك."))
        description = ("Four distinctive locations in Dammam, Al Qaisumah and Al Majmaah. "
                       "Discover our actual apartments and plan your stay with confidence.") if en else (
                       "أربع وجهات للإقامة في الدمام والقيصومة والمجمعة. صور حقيقية لشققنا، "
                       "وتجربة تبدأ من اختيار المكان الذي يناسبك.")
    else:
        h1.append(new(s,"span",f"FLOWER {data[1]}  ·  {data[3]}" if en else f"فلور {int(data[1])}  ·  {data[2]}"))
        h1.append(new(s,"em",data[7] if en else data[6]))
        description = (f"Serviced apartments in {data[5]}. Explore actual rooms, compare unit types, "
                       "and enquire directly about your preferred stay.") if en else (
                       f"شقق مخدومة في {data[4]}. اكتشف صور الوحدات الحقيقية والتجهيزات المتاحة، "
                       "واستفسر مباشرة عن تفاصيل إقامتك.")
    side.append(h1)
    side.append(new(s,"p",description,**{"class":"fx19-hero-description"}))
    links = new(s,"div",**{"class":"fx19-hero-actions"})
    links.append(new(s,"a","Explore stays" if en else "استكشف الإقامات" if home else "ابدأ الاستفسار",
                     **{"href":"#branches" if home else "#booking","class":"fx19-button fx19-button-primary"}))
    links.append(new(s,"a","Plan your stay" if en and home else "View apartments" if en else "خطّط لإقامتك" if home else "شاهد الوحدات",
                     **{"href":"#booking" if home else "#stay","class":"fx19-button fx19-button-secondary"}))
    side.append(links)
    details = new(s,"div",**{"class":"fx19-hero-facts"})
    for fact in (("04 LOCATIONS","4 فروع"),("REAL PHOTOGRAPHY","صور حقيقية"),("DIRECT ENQUIRY","تواصل مباشر")) if home else (
        (f"FLOWER {data[1]}", f"فلور {int(data[1])}"), ("SERVICED APARTMENTS","شقق مخدومة"), ("24H RECEPTION","استقبال 24 ساعة")):
        details.append(new(s,"span",fact[0] if en else fact[1]))
    side.append(details)
    wrap.append(side)
    if home:
        inset=new(s,"div",**{"class":"fx19-hero-inset"})
        second="/assets/images/dammam-al-salam/enhanced/05-enhanced.webp"
        if second.lstrip("/") in available:
            inset.append(new(s,"img",**{"src":second,"alt":"Another original FLOWER apartment interior" if en else "غرفة من صور فلور الحقيقية",
                      "loading":"lazy","decoding":"async","width":"480","height":"520"}))
            inset.append(new(s,"span","FOUR PLACES. ONE FEELING." if en else "تفاصيل تليق بإقامتك."))
            wrap.append(inset)
    hero.append(wrap)
    edge=new(s,"div",**{"class":"fx19-hero-index","aria-hidden":"true"})
    edge.string="FLOWER  /  01—04" if home else f"FLOWER  /  {data[1]}"
    hero.append(edge)
    return hero

def tune_booking(s, book, en):
    book["class"]=list(dict.fromkeys((book.get("class") or [])+["fx19-booking"]))
    wrap=book.select_one(".wrap")
    head=book.select_one(".v7-booking-head")
    if head:
        desc=head.find("p")
        if desc: desc.string=("Choose a property, your dates and guests. We will connect you with the existing reservation channels; this is an enquiry, not an instant confirmation." if en else
             "اختر الفرع والوحدة وتواريخ الإقامة والضيوف، ثم انتقل لقناة الحجز المتاحة. الاستفسار ليس تأكيدًا فوريًا للحجز.")
    if wrap:
        badge=new(s,"div",**{"class":"fx19-booking-topline"})
        badge.append(new(s,"span","YOUR STAY STARTS HERE" if en else "تجربتك تبدأ من هنا"))
        badge.append(new(s,"span","CHECK-IN  4:00 PM    ·    CHECK-OUT  2:00 PM" if en else "الدخول 4:00 م    ·    الخروج 2:00 م"))
        wrap.insert(0,badge)
    for f in book.select("input[type=date]"):
        f["required"]="required"
    return book

def insert_editorial(s, main, after, slug, en, assets):
    art=new(s,"section",**{"class":"fx19-editorial","aria-label":"Original FLOWER property photography" if en else "صور حقيقية من فلور"})
    top=new(s,"div",**{"class":"fx19-editorial-head"})
    txt=new(s,"div")
    txt.append(new(s,"span","THE FLOWER EXPERIENCE" if en else "تجربة فلور",**{"class":"fx19-overline-dark"}))
    txt.append(new(s,"h2","Each place has a story." if en else "لكل مكان تفاصيله."))
    txt.append(new(s,"p","Real apartments, carefully presented — discover more before making your enquiry." if en else
        "مساحات من الواقع، وصور من فروعنا الفعلية، لتختار إقامتك بثقة."))
    top.append(txt)
    art.append(top)
    imgs=[
        ("/assets/images/al-majmaah-harmah/polished/harmah-twin-polished.webp", "حرمة • المجمعة","Harmah • Al Majmaah"),
        ("/assets/images/dammam-al-anoud/enhanced/06-enhanced.webp","العنود • الدمام","Al Anoud • Dammam"),
        ("/assets/images/al-qaisumah/enhanced/05-enhanced.webp","القيصومة","Al Qaisumah")
    ] if slug is None else [
        (f"/assets/images/{slug}/enhanced/02-enhanced.webp","من وحدات الفرع","From our apartments"),
        (f"/assets/images/{slug}/enhanced/05-enhanced.webp","تفاصيل الإقامة","Your stay"),
        (f"/assets/images/{slug}/enhanced/03-enhanced.webp","تعرّف على الفرع","Explore the property")
    ]
    grid=new(s,"div",**{"class":"fx19-editorial-grid"})
    found=0
    for src,ar,eng in imgs:
        if src.lstrip("/") not in assets: continue
        tile=new(s,"figure")
        tile.append(new(s,"img",**{"src":src,"alt":eng if en else ar,"loading":"lazy","decoding":"async","width":"840","height":"620"}))
        tile.append(new(s,"figcaption",eng if en else ar))
        grid.append(tile)
        found+=1
    if found < 2: return
    art.append(grid)
    after.insert_after(art)

def tune_units(s, main, en):
    stay=main.select_one("#stay")
    if not stay: return
    stay["class"]=list(dict.fromkeys((stay.get("class") or [])+["fx19-units"]))
    for idx,unit in enumerate(stay.select(".v7-unit,.v7-home-unit"),1):
        unit["data-v19-unit"]=str(idx)
        imgs=unit.select(".v7-unit-media img")
        for img in imgs:
            if not img.get("decoding"): img["decoding"]="async"
    return stay

def patch(raw, filename, assets):
    soup=BeautifulSoup(raw.decode("utf-8"),"html.parser")
    en=filename.startswith("en/")
    relative=filename[3:] if en else filename
    slug=None if relative=="index.html" else relative.split("/")[0]
    if slug is not None and slug not in BRANCH_BY_SLUG: raise ValueError("Unrecognized page "+filename)
    main=soup.select_one("main")
    book=soup.select_one("#booking")
    assert main and book and soup.head and soup.body,(filename,"missing structure")
    assert soup.select_one("#book-branch") and soup.select_one("#book-unit"),filename
    assert soup.select_one("#book-whatsapp") and soup.select_one("#book-booking"),filename
    old_hero=main.find("section",recursive=False)
    assert old_hero and (old_hero.select_one("h1") or old_hero.find("h1")),(filename,"missing original hero")
    # Reuse each actual property's original hero image; V19 keeps all original assets.
    old_image=old_hero.find("img",src=True)
    assert old_image,(filename,"original photo missing")
    photo=old_image["src"]
    if slug is None:
        homepage_feature="/assets/images/al-majmaah-harmah/polished/harmah-twin-polished.webp"
        if homepage_feature.lstrip("/") in assets: photo=homepage_feature
    assert photo.lstrip("/") in assets,(filename,photo)
    hero=make_hero(soup,slug,photo,en,assets)
    old_hero.replace_with(hero)
    book=tune_booking(soup,book,en)
    # Genuine multi-photo editorial strip, not synthetic image generation.
    if slug is None:
        insert_editorial(soup,main,book,None,en,assets)
    else:
        tune_units(soup,main,en)
        stay=main.select_one("#stay")
        if stay:
            # Let rooms and unit choices precede secondary feature stories.
            story=main.select_one("#flower-signature")
            if story:
                story.extract()
                stay.insert_after(story)
            insert_editorial(soup,main,stay,slug,en,assets)
            gallery=main.select_one("#gallery")
            if gallery:
                gallery.extract()
                # Move the complete original interactive gallery next to the unit showcase.
                tail=stay.find_next_sibling("section")
                (tail or stay).insert_after(gallery)
    soup.html["data-flower-v19"]="signature"
    soup.body["class"]=list(dict.fromkeys((soup.body.get("class") or [])+["fx19-site"]))
    # Preserve existing CSS/JS, then apply one fully isolated V19 override layer.
    css=new(soup,"link",**{"rel":"stylesheet","href":"/"+CSS_PATH})
    soup.head.append(css)
    script=new(soup,"script",**{"src":"/"+JS_PATH,"defer":"defer"})
    soup.body.append(script)
    preload=new(soup,"link",**{"rel":"preload","as":"image","href":photo,"fetchpriority":"high"})
    soup.head.append(preload)
    # No invented prices/availability, no SEO rewrites, maintain one accessible H1.
    assert len(soup.select("h1"))==1,filename
    assert soup.select_one("#book-arrival") and soup.select_one("#book-departure")
    assert soup.select_one('link[rel=canonical]'),filename
    assert soup.select_one("img[src*=flower-hotel-logo]"),filename
    assert soup.select_one("#reviews"),filename
    if slug:
        assert len(soup.select("#stay .v7-unit"))>=3,filename
        assert soup.select_one(".v7-policy-list"),filename
    return str(soup).encode("utf-8"), {"path":filename,"photo":photo,"branches_preserved":len(soup.select("#book-branch option")),
        "h1":soup.select_one("h1").get_text(" ",strip=True),"unit_count":len(soup.select("#stay .v7-unit")),
        "v19_css":True,"v19_js":True}

def main():
    if not SOURCE.is_file(): raise SystemExit(f"V18 source missing: {SOURCE}")
    css=pathlib.Path("site-build/flower-v19.css").read_bytes()
    js=pathlib.Path("site-build/flower-v19.js").read_bytes()
    paths={"index.html","en/index.html"}
    paths.update((f"{pre}{slug}/index.html" for pre in ("","en/") for slug in BRANCH_BY_SLUG))
    rows=[]
    with zipfile.ZipFile(SOURCE) as z,zipfile.ZipFile(OUTPUT,"w",compression=zipfile.ZIP_DEFLATED,compresslevel=7) as out:
        available=set(z.namelist())
        assert paths<=available,paths-available
        assert CSS_PATH not in available and JS_PATH not in available
        for i in z.infolist():
            content=z.read(i.filename)
            if i.filename in paths:
                content,details=patch(content,i.filename,available)
                rows.append(details)
            out.writestr(i,content)
        out.writestr(CSS_PATH,css)
        out.writestr(JS_PATH,js)
    assert len(rows)==10
    with zipfile.ZipFile(SOURCE) as z1,zipfile.ZipFile(OUTPUT) as z2:
        assert set(z2.namelist())==set(z1.namelist())|{CSS_PATH,JS_PATH}
        same=[x for x in z1.namelist() if x not in paths]
        assert all(hashlib.sha256(z1.read(n)).digest()==hashlib.sha256(z2.read(n)).digest() for n in same)
        for filename in paths:
            doc=BeautifulSoup(z2.read(filename),"html.parser")
            assert len(doc.select("section.fx19-hero"))==1
            assert doc.select_one("#book-whatsapp") and doc.select_one("#book-booking")
            assert doc.select_one('#book-branch option[data-booking][data-phone]')
            assert doc.select_one("#stay") and doc.select_one("#gallery")
            assert '2:00 م من اليوم التالي' not in str(doc)
            assert '2:00 PM the following day' not in str(doc)
            if filename not in ("index.html","en/index.html"):
                label="Check-in" if filename.startswith("en/") else "وقت الدخول"
                endlabel="Check-out" if filename.startswith("en/") else "وقت الخروج"
                policies=doc.select(".v7-policy-list > div")
                values={x.select_one("span").get_text(" ",strip=True):x.select_one("strong").get_text(" ",strip=True) for x in policies if x.select_one("span") and x.select_one("strong")}
                assert values.get(label)==("4:00 PM" if filename.startswith("en/") else "4:00 م"), (filename,values)
                assert values.get(endlabel)==("2:00 PM" if filename.startswith("en/") else "2:00 م"),(filename,values)
        assert z2.testzip() is None
    result={
       "variant":"flower-signature-v19-staging",
       "based_on":"flower-signature-v18-unified-times.zip",
       "baseline_preserved":True,
       "production_changed":False,
       "total_pages_changed":len(rows),
       "all_original_assets_unchanged":True,
       "all_untouched_files_byte_identical":True,
       "booking_ids_preserved":True,
       "live_prices_or_availability_invented":False,
       "all_branches_ar_en_checked":True,
       "pages":rows,
       "archive_sha256":hashlib.sha256(OUTPUT.read_bytes()).hexdigest(),
       "archive_bytes":OUTPUT.stat().st_size
    }
    MANIFEST.write_text(json.dumps(result,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    print(json.dumps({"status":"V19_BUILD_VALIDATION_PASS","pages":len(rows),"zip_bytes":OUTPUT.stat().st_size,"archive_sha256":result["archive_sha256"]}))
if __name__=="__main__":
    main()
