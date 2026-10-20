/* FLOWER Interactive V17.4.
   Hairline-inspired, fully original SVG interaction. No packages or external calls.
   Default HTML works with JS disabled, and keyboard/touch access is supported. */
(() => {
  "use strict";
  const root=document.querySelector("#flower-interactive");
  if(!root) return;
  const reduce=matchMedia("(prefers-reduced-motion: reduce)");
  const saveData=navigator.connection?.saveData===true;
  const gentle=()=>reduce.matches||saveData;
  const floorNodes=[...root.querySelectorAll("[data-fi-floor]")];
  const floorButtons=[...root.querySelectorAll("[data-fi-choose]")];
  const level=root.querySelector("#fi-level-value");
  const cards=[...root.querySelectorAll("[data-fi-unit]")];
  const chosen=root.querySelector("#fi-selected-unit");
  const link=root.querySelector("#fi-unit-link");
  if(floorNodes.length!==4||floorButtons.length!==4||cards.length!==3||!level||!chosen||!link)return;
  root.dataset.fiReady="true";
  const active=(node,state)=>node.setAttribute("aria-pressed",state?"true":"false");
  const chooseFloor=index=>{
    if(index<0||index>=floorButtons.length)return;
    floorNodes.forEach((el,i)=>active(el,i===index));
    floorButtons.forEach((el,i)=>active(el,i===index));
    const value=floorButtons[index].textContent.trim();
    level.textContent=value;
  };
  floorButtons.forEach((button,index)=>{
    button.addEventListener("click",()=>chooseFloor(index));
    button.addEventListener("keydown",ev=>{
      const step=ev.key==="ArrowRight"?1:ev.key==="ArrowLeft"?-1:0;
      if(!step)return;
      ev.preventDefault();
      const next=(index+step+floorButtons.length)%floorButtons.length;
      chooseFloor(next);
      floorButtons[next].focus();
    });
  });
  floorNodes.forEach((group,index)=>{
    group.addEventListener("click",()=>chooseFloor(index));
    group.addEventListener("focus",()=>chooseFloor(index));
    group.addEventListener("keydown",ev=>{
      if(ev.key==="Enter"||ev.key===" "){
        ev.preventDefault();chooseFloor(index);
      }
      const step=ev.key==="ArrowUp"?1:ev.key==="ArrowDown"?-1:0;
      if(step){
        ev.preventDefault();
        const next=(index+step+floorNodes.length)%floorNodes.length;
        chooseFloor(next);
        floorNodes[next].focus();
      }
    });
  });
  const selectCard=(index,focus)=>{
    if(index<0||index>=cards.length)return;
    cards.forEach((card,i)=>active(card,i===index));
    const card=cards[index];
    chosen.textContent=card.querySelector(".fi-unit-info strong")?.textContent.trim()||"";
    link.href="#flower-unit-choice-"+index;
    root.dataset.fiSelectedUnit=String(index);
    if(focus)card.focus({preventScroll:true});
  };
  cards.forEach((card,index)=>{
    card.addEventListener("click",()=>selectCard(index,false));
    card.addEventListener("focus",()=>selectCard(index,false));
    card.addEventListener("keydown",ev=>{
      const rtl=document.documentElement.dir==="rtl"||getComputedStyle(root).direction==="rtl";
      const step=ev.key==="ArrowRight"?(rtl?-1:1):ev.key==="ArrowLeft"?(rtl?1:-1):0;
      if(!step)return;
      ev.preventDefault();
      const next=(index+step+cards.length)%cards.length;
      selectCard(next,true);
      if(matchMedia("(max-width:700px)").matches)
        cards[next].scrollIntoView({block:"nearest",inline:"center",behavior:gentle()?"auto":"smooth"});
    });
  });
  // Riffle-like pointer response is disabled on touch/reduced-motion devices.
  const pointerFine=matchMedia("(hover:hover) and (pointer:fine)");
  let scheduled=0;
  const reset=()=>{
    cards.forEach(card=>{
      card.style.removeProperty("--fi-tiltx");
      card.style.removeProperty("--fi-tilty");
    });
  };
  cards.forEach(card=>{
    card.addEventListener("pointermove",ev=>{
      if(!pointerFine.matches||gentle())return;
      if(scheduled)return;
      const rect=card.getBoundingClientRect();
      const dx=(ev.clientX-rect.left)/rect.width-.5;
      const dy=(ev.clientY-rect.top)/rect.height-.5;
      scheduled=requestAnimationFrame(()=>{
        scheduled=0;
        card.style.setProperty("--fi-tiltx",(-dy*3).toFixed(2)+"deg");
        card.style.setProperty("--fi-tilty",(dx*3).toFixed(2)+"deg");
      });
    },{passive:true});
    card.addEventListener("pointerleave",()=>{
      card.style.removeProperty("--fi-tiltx");card.style.removeProperty("--fi-tilty");
    });
  });
  reduce.addEventListener?.("change",ev=>{if(ev.matches)reset();});
  selectCard(0,false);
  chooseFloor(0);
})();