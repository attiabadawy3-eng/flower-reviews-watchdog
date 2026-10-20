/* FLOWER V19 — small, progressive-enhancement layer.
   The established FLOWER booking engine (site-v2.js) stays the sole owner of
   branch/WhatsApp/Booking.com destination selection and outbound navigation.
   No external network operations or invented price/availability state.
*/
(() => {
  "use strict";
  function install(){
    const form=document.querySelector(".fx19-booking .v7-booking-form");
    if(!form)return;
    const ar=(document.documentElement.lang||"ar").toLowerCase().startsWith("ar");
    const arrival=form.querySelector("#book-arrival"),departure=form.querySelector("#book-departure");
    const status=document.createElement("p");
    status.className="fx19-booking-feedback";
    status.setAttribute("role","status");
    status.setAttribute("aria-live","polite");
    status.style.cssText="grid-column:1/-1;min-height:0;margin:0;color:#7A314D;font-size:.86rem;font-weight:700;";
    form.append(status);
    function checkDates(){
      if(!arrival||!departure)return true;
      const a=arrival.value,d=departure.value;
      const invalid=Boolean(a&&d&&d<=a);
      departure.setAttribute("aria-invalid",invalid?"true":"false");
      status.textContent=invalid?
        (ar?"يجب أن يكون تاريخ المغادرة بعد تاريخ الوصول.":"Departure must be after arrival."):"";
      return !invalid;
    }
    if(arrival&&departure){
      arrival.addEventListener("change",checkDates);
      departure.addEventListener("change",checkDates);
      form.addEventListener("click",(ev)=>{
        const c=ev.target.closest("#book-whatsapp,#book-booking");
        if(c&&!checkDates()){ev.preventDefault();ev.stopImmediatePropagation();departure.focus();}
      },true);
    }
    const nav=document.querySelector(".v7-header");
    if(nav&&"IntersectionObserver" in window){
      const sentinel=document.createElement("div");
      sentinel.setAttribute("aria-hidden","true");
      sentinel.style.cssText="height:1px;position:absolute;top:0;pointer-events:none";
      nav.insertAdjacentElement("beforebegin",sentinel);
      const obs=new IntersectionObserver((items)=>{
        nav.classList.toggle("fx19-scrolled",!items[0].isIntersecting);
      },{threshold:0});
      obs.observe(sentinel);
    }
  }
  if(document.readyState==="loading")document.addEventListener("DOMContentLoaded",install,{once:true});
  else install();
})();
