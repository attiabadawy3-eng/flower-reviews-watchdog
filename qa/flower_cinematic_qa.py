from __future__ import annotations
import asyncio, json
from pathlib import Path
from playwright.async_api import async_playwright

BASE="https://flower-unified-staging.onrender.com"
OUT=Path("apple-cinematic-qa")
OUT.mkdir(exist_ok=True)
ROUTES=[
    ("/al-majmaah-harmah/","flower4-ar-390",390),
    ("/en/al-majmaah-harmah/","flower4-en-390",390),
    ("/al-majmaah-harmah/","flower4-ar-1440",1440),
    ("/en/al-majmaah-harmah/","flower4-en-1440",1440),
]

async def measure(page):
    return await page.evaluate("""() => {
       const root=document.documentElement, area=document.querySelector('#flower-cinema');
       const track=area?.querySelector('[data-cinema-track]');
       const stage=area?.querySelector('[data-cinema-stage]');
       const scenes=Array.from(area?.querySelectorAll('[data-cinema-scene]')||[]);
       const img=area?.querySelector('img');
       return {
         mode:root.dataset.flowerCinema, motion:root.dataset.flowerMotion, width:innerWidth,
         scrollWidth:root.scrollWidth, h1:document.querySelectorAll('h1').length,
         area:!!area, stageHeight:stage?.getBoundingClientRect().height,
         trackHeight:track?.getBoundingClientRect().height,
         sceneCount:scenes.length, chapter:stage?.dataset.cinemaChapter,
         opacity:scenes.map(x=>Number(getComputedStyle(x).opacity)),
         aria:scenes.map(x=>x.getAttribute('aria-hidden')),
         photoReady:!!img&&img.complete&&img.naturalWidth>0,
         imageUrls:scenes.map(x=>x.querySelector('img')?.getAttribute('src')),
         cta:area?.querySelector('a.flower-cinema-link')?.getAttribute('href'),
         booking:!!document.querySelector('#book-branch')&&!!document.querySelector('#book-unit')&&!!document.querySelector('#book-whatsapp'),
         bookingLink:!!document.querySelector('a[href*="booking.com"]'),
         canonical:document.querySelector('link[rel=canonical]')?.href,
         css:!!document.querySelector('link[href="/assets/css/flower-apple-cinema.css"]'),
         js:!!document.querySelector('script[src="/assets/js/flower-apple-cinema.js"]'),
       }
    }""")

async def move(page,fraction):
    await page.evaluate("""fraction=>{
      const track=document.querySelector('#flower-cinema [data-cinema-track]');
      const rect=track.getBoundingClientRect();
      const top=window.scrollY+rect.top;
      const distance=Math.max(0,rect.height-document.querySelector('#flower-cinema [data-cinema-stage]').clientHeight);
      window.scrollTo({top:top+distance*fraction,behavior:'instant'});
    }""", fraction)
    await page.wait_for_timeout(370)
    return await measure(page)

async def main():
    results=[]
    async with async_playwright() as p:
        for browser_name in ("chromium","webkit"):
            browser=await getattr(p,browser_name).launch()
            for route,label,width in ROUTES:
                context=await browser.new_context(viewport={"width":width,"height":860},device_scale_factor=1)
                page=await context.new_page()
                errs=[]
                page.on("pageerror",lambda e:errs.append(str(e)))
                problems=[]
                try:
                    response=await page.goto(BASE+route+"?cinema_qa=20261019",wait_until="domcontentloaded",timeout=40000)
                    await page.wait_for_timeout(1000)
                    start=await move(page,.08)
                    mid=await move(page,.51)
                    end=await move(page,.92)
                    if response is None or response.status!=200:problems.append("http_non200")
                    if start["mode"]!="ready":problems.append("cinema_not_active")
                    if any(not x["css"] or not x["js"] for x in (start,mid,end)):problems.append("assets_missing")
                    if any(x["sceneCount"]!=3 or not x["area"] for x in (start,mid,end)):problems.append("cinematic_scenes_missing")
                    if not start["photoReady"]:problems.append("original_photo_failed")
                    if start["chapter"]!="1" or mid["chapter"]!="2" or end["chapter"]!="3":problems.append("chapter_does_not_advance")
                    if not (start["opacity"][0]>.8 and mid["opacity"][1]>.8 and end["opacity"][2]>.8):problems.append("crossfade_incorrect")
                    if any(x["scrollWidth"]>width+3 for x in (start,mid,end)):problems.append("horizontal_overflow")
                    if any(x["cta"]!="#booking" or not x["booking"] or not x["bookingLink"] for x in (start,mid,end)):problems.append("booking_missing")
                    if any(x["h1"]!=1 or not x["canonical"] for x in (start,mid,end)):problems.append("seo_or_h1")
                    allowed_prefix="/assets/images/al-majmaah-harmah/"
                    if not all(u and u.startswith(allowed_prefix) for u in mid["imageUrls"]):problems.append("non_flower4_image")
                    if errs:problems.append("javascript_error:"+str(errs)[:100])
                    await page.screenshot(path=str(OUT/(browser_name+"-"+label+".png")),full_page=False)
                    result={"browser":browser_name,"case":label,"status":"PASS" if not problems else "FAIL","problems":problems,
                             "chapters":[start["chapter"],mid["chapter"],end["chapter"]],
                             "opacity":[start["opacity"],mid["opacity"],end["opacity"]],
                             "width":width,"imageLoaded":start["photoReady"]}
                except Exception as e:
                    result={"browser":browser_name,"case":label,"status":"FAIL","problems":[repr(e)[:250]]}
                results.append(result)
                print(json.dumps(result,ensure_ascii=False),flush=True)
                await context.close()
            # Reduced motion: all 3 scenes readable (no sticky JS, no hidden opacity).
            context=await browser.new_context(viewport={"width":390,"height":860},reduced_motion="reduce")
            page=await context.new_page()
            await page.goto(BASE+"/al-majmaah-harmah/?cinema_reduce=1",wait_until="domcontentloaded")
            await page.wait_for_timeout(350)
            data=await measure(page)
            ok=data["mode"] in (None,"static") and data["sceneCount"]==3 and data["booking"] and data["scrollWidth"]<=393
            results.append({"browser":browser_name,"case":"reduced-motion","status":"PASS" if ok else "FAIL","metrics":data})
            await context.close()
            # JS disabled: semantic complete scenes must remain visible.
            context=await browser.new_context(viewport={"width":390,"height":860},java_script_enabled=False)
            page=await context.new_page()
            await page.goto(BASE+"/al-majmaah-harmah/?cinema_nojs=1",wait_until="domcontentloaded")
            data=await measure(page)
            ok=data["mode"] is None and data["sceneCount"]==3 and data["booking"] and data["scrollWidth"]<=393
            results.append({"browser":browser_name,"case":"no-js-fallback","status":"PASS" if ok else "FAIL","metrics":data})
            await context.close()
            # Other branches and homepage cannot inherit cinematic panel.
            context=await browser.new_context(viewport={"width":390,"height":860})
            page=await context.new_page()
            await page.goto(BASE+"/?cinema_homecheck=1",wait_until="domcontentloaded")
            ok=(await page.locator("#flower-cinema").count())==0 and (await page.locator("#book-branch").count())>0
            results.append({"browser":browser_name,"case":"homepage-isolated","status":"PASS" if ok else "FAIL"})
            await context.close()
            await browser.close()
    (OUT/"report.json").write_text(json.dumps(results,ensure_ascii=False,indent=2))
    failed=[r for r in results if r["status"]!="PASS"]
    print(f"FLOWER CINEMATIC V17.2 QA: {len(results)-len(failed)}/{len(results)} PASS",flush=True)
    if failed:raise SystemExit(1)

if __name__=="__main__":
    asyncio.run(main())
