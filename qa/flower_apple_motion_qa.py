from __future__ import annotations
import asyncio,json,os
from pathlib import Path
from playwright.async_api import async_playwright

BASE=os.environ.get("FLOWER_MOTION_QA_BASE","https://flower-unified-staging.onrender.com").rstrip("/")
OUT=Path("apple-motion-qa")
OUT.mkdir(exist_ok=True)
CASES=[
    ("/al-majmaah-harmah/","f4-ar-390",390),
    ("/en/al-majmaah-harmah/","f4-en-390",390),
    ("/","home-ar-390",390),
    ("/en/","home-en-390",390),
    ("/al-majmaah-harmah/","f4-ar-1440",1440),
    ("/","home-ar-1440",1440),
]

async def main():
    reports=[]
    async with async_playwright() as playwright:
        for engine in ("chromium","webkit"):
            browser=await getattr(playwright,engine).launch()
            for route,label,width in CASES:
                context=await browser.new_context(viewport={"width":width,"height":850},device_scale_factor=1)
                page=await context.new_page()
                errors=[]
                page.on("pageerror",lambda error: errors.append(str(error)))
                result={"engine":engine,"case":label,"width":width,"issues":[]}
                try:
                    response=await page.goto(BASE+route+"?flower_motion_test=1",wait_until="domcontentloaded",timeout=35000)
                    await page.wait_for_timeout(1350)
                    before=await page.evaluate("""() => {
                      const doc=document.documentElement;
                      const img=document.querySelector('.flower-v16-hero-bg');
                      const form=document.querySelector('.v7-booking-form');
                      const gallery=document.querySelector('#gallery .v7-gallery-grid');
                      const btn=document.querySelector('#book-whatsapp');
                      return {http:location.hostname,mode:doc.dataset.flowerMotion,
                        w:innerWidth,scroll:doc.scrollWidth,
                        photo:!!img&&img.complete&&img.naturalWidth>0,
                        h1:document.querySelectorAll('h1').length,
                        formW:form?.getBoundingClientRect().width,
                        js:!!document.querySelector('script[src="/assets/js/flower-apple-motion.js"]'),
                        css:!!document.querySelector('link[href="/assets/css/flower-apple-motion.css"]'),
                        gallery:!!gallery,
                        heroAnimation:getComputedStyle(document.querySelector('h1')).animationName,
                        whatsapp:btn?.getAttribute('href'),
                        canonical:document.querySelector('link[rel=canonical]')?.href,
                        robots:document.querySelector('meta[name=robots]')?.content,
                        mediaExternal:[...document.querySelectorAll('img[src]')].filter(i=>i.src.startsWith('http')&&!i.src.startsWith(location.origin)).map(i=>i.src).slice(0,5)};
                    }""")
                    result["before"]=before
                    if not response or response.status!=200: result["issues"].append("http")
                    if before["mode"]!="enabled": result["issues"].append("motion_not_enabled")
                    if not before["js"] or not before["css"]: result["issues"].append("motion_assets_missing")
                    if "flower-motion-rise" not in before["heroAnimation"]: result["issues"].append("hero_not_animated")
                    if not before["photo"] or before["h1"]!=1: result["issues"].append("hero_or_h1_missing")
                    if before["scroll"]>width+3: result["issues"].append("body_horizontal_overflow")
                    if before["formW"]<width*.7 if width<700 else before["formW"]<600: result["issues"].append("form_too_narrow")
                    if not before["whatsapp"] or before["whatsapp"]=="#":result["issues"].append("whatsapp_link_missing")
                    if not before["canonical"] or (before["robots"] and "noindex" in before["robots"]):result["issues"].append("seo_broken")
                    if before["mediaExternal"]:result["issues"].append("unexpected_third_party_photos")
                    if width<700 and before["gallery"]:
                        await page.locator("#gallery").scroll_into_view_if_needed()
                        await page.wait_for_timeout(650)
                        nav=page.locator(".flower-gallery-nav")
                        if await nav.count()==0 or not await nav.is_visible():result["issues"].append("gallery_nav_missing")
                        else:
                            initial=await page.locator(".flower-gallery-status").inner_text()
                            next_btn=nav.locator("button").last
                            if await next_btn.is_enabled():
                                await next_btn.click()
                                await page.wait_for_timeout(780)
                                after=await page.locator(".flower-gallery-status").inner_text()
                                if initial==after: result["issues"].append("gallery_next_inert")
                                result["swipe"]={"before":initial,"after":after}
                    await page.screenshot(path=str(OUT/(engine+"-"+label+".png")),full_page=False)
                    # Prevent observing hidden text forever: scroll into view.
                    if await page.locator("#stay .v7-unit").count()>0:
                        card=page.locator("#stay .v7-unit").first
                        await card.scroll_into_view_if_needed()
                        await page.wait_for_timeout(850)
                        invisible=await card.evaluate("""el => {const s=getComputedStyle(el);return s.opacity==='0' || s.visibility==='hidden'}""")
                        if invisible:result["issues"].append("unit_card_still_invisible")
                    if errors:result["issues"].append("js_errors:"+str(errors)[:140])
                except Exception as e:
                    result["issues"].append(type(e).__name__+":"+str(e)[:180])
                result["status"]="PASS" if not result["issues"] else "FAIL"
                reports.append(result)
                print(json.dumps(result,ensure_ascii=False),flush=True)
                await context.close()
            # A reduced-motion visit must retain all site content and not activate effects.
            context=await browser.new_context(viewport={"width":390,"height":850},reduced_motion="reduce")
            page=await context.new_page()
            await page.goto(BASE+"/al-majmaah-harmah/?reduced_motion_qa=1",wait_until="domcontentloaded")
            await page.wait_for_timeout(650)
            val=await page.evaluate("""()=>({mode:document.documentElement.dataset.flowerMotion,h1:document.querySelectorAll('h1').length,
              image:document.querySelector('.flower-v16-hero-bg')?.naturalWidth>0,book:!!document.querySelector('#book-whatsapp')})""")
            issues=[] if val["mode"]=="disabled" and val["h1"]==1 and val["image"] and val["book"] else ["reduced_motion_failure"]
            reports.append({"engine":engine,"case":"reduced-motion","status":"PASS" if not issues else "FAIL","issues":issues,"metrics":val})
            await context.close()
            await browser.close()
    (OUT/"report.json").write_text(json.dumps(reports,ensure_ascii=False,indent=2))
    bad=[r for r in reports if r["status"]=="FAIL"]
    print(f"FLOWER APPLE MOTION QA: {len(reports)-len(bad)}/{len(reports)} PASS",flush=True)
    if bad:raise SystemExit(1)

if __name__=="__main__":
    asyncio.run(main())
