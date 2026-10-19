import asyncio, json, os
from pathlib import Path
from playwright.async_api import async_playwright

BASE="https://flower-unified-staging.onrender.com"
OUT=Path("apple-qa")
OUT.mkdir(parents=True,exist_ok=True)
CASES=[
    ("/",390,"home-ar-mobile"),("/en/",390,"home-en-mobile"),
    ("/al-majmaah-harmah/",390,"flower4-ar-mobile"),
    ("/en/al-majmaah-harmah/",390,"flower4-en-mobile"),
    ("/al-majmaah-harmah/",320,"flower4-small"),
    ("/al-majmaah-harmah/",768,"flower4-tablet"),
    ("/al-majmaah-harmah/",1440,"flower4-desktop"),
    ("/",1440,"home-desktop"),
    ("/dammam-al-anoud/",390,"flower1-mobile"),
    ("/dammam-al-salam/",390,"flower2-mobile"),
    ("/al-qaisumah/",390,"flower3-mobile"),
]
async def main():
    reports=[]
    async with async_playwright() as p:
        for engine in ("chromium","webkit"):
            browser=await getattr(p,engine).launch(headless=True)
            for path,width,label in CASES:
                page=await browser.new_page(viewport={"width":width,"height":844 if width<800 else 900},device_scale_factor=1)
                errors=[]
                page.on("pageerror",lambda ex: errors.append(str(ex)))
                url=f"{BASE}{path}?apple_v17_check=20261019"
                try:
                    response=await page.goto(url,wait_until="domcontentloaded",timeout=30000)
                    await page.wait_for_timeout(1300)
                    data=await page.evaluate("""() => {
                      const r=s=>{const e=document.querySelector(s);if(!e)return null;const b=e.getBoundingClientRect();return {w:Math.round(b.width),h:Math.round(b.height),x:Math.round(b.x),y:Math.round(b.y),display:getComputedStyle(e).display}};
                      const hero=document.querySelector('.flower-v16-home-hero,.flower-v16-property-hero');
                      const image=document.querySelector('.flower-v16-hero-bg');
                      const form=document.querySelector('.v7-booking-form');
                      const branch=document.querySelector('#book-branch');
                      const css=Array.from(document.styleSheets).some(x=>x.href&&x.href.includes('flower-apple-v17.css'));
                      return {apple:document.documentElement.dataset.flowerApple,viewport:innerWidth,scroll:document.documentElement.scrollWidth,
                        h1:document.querySelectorAll('h1').length,hero:r('.flower-v16-home-hero,.flower-v16-property-hero'),
                        heroImage:r('.flower-v16-hero-bg'),imageLoaded:image?image.complete&&image.naturalWidth>0:null,
                        form:r('.v7-booking-form'),branch:r('#book-branch'),
                        switcher:r('.flower-design-compare'),css,canonical:document.querySelector('link[rel=canonical]')?.href,
                        robots:document.querySelector('meta[name=robots]')?.content,
                        google:document.querySelector('[data-google-rating="flower-4"]')?.textContent,
                        booking:document.querySelector('a[href*="booking.com"]')?.href,
                        whatsapp:!!document.querySelector('a[href*="wa.me"]'),heroBackground:hero?getComputedStyle(hero).backgroundColor:null,
                        galleryImages:Array.from(document.querySelectorAll('#gallery img')).slice(0,10).map(x=>({ok:x.complete&&x.naturalWidth>0,src:x.getAttribute('src')}))
                      };
                    }""")
                    problems=[]
                    if not response or response.status!=200:problems.append(f"http_{response.status if response else 'none'}")
                    if data["apple"]!="v17" or not data["css"]:problems.append("v17_missing")
                    if data["scroll"]>width+3:problems.append(f"overflow_{data['scroll']}")
                    if data["robots"] and "noindex" in data["robots"].lower():problems.append("noindex")
                    if not data["canonical"]:problems.append("canonical_missing")
                    if not data["booking"] or not data["whatsapp"]:problems.append("contact_links_missing")
                    if not data["form"] or data["form"]["w"]<min(width*.75,580):problems.append("booking_form_too_narrow")
                    if not data["branch"] or data["branch"]["w"]<min(width*.48,180):problems.append("branch_field_narrow")
                    if path in ("/","/en/","/al-majmaah-harmah/","/en/al-majmaah-harmah/"):
                        if data["h1"]!=1:problems.append(f"h1_{data['h1']}")
                        if not data["hero"] or not data["heroImage"] or not data["imageLoaded"]:problems.append("hero_image_missing")
                        if width<=430 and data["heroImage"] and data["heroImage"]["h"]<180:problems.append("hero_too_short")
                    if data["switcher"] and data["switcher"]["display"]!="none":problems.append("preview_switcher_visible")
                    if errors:problems.append("js_errors:"+str(errors)[:100])
                    if "flower4" in label:
                        if data["google"]!="4.6":problems.append("google_rating_wrong")
                    if "flower4" in label or label in ("home-ar-mobile","home-desktop"):
                        await page.screenshot(path=str(OUT/f"{engine}-{label}.png"),full_page=True)
                    report={"engine":engine,"case":label,"width":width,"status":"PASS" if not problems else "FAIL","problems":problems,"measurements":data}
                except Exception as exc:
                    report={"engine":engine,"case":label,"width":width,"status":"FAIL","problems":[type(exc).__name__+":"+str(exc)[:180]]}
                reports.append(report)
                print(json.dumps(report,ensure_ascii=False),flush=True)
                await page.close()
            await browser.close()
    (OUT/"report.json").write_text(json.dumps(reports,ensure_ascii=False,indent=2),encoding="utf-8")
    bad=[x for x in reports if x["status"]!="PASS"]
    print(f"FLOWER APPLE V17 QA: {len(reports)-len(bad)}/{len(reports)} PASS",flush=True)
    if bad:raise SystemExit(1)

if __name__=="__main__":
    asyncio.run(main())
