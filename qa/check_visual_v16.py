"""Headless Chromium viewport QA for FLOWER V16 staging. Read-only."""
import asyncio
import json
from pathlib import Path
from playwright.async_api import async_playwright

SITE = "https://flower-unified-staging.onrender.com"
VIEWS = [(390, 844, "mobile"), (1440, 900, "desktop")]
PAGES = [
    ("/", ".flower-v16-home-hero", ".v13-group-hero", "home"),
    ("/al-majmaah-harmah/", ".flower-v16-property-hero", ".v10-property-hero", "f4"),
    ("/en/", ".flower-v16-home-hero", ".v13-group-hero", "home-en"),
    ("/en/al-majmaah-harmah/", ".flower-v16-property-hero", ".v10-property-hero", "f4-en"),
]
out = Path("deploy-assets/v16-qa")
out.mkdir(parents=True, exist_ok=True)
summary = []

async def check(page, width, height, label, route, new, original, slug):
    url = SITE + route + "?design=editorial&check=v16"
    response = await page.goto(url, wait_until="domcontentloaded", timeout=60000)
    await page.locator(new).wait_for(state="visible", timeout=15000)
    await page.evaluate("document.fonts.ready")
    await page.wait_for_timeout(850)
    code = response.status if response else 0
    data = await page.evaluate("""({w:innerWidth,sw:document.documentElement.scrollWidth,sh:document.documentElement.scrollHeight,
       hero: (()=>{let r=document.querySelector(".flower-v16-home-hero,.flower-v16-property-hero").getBoundingClientRect();return {x:r.x,y:r.y,width:r.width,height:r.height}})(),
       images:[...document.querySelectorAll(".flower-v16-home-hero img,.flower-v16-property-hero img")].map(i=>({src:i.getAttribute("src"),ok:i.complete&&i.naturalWidth>0,visible:i.getBoundingClientRect().width>0})),
       primary: (()=>{let el=document.querySelector(".flower-v16-home-hero .v16-primary,.flower-v16-property-hero .v16-primary"); let r=el.getBoundingClientRect();return {x:r.x,right:r.right,y:r.y,height:r.height,text:el.textContent.trim(),href:el.getAttribute("href")}})(),
       booking:!!document.querySelector("#book-whatsapp,#book-arrival,#book-departure"),
       classicHeroHidden: (()=>{let e=document.querySelector(".v13-group-hero,.v10-property-hero");return getComputedStyle(e).display==="none"})(),
       current:new URLSearchParams(location.search).get("design"),
       newHeroVisible: (()=>{let e=document.querySelector(".flower-v16-home-hero,.flower-v16-property-hero");return getComputedStyle(e).display!=="none"})()
    })""")
    errors = []
    if code != 200: errors.append("response code " + str(code))
    if data["sw"] > width+2: errors.append("horizontal overflow " + str(data["sw"]-width))
    if data["hero"]["width"] > width+2: errors.append("hero exceeds width")
    if data["primary"]["x"] < -2 or data["primary"]["right"] > width+2: errors.append("primary CTA offscreen horizontally")
    if data["primary"]["height"] < 40: errors.append("primary CTA too short")
    if not data["classicHeroHidden"]: errors.append("old hero still visible")
    if not data["newHeroVisible"]: errors.append("new hero not visible")
    if not data["booking"]: errors.append("booking controls missing")
    if not all(i["ok"] for i in data["images"]):errors.append("one or more new hero photos missing")
    if width == 390 and data["hero"]["height"] < 340: errors.append("mobile hero too small")
    if width == 1440 and data["hero"]["height"] < 540: errors.append("desktop hero too small")
    screenshot = out / f"{slug}-{label}.png"
    await page.screenshot(path=str(screenshot), full_page=False)
    summary.append({"url":url,"viewport":[width,height],"data":data,"errors":errors,
                    "screenshot":str(screenshot)})
    print(("PASS" if not errors else "FAIL"), slug, label, json.dumps(data,ensure_ascii=False), "problems",errors)

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox"])
        try:
            for width,height,label in VIEWS:
                ctx = await browser.new_context(viewport={"width":width,"height":height},device_scale_factor=1)
                page = await ctx.new_page()
                for route,new,old,slug in PAGES:
                    await check(page,width,height,label,route,new,old,slug)
                # Same exact markup should show the old hero in comparison mode.
                await page.goto(SITE + "/?design=classic&check=v16",wait_until="domcontentloaded",timeout=60000)
                await page.locator(".v13-group-hero").wait_for(state="visible",timeout=10000)
                classic = await page.evaluate("""({old:getComputedStyle(document.querySelector(".v13-group-hero")).display,
                  fresh:getComputedStyle(document.querySelector(".flower-v16-home-hero")).display})""")
                if classic["old"]=="none" or classic["fresh"]!="none":
                    summary.append({"url":"classic", "viewport":[width,height], "errors":["A/B switcher invalid"],"state":classic})
                    print("FAIL A/B",width,classic)
                else:
                    print("PASS A/B",width,classic)
                await ctx.close()
        finally:
            await browser.close()
    (out/"summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding="utf-8")
    failures = [x for x in summary if x.get("errors")]
    print("V16 TOTAL CHECKS",len(summary),"FAILURES",len(failures))
    if failures:
        raise SystemExit(1)

if __name__ == "__main__":
    asyncio.run(main())
