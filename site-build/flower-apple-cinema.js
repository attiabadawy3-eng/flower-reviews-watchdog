/* FLOWER cinematic chapter reveal (staging) — requestAnimationFrame, no libraries. */
(() => {
 "use strict";
 const root=document.documentElement;
 const area=document.querySelector("#flower-cinema");
 if(!area || root.dataset.flowerApple!=="v17") return;
 const reduced=matchMedia("(prefers-reduced-motion: reduce)");
 const saver=navigator.connection?.saveData === true;
 const track=area.querySelector("[data-cinema-track]");
 const stage=area.querySelector("[data-cinema-stage]");
 const frame=area.querySelector("[data-cinema-frame]");
 const scenes=[...area.querySelectorAll("[data-cinema-scene]")];
 const segments=[...area.querySelectorAll("[data-cinema-segment]")];
 if(!track||!stage||!frame||scenes.length!==3) return;
 if(reduced.matches||saver||!("requestAnimationFrame" in window)){
  root.dataset.flowerCinema="static";
  return;
 }
 let raf=0, lastScene=-1, enabled=true;
 const clamp=(v,min=0,max=1)=>Math.max(min,Math.min(max,v));
 const smooth=t=>t*t*(3-2*t);
 const fade=(a,b,v)=>smooth(clamp((v-a)/(b-a)));
 // Three distinct chapters, with a gentle crossfade near the boundaries.
 function render(){
  raf=0;
  if(!enabled)return;
  const rect=track.getBoundingClientRect();
  const travel=Math.max(1,rect.height-stage.clientHeight);
  const progress=clamp(-rect.top/travel);
  const expansion=smooth(clamp(progress/.19));
  frame.style.setProperty("--fc-frame-scale",(0.88+0.12*expansion).toFixed(4));
  frame.style.setProperty("--fc-radius",(32-23*expansion).toFixed(1)+"px");
  frame.style.setProperty("--fc-img-scale",(1.045-0.045*expansion).toFixed(4));
  const cross1=fade(.29,.39,progress);
  const cross2=fade(.63,.73,progress);
  const opacities=[1-cross1,cross1*(1-cross2),cross2];
  scenes.forEach((scene,i)=>{
    const opacity=clamp(opacities[i]);
    scene.style.opacity=opacity.toFixed(4);
    scene.style.visibility=opacity<=.002?"hidden":"visible";
    // An adjacent inactive chapter is presentation-only; preserve visible ALT fallback.
    scene.setAttribute("aria-hidden",opacity < .5 ? "true":"false");
    scene.style.setProperty("--fc-copy-shift",(20*(1-opacity)).toFixed(1)+"px");
  });
  const chapter=progress<.35?0:progress<.68?1:2;
  if(chapter!==lastScene){
    segments.forEach((item,i)=>item.classList.toggle("fc-active",i<=chapter));
    stage.dataset.cinemaChapter=String(chapter+1);
    lastScene=chapter;
  }
 }
 const schedule=()=>{if(!raf)raf=requestAnimationFrame(render)};
 // No persistent will-change outside viewport; scroll is passive and frame throttled.
 const observer=new IntersectionObserver(entries=>{
   enabled=entries[0]?.isIntersecting||false;
   if(enabled)schedule();
 },{threshold:0,rootMargin:"140px 0px 140px 0px"});
 root.dataset.flowerCinema="ready";
 observer.observe(track);
 addEventListener("scroll",schedule,{passive:true});
 addEventListener("resize",schedule,{passive:true});
 addEventListener("pageshow",schedule,{passive:true});
 reduced.addEventListener?.("change",event=>{
   if(event.matches){
     root.dataset.flowerCinema="static";
     enabled=false;
     scenes.forEach(scene=>{
       scene.style.opacity="";
       scene.style.visibility="";
       scene.style.removeProperty("--fc-copy-shift");
       scene.removeAttribute("aria-hidden");
     });
     frame.style.removeProperty("--fc-frame-scale");
     frame.style.removeProperty("--fc-radius");
     frame.style.removeProperty("--fc-img-scale");
     observer.disconnect();
   }
 });
 schedule();
})();