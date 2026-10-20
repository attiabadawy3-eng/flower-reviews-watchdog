"""FLOWER Interactive V17.4 — original hotel-focused line illustration inspired by Hairline.
Separate opt-in staging variant, no third-party runtime. Photographs are copied
from the corresponding existing room cards; no unit images or room claims invented.
"""
from __future__ import annotations
from bs4 import BeautifulSoup

BRANCH_PATHS = {"/al-majmaah-harmah/", "/en/al-majmaah-harmah/"}
FLOORS = [
    ("الأرضي", "Ground floor"),
    ("الأول", "First floor"),
    ("الثاني", "Second floor"),
    ("الثالث", "Third floor"),
]

def t(soup, tag, text="", css=None, **attrs):
    node = soup.new_tag(tag)
    if css:
        node["class"] = css.split()
    for k, val in attrs.items():
        node[k.replace("_","-")] = val
    if text:
        node.string=text
    return node

def building_svg(soup, english):
    svg=soup.new_tag("svg", xmlns="http://www.w3.org/2000/svg", viewBox="0 0 640 520")
    svg["class"]=["fi-building"]
    svg["role"]="group"
    svg["aria-label"]="Illustrative interactive four-level building, not a floor plan" if english else "رسم تفاعلي توضيحي لأربعة مستويات بالمبنى وليس مخطط الغرف"
    svg["focusable"]="false"
    defs=soup.new_tag("defs")
    for name, stops in [
        ("fi-top",[(0,"#ae8b73"),(100,"#663747")]),
        ("fi-left",[(0,"#6c3247"),(100,"#341a2b")]),
        ("fi-right",[(0,"#803b51"),(100,"#491f34")]),
    ]:
        grad=soup.new_tag("linearGradient",id=name,x1="0",y1="0",x2="1",y2="1")
        for pct,color in stops:
            stop=soup.new_tag("stop",offset=f"{pct}%",stop_color=color)
            grad.append(stop)
        defs.append(grad)
    svg.append(defs)
    shadow=soup.new_tag("ellipse",cx="338",cy="491",rx="238",ry="25",fill="#0a0610",opacity=".4")
    svg.append(shadow)
    for index in range(4):
        y=350-index*78
        group=soup.new_tag("g")
        group["class"]=["fi-floor"]
        group["data-fi-floor"]=str(index)
        group["tabindex"]="0"
        group["role"]="button"
        group["aria-pressed"]="true" if index==0 else "false"
        label=(FLOORS[index][1] if english else FLOORS[index][0])
        group["aria-label"]=label
        group["style"]=f"--fi-layer:{index}"
        # Original vector design: three visible prisms per level.
        polygons=[
            (f"153,{y} 348,{y+77} 348,{y+147} 153,{y+70}","url(#fi-left)"),
            (f"348,{y+77} 526,{y} 526,{y+70} 348,{y+147}","url(#fi-right)"),
            (f"153,{y} 330,{y-76} 526,{y} 348,{y+77}","url(#fi-top)"),
        ]
        for points,color in polygons:
            poly=soup.new_tag("polygon",points=points,fill=color,stroke="#d9ae81",stroke_width="1.4",stroke_linejoin="round")
            group.append(poly)
        # Façade windows are decorative line shapes, not actual room layouts.
        for col in range(3):
            x=181+col*52
            yy=y+21+col*19
            window=soup.new_tag("polygon",points=f"{x},{yy} {x+24},{yy+9} {x+24},{yy+36} {x},{yy+27}",
                                fill="#d6bb95",fill_opacity=".06",stroke="#cba87b",stroke_opacity=".68",stroke_width="1")
            group.append(window)
        for col in range(3):
            x=379+col*45
            yy=y+96-col*18
            window=soup.new_tag("polygon",points=f"{x},{yy} {x+22},{yy-9} {x+22},{yy+18} {x},{yy+27}",
                                fill="#d6bb95",fill_opacity=".06",stroke="#cba87b",stroke_opacity=".65",stroke_width="1")
            group.append(window)
        svg.append(group)
    return svg

def install_flower_interactive(soup: BeautifulSoup, path:str)->None:
    if path not in BRANCH_PATHS:
        return
    if not soup.body or not soup.head:
        raise RuntimeError(f"Missing document structure: {path}")
    if soup.select_one("#flower-interactive"):
        return
    is_en=path.startswith("/en/")
    anchor=soup.select_one("#flower-cinema") or soup.select_one(".flower-v16-property-hero")
    stay=soup.select_one("#stay")
    if anchor is None or stay is None:
        raise RuntimeError(f"Missing genuine FLOWER 4 staging baseline: {path}")
    units=stay.select(".v7-unit")
    if len(units)!=3:
        raise RuntimeError(f"Expected three verified room card types: {path}, got {len(units)}")
    section=t(soup,"section",css="fi-section",id="flower-interactive")
    section["aria-label"]="FLOWER interactive building and room types" if is_en else "فلور التفاعلي: استكشف الأدوار وأنواع الوحدات"
    head=t(soup,"div",css="fi-head")
    head.append(t(soup,"span","THE FLOWER EXPERIENCE",css="fi-eyebrow"))
    head.append(t(soup,"h2","Explore FLOWER, interactively." if is_en else "فلور، بتفاصيل تتحرك معاك."))
    head.append(t(soup,"p","A new way to explore the building and its genuine room categories." if is_en else "طريقة جديدة لاستكشاف مبنى فلور وأنواع الوحدات الحقيقية."))
    section.append(head)
    container=t(soup,"div",css="fi-shell")
    illustration=t(soup,"div",css="fi-illustration")
    illustration.append(t(soup,"div","FLOWER / ARCHITECTURE",css="fi-illustration-tag"))
    illustration.append(building_svg(soup,is_en))
    illustration.append(t(soup,"div","Move your pointer or tap a floor" if is_en else "حرّك الماوس أو اضغط على أحد الأدوار",css="fi-illustration-hint"))
    container.append(illustration)
    panel=t(soup,"div",css="fi-panel")
    panel.append(t(soup,"span","01 / INTERACTIVE VIEW" if is_en else "01 / استكشاف تفاعلي",css="fi-panel-kicker"))
    panel.append(t(soup,"h3","Discover the levels." if is_en else "استكشف أدوار المبنى."))
    panel.append(t(soup,"p","Choose a level to highlight it. This is an illustrative drawing, not an availability or floor-plan map."
                       if is_en else "اختار الدور وشوفه يبرز في الرسم. العرض توضيحي وليس مخططًا لتوزيع الغرف أو حالة توفرها."))
    level=t(soup,"div",css="fi-level-readout")
    level.append(t(soup,"span","Selected level" if is_en else "الدور المحدد",css="fi-level-label"))
    level.append(t(soup,"strong",FLOORS[0][1] if is_en else FLOORS[0][0],css="fi-level-value",id="fi-level-value"))
    panel.append(level)
    buttons=t(soup,"div",css="fi-floor-controls")
    for index,(ar,en) in enumerate(FLOORS):
        b=t(soup,"button",en if is_en else ar,css="fi-floor-button",type="button",data_fi_choose=str(index))
        b["aria-pressed"]="true" if index==0 else "false"
        buttons.append(b)
    panel.append(buttons)
    panel.append(t(soup,"span","04 LEVELS • ARTISTIC ILLUSTRATION" if is_en else "أرضي + 3 أدوار · رسم فني توضيحي",css="fi-micro"))
    container.append(panel)
    section.append(container)

    display=t(soup,"div",css="fi-units")
    display.append(t(soup,"div","02 / ROOM COLLECTION" if is_en else "02 / أنواع الإقامة",css="fi-units-kicker"))
    display.append(t(soup,"h3","Choose your stay." if is_en else "اختار المساحة المناسبة ليك."))
    display.append(t(soup,"p","Genuine unit categories and photographs from FLOWER 4." if is_en else "أنواع الوحدات وصورها الأصلية من فلور 4."))
    deck=t(soup,"div",css="fi-deck")
    deck["role"]="group"
    deck["aria-label"]="Choose a room category" if is_en else "اختر نوع الوحدة"
    for i,unit in enumerate(units):
        title=unit.select_one("h3")
        img=unit.select_one(".v7-unit-media img")
        if not title or not img or not img.get("src","").startswith("/assets/images/al-majmaah-harmah/"):
            raise RuntimeError("Unit mapping must use existing original photos and category titles")
        if not unit.has_attr("id"):
            unit["id"]=f"flower-unit-choice-{i}"
        card=t(soup,"button",css="fi-unit-card",type="button",data_fi_unit=str(i))
        card["aria-pressed"]="true" if i==0 else "false"
        photo=t(soup,"span",css="fi-unit-photo")
        im=soup.new_tag("img",src=img["src"],alt=img.get("alt",str(title.get_text(" ",strip=True))),
                        loading="lazy",decoding="async",width="460",height="320")
        photo.append(im)
        card.append(photo)
        info=t(soup,"span",css="fi-unit-info")
        info.append(t(soup,"small",f"0{i+1} / FLOWER 4"))
        info.append(t(soup,"strong",title.get_text(" ",strip=True)))
        info.append(t(soup,"span","Select to explore" if is_en else "اضغط للاختيار",css="fi-card-action"))
        card.append(info)
        deck.append(card)
    display.append(deck)
    foot=t(soup,"div",css="fi-units-bottom")
    foot.append(t(soup,"p","Selected type" if is_en else "نوع الوحدة المحدد",css="fi-selected-label"))
    first_title=units[0].select_one("h3").get_text(" ",strip=True)
    foot.append(t(soup,"strong",first_title,id="fi-selected-unit",css="fi-selected-unit"))
    foot.append(t(soup,"a","View original unit details ↗" if is_en else "عرض تفاصيل الوحدة الأصلية ←",
                  css="fi-unit-link",href="#flower-unit-choice-0",id="fi-unit-link"))
    display.append(foot)
    section.append(display)
    anchor.insert_after(section)
    for asset,typ in [("/assets/css/flower-interactive-v17-4.css","css"),("/assets/js/flower-interactive-v17-4.js","js")]:
        if typ=="css" and not soup.head.find("link",href=asset):
            soup.head.append(soup.new_tag("link",rel="stylesheet",href=asset))
        if typ=="js" and not soup.body.find("script",src=asset):
            soup.body.append(soup.new_tag("script",src=asset,defer=True))
