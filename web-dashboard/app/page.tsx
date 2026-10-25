import { 
  Laptop, 
  Files, 
  HardDrive, 
  Lock, 
  ShieldCheck, 
  ArrowUpRight, 
  Clock,
  AlertTriangle,
  Inbox,
  Download
} from 'lucide-react';

export default function OverviewPage() {
  return (
    <div className="p-6 md:p-8 space-y-6 max-w-6xl">
      {/* الترويسة المنظمة */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 bg-white p-5 rounded-xl border border-slate-200 shadow-sm">
        <div>
          <h2 className="text-xl font-bold text-slate-900">
            غرفة تجارة كربلاء المقدسة – منظومة التبادل السحابي
          </h2>
          <p className="text-slate-500 text-xs mt-1">
            متابعة الأرشفة والتزامن اللحظي لملفات Word و Excel و Access بين أجهزة موظفي الغرفة
          </p>
        </div>

        <div className="flex items-center gap-3">
          <a
            href="/FileExchangeSetup.exe"
            download
            className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-slate-900 hover:bg-slate-800 text-white text-xs font-bold transition shadow-sm"
          >
            <Download className="w-4 h-4 text-emerald-400" />
            <span>تحميل برنامج Windows (EXE)</span>
          </a>
          <span className="inline-flex items-center gap-1.5 px-3 py-2 rounded-lg bg-emerald-50 text-emerald-800 text-xs font-bold border border-emerald-200">
            <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse"></span>
            السحابة متصلة
          </span>
        </div>
      </div>

      {/* بطاقات الإحصائيات الأربع المنظمة */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        {/* الأجهزة */}
        <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-sm flex items-center justify-between">
          <div>
            <p className="text-xs font-semibold text-slate-500">الأجهزة المعتمدة</p>
            <p className="text-2xl font-bold text-slate-900 mt-1">10 <span className="text-xs font-normal text-slate-400">/ 10 أجهزة</span></p>
            <p className="text-[11px] text-emerald-600 font-semibold mt-1">الشبكة مكتملة وجاهزة</p>
          </div>
          <div className="w-10 h-10 rounded-lg bg-sky-50 text-[#0f6cbd] flex items-center justify-center font-bold">
            <Laptop className="w-5 h-5" />
          </div>
        </div>

        {/* مستندات Word */}
        <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-sm flex items-center justify-between">
          <div>
            <p className="text-xs font-semibold text-slate-500">مستندات Word (.docx)</p>
            <p className="text-2xl font-bold text-[#185abd] mt-1">تزامن فوري</p>
            <p className="text-[11px] text-slate-500 mt-1">رصد الحفظ بـ Ctrl+S</p>
          </div>
          <div className="w-10 h-10 rounded-lg bg-[#185abd] text-white flex items-center justify-center font-black text-sm">
            W
          </div>
        </div>

        {/* جداول Excel */}
        <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-sm flex items-center justify-between">
          <div>
            <p className="text-xs font-semibold text-slate-500">جداول Excel (.xlsx)</p>
            <p className="text-2xl font-bold text-[#107c41] mt-1">تزامن فوري</p>
            <p className="text-[11px] text-slate-500 mt-1">رصد الحفظ بـ Ctrl+S</p>
          </div>
          <div className="w-10 h-10 rounded-lg bg-[#107c41] text-white flex items-center justify-center font-black text-sm">
            X
          </div>
        </div>

        {/* قواعد Access */}
        <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-sm flex items-center justify-between">
          <div>
            <p className="text-xs font-semibold text-slate-500">قواعد Access (.accdb)</p>
            <p className="text-2xl font-bold text-[#a4373a] mt-1">قفل حصري</p>
            <p className="text-[11px] text-emerald-600 font-semibold mt-1">حماية تامة من التلف</p>
          </div>
          <div className="w-10 h-10 rounded-lg bg-[#a4373a] text-white flex items-center justify-center font-black text-sm">
            A
          </div>
        </div>
      </div>

      {/* سجل المزامنة المباشر المنظم */}
      <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
        <div className="p-4 border-b border-slate-100 flex items-center justify-between bg-slate-50/50">
          <h3 className="font-bold text-slate-800 text-sm">سجل عمليات الحفظ والتزامن السحابي</h3>
          <span className="text-xs text-slate-400 font-medium">مراقبة مباشرة بالثواني</span>
        </div>

        <div className="p-12 text-center text-slate-400 flex flex-col items-center justify-center space-y-3">
          <div className="w-12 h-12 rounded-xl bg-slate-50 border border-slate-200 text-slate-400 flex items-center justify-center">
            <Inbox className="w-6 h-6" />
          </div>
          <div>
            <h4 className="text-sm font-bold text-slate-700">لا توجد عمليات مسجلة حالياً</h4>
            <p className="text-xs text-slate-400 mt-1 max-w-sm leading-relaxed">
              عند تعديل أي ملف في Word أو Excel وحفظه بـ Ctrl+S، أو إغلاق قاعدة Access على أي جهاز، ستظهر تفاصيل المزامنة هنا فوراً.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
