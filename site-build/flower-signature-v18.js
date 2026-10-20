/* FLOWER Signature V18: progressive, non-essential image/content reveal.
   No remote scripts, image synthesis, forced sticky scrolling, or tracking. */
(() => {
 "use strict";
 const root=document.documentElement;
 if(root.dataset.flowerSignature!=="v18")return;
 const reduced=matchMedia("(prefers-reduced-motion: reduce)");
 if(reduced.matches||navigator.connection?.saveData)return;
 const prepare=()=>{
   const nodes=[...document.querySelectorAll(".lx-chapter,.lx-statement,#stay .lx-unit")];
   if(!("IntersectionObserver" in window))return;
   const io=new IntersectionObserver(entries=>{
     entries.forEach(entry=>{
       if(entry.isIntersecting){
         entry.target.classList.add("lx-entered");
         io.unobserve(entry.target);
       }
     });
   },{threshold:.1,rootMargin:"0px 0px -35px 0px"});
   nodes.forEach((node,index)=>{
     const r=node.getBoundingClientRect();
     if(r.top<innerHeight*.9)return;
     node.classList.add("lx-observed");
     node.style.setProperty("--lx-delay",Math.min(index%2*90,90)+"ms");
     io.observe(node);
   });
   addEventListener("pageshow",e=>{
     if(e.persisted)nodes.forEach(n=>n.classList.add("lx-entered"));
   },{passive:true});
   reduced.addEventListener?.("change",e=>{
     if(e.matches){
       io.disconnect();
       nodes.forEach(n=>n.classList.add("lx-entered"));
     }
   });
 };
 if(document.readyState==="loading")document.addEventListener("DOMContentLoaded",prepare,{once:true});
 else prepare();
})();