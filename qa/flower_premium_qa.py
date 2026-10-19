from __future__ import annotations
import asyncio, json
from pathlib import Path
from playwright.async_api import async_playwright

BASE = "https://flower-unified-staging.onrender.com"
OUT = Path("premium-qa")
OUT.mkdir(exist_ok=True)

async def main():
    reports=[]
    async with async_playwright() as playwright:
        for engine in ("chromium", "webkit"):
            browser=await getattr(playwright,engine).launch()
            for path in ("/al-majmaah-harmah/","/en/al-majmaah-harmah/"):
                for width in (375,390,430,768,1440):
                    context=await browser.new_context(viewport={"width":width,"height":860},device_scale_factor=1)
                    page=await context.new_page()
                    errors=[]
                    page.on("pageerror",lambda e:errors.append(str(e)))
                    issues=[]
                    try:
                        response=await page.goto(BASE+path+"?premium_v17_3=1",wait_until="load",timeout=45000)
                        await page.wait_for_timeout(750)
                        details=await page.evaluate("""() => {
                            const rect=el=>{if(!el)return null;const r=el.getBoundingClientRect();return {
                              x:Math.round(r.x),y:Math.round(r.y),width:Math.round(r.width),height:Math.round(r.height),
                              opacity:getComputedStyle(el).opacity,visible:getComputedStyle(el).visibility,
                              display:getComputedStyle(el).display
                            }};
                            const hero=document.querySelector('.flower-v16-property-hero');
                            const image=hero?.querySelector('.flower-v16-hero-bg');
                            const h1=hero?.querySelector('h1');
                            const premium=document.querySelector('#flower-cinema[data-flower-story="premium"]');
                            const booking=document.querySelector('#booking');
                            const firstUnit=document.querySelector('#stay .v7-unit');
                            const media=firstUnit?.querySelector('.v7-unit-media');
                            const copy=firstUnit?.querySelector('.v7-unit-copy');
                            return {width:innerWidth,scrollWidth:document.documentElement.scrollWidth,
                              hero:rect(hero),heroImage:rect(image),imageLoaded:!!image&&image.complete&&image.naturalWidth>0,
                              imageSrc:image?.getAttribute('src'),h1:rect(h1),h1Count:document.querySelectorAll('h1').length,
                              premium:!!premium,assets:!!document.querySelector('link[href="/assets/css/flower-apple-premium-v17-3.css"]'),
                              cinemaMode:document.documentElement.dataset.flowerCinema,
                              booking:rect(booking),fields:['book-branch','book-unit','book-whatsapp'].every(id=>!!document.getElementById(id)),
                              bookingCom:!!document.querySelector('a[href*="booking.com"]'),
                              canonical:document.querySelector('link[rel="canonical"]')?.href,
                              unit:rect(firstUnit),unitMedia:rect(media),unitCopy:rect(copy),
                              copyTitles:[...premium?.querySelectorAll('.flower-cinema-copy h3')||[]].map(e=>e.textContent.trim()),
                              cta:premium?.querySelector('.flower-cinema-link')?.getAttribute('href'),
                              cinemaPhotos:[...premium?.querySelectorAll('.flower-cinema-scene img')||[]].map(x=>x.getAttribute('src'))};
                        }""")
                        if response is None or response.status!=200:issues.append("http_failed")
                        if not details["premium"] or not details["assets"]:issues.append("premium_not_deployed")
                        if not details["imageLoaded"]:issues.append("hero_image_not_loaded")
                        if not details["heroImage"] or details["heroImage"]["height"]<220:issues.append("hero_photo_too_small")
                        if width<=430 and details["heroImage"] and details["h1"] and details["heroImage"]["y"]>details["h1"]["y"]:
                            issues.append("mobile_not_image_first")
                        if details["scrollWidth"]>width+3:issues.append("horizontal_overflow")
                        if not details["fields"] or not details["bookingCom"] or not details["booking"]:issues.append("booking_missing")
                        if details["h1Count"]!=1 or not details["canonical"]:issues.append("seo_invalid")
                        if len(details["cinemaPhotos"])!=3 or any(not z.startswith('/assets/images/al-majmaah-harmah/') for z in details["cinemaPhotos"]):
                            issues.append("non_original_cinema_photos")
                        if len(details["copyTitles"])!=3:issues.append("story_titles_missing")
                        if details["cta"]!="#booking":issues.append("final_enquiry_link_missing")
                        if not details["unit"] or not details["unitMedia"] or not details["unitCopy"]:issues.append("units_missing")
                        if width>=900 and details["unitMedia"] and details["unitCopy"] and
                            min(details["unitMedia"]["width"],details["unitCopy"]["width"])<width*.25):
                            issues.append("desktop_units_layout_too_narrow")
                        if errors:issues.append("js_errors:"+str(errors)[:100])
                        await page.screenshot(path=str(OUT/(engine+"-"+("en" if path.startswith("/en/") else "ar")+"-"+str(width)+".png")),full_page=False)
                        reports.append({"engine":engine,"path":path,"width":width,"status":"PASS" if not issues else "FAIL","issues":issues,"metrics":details})
                    except Exception as exc:
                        reports.append({"engine":engine,"path":path,"width":width,"status":"FAIL","issues":[type(exc).__name__+":"+str(exc)[:160]]})
                    print(json.dumps(reports[-1],ensure_ascii=False),flush=True)
                    await context.close()
            # Check the three photo chapters remain scroll-linked in both languages.
            context=await browser.new_context(viewport={"width":390,"height":860})
            page=await context.new_page()
            await page.goto(BASE+"/al-majmaah-harmah/?chapter_premium=1",wait_until="load")
            chapters=[]
            for fraction in (.08,.51,.92):
                await page.evaluate("""fraction=>{
                  document.documentElement.style.setProperty('scroll-behavior','auto','important');
                  document.body.style.setProperty('scroll-behavior','auto','important');
                  const track=document.querySelector('#flower-cinema [data-cinema-track]');
                  const stage=document.querySelector('#flower-cinema [data-cinema-stage]');
                  const top=scrollY+track.getBoundingClientRect().top;
                  scrollTo(0,top+(track.getBoundingClientRect().height-stage.clientHeight)*fraction);
                }""",fraction)
                await page.wait_for_timeout(700)
                chapters.append(await page.evaluate("""() => ({
                  chapter:document.querySelector('#flower-cinema [data-cinema-stage]')?.dataset.cinemaChapter,
                  cta:getComputedStyle(document.querySelector('.flower-cinema-link')).visibility,
                  copyOpacity:getComputedStyle(document.querySelector('.flower-cinema-scene[data-cinema-scene="2"] .flower-cinema-copy')).opacity
                })"""))
            ok=[x["chapter"] for x in chapters]==["1","2","3"] and chapters[-1]["cta"]=="visible" and chapters[0]["cta"]=="hidden"
            reports.append({"engine":engine,"path":"/al-majmaah-harmah/","width":390,"case":"chapters_and_final_cta","status":"PASS" if ok else "FAIL","metrics":chapters})
            print(json.dumps(reports[-1]),flush=True)
            await context.close()
            # Respect reduced motion and no-JS static fallback.
            for mode in ("reduce","nojs"):
                context=await browser.new_context(viewport={"width":390,"height":860},
                    reduced_motion="reduce" if mode=="reduce" else "no-preference",
                    java_script_enabled=mode!="nojs")
                page=await context.new_page()
                await page.goto(BASE+"/al-majmaah-harmah/?accessibility="+mode,wait_until="load",timeout=45000)
                await page.wait_for_timeout(250)
                vals=await page.evaluate("""() => ({
                   cinema:document.documentElement.dataset.flowerCinema,
                   scenes:[...document.querySelectorAll('#flower-cinema [data-cinema-scene]')].map(x=>getComputedStyle(x).opacity),
                   overflow:document.documentElement.scrollWidth>innerWidth+3,
                   booking:!!document.querySelector('#book-whatsapp')
                })""")
                ok=vals["cinema"] in (None,"static") and all(float(x)>.8 for x in vals["scenes"]) and not vals["overflow"] and vals["booking"]
                reports.append({"engine":engine,"case":mode,"status":"PASS" if ok else "FAIL","metrics":vals})
                print(json.dumps(reports[-1]),flush=True)
                await context.close()
            await browser.close()
    (OUT/"report.json").write_text(json.dumps(reports,ensure_ascii=False,indent=2),encoding="utf-8")
    failures=[x for x in reports if x["status"]!="PASS"]
    print(f"FLOWER PREMIUM V17.3 BROWSER QA {len(reports)-len(failures)}/{len(reports)} PASS",flush=True)
    if failures:raise SystemExit(1)

if __name__=="__main__":
    asyncio.run(main())
