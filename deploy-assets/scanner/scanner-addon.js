(function(){
"use strict";

const S={modal:null,canvas:null,ctx:null,status:null,mode:null,originalImg:null,callback:null,points:null,dragging:-1,previewW:0,previewH:0};
function qs(id){return document.getElementById(id)}
function clamp(v,min,max){return Math.max(min,Math.min(max,v))}
function dist(a,b){const dx=a.x-b.x,dy=a.y-b.y;return Math.sqrt(dx*dx+dy*dy)}
function orderPoints(pts){
  const p=pts.slice();let tl=p[0],tr=p[0],br=p[0],bl=p[0],minSum=1e18,maxSum=-1e18,minDiff=1e18,maxDiff=-1e18;
  p.forEach(pt=>{const sum=pt.x+pt.y,diff=pt.x-pt.y;if(sum<minSum){minSum=sum;tl=pt}if(sum>maxSum){maxSum=sum;br=pt}if(diff>maxDiff){maxDiff=diff;tr=pt}if(diff<minDiff){minDiff=diff;bl=pt}});
  return [tl,tr,br,bl];
}
function expandPoints(pts,w,h,pct){
  const p=orderPoints(pts),cx=p.reduce((s,q)=>s+q.x,0)/4,cy=p.reduce((s,q)=>s+q.y,0)/4;
  return p.map(q=>({x:clamp(cx+(q.x-cx)*(1+pct),0,w-1),y:clamp(cy+(q.y-cy)*(1+pct),0,h-1)}));
}
function ensureUI(){
  if(S.modal)return;
  const style=document.createElement("style");
  style.textContent=`
  #flowerScannerModal{position:fixed;inset:0;z-index:99999;background:rgba(20,10,15,.94);display:none;align-items:center;justify-content:center;padding:10px;direction:rtl}
  #flowerScannerModal.open{display:flex}
  .fs-panel{width:min(760px,100%);max-height:96vh;overflow:auto;background:#fff;border-radius:18px;padding:12px;box-shadow:0 18px 60px rgba(0,0,0,.35)}
  .fs-head{display:flex;align-items:center;justify-content:space-between;gap:10px;margin-bottom:8px}.fs-title{font:bold 16px Tahoma,Arial;color:#5b2038}
  .fs-close{border:0;background:#f1e7eb;color:#5b2038;border-radius:10px;padding:8px 12px;font:bold 13px Tahoma;cursor:pointer}
  #flowerScannerCanvas{display:block;width:100%;height:auto;background:#151515;border-radius:12px;touch-action:none}
  .fs-status{font:700 12px/1.7 Tahoma,Arial;color:#66565e;padding:9px 2px}
  .fs-controls{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-top:8px}.fs-controls button,.fs-controls select{min-height:46px;border-radius:11px;font:bold 13px Tahoma,Arial}
  .fs-primary{border:0;background:#7a314d;color:#fff}.fs-secondary{border:1px solid #d8c1ca;background:#f5edf0;color:#5b2038}
  @media(max-width:560px){.fs-controls{grid-template-columns:1fr}}
  `;
  document.head.appendChild(style);
  const modal=document.createElement("div");modal.id="flowerScannerModal";
  modal.innerHTML='<div class="fs-panel"><div class="fs-head"><div class="fs-title">مسح الفاتورة ضوئيًا</div><button type="button" class="fs-close" id="fsClose">إلغاء</button></div><canvas id="flowerScannerCanvas"></canvas><div class="fs-status" id="fsStatus">جاري تجهيز الماسح...</div><div class="fs-controls"><button type="button" class="fs-secondary" id="fsDetect">إعادة اكتشاف الحواف</button><select id="fsMode"><option value="gray" selected>رمادي واضح - مفضل</option><option value="bw">أبيض وأسود سكانر</option><option value="color">ملون محسّن</option><option value="original">ألوان أصلية</option></select><button type="button" class="fs-primary" id="fsAccept">اعتماد المسح</button><button type="button" class="fs-secondary" id="fsOriginal">استخدام الأصل عند الضرورة</button></div></div>';
  document.body.appendChild(modal);
  S.modal=modal;S.canvas=qs("flowerScannerCanvas");S.ctx=S.canvas.getContext("2d");S.status=qs("fsStatus");S.mode=qs("fsMode");
  qs("fsClose").addEventListener("click",closeScanner);qs("fsDetect").addEventListener("click",()=>detectEdges(true));qs("fsAccept").addEventListener("click",acceptScan);qs("fsOriginal").addEventListener("click",useOriginal);
  S.canvas.addEventListener("pointerdown",onPointerDown);S.canvas.addEventListener("pointermove",onPointerMove);S.canvas.addEventListener("pointerup",onPointerUp);S.canvas.addEventListener("pointercancel",onPointerUp);
}
function setStatus(t){if(S.status)S.status.textContent=t}
function waitForCV(timeoutMs){return new Promise((resolve,reject)=>{const start=Date.now();(function check(){if(window.cv&&cv.Mat&&cv.imread&&cv.findContours){resolve();return}if(Date.now()-start>timeoutMs){reject(new Error("CV load timeout"));return}setTimeout(check,120)})()})}
function drawPreview(){
  if(!S.originalImg||!S.canvas)return;
  const maxW=1200,ratio=Math.min(1,maxW/S.originalImg.naturalWidth),w=Math.max(1,Math.round(S.originalImg.naturalWidth*ratio)),h=Math.max(1,Math.round(S.originalImg.naturalHeight*ratio));
  S.previewW=w;S.previewH=h;S.canvas.width=w;S.canvas.height=h;S.ctx.clearRect(0,0,w,h);S.ctx.drawImage(S.originalImg,0,0,w,h);
  if(S.points&&S.points.length===4){
    const pts=orderPoints(S.points);S.ctx.save();S.ctx.lineWidth=Math.max(4,Math.round(w/250));S.ctx.strokeStyle="#b79862";S.ctx.fillStyle="rgba(122,49,77,.12)";
    S.ctx.beginPath();S.ctx.moveTo(pts[0].x,pts[0].y);for(let i=1;i<4;i++)S.ctx.lineTo(pts[i].x,pts[i].y);S.ctx.closePath();S.ctx.fill();S.ctx.stroke();
    const r=Math.max(11,Math.round(w/65));pts.forEach((p,i)=>{S.ctx.beginPath();S.ctx.arc(p.x,p.y,r,0,Math.PI*2);S.ctx.fillStyle="#fff";S.ctx.fill();S.ctx.lineWidth=Math.max(4,Math.round(w/280));S.ctx.strokeStyle="#7a314d";S.ctx.stroke();S.ctx.fillStyle="#7a314d";S.ctx.font="bold "+Math.max(12,Math.round(w/70))+"px Tahoma";S.ctx.textAlign="center";S.ctx.textBaseline="middle";S.ctx.fillText(String(i+1),p.x,p.y)});S.ctx.restore();
  }
}
function defaultPoints(){const mx=Math.round(S.previewW*.025),my=Math.round(S.previewH*.025);return[{x:mx,y:my},{x:S.previewW-mx,y:my},{x:S.previewW-mx,y:S.previewH-my},{x:mx,y:S.previewH-my}]}
function findBestQuad(edge,canvas){
  const contours=new cv.MatVector(),hierarchy=new cv.Mat();let best=null,bestScore=0;
  try{
    cv.findContours(edge,contours,hierarchy,cv.RETR_LIST,cv.CHAIN_APPROX_SIMPLE);
    const imageArea=canvas.width*canvas.height,minArea=imageArea*.055;
    for(let i=0;i<contours.size();i++){
      const c=contours.get(i),area=cv.contourArea(c,false);
      if(area<minArea){c.delete();continue}
      const peri=cv.arcLength(c,true);
      for(const eps of [.015,.022,.03,.04]){
        const approx=new cv.Mat();cv.approxPolyDP(c,approx,eps*peri,true);
        if(approx.rows===4&&cv.isContourConvex(approx)){
          const d=approx.data32S,pts=[];for(let j=0;j<4;j++)pts.push({x:d[j*2],y:d[j*2+1]});
          const rect=cv.boundingRect(approx),rectArea=Math.max(1,rect.width*rect.height),fill=area/rectArea;
          const borderPenalty=(rect.x<3||rect.y<3||rect.x+rect.width>canvas.width-3||rect.y+rect.height>canvas.height-3)?.82:1;
          const score=area*fill*borderPenalty;
          if(score>bestScore){bestScore=score;best=pts}
        }
        approx.delete();
      }
      c.delete();
    }
    return best;
  }finally{contours.delete();hierarchy.delete()}
}
function detectDocumentOnCanvas(canvas){
  const src=cv.imread(canvas),gray=new cv.Mat(),blur=new cv.Mat(),edge1=new cv.Mat(),edge2=new cv.Mat(),dil1=new cv.Mat(),dil2=new cv.Mat();
  try{
    cv.cvtColor(src,gray,cv.COLOR_RGBA2GRAY,0);cv.GaussianBlur(gray,blur,new cv.Size(5,5),0,0,cv.BORDER_DEFAULT);
    cv.Canny(blur,edge1,35,120,3,false);cv.Canny(blur,edge2,70,200,3,false);
    const k=cv.getStructuringElement(cv.MORPH_RECT,new cv.Size(5,5));
    cv.dilate(edge1,dil1,k,new cv.Point(-1,-1),2,cv.BORDER_CONSTANT,cv.morphologyDefaultBorderValue());cv.dilate(edge2,dil2,k,new cv.Point(-1,-1),1,cv.BORDER_CONSTANT,cv.morphologyDefaultBorderValue());k.delete();
    let best=findBestQuad(dil1,canvas)||findBestQuad(dil2,canvas);
    if(best)return expandPoints(best,canvas.width,canvas.height,.018);
    const nz=new cv.Mat();cv.findNonZero(edge1,nz);if(nz.rows>0){const r=cv.boundingRect(nz);nz.delete();if(r.width>canvas.width*.35&&r.height>canvas.height*.35){return expandPoints([{x:r.x,y:r.y},{x:r.x+r.width,y:r.y},{x:r.x+r.width,y:r.y+r.height},{x:r.x,y:r.y+r.height}],canvas.width,canvas.height,.025)}}else nz.delete();
    return null;
  }catch(e){return null}
  finally{src.delete();gray.delete();blur.delete();edge1.delete();edge2.delete();dil1.delete();dil2.delete()}
}
async function detectEdges(manual){
  try{
    setStatus("جاري اكتشاف حواف الفاتورة...");await waitForCV(15000);
    const temp=document.createElement("canvas"),max=1400,ratio=Math.min(1,max/Math.max(S.originalImg.naturalWidth,S.originalImg.naturalHeight));
    temp.width=Math.max(1,Math.round(S.originalImg.naturalWidth*ratio));temp.height=Math.max(1,Math.round(S.originalImg.naturalHeight*ratio));temp.getContext("2d").drawImage(S.originalImg,0,0,temp.width,temp.height);
    const found=detectDocumentOnCanvas(temp);
    if(found){const sx=S.previewW/temp.width,sy=S.previewH/temp.height;S.points=found.map(p=>({x:p.x*sx,y:p.y*sy}));setStatus("تم اكتشاف الحواف مع هامش أمان. راجع الزوايا الأربع وعدّلها عند الحاجة.")}
    else{if(!S.points||manual)S.points=defaultPoints();setStatus("لم يُحسم اكتشاف الحواف تلقائيًا. ضع الدوائر الأربع على زوايا الفاتورة ثم اعتمد المسح.")}
    drawPreview();
  }catch(e){if(!S.points)S.points=defaultPoints();drawPreview();setStatus("تعذر الاكتشاف التلقائي. حدّد الزوايا الأربع يدويًا ثم اعتمد المسح.")}
}
function eventPoint(e){const r=S.canvas.getBoundingClientRect();return{x:(e.clientX-r.left)*(S.canvas.width/r.width),y:(e.clientY-r.top)*(S.canvas.height/r.height)}}
function onPointerDown(e){if(!S.points)return;const p=eventPoint(e),pts=orderPoints(S.points);let idx=-1,best=Infinity;pts.forEach((q,i)=>{const d=dist(p,q);if(d<best){best=d;idx=i}});if(best<Math.max(44,S.previewW/11)){S.points=pts;S.dragging=idx;if(S.canvas.setPointerCapture)S.canvas.setPointerCapture(e.pointerId);e.preventDefault()}}
function onPointerMove(e){if(S.dragging<0||!S.points)return;const p=eventPoint(e);S.points[S.dragging]={x:clamp(p.x,0,S.previewW),y:clamp(p.y,0,S.previewH)};drawPreview();e.preventDefault()}
function onPointerUp(){S.dragging=-1}
function makeWorkCanvas(){
  const maxDim=2600,ratio=Math.min(1,maxDim/Math.max(S.originalImg.naturalWidth,S.originalImg.naturalHeight)),c=document.createElement("canvas");
  c.width=Math.max(1,Math.round(S.originalImg.naturalWidth*ratio));c.height=Math.max(1,Math.round(S.originalImg.naturalHeight*ratio));c.getContext("2d").drawImage(S.originalImg,0,0,c.width,c.height);return c;
}
function cleanGray(gray){
  const bg=new cv.Mat(),norm=new cv.Mat(),eq=new cv.Mat(),small=new cv.Mat(),sharp=new cv.Mat();
  try{
    cv.GaussianBlur(gray,bg,new cv.Size(0,0),25,25,cv.BORDER_DEFAULT);
    cv.divide(gray,bg,norm,255,-1);
    cv.equalizeHist(norm,eq);
    cv.GaussianBlur(eq,small,new cv.Size(0,0),1.2,1.2,cv.BORDER_DEFAULT);
    cv.addWeighted(eq,1.45,small,-.45,4,sharp);
    return sharp.clone();
  }finally{bg.delete();norm.delete();eq.delete();small.delete();sharp.delete()}
}
function warpFromPoints(){
  const work=makeWorkCanvas(),pts=orderPoints(S.points),sx=work.width/S.previewW,sy=work.height/S.previewH,p=pts.map(q=>({x:q.x*sx,y:q.y*sy}));
  let outW=Math.round(Math.max(dist(p[0],p[1]),dist(p[3],p[2]))),outH=Math.round(Math.max(dist(p[0],p[3]),dist(p[1],p[2])));
  const ratio=Math.min(1,2400/Math.max(1,outW),5200/Math.max(1,outH));outW=Math.max(420,Math.round(outW*ratio));outH=Math.max(620,Math.round(outH*ratio));
  const src=cv.imread(work),dst=new cv.Mat(),srcTri=cv.matFromArray(4,1,cv.CV_32FC2,[p[0].x,p[0].y,p[1].x,p[1].y,p[2].x,p[2].y,p[3].x,p[3].y]),dstTri=cv.matFromArray(4,1,cv.CV_32FC2,[0,0,outW-1,0,outW-1,outH-1,0,outH-1]),M=cv.getPerspectiveTransform(srcTri,dstTri);
  cv.warpPerspective(src,dst,M,new cv.Size(outW,outH),cv.INTER_CUBIC,cv.BORDER_REPLICATE,new cv.Scalar());
  const mode=S.mode.value;let finalMat=null;
  try{
    if(mode==="original"){finalMat=dst.clone()}
    else if(mode==="color"){
      const blur=new cv.Mat(),enh=new cv.Mat();cv.GaussianBlur(dst,blur,new cv.Size(0,0),2.2,2.2,cv.BORDER_DEFAULT);cv.addWeighted(dst,1.18,blur,-.18,7,enh);finalMat=enh.clone();blur.delete();enh.delete();
    }else{
      const gray=new cv.Mat();cv.cvtColor(dst,gray,cv.COLOR_RGBA2GRAY,0);const cleaned=cleanGray(gray);gray.delete();
      if(mode==="bw"){const bw=new cv.Mat();const block=cleaned.cols>1400?41:31;cv.adaptiveThreshold(cleaned,bw,255,cv.ADAPTIVE_THRESH_GAUSSIAN_C,cv.THRESH_BINARY,block,10);finalMat=bw.clone();bw.delete()}
      else finalMat=cleaned.clone();
      cleaned.delete();
    }
    const out=document.createElement("canvas");cv.imshow(out,finalMat);return out;
  }finally{if(finalMat)finalMat.delete();dst.delete();src.delete();srcTri.delete();dstTri.delete();M.delete()}
}
async function acceptScan(){
  try{
    setStatus("جاري تنظيف الخلفية والظلال وتحسين الكتابة وتصحيح المنظور...");await waitForCV(15000);const canvas=warpFromPoints(),img=new Image();
    img.onload=function(){const cb=S.callback;closeScanner();if(cb)cb(img,canvas.toDataURL("image/jpeg",.96))};
    img.onerror=function(){setStatus("تعذر إنشاء النسخة الممسوحة. أعد المحاولة.")};img.src=canvas.toDataURL("image/jpeg",.96);
  }catch(e){setStatus("تعذر تجهيز المسح. راجع الزوايا أو جرّب وضع «رمادي واضح» ثم أعد المحاولة.")}
}
function useOriginal(){if(!S.originalImg)return;const cb=S.callback,src=S.originalImg.src;closeScanner();if(cb)cb(S.originalImg,src)}
function closeScanner(){if(S.modal)S.modal.classList.remove("open");S.dragging=-1}
window.FlowerScanner={process:function(img,dataUrl,callback){ensureUI();S.originalImg=img;S.callback=callback;S.points=null;S.dragging=-1;S.mode.value="gray";drawPreview();S.modal.classList.add("open");setStatus("جاري اكتشاف حواف الفاتورة...");setTimeout(()=>detectEdges(false),80)}};
})();