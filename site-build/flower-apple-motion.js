/* Flower Apple Motion V17.1. No external dependencies, no network requests.
 * Honors reduced motion and data saver, never touches booking state or user info.
 */
(() => {
  "use strict";
  const root = document.documentElement;
  if (root.dataset.flowerApple !== "v17") return;
  const mqReduce = window.matchMedia("(prefers-reduced-motion: reduce)");
  const saveData = navigator.connection?.saveData === true;
  const allow = !mqReduce.matches && !saveData;
  if (!allow) {
    root.dataset.flowerMotion = "disabled";
    return;
  }
  const start = () => {
    root.dataset.flowerMotion = "enabled";
    // Sections already use v11-reveal; animate child headings/photos only once.
    const items = Array.from(document.querySelectorAll([
      "#stay .v7-section-head", "#stay .v7-unit",
      "#services .v7-section-head", "#services .v7-service",
      "#reviews .v7-section-head", "#reviews .v7-review-card",
      "#gallery .v7-section-head", "#about .v7-section-head",
      ".v8-similar .v7-branch-card", ".v7-final-cta .wrap"
    ].join(", "))).slice(0,40);
    if ("IntersectionObserver" in window) {
      let step = 0;
      const observer = new IntersectionObserver(entries => {
        for (const entry of entries) {
          if (!entry.isIntersecting) continue;
          entry.target.classList.add("flower-in-view");
          observer.unobserve(entry.target);
        }
      }, {rootMargin:"0px 0px -6% 0px",threshold:.1});
      for(const item of items){
        const bounds=item.getBoundingClientRect();
        // Never hide above-the-fold content or anything the user already scrolled past.
        if(bounds.top < window.innerHeight*.85) continue;
        item.style.setProperty("--fm-item-delay", String((step++%3)*75)+"ms");
        item.classList.add("flower-scroll-prepare");
        observer.observe(item);
      }
      // Guarantee no content remains hidden if page is backgrounded/restored.
      window.addEventListener("pageshow",ev=>{
        if(ev.persisted) for(const item of items) item.classList.add("flower-in-view");
      });
    }
    // Hero scroll progress controls a minimal photography-only transform.
    const image = document.querySelector(".flower-v16-hero-bg");
    const hero = image?.closest(".flower-v16-home-hero,.flower-v16-property-hero");
    const desktop = window.matchMedia("(min-width: 901px) and (hover: hover)");
    let pending = false;
    const refresh = () => {
      pending = false;
      if(!image || !hero || !desktop.matches) return;
      const rect=hero.getBoundingClientRect();
      if(rect.bottom < -50 || rect.top > innerHeight+50) return;
      const progress=Math.min(1,Math.max(0,(innerHeight-rect.top)/(innerHeight+rect.height)));
      const eased=progress*progress*(3-2*progress);
      image.style.setProperty("--fm-hero-scale",(1+eased*.042).toFixed(4));
      image.style.setProperty("--fm-hero-shift",(-eased*9).toFixed(1)+"px");
    };
    const tick = () => {
      if (!pending) {pending=true;requestAnimationFrame(refresh);}
    };
    if(hero){
      addEventListener("scroll",tick,{passive:true});
      addEventListener("resize",tick,{passive:true});
      tick();
    }
    // Phone-size swipe gallery with functional previous/next controls.
    const gallery = document.querySelector("#gallery .v7-gallery-grid");
    if (!gallery || gallery.parentElement.querySelector(".flower-gallery-nav")) return;
    const nav = document.createElement("div");
    nav.className = "flower-gallery-nav";
    const prev = document.createElement("button");
    prev.type = "button"; prev.textContent = "→";
    prev.setAttribute("aria-label", "الصورة السابقة");
    const next = document.createElement("button");
    next.type = "button"; next.textContent = "←";
    next.setAttribute("aria-label", "الصورة التالية");
    if (root.lang?.startsWith("en")) {
      prev.textContent = "←"; next.textContent = "→";
      prev.setAttribute("aria-label", "Previous photo");
      next.setAttribute("aria-label", "Next photo");
    }
    const status = document.createElement("span");
    status.className = "flower-gallery-status";
    status.setAttribute("role","status");
    status.setAttribute("aria-live","polite");
    nav.append(prev,status,next);
    gallery.insertAdjacentElement("afterend",nav);
    const active = () => Array.from(gallery.children).filter(e => getComputedStyle(e).display!=="none" && !e.hidden);
    let selected=0;
    const update=()=>{
      const all=active();
      if(!all.length){nav.hidden=true;return;}
      nav.hidden=false;
      const center=gallery.scrollLeft+gallery.clientWidth/2;
      let best=Infinity;
      all.forEach((e,i)=>{
        const pos=e.offsetLeft+e.offsetWidth/2;
        const delta=Math.abs(pos-center);
        if(delta<best){best=delta;selected=i;}
      });
      // For RTL/browser scrollLeft conventions, geometric centres are more reliable.
      const container=gallery.getBoundingClientRect();
      const mid=container.left+container.width/2;
      best=Infinity;
      all.forEach((e,i)=>{
        const r=e.getBoundingClientRect();
        const delta=Math.abs(r.left+r.width/2-mid);
        if(delta<best){best=delta;selected=i;}
      });
      status.textContent=(selected+1)+" / "+all.length;
      prev.disabled=selected===0;
      next.disabled=selected>=all.length-1;
    };
    const go=(delta)=>{
      const all=active();
      const target=all[Math.min(all.length-1,Math.max(0,selected+delta))];
      target?.scrollIntoView({behavior:mqReduce.matches?"auto":"smooth",block:"nearest",inline:"center"});
    };
    prev.addEventListener("click",()=>go(-1));
    next.addEventListener("click",()=>go(1));
    gallery.addEventListener("scroll",()=>requestAnimationFrame(update),{passive:true});
    new MutationObserver(update).observe(gallery,{childList:true,subtree:true,attributes:true,attributeFilter:["class","hidden","style"]});
    addEventListener("resize",update,{passive:true});
    requestAnimationFrame(update);
  };
  if(document.readyState==="loading")document.addEventListener("DOMContentLoaded",start,{once:true});
  else start();
  mqReduce.addEventListener?.("change",ev=>{
    if(ev.matches){
      root.dataset.flowerMotion="disabled";
      document.querySelectorAll(".flower-scroll-prepare").forEach(e=>e.classList.add("flower-in-view"));
    }
  });
})();