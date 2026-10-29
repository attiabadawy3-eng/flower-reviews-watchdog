/* FLOWER V20 hotel photography carousel (V19.1 + preview follows the next photo). */
(function(){
 "use strict";
 function init(){
  document.querySelectorAll(".flv-scene").forEach(function(scene){
   if(scene.dataset.initialized)return;
   scene.dataset.initialized="true";
   var slides=[].slice.call(scene.querySelectorAll(".flv-slide"));
   var counter=scene.querySelector(".flv-counter");
   var caption=scene.querySelector(".flv-active-caption");
   var preview=scene.querySelector(".flv-preview img");
   if(slides.length<2||!counter||!caption)return;
   var current=0;
   function change(delta){
     var next=(current+delta+slides.length)%slides.length;
     if(next===current)return;
     slides.forEach(function(el,i){
       var active=i===next;
       el.classList.toggle("is-active",active);
       el.setAttribute("aria-hidden",active?"false":"true");
       if(active){
         var image=el.querySelector("img");
         if(image&&image.loading==="lazy")image.loading="eager";
       }
     });
     var label=slides[next].querySelector("figcaption");
     caption.textContent=label?label.textContent:"";
     counter.textContent=String(next+1).padStart(2,"0")+" / "+String(slides.length).padStart(2,"0");
     if(preview){
       var upcoming=slides[(next+1)%slides.length].querySelector("img");
       if(upcoming)preview.src=upcoming.getAttribute("src");
     }
     current=next;
   }
   scene.querySelectorAll("[data-flv-move]").forEach(function(button){
     button.addEventListener("click",function(){
       change(button.dataset.flvMove==="next"?1:-1);
     });
   });
   scene.addEventListener("keydown",function(ev){
     if(ev.target!==scene)return;
     if(ev.key==="ArrowRight"||ev.key==="ArrowLeft"){
       ev.preventDefault();change(ev.key==="ArrowRight"?1:-1);
     }
   });
  });
 }
 if(document.readyState==="loading")
  document.addEventListener("DOMContentLoaded",init,{once:true});
 else init();
})();
