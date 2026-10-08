from pathlib import Path
import base64
import re
import sys

html_path = Path(sys.argv[1])
logo_path = Path(sys.argv[2])

s = html_path.read_text(encoding="utf-8")
logo = base64.b64encode(logo_path.read_bytes()).decode("ascii")
data = "data:image/webp;base64," + logo

# Always embed the verified Flower logo so iPhone canvas stays same-origin.
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

# iPhone/Safari compatibility.
s = s.replace('ctx.direction="rtl";', 'try{ctx.direction="rtl"}catch(e){};')
s = s.replace('ctx.direction="rtl";ctx.fillStyle', 'try{ctx.direction="rtl"}catch(e){};ctx.fillStyle')
s = s.replace('el.printArea.scrollIntoView({behavior:"smooth",block:"start"})', 'el.printArea.scrollIntoView()')
s = s.replace('window.scrollTo({top:0,behavior:"smooth"})', 'window.scrollTo(0,0)')
s = s.replace(
    'showMessage("تعذر تجهيز الفاتورة على هذا الجهاز. أعد فتح الصفحة في Safari أو Chrome ثم حاول مرة أخرى.","err");',
    'showMessage("تعذر تجهيز الفاتورة: "+((ex&&ex.message)?ex.message:"خطأ غير معروف")+". أعد المحاولة بصورة أوضح أو بصورة ملتقطة من الكاميرا.","err");'
)

# Terminology requested by operations.
s = s.replace('اسم الموظف</label>', 'اسم الموظف / المسؤول</label>')
s = s.replace('placeholder="اسم الموظف"', 'placeholder="اسم الموظف / المسؤول"')
s = s.replace('ctx.fillText("الموظف",', 'ctx.fillText("الموظف / المسؤول",')
s = s.replace('"الموظف",employee', '"الموظف / المسؤول",employee')
s = s.replace('\nالموظف: "+employee', '\nالموظف / المسؤول: "+employee')

# First-time scanner integration.
if "scanner-addon.js" not in s:
    s = s.replace('<h2 class="title">صورة الفاتورة</h2>', '<h2 class="title">مسح الفاتورة ضوئيًا</h2>')
    s = s.replace('>تصوير الفاتورة</label>', '>مسح الفاتورة بالكاميرا</label>')
    s = s.replace('>اختيار صورة موجودة</label>', '>اختيار فاتورة من الصور</label>')
    s = s.replace(
        '<div class="meta" id="fileMeta">لم يتم اختيار صورة.</div><div class="meta">على iPhone افتح الصفحة في Safari، وعلى Android افتحها في Chrome. لا تستخدم معاينة الملف داخل تطبيق الملفات أو داخل معاينة المحادثة.</div>',
        '<div class="meta" id="fileMeta">لم يتم اختيار فاتورة.</div><div class="meta">بعد التصوير أو الاختيار سيتم اكتشاف حواف الفاتورة وتصحيح المنظور، ثم تنظيف الخلفية والظلال وتحسين الكتابة قبل التصدير.</div>'
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
     showMessage("جاري تشغيل ماسح المستندات واكتشاف الحواف...","ok");
     if(window.FlowerScanner&&typeof window.FlowerScanner.process==="function"){
       window.FlowerScanner.process(img,ev.target.result,function(scannedImg,scannedDataUrl){
         sourceImage=scannedImg;
         el.photoPreview.src=scannedDataUrl;el.photoPreview.style.display="block";
         el.fileMeta.innerHTML="<b>تم اعتماد المسح الاحترافي:</b> "+escapeHtml(sourceFileName)+"<br>"+scannedImg.naturalWidth+" × "+scannedImg.naturalHeight;
         showQuality("تم ضبط القص والمنظور وتنظيف الخلفية والظلال وتحسين الكتابة. هذه النسخة هي التي ستدخل في JPG وPDF.","ok");
         showMessage("المسح الاحترافي جاهز. أكمل البيانات ثم اضغط «تجهيز الفاتورة».","ok");
       });
     }else{
       sourceImage=img;
       showQuality("تعذر تحميل محرك المسح؛ تم الاحتفاظ بالصورة الأصلية.","warn");
       showMessage("تم الاحتفاظ بالصورة الأصلية ويمكنك المحاولة مرة أخرى بعد تحديث الصفحة.","warn");
     }
   };'''

    if old not in s:
        raise RuntimeError("invoice image loader block not found")
    s = s.replace(old, new)

    addon = '<script>var Module={onRuntimeInitialized:function(){window.__flowerCVReady=true;}};</script>\n<script async src="./opencv.js"></script>\n<script src="./scanner-addon.js"></script>\n'
    s = s.replace("</body>", addon + "</body>")

# Force browsers to fetch the newest scanner build instead of a cached script.
s = s.replace('<script src="./scanner-addon.js"></script>', '<script src="./scanner-addon.js?v=profix-20261008-1536"></script>')

# Upgrade scan/explanation text on already-integrated copies too.
s = s.replace(
    'بعد التصوير أو الاختيار سيتم اكتشاف حواف الفاتورة تلقائيًا وتصحيح الميل والمنظور. ويمكن تعديل الزوايا الأربع يدويًا قبل الاعتماد.',
    'بعد التصوير أو الاختيار سيتم اكتشاف الحواف وتصحيح المنظور، ثم تنظيف الخلفية والظلال وتحسين الكتابة. ويمكن تعديل الزوايا الأربع يدويًا قبل الاعتماد.'
)
s = s.replace(
    'تم قص حواف الفاتورة وتصحيح الميل والمنظور. هذه النسخة الممسوحة هي التي ستدخل في JPG وPDF.',
    'تم ضبط القص والمنظور وتنظيف الخلفية والظلال وتحسين الكتابة. هذه النسخة المحسّنة هي التي ستدخل في JPG وPDF.'
)

# Give long receipts much more printable/export area instead of shrinking them into an A4-sized image.
s = re.sub(
    r'var W=1240,H=1754,canvas=document\.createElement\("canvas"\);canvas\.width=W;canvas\.height=H;',
    'var scanIw=sourceImage.naturalWidth||sourceImage.width,scanIh=sourceImage.naturalHeight||sourceImage.height;'
    'var W=1600,receiptTargetW=W-148,receiptTargetH=Math.max(1000,Math.round(receiptTargetW*(scanIh/scanIw))),'
    'H=(custom?786:674)+receiptTargetH+108,canvas=document.createElement("canvas");canvas.width=W;canvas.height=H;',
    s
)
s = s.replace('canvasToBlob(canvas,"image/jpeg",0.88,function(blob){', 'canvasToBlob(canvas,"image/jpeg",0.94,function(blob){')

# Preserve the image aspect ratio inside the PDF instead of forcing every receipt into 595x842.
needle = 'var parts=[],offsets=[0],pos=0;'
if needle in s and 'var pdfH=Math.max(842,Math.round(595*(imgH/imgW)));' not in s:
    s = s.replace(needle, needle + 'var pdfH=Math.max(842,Math.round(595*(imgH/imgW)));', 1)
s = s.replace('/MediaBox [0 0 595 842]', '/MediaBox [0 0 595 "+pdfH+"]')
s = s.replace('var content="q\n595 0 0 842 0 0 cm\n/Im0 Do\nQ\n"', 'var content="q\n595 0 0 "+pdfH+" 0 0 cm\n/Im0 Do\nQ\n"')


# Critical PDF layout fix: the MediaBox may be dynamic, but the image transform
# must use the same dynamic height. Otherwise the image occupies only the lower
# 842 points and the remaining page appears blank above it.
s = s.replace(
    'var content="q\\n595 0 0 842 0 0 cm\\n/Im0 Do\\nQ\\n",contentBytes=ascii(content);',
    'var content="q\\n595 0 0 "+pdfH+" 0 0 cm\\n/Im0 Do\\nQ\\n",contentBytes=ascii(content);'
)
s = s.replace(
    'var content="q\\n595 0 0 842 0 0 cm\\n/Im0 Do\\nQ\\n", contentBytes=ascii(content);',
    'var content="q\\n595 0 0 "+pdfH+" 0 0 cm\\n/Im0 Do\\nQ\\n", contentBytes=ascii(content);'
)
# Also handle an already partially-patched bundle idempotently.
s = re.sub(
    r'var content="q\\\\n595 0 0 842 0 0 cm\\\\n/Im0 Do\\\\nQ\\\\n"',
    'var content="q\\\\n595 0 0 "+pdfH+" 0 0 cm\\\\n/Im0 Do\\\\nQ\\\\n"',
    s
)

# Print the generated image at natural aspect ratio, not forced to 210x297 mm.
s = s.replace('html,body{width:210mm;height:297mm;background:#fff}', 'html,body{background:#fff}')
s = s.replace('width:210mm!important;height:297mm!important;', 'width:100%!important;height:auto!important;')
s = s.replace('width:210mm!important;height:297mm!important;object-fit:contain!important;', 'width:100%!important;height:auto!important;object-fit:contain!important;')

html_path.write_text(s, encoding="utf-8")
print("patched", html_path)
