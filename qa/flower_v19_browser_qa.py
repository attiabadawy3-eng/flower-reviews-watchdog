"""FLOWER Signature V19 staging-only browser verification and authentic screenshots.
Captures real browser pixels from staging, never fabricated or generated artwork.
"""
from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from playwright.async_api import async_playwright

ROOT = "https://flower-unified-staging.onrender.com"
PAGES = [
    "/", "/en/",
    "/dammam-al-anoud/", "/en/dammam-al-anoud/",
    "/dammam-al-salam/", "/en/dammam-al-salam/",
    "/al-qaisumah/", "/en/al-qaisumah/",
    "/al-majmaah-harmah/", "/en/al-majmaah-harmah/",
]
OUT = Path("qa/v19-evidence")
OUT.mkdir(parents=True, exist_ok=True)

async def main():
    rows=[]
    errors=[]
    async with async_playwright() as playwright:
        browser=await playwright.chromium.launch(headless=True,args=["--no-sandbox"])
        for mode, vp, mobile in [
            ("desktop",{"width":1440,"height":900},False),
            ("mobile",{"width":390,"height":844},True)
        ]:
            context=await browser.new_context(
                viewport=vp,device_scale_factor=1,
                is_mobile=mobile,has_touch=mobile,
                locale="en-GB" if False else "ar-SA",
                reduced_motion="reduce" if mobile else "no-preference",
            )
            for path in PAGES:
                page=await context.new_page()
                exceptions=[]
                page.on("pageerror",lambda err: exceptions.append(str(err)))
                name=(path.strip("/").replace("/","-") or "home")
                try:
                    response=await page.goto(ROOT+path,wait_until="domcontentloaded",timeout=45000)
                    await page.locator("section.fx19-hero").wait_for(state="visible",timeout=18000)
                    await page.wait_for_timeout(900)
                    assert response and response.status==200,(path,response.status if response else None)
                    data=await page.evaluate("""() => {
                      const one=(s)=>document.querySelector(s);
                      const hero=one('.fx19-hero'),heroImg=one('.fx19-hero-media img'),logo=one('.v7-logo img');
                      const b=one('#booking');
                      return {
                        title:document.title,lang:document.documentElement.lang,
                        h1:document.querySelectorAll('h1').length,
                        hero:!!hero,heroLoaded:!!heroImg&&heroImg.complete&&heroImg.naturalWidth>0,
                        heroHeight:hero?.getBoundingClientRect().height,
                        heroCss:getComputedStyle(hero).minHeight,
                        logoLoaded:!!logo&&logo.complete&&logo.naturalWidth>0,
                        bookTop:b?.getBoundingClientRect().top,
                        bookFields:['book-branch','book-unit','book-arrival','book-departure','book-adults','book-children','book-whatsapp','book-booking'].every(id=>!!document.getElementById(id)),
                        branches:one('#book-branch')?.options.length,
                        hasCss:!!one('link[href*="flower-signature-v19-bundle-"]'),
                        hasJs:!!one('script[src="/assets/js/flower-signature-v19.js"]'),
                        canonical:!!one('link[rel=canonical]'),meta:!!one('meta[name=description]'),
                        bodyWidth:document.documentElement.scrollWidth,viewport:innerWidth,
                        policy:Array.from(document.querySelectorAll('.v7-policy-list>div')).map(el=>[el.querySelector('span')?.innerText.trim(),el.querySelector('strong')?.innerText.trim()]),
                        units:document.querySelectorAll('#stay .v7-unit').length,
                        whatsapp:!!document.querySelector('a[href^="https://wa.me/"]'),
                        booking:!!document.querySelector('a[href*="booking.com"]')
                      };
                    }""")
                    assert data["h1"]==1,(path,data["h1"])
                    assert data["hasCss"] and data["hasJs"] and data["heroLoaded"] and data["logoLoaded"],(path,"assets",data)
                    assert data["bookFields"] and data["branches"]==4,(path,"booking widget")
                    assert data["canonical"] and data["meta"],(path,"SEO")
                    assert data["bodyWidth"]<=data["viewport"]+8,(mode,path,"horizontal overflow",data["bodyWidth"],data["viewport"])
                    if path not in ("/","/en/"):
                        assert data["units"]>=3 and data["whatsapp"] and data["booking"],(path,"property units booking")
                        en=path.startswith("/en/")
                        expected=["4:00 PM","2:00 PM"] if en else ["4:00 م","2:00 م"]
                        rows2={x[0]:x[1] for x in data["policy"]}
                        assert rows2.get("Check-in" if en else "وقت الدخول")==expected[0],(path,rows2)
                        assert rows2.get("Check-out" if en else "وقت الخروج")==expected[1],(path,rows2)
                    # Ensure V19's validation works without navigating away.
                    if path in ("/","/en/"):
                        await page.locator("#book-arrival").fill("2026-11-18")
                        await page.locator("#book-departure").fill("2026-11-17")
                        invalid=await page.locator("#book-departure").get_attribute("aria-invalid")
                        actual_arrival=await page.locator("#book-arrival").input_value()
                        actual_departure=await page.locator("#book-departure").input_value()
                        # The existing FLOWER booking engine may auto-correct an
                        # invalid departure date. Both that and V19 inline validation
                        # are acceptable, but a silently invalid stay is not.
                        assert invalid=="true" or (actual_arrival and actual_departure and actual_departure>actual_arrival), (path,"invalid date neither blocked nor corrected",invalid,actual_arrival,actual_departure)
                        await page.locator("#book-departure").fill("2026-11-20")
                        valid=await page.locator("#book-departure").get_attribute("aria-invalid")
                        assert valid=="false",(path,"date reset",valid)
                    assert not exceptions,(path,"uncaught browser exceptions",exceptions)
                    if (mode,path) in [
                        ("desktop","/"),("mobile","/"),
                        ("desktop","/al-majmaah-harmah/"),("mobile","/al-majmaah-harmah/"),
                        ("desktop","/dammam-al-anoud/"),("mobile","/dammam-al-anoud/")
                    ]:
                        # The capture is from the actual rendered website, not a mocked HTML file.
                        await page.evaluate("window.scrollTo(0,0)")
                        await page.wait_for_timeout(200)
                        await page.screenshot(path=str(OUT/f"{name}-{mode}.png"),full_page=False,animations="disabled")
                    if (mode,path)==("mobile","/"):
                        await page.locator("#booking").scroll_into_view_if_needed()
                        await page.screenshot(path=str(OUT/"home-mobile-booking.png"),full_page=False,animations="disabled")
                    if (mode,path)==("desktop","/"):
                        await page.locator("#booking").scroll_into_view_if_needed()
                        await page.screenshot(path=str(OUT/"home-desktop-booking.png"),full_page=False,animations="disabled")
                    rows.append({"mode":mode,"page":path,"status":"PASS","heroHeight":round(data["heroHeight"]),"bookingTop":round(data["bookTop"]),"horizontalOverflow":max(0,data["bodyWidth"]-data["viewport"]),"unitCount":data["units"],"originalHeroLoaded":True})
                    print("PASS",mode,path,"overflow",max(0,data["bodyWidth"]-data["viewport"]),flush=True)
                except Exception as exc:
                    errors.append({"mode":mode,"page":path,"error":str(exc)[:1300]})
                    print("FAIL",mode,path,str(exc)[:700],flush=True)
                    await page.screenshot(path=str(OUT/f"fail-{name}-{mode}.png"),full_page=False,animations="disabled")
                finally:
                    await page.close()
            await context.close()
        await browser.close()
    report={"source":ROOT,"variant":"FLOWER Signature V19","screenshots":"authentic Playwright Chromium 1440x900 + 390x844","pageChecks":len(rows)+len(errors),"passed":len(rows),"failed":len(errors),"errors":errors,"results":rows}
    (OUT/"browser-qa.json").write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print("BROWSER_RESULT",json.dumps({"checked":report["pageChecks"],"passed":len(rows),"failed":len(errors),"evidence":sorted(x.name for x in OUT.glob("*.png"))},ensure_ascii=False))
    if errors: raise SystemExit(1)
if __name__=="__main__":
    asyncio.run(main())
