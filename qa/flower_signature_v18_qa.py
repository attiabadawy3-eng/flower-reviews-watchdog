from __future__ import annotations
import asyncio, json, time
from pathlib import Path
from playwright.async_api import async_playwright

BASE="https://flower-unified-staging.onrender.com"
OUT=Path("signature-v18-qa");OUT.mkdir(exist_ok=True)
STAMP=str(int(time.time()*1000))
CASES=[
 ("/al-majmaah-harmah/","ar",375),
 ("/al-majmaah-harmah/","ar",390),
 ("/al-majmaah-harmah/","ar",768),
 ("/al-majmaah-harmah/","ar",1440),
 ("/en/al-majmaah-harmah/","en",375),
 ("/en/al-majmaah-harmah/","en",390),
 ("/en/al-majmaah-harmah/","en",768),
 ("/en/al-majmaah-harmah/","en",1440),
]
async def measure(page):
    return await page.evaluate("""() => {
      const r=s=>{const e=document.querySelector(s);if(!e)return null;
        const b=e.getBoundingClientRect();return {x:Math.round(b.x),y:Math.round(b.y),w:Math.round(b.width),h:Math.round(b.height),
         display:getComputedStyle(e).display,visible:getComputedStyle(e).visibility}};
      const hero=document.querySelector('.lx-hero');
      const photo=hero?.querySelector('.flower-v16-hero-bg');
      const chapters=[...document.querySelectorAll('.lx-chapter-photo')];
      const units=[...document.querySelectorAll('#stay .v7-unit')];
      return {
       signature:document.documentElement.dataset.flowerSignature,
       viewport:innerWidth,docW:document.documentElement.scrollWidth,
       hero:r('.lx-hero'),media:r('.lx-media'),heroCopy:r('.lx-hero-content'),photo:r('.lx-media .flower-v16-hero-bg'),
       photoLoaded:!!photo&&photo.complete&&photo.naturalWidth>0,
       h1Count:document.querySelectorAll('h1').length,
       h1:r('.lx-hero h1'),story:r('#flower-signature'),storyCount:chapters.length,
       scenes:chapters.map(x=>x.getAttribute('src')),
       rooms:units.length,unitPhotos:units.map(x=>x.querySelector('.v7-unit-media img')?.getAttribute('src')),
       legacy:!!document.querySelector('#flower-interactive,#flower-cinema'),
       oldScript:!!document.querySelector('script[src="/assets/js/flower-apple-cinema.js"],script[src="/assets/js/flower-interactive-v17-4.js"]'),
       booking:!!document.querySelector('#book-whatsapp')&&!!document.querySelector('#book-branch')&&
         !!document.querySelector('#book-unit')&&!!document.querySelector('#book-arrival')&&!!document.querySelector('#book-departure'),
       bookingBtn:!!document.querySelector('.lx-hero a[href="#booking"]'),
       bookingCom:!!document.querySelector('a[href*="booking.com"]'),
       logo:!!document.querySelector('.v7-logo img[src*="flower-hotel-logo"]'),
       review:!!document.querySelector('[data-google-rating="flower-4"]'),
       canonical:document.querySelector('link[rel=canonical]')?.href,
       robots:document.querySelector('meta[name=robots]')?.content,
       v18CSS:!!document.querySelector('link[href="/assets/css/flower-signature-v18.css"]'),
       v18JS:!!document.querySelector('script[src="/assets/js/flower-signature-v18.js"]')
      };
    }""")

async def main():
    reports=[]
    async with async_playwright() as p:
      for browser_type in ("chromium","webkit"):
        browser=await getattr(p,browser_type).launch()
        for path,lang,width in CASES:
          ctx=await browser.new_context(viewport={"width":width,"height":840},device_scale_factor=1)
          page=await ctx.new_page()
          errors=[]
          page.on("pageerror",lambda e:errors.append(str(e)))
          issues=[]
          try:
            response=await page.goto(BASE+path+"?signatureV18="+STAMP+browser_type+str(width),wait_until="load",timeout=45000)
            await page.wait_for_timeout(750)
            d=await measure(page)
            if not response or response.status!=200:issues.append("http")
            if d["signature"]!="v18" or not d["v18CSS"] or not d["v18JS"]:issues.append("missing_signature")
            if d["legacy"] or d["oldScript"]:issues.append("rejected_component_still_present")
            if d["storyCount"]!=3 or d["rooms"]!=3:issues.append("missing_rooms_or_photos")
            if d["docW"]>width+3:issues.append("horizontal_overflow")
            if not d["photoLoaded"] or not d["photo"] or d["photo"]["h"]<250:issues.append("hero_image_invalid")
            if width<=390 and d["media"] and d["heroCopy"] and d["media"]["y"]>d["heroCopy"]["y"]:issues.append("not_image_first_mobile")
            if width>=1100 and d["media"] and d["media"]["w"]<width*.45:issues.append("not_photo_led_desktop")
            if d["h1Count"]!=1 or not d["h1"] or not d["canonical"]:issues.append("seo_or_headline")
            if not all([d["booking"],d["bookingBtn"],d["bookingCom"],d["logo"],d["review"]]):issues.append("booking_identity_or_google")
            if not all(u and u.startswith('/assets/images/al-majmaah-harmah/') for u in d["scenes"]+d["unitPhotos"]):
              issues.append("unverified_photo")
            if d["robots"] and "noindex" in d["robots"].lower():issues.append("noindex")
            if errors:issues.append("javascript:"+str(errors)[:130])
            if width in (390,1440):
              await page.screenshot(path=str(OUT/(browser_type+"-"+lang+"-"+str(width)+"-top.png")),full_page=False)
              # Check real source photograph renders after scroll to a story chapter.
              photo=page.locator(".lx-chapter-photo").first
              await photo.scroll_into_view_if_needed()
              try:
                await page.wait_for_function("() => {let i=document.querySelector('.lx-chapter-photo');return i&&i.complete&&i.naturalWidth>0}",timeout=8000)
              except Exception:issues.append("story_photo_not_loaded")
              await page.screenshot(path=str(OUT/(browser_type+"-"+lang+"-"+str(width)+"-story.png")),full_page=False)
            outcome={"browser":browser_type,"lang":lang,"width":width,"status":"PASS" if not issues else "FAIL","issues":issues,
              "metrics":{"photoLoaded":d["photoLoaded"],"media":d["media"],"copy":d["heroCopy"],
                "storyCount":d["storyCount"],"roomCount":d["rooms"],"scroll":d["docW"]}}
          except Exception as e:
            outcome={"browser":browser_type,"lang":lang,"width":width,"status":"FAIL","issues":[repr(e)[:230]]}
          reports.append(outcome);print(json.dumps(outcome,ensure_ascii=False),flush=True)
          await ctx.close()
        for mode in ("reduced","nojs"):
          ctx=await browser.new_context(viewport={"width":390,"height":840},
            java_script_enabled=(mode!="nojs"),reduced_motion="reduce" if mode=="reduced" else "no-preference")
          page=await ctx.new_page()
          try:
            await page.goto(BASE+"/al-majmaah-harmah/?mode="+mode+STAMP,wait_until="load",timeout=45000)
            d=await measure(page)
            visible=d["signature"]=="v18" and d["photoLoaded"] and d["storyCount"]==3 and d["booking"] and d["docW"]<=393
            o={"browser":browser_type,"case":mode,"status":"PASS" if visible else "FAIL","metrics":{"scroll":d["docW"],"photo":d["photoLoaded"],"story":d["storyCount"]}}
          except Exception as e:o={"browser":browser_type,"case":mode,"status":"FAIL","issues":[repr(e)[:160]]}
          reports.append(o);print(json.dumps(o,ensure_ascii=False),flush=True)
          await ctx.close()
        await browser.close()
    (OUT/"report.json").write_text(json.dumps(reports,indent=2,ensure_ascii=False),encoding="utf-8")
    failures=[x for x in reports if x["status"]!="PASS"]
    print(f"FLOWER SIGNATURE V18 QA: {len(reports)-len(failures)}/{len(reports)} PASS",flush=True)
    if failures:raise SystemExit(1)

if __name__=="__main__":
 asyncio.run(main())
