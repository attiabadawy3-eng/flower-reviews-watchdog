from __future__ import annotations
import asyncio, json, time, os
from pathlib import Path
from playwright.async_api import async_playwright

BASE=os.getenv("FLOWER_INTERACTIVE_BASE","https://flower-unified-staging.onrender.com").rstrip("/")
OUT=Path("interactive-qa"); OUT.mkdir(exist_ok=True)
NONCE=str(int(time.time()*1000))

async def check(page,route,width,engine,language):
    errors=[]
    page.on("pageerror",lambda e:errors.append(str(e)))
    issues=[]
    response=await page.goto(BASE+route+"?fiqa="+NONCE+engine+str(width),wait_until="load",timeout=45000)
    await page.wait_for_timeout(600)
    section=page.locator("#flower-interactive")
    if not response or response.status!=200: issues.append("http")
    if await section.count()!=1:
        issues.append("interactive_section_missing")
        return {"engine":engine,"case":language,"width":width,"status":"FAIL","issues":issues}
    await section.scroll_into_view_if_needed()
    await page.wait_for_timeout(350)
    # Photos are lazily loaded; verify each after scrolling it into view.
    for i in range(3):
        photo=page.locator(".fi-unit-card img").nth(i)
        await photo.scroll_into_view_if_needed()
        try:
            await page.wait_for_function(
              "(i) => {const img=document.querySelectorAll('.fi-unit-card img')[i];return img && img.complete && img.naturalWidth>0}",
              arg=i,timeout=6500)
        except Exception:
            issues.append("card_"+str(i)+"_photo_not_loaded_on_view")
    start=await page.evaluate("""() => {
      const root=document.documentElement, sec=document.querySelector('#flower-interactive');
      const img=document.querySelector('.flower-v16-hero-bg');
      const c=e=>e?.getBoundingClientRect().width;
      const cards=[...sec.querySelectorAll('.fi-unit-card img')];
      const originals=[...document.querySelectorAll('#stay .v7-unit-media img')].slice(0,3);
      return {ready:sec.dataset.fiReady,scrollWidth:root.scrollWidth,viewport:innerWidth,
        svg:!!sec.querySelector('svg.fi-building'), floors:sec.querySelectorAll('[data-fi-floor]').length,
        controls:sec.querySelectorAll('[data-fi-choose]').length,
        cards:cards.length, imgs:cards.map(i=>i.getAttribute('src')),
        originals:originals.map(i=>i.getAttribute('src')),
        loaded:cards.map(i=>i.complete&&i.naturalWidth>0),
        booking:!!document.getElementById('book-whatsapp')&&!!document.getElementById('book-unit')
                 &&!!document.getElementById('book-branch'),
        bookingCom:!!document.querySelector('a[href*="booking.com"]'),
        canonical:document.querySelector('link[rel=canonical]')?.href,
        heroOk:!!img&&img.complete&&img.naturalWidth>0,
        sectionWidth:c(sec),h1:document.querySelectorAll('h1').length,
        svgStroke:sec.querySelector('[data-fi-floor] polygon')?.getAttribute('stroke'),
        phone:!!document.querySelector('a[href*="wa.me"]')};
    }""")
    if start["ready"]!="true" or not start["svg"]:issues.append("interaction_not_initialized")
    if start["floors"]!=4 or start["controls"]!=4 or start["cards"]!=3:issues.append("wrong_counts")
    if start["imgs"]!=start["originals"]:issues.append("photos_not_original")
    if any(not x for x in start["loaded"]):issues.append("card_photo_failed")
    if start["scrollWidth"]>width+3:issues.append("horizontal_overflow")
    if not start["booking"] or not start["bookingCom"] or not start["phone"]:issues.append("booking_missing")
    if not start["canonical"] or start["h1"]!=1 or not start["heroOk"]:issues.append("baseline_missing")
    await page.locator('[data-fi-choose="2"]').click()
    chosen=await page.locator("#fi-level-value").inner_text()
    expected="Second floor" if language=="en" else "الثاني"
    if chosen!=expected:issues.append("floor_tap_failed:"+chosen)
    if await page.locator('[data-fi-floor="2"]').get_attribute("aria-pressed")!="true":issues.append("svg_floor_sync_failed")
    await page.locator('[data-fi-floor="3"]').focus()
    if await page.locator('[data-fi-choose="3"]').get_attribute("aria-pressed")!="true":issues.append("svg_keyboard_focus_failed")
    await page.locator('[data-fi-unit="1"]').click()
    selected=await page.locator("#fi-selected-unit").inner_text()
    actual=await page.locator("#stay .v7-unit h3").nth(1).inner_text()
    target=await page.locator("#fi-unit-link").get_attribute("href")
    if selected!=actual or target!="#flower-unit-choice-1":issues.append("card_selection_failed")
    await page.locator('[data-fi-unit="1"]').focus()
    await page.keyboard.press("ArrowRight")
    pressed=[await page.locator('[data-fi-unit="'+str(i)+'"]').get_attribute("aria-pressed") for i in range(3)]
    if pressed.count("true")!=1:issues.append("card_arrow_navigation_failed")
    if errors:issues.append("js_errors:"+str(errors)[:160])
    await section.screenshot(path=str(OUT/(engine+"-"+language+"-"+str(width)+".png")))
    return {"engine":engine,"case":language,"width":width,"status":"PASS" if not issues else "FAIL",
            "issues":issues,"metrics":{"building":start["floors"],"cards":start["cards"],
                "cardImageSourcesCorrect":start["imgs"]==start["originals"],
                "floorSelected":chosen,"selectedUnit":selected,"svgStroke":start["svgStroke"],
                "scrollWidth":start["scrollWidth"]}}

async def main():
    results=[]
    async with async_playwright() as p:
        for engine in ("chromium","webkit"):
            browser=await getattr(p,engine).launch()
            for route,language in (("/al-majmaah-harmah/","ar"),("/en/al-majmaah-harmah/","en")):
                for width in (390,768,1440):
                    context=await browser.new_context(viewport={"width":width,"height":850},device_scale_factor=1)
                    page=await context.new_page()
                    try:result=await check(page,route,width,engine,language)
                    except Exception as exc:result={"engine":engine,"case":language,"width":width,"status":"FAIL","issues":[repr(exc)[:200]]}
                    results.append(result);print(json.dumps(result,ensure_ascii=False),flush=True)
                    await context.close()
            for mode in ("reduced","nojs"):
                ctx=await browser.new_context(viewport={"width":390,"height":850},
                     reduced_motion="reduce" if mode=="reduced" else "no-preference",
                     java_script_enabled=mode!="nojs")
                page=await ctx.new_page()
                try:
                    await page.goto(BASE+"/al-majmaah-harmah/?mode="+mode+NONCE,wait_until="load",timeout=45000)
                    data=await page.evaluate("""()=>({
                       section:document.querySelectorAll('#flower-interactive').length,
                       cards:document.querySelectorAll('.fi-unit-card').length,
                       floors:document.querySelectorAll('[data-fi-floor]').length,
                       visible:getComputedStyle(document.querySelector('.fi-section')).display!=='none',
                       width:document.documentElement.scrollWidth,
                       motion:getComputedStyle(document.querySelector('.fi-unit-card')).transitionDuration
                    })""")
                    ok=data["section"]==1 and data["cards"]==3 and data["floors"]==4 and data["visible"] and data["width"]<=393
                    if mode=="reduced":ok=ok and data["motion"] in ("0s","0s, 0s")
                    result={"engine":engine,"case":mode,"status":"PASS" if ok else "FAIL","metrics":data}
                except Exception as exc:result={"engine":engine,"case":mode,"status":"FAIL","issues":[repr(exc)[:160]]}
                results.append(result);print(json.dumps(result,ensure_ascii=False),flush=True)
                await ctx.close()
            ctx=await browser.new_context(viewport={"width":390,"height":850})
            page=await ctx.new_page()
            await page.goto(BASE+"/?isolated="+NONCE,wait_until="domcontentloaded",timeout=45000)
            isolated=(await page.locator("#flower-interactive").count())==0
            result={"engine":engine,"case":"homepage-isolated","status":"PASS" if isolated else "FAIL"}
            results.append(result);print(json.dumps(result),flush=True)
            await ctx.close()
            await browser.close()
    (OUT/"report.json").write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding="utf-8")
    failed=[x for x in results if x["status"]!="PASS"]
    print(f"FLOWER INTERACTIVE V17.4 QA {len(results)-len(failed)}/{len(results)} PASS",flush=True)
    if failed:raise SystemExit(1)

if __name__=="__main__":
    asyncio.run(main())
