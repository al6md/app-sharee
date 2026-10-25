# تبادل الملفات – File Exchange System
### نظام مركزي سحابي لمشاركة الملفات والتكامل المباشر مع Microsoft Office (Word, Excel, Access)

نظام متكامل واحترافي مصمم لمشاركة ومزامنة الملفات والمستندات وقواعد البيانات بين 10 أجهزة حاسوب تعمل بنظام Windows 10 و Windows 11، مع لوحة تحكم سحابية تعمل على Vercel و Supabase.

---

## 📁 هيكلية المشروع (Project Architecture)

```
c:\Users\tohiba\OneDrive\Desktop\شييييير\
│
├── desktop-client/                    # تطبيق سطح المكتب لنظام Windows
│   ├── dist/
│   │   └── FileExchangeSetup.exe      # ملف التثبيت المترجم الجاهز (40.3 MB)
│   ├── src/
│   │   ├── main.py                    # نقطة الدخول وبدء التطبيق
│   │   ├── gui.py                     # الواجهة الرسومية العربية (PyQt6 - RTL)
│   │   ├── sync_engine.py             # محرك المراقبة التلقائية والتقاط Ctrl+S
│   │   ├── office_handler.py          # تكامل Office ونظام أمان قفل Access
│   │   ├── supabase_client.py         # الاتصال بـ Supabase (REST, Storage & Realtime)
│   │   ├── conflict_manager.py        # إدارة واحتواء التعارضات التلقائية
│   │   ├── offline_queue.py           # قاعدة بيانات محلية SQLite للعمل دون اتصال
│   │   └── autostart.py               # التشغيل التلقائي مع بدء تشغيل Windows
│   ├── requirements.txt               # متطلبات بيئة Python
│   ├── FileExchange.spec              # إعدادات PyInstaller للتجميع
│   └── build_installer.py             # سكريبت بناء وتجميع ملف التثبيت
│
├── web-dashboard/                     # لوحة التحكم السحابية الموجهة لـ Vercel
│   ├── app/
│   │   ├── page.tsx                   # نظرة عامة واستهلاك التخزين المجاني
│   │   ├── files/page.tsx             # مستكشف الملفات وسجل الإصدارات
│   │   ├── devices/page.tsx           # إدارة واعتماد الأجهزة العشرة
│   │   ├── users/page.tsx             # المستخدمين ومصفوفة الصلاحيات
│   │   ├── audit/page.tsx             # سجل العمليات والتدقيق الشامل
│   │   └── api/storage/signed-url/    # مسار الرفع المباشر لتجاوز حدود Vercel
│   ├── lib/supabase.ts                # عميل الربط مع السحابة
│   ├── package.json                   # إعدادات حزم Next.js 14
│   └── .env.example                   # نموذج متغيرات البيئة الآمن
│
├── database/                          # مخطط وسياسات قاعدة بيانات Supabase
│   ├── 01_schema.sql                  # الجداول والفهارس والعلاقات
│   ├── 02_security_rls.sql            # سياسات الأمان Row Level Security
│   ├── 03_storage_setup.sql           # إعداد وعاء التخزين file-exchange-storage
│   └── 04_seed_data.sql               # المجلدات الافتراضية والمحفزات
│
└── docs/                              # الأدلة والتوثيق والتقارير
    ├── ARABIC_USER_MANUAL.md          # دليل المستخدم العربي الشامل
    ├── DEPLOYMENT_GUIDE.md            # دليل النشر والاستضافة السحابية المجانية
    ├── OFFICE_ACCESS_GUIDE.md         # دليل التكامل مع Office وأمان Access
    └── TEST_REPORT.md                 # تقرير الاختبارات الميدانية (12 سيناريو)
```

---

## ⚡ الميزات التقنية الرئيسية

1. **تكامل أصلي 100% مع Microsoft Office**:
   - فتح الملفات في برامجها الأصلية (Word، Excel، Access).
   - رصد اختصار الحفظ `Ctrl + S` فورياً عبر خوارزمية ذكية تتأكد من اكتمال كتابة الملف وفك مقبض النظام قبل بدء الرفع.
2. **معالجة حاسمة وآمنة لقواعد بيانات Access (`.accdb`)**:
   - نظام القفل الحصري (Exclusive Checkout) يمنع فتح وتعديل ملف Access من جهازين في نفس الوقت لتفادي تلف قاعدة البيانات.
   - دعم كامل لتقسيم Access (Split Database) وربطه مع PostgreSQL للعمل التشاركي المفتوح.
3. **مجاني 100% وبلا أي تكاليف خفية**:
   - مبني ليعمل ضمن حدود الخطط المجانية لـ **Supabase** و **Vercel**.
   - رفع مباشر بالروابط الموقعة لتجاوز حد 4.5MB الخاص بدوال Vercel Serverless.
   - دعم التبديل إلى **Cloudflare R2** بـ 10GB مجاناً متى ما دعت الحاجة.
4. **تطبيق تنفيذي حقيقي `FileExchangeSetup.exe`**:
   - يعمل في شريط المهام (System Tray) في الخلفية.
   - يدعم البدء التلقائي مع إقلاع Windows.
   - واجهة مستخدم عربية حديثة تدعم الاتجاه من اليمين لليسار (RTL).
   - إدارة كاملة للتعارضات وحفظ التعديلات في قائمة انتظار محلية (Offline Queue) عند انقطاع الإنترنت.
