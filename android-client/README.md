# تطبيق Share COC للأندرويد – غرفة تجارة كربلاء المقدسة
### النسخة الرسمية لنظام Android المتصلة مباشرة بسحابة Google Drive

تطبيق أندرويد متكامل وأصيل (Native Android App) مصمم لمزامنة وتبادل المستندات وقواعد البيانات مع حواسيب المؤسسة (10 أجهزة) ولوحة تحكم الويب، متصل بنسبة 100% بنفس المجلد السحابي المشترك على **Google Drive**.

---

## ⚡ أبرز المميزات والإمكانيات

1. **الاتصال المباشر بسحابة Google Drive (v3 REST API)**:
   - يتصل التطبيق مباشرة بنفس المجلد الجذري `1BF6mDMuwuaS5c4Ekq9KPcEXaAOxGOmfB`.
   - لا يحتاج لأي خادم وسيط؛ التزامن فوري ومباشر بين الهاتف والسحابة.

2. **الرفع المجزأ القابل للاستئناف (Resumable Chunked Upload)**:
   - رفع سريع أحادي للمستندات الصغيرة (Word و Excel).
   - تقسيم ورفع الملفات الكبيرة (حتى 2GB) بنظام الشرائح (2MB Chunks) مع إمكانية استئناف الرفع عند انقطاع الإنترنت أو التبديل بين الـ Wi-Fi وبيانات الهاتف (4G/5G).

3. **تكامل أصلي مع تطبيقات Microsoft Office للأندرويد**:
   - فتح مستندات Word (`.docx`) و Excel (`.xlsx`) و PowerPoint (`.pptx`) عبر `FileProvider` الآمن.
   - إمكانية التعديل داخل تطبيقات أوفيس الرسمية أو تطبيق WPS Office.

4. **نظام حماية وقفل قواعد بيانات Microsoft Access (`.accdb`)**:
   - حجز حصري لقاعدة البيانات من الهاتف لمنع التعديل المزدوج وتلف البيانات.
   - ميزة **«افتح على حاسوب المكتب» (Remote PC Launcher)** لإرسال أمر مباشر عبر منفذ الجسر `18290` لفتح قاعدة البيانات على شاشة الكمبيوتر في المكتب بضغطة زر من الهاتف.

5. **أمان الأقسام وحمايتها بالبصمة (Biometrics & PIN Code)**:
   - قراءة وتطبيق نفس مصفوفة الصلاحيات من ملف `.sharecoc_permissions.json`.
   - دعم فتح الأقسام المحمية برمز PIN بواسطة **بصمة الإصبع** أو **التعرف على الوجه**.

6. **تسجيل الأجهزة واعتمادها (Authorized Devices)**:
   - استخراج وتثبيت رقم Hardware GUID فريد للهاتف وتسجيله ضمن قائمة الأجهزة المصرح بها.

---

## 📁 هيكلية مجلدات المشروع (`android-client`)

```
android-client/
├── app/
│   ├── src/main/
│   │   ├── AndroidManifest.xml                  # أذونات النظام والمزودات (FileProvider)
│   │   ├── assets/
│   │   │   └── gdrive_credentials.json          # مفاتيح الربط السحابي مع Google Drive
│   │   ├── java/iq/sharecoc/app/
│   │   │   ├── ShareCocApplication.kt           # فئة التطبيق وتحميل الإعدادات
│   │   │   ├── MainActivity.kt                  # نقطة الدخول وإدارة الرجوع
│   │   │   ├── config/AppConfig.kt              # إعدادات الروابط والمجلدات والمفاتيح
│   │   │   ├── data/
│   │   │   │   ├── models/                      # نماذج البيانات (DriveItem, AdminStore, Device)
│   │   │   │   └── network/GoogleDriveApiClient.kt # عميل Google Drive REST API v3
│   │   │   ├── office/
│   │   │   │   ├── OfficeLauncher.kt            # فتح الملفات في Word/Excel/WPS
│   │   │   │   └── AccessLockManager.kt         # أقفال Access وأمر فتح حاسوب المكتب
│   │   │   ├── security/
│   │   │   │   ├── BiometricHelper.kt           # التحقق بالبصمة والوجه
│   │   │   │   └── DeviceUuidManager.kt         # توليد واعتماد رقم الجهاز
│   │   │   └── ui/
│   │   │       ├── theme/                       # ثيم وهوية غرفة تجارة كربلاء (RTL)
│   │   │       ├── viewmodel/DriveViewModel.kt  # إدارة الحالة والعمليات
│   │   │       └── screens/                     # شاشات العرض والتصفح والأقفال
│   │   └── res/                                 # الألوان والأيقونات والنصوص العربية
│   └── build.gradle.kts                         # حزم وإعدادات تطبيق أندرويد
├── build.gradle.kts                             # إعدادات المشروع الرئيسية
├── settings.gradle.kts                          # الموديولات والمستودعات
└── gdrive_credentials.json                      # ملف الاعتماد السحابي
```

---

## 🛠️ كيفية بناء وتشغيل التطبيق

### الطريقة الأولى: عبر برنامج Android Studio (موصى بها)
1. افتح برنامج **Android Studio**.
2. اختر **Open** ثم حدد المجلد:
   `c:\Users\tohiba\OneDrive\Desktop\شييييير\android-client`
3. سيبدأ Android Studio بعمل مزامنة للمشروع (Gradle Sync) تلقائياً.
4. قم بتوصيل هاتف الأندرويد عبر وصلة USB (مع تفعيل خيار تصحيح USB - USB Debugging).
5. اضغط على زر **Run ▶** لتثبيت وتشغيل التطبيق على الهاتف مباشرة.

### الطريقة الثانية: بناء ملف APK جاهز للتثبيت عبر موجه الأوامر
```bash
cd android-client
./gradlew assembleRelease
```
ستجد ملف الـ APK النهائي جاهزاً في المسار:
`app/build/outputs/apk/release/app-release.apk`
يمكنك نسخه إلى أي هاتف أندرويد وتثبيته مباشرة.
