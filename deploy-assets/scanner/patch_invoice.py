from pathlib import Path
import base64
import re
import sys

html_path = Path(sys.argv[1])
logo_path = Path(sys.argv[2])

s = html_path.read_text(encoding="utf-8")
logo = base64.b64encode(logo_path.read_bytes()).decode("ascii")
data = "data:image/webp;base64," + logo

s = re.sub(
    r'https://raw\.githubusercontent\.com/attiabadawy3-eng/flower-reviews-watchdog/main/deploy-assets/(?:flower-logo\.svg|flower-invoices-logo\.webp)',
    data,
    s,
)
s = re.sub(
    r'(<img class="logo" src=")[^"]+(" alt="شعار فلور">)',
    lambda m: m.group(1) + data + m.group(2),
    s,
)
s = re.sub(r'var LOGO_DATA="[^"]*";', 'var LOGO_DATA="' + data + '";', s)

s = s.replace('ctx.direction="rtl";', 'try{ctx.direction="rtl"}catch(e){};')
s = s.replace('ctx.direction="rtl";ctx.fillStyle', 'try{ctx.direction="rtl"}catch(e){};ctx.fillStyle')
s = s.replace('el.printArea.scrollIntoView({behavior:"smooth",block:"start"})', 'el.printArea.scrollIntoView()')
s = s.replace('window.scrollTo({top:0,behavior:"smooth"})', 'window.scrollTo(0,0)')
s = s.replace(
    'showMessage("تعذر تجهيز الفاتورة على هذا الجهاز. أعد فتح الصفحة في Safari أو Chrome ثم حاول مرة أخرى.","err");',
    'showMessage("تعذر تجهيز الفاتورة: "+((ex&&ex.message)?ex.message:"خطأ غير معروف")+". أعد المحاولة بصورة JPG أو بصورة ملتقطة من الكاميرا.","err");'
)

if "scanner-addon.js" not in s:
    s = s.replace('<h2 class="title">صورة الفاتورة</h2>', '<h2 class="title">مسح الفاتورة ضوئيًا</h2>')
    s = s.replace('>تصوير الفاتورة</label>', '>مسح الفاتورة بالكاميرا</label>')
    s = s.replace('>اختيار صورة موجودة</label>', '>اختيار فاتورة من الصور</label>')
    s = s.replace(
        '<div class="meta" id="fileMeta">لم يتم اختيار صورة.</div><div class="meta">على iPhone افتح الصفحة في Safari، وعلى Android افتحها في Chrome. لا تستخدم معاينة الملف داخل تطبيق الملفات أو داخل معاينة المحادثة.</div>',
        '<div class="meta" id="fileMeta">لم يتم اختيار فاتورة.</div><div class="meta">بعد التصوير أو الاختيار سيتم اكتشاف حواف الفاتورة تلقائيًا وتصحيح الميل والمنظور. ويمكن تعديل الزوايا الأربع يدويًا قبل الاعتماد.</div>'
    )

    old = '''   img.onload=function(){
     sourceImage=img;sourceFileName=file.name||"صورة الفاتورة";
     el.photoPreview.src=ev.target.result;el.photoPreview.style.display="block";
     var mb=(file.size/1024/1024).toFixed(1);
     el.fileMeta.innerHTML="<b>تم اختيار الصورة:</b> "+escapeHtml(sourceFileName)+"<br>"+img.naturalWidth+" × "+img.naturalHeight+" - "+mb+" MB";
     if(Math.min(img.naturalWidth,img.naturalHeight)<700)showQuality("الصورة منخفضة الدقة نسبيًا، لكن يمكن تجهيزها لأن بيانات المورد والمبلغ ستظهر منفصلة بوضوح.","warn");
     else showQuality("تم تحميل الصورة بنجاح. الصور الطويلة سيتم تصغيرها تلقائيًا داخل صفحة واحدة.","ok");
     showMessage("الصورة جاهزة. أكمل البيانات ثم اضغط «تجهيز الفاتورة».","ok");
   };'''

    new = '''   img.onload=function(){
     sourceFileName=file.name||"فاتورة";
     var mb=(file.size/1024/1024).toFixed(1);
     el.photoPreview.src=ev.target.result;el.photoPreview.style.display="block";
     el.fileMeta.innerHTML="<b>تم استلام الفاتورة:</b> "+escapeHtml(sourceFileName)+"<br>"+img.naturalWidth+" × "+img.naturalHeight+" - "+mb+" MB";
     showMessage("جاري تشغيل ماسح المستندات واكتشاف حواف الفاتورة...","ok");
     if(window.FlowerScanner&&typeof window.FlowerScanner.process==="function"){
       window.FlowerScanner.process(img,ev.target.result,function(scannedImg,scannedDataUrl){
         sourceImage=scannedImg;
         el.photoPreview.src=scannedDataUrl;el.photoPreview.style.display="block";
         el.fileMeta.innerHTML="<b>تم اعتماد المسح الضوئي:</b> "+escapeHtml(sourceFileName)+"<br>"+scannedImg.naturalWidth+" × "+scannedImg.naturalHeight;
         showQuality("تم قص حواف الفاتورة وتصحيح الميل والمنظور. هذه النسخة الممسوحة هي التي ستدخل في JPG وPDF.","ok");
         showMessage("المسح الضوئي جاهز. أكمل البيانات ثم اضغط «تجهيز الفاتورة».","ok");
       });
     }else{
       sourceImage=img;
       showQuality("تعذر تحميل ماسح المستندات؛ تم الاحتفاظ بالصورة الأصلية.","warn");
       showMessage("تم الاحتفاظ بالصورة الأصلية. يمكنك تجهيز الفاتورة أو إعادة المحاولة لاحقًا.","warn");
     }
   };'''

    if old not in s:
        raise RuntimeError("invoice image loader block not found")
    s = s.replace(old, new)

    addon = '<script>var Module={onRuntimeInitialized:function(){window.__flowerCVReady=true;}};</script>\n<script async src="./opencv.js"></script>\n<script src="./scanner-addon.js"></script>\n'
    s = s.replace("</body>", addon + "</body>")

html_path.write_text(s, encoding="utf-8")
print("patched", html_path)
