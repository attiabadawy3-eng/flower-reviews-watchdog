/* FLOWER Motion V19: opt-in progressive enhancement, no external dependencies. */
(function(){
 "use strict";
 if(window.__FLOWER_MOTION_V19__)return;
 window.__FLOWER_MOTION_V19__=true;
 function start(){
  var doc=document.documentElement;
  var reduced=window.matchMedia&&window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  if(reduced||!("IntersectionObserver" in window))return;
  var selectors=[
   "#branches article","#stay article",
   ".lx-chapter","#flower-signature .lx-chapter",
   "#gallery .v7-section-head",
   "#branches .v7-section-head",
   "#stay .v7-section-head"
  ];
  var seen=new Set(),targets=[];
  selectors.forEach(function(sel){
   document.querySelectorAll(sel).forEach(function(el){
    if(!seen.has(el)&&!el.closest("dialog")&&!el.closest("form")){
     seen.add(el);targets.push(el);
    }
   });
  });
  if(!targets.length)return;
  var observer=new IntersectionObserver(function(entries){
    entries.forEach(function(entry){
      if(entry.isIntersecting){
        entry.target.classList.add("fl-m19-shown");
        observer.unobserve(entry.target);
      }
    });
  },{threshold:.075,rootMargin:"0px 0px -24px 0px"});
  targets.forEach(function(el,i){
    el.style.setProperty("--fl-m19-delay",String(Math.min((i%3)*75,150))+"ms");
    el.classList.add("fl-m19-reveal");
    observer.observe(el);
  });
  doc.setAttribute("data-flower-motion-v19","ready");
  document.addEventListener("visibilitychange",function(){
    if(document.visibilityState==="hidden"){
     targets.forEach(function(el){el.classList.add("fl-m19-shown");});
     observer.disconnect();
    }
  },{once:true});
 }
 if(document.readyState==="loading"){
   document.addEventListener("DOMContentLoaded",start,{once:true});
 }else{start();}
})();
