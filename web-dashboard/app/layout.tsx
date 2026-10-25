import './globals.css';
import Link from 'next/link';
import { 
  FolderSync, 
  Files, 
  Laptop, 
  Users, 
  ShieldAlert, 
  Cloud, 
  History,
  CheckCircle2,
  HardDrive
} from 'lucide-react';

export const metadata = {
  title: 'تبادل الملفات – لوحة التحكم المنظمة',
  description: 'إدارة مشاركة الملفات والأجهزة وقواعد بيانات Office',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="ar" dir="rtl">
      <body className="bg-slate-100 text-slate-800 antialiased font-sans flex min-h-screen">
        {/* شريط جانبي نظيف ومنظم بنمط Microsoft 365 */}
        <aside className="w-64 bg-white border-l border-slate-200 flex flex-col justify-between shrink-0 shadow-sm">
          <div>
            {/* الشعار والترويسة */}
            <div className="p-5 border-b border-slate-200 flex items-center gap-3 bg-slate-50/50">
              <div className="w-9 h-9 rounded-lg bg-[#0f6cbd] text-white flex items-center justify-center font-bold text-lg shadow-sm">
                📁
              </div>
              <div>
                <h1 className="font-bold text-sm text-slate-900 leading-tight">تبادل الملفات</h1>
                <p className="text-[11px] text-[#0f6cbd] font-semibold">Microsoft 365 Integration</p>
              </div>
            </div>

            {/* الروابط التنقلية المنظمة */}
            <nav className="p-3 space-y-1 text-xs">
              <Link 
                href="/" 
                className="flex items-center gap-3 px-3 py-2.5 rounded-lg text-slate-700 hover:bg-slate-100 font-semibold transition"
              >
                <HardDrive className="w-4 h-4 text-[#0f6cbd]" />
                <span>نظرة عامة والتخزين</span>
              </Link>

              <Link 
                href="/files" 
                className="flex items-center gap-3 px-3 py-2.5 rounded-lg text-slate-700 hover:bg-slate-100 font-semibold transition"
              >
                <Files className="w-4 h-4 text-[#107c41]" />
                <span>الملفات والمستندات</span>
              </Link>

              <Link 
                href="/devices" 
                className="flex items-center gap-3 px-3 py-2.5 rounded-lg text-slate-700 hover:bg-slate-100 font-semibold transition"
              >
                <Laptop className="w-4 h-4 text-[#a4373a]" />
                <span>الأجهزة العشرة المعتمدة</span>
              </Link>

              <Link 
                href="/users" 
                className="flex items-center gap-3 px-3 py-2.5 rounded-lg text-slate-700 hover:bg-slate-100 font-semibold transition"
              >
                <Users className="w-4 h-4 text-indigo-600" />
                <span>المستخدمين والصلاحيات</span>
              </Link>

              <Link 
                href="/audit" 
                className="flex items-center gap-3 px-3 py-2.5 rounded-lg text-slate-700 hover:bg-slate-100 font-semibold transition"
              >
                <History className="w-4 h-4 text-slate-600" />
                <span>سجل التدقيق والعمليات</span>
              </Link>
            </nav>
          </div>

          {/* حالة السحابة المنظمة في الأسفل */}
          <div className="p-3.5 m-3 bg-slate-50 rounded-xl border border-slate-200 text-xs">
            <div className="flex items-center justify-between mb-2">
              <span className="font-bold text-slate-700 text-[11px]">السحابة المشتركة</span>
              <span className="text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded-full text-[10px] font-bold border border-emerald-200">
                🟢 متصلة
              </span>
            </div>
            <div className="w-full bg-slate-200 rounded-full h-1.5 mb-1 overflow-hidden">
              <div className="bg-[#0f6cbd] h-1.5 rounded-full" style={{ width: '15%' }}></div>
            </div>
            <p className="text-slate-500 text-[10px]">الخطة المجانية: 0 MB / 1024 MB</p>
          </div>
        </aside>

        {/* مساحة المحتوى الرئيسية النظيفة */}
        <main className="flex-1 flex flex-col overflow-y-auto bg-slate-100">
          {children}
        </main>
      </body>
    </html>
  );
}
