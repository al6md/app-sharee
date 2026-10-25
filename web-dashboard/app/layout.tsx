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
  HardDrive,
  Menu
} from 'lucide-react';
import PwaRegistrar from './PwaRegistrar';

export const metadata = {
  title: 'Share COC – غرفة تجارة كربلاء المقدسة',
  description: 'منظومة التبادل السحابي وأرشفة المستندات الرسمية لغرفة تجارة كربلاء المقدسة',
  manifest: '/manifest.json',
  appleWebApp: {
    capable: true,
    statusBarStyle: 'black-translucent',
    title: 'Share COC',
  },
  icons: {
    icon: '/logo.png',
    apple: '/icon-192.png',
  },
};

export const viewport = {
  width: 'device-width',
  initialScale: 1,
  maximumScale: 1,
  userScalable: false,
  viewportFit: 'cover',
  themeColor: '#14372e',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="ar" dir="rtl">
      <head>
        <link rel="manifest" href="/manifest.json" />
        <meta name="theme-color" content="#14372e" />
        <meta name="apple-mobile-web-app-capable" content="yes" />
        <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent" />
        <link rel="apple-touch-icon" href="/icon-192.png" />
      </head>
      <body className="bg-slate-100 text-slate-800 antialiased font-sans min-h-screen flex flex-col md:flex-row">
        <PwaRegistrar />

        {/* 1. الترويسة العلوية الخاصة بالهواتف المحمولة (Mobile Top Header) */}
        <header className="md:hidden bg-[#0e2720] text-white px-4 py-3 flex items-center justify-between border-b border-[#c59b27]/30 sticky top-0 z-40 shadow-md">
          <div className="flex items-center gap-2.5">
            <img 
              src="/logo.png" 
              alt="شعار الغرفة" 
              className="w-9 h-9 rounded-full border border-[#c59b27] object-cover bg-white" 
            />
            <div>
              <div className="flex items-center gap-1.5">
                <h1 className="font-bold text-sm text-white">Share COC</h1>
                <span className="text-[10px] bg-[#c59b27]/20 text-[#ecd58a] px-1.5 py-0.5 rounded font-bold border border-[#c59b27]/30">جوال</span>
              </div>
              <p className="text-[10px] text-slate-300">غرفة تجارة كربلاء المقدسة</p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <span className="inline-flex items-center gap-1 text-[10px] bg-emerald-950/80 text-emerald-400 font-bold px-2 py-0.5 rounded-full border border-emerald-600/40">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse"></span>
              سحابة متصلة
            </span>
          </div>
        </header>

        {/* 2. الشريط الجانبي للشاشات الكبيرة (Desktop Sidebar) */}
        <aside className="hidden md:flex w-64 bg-white border-l border-slate-200 flex-col justify-between shrink-0 shadow-sm min-h-screen sticky top-0">
          <div>
            {/* الشعار والترويسة الرسمية */}
            <div className="p-4 border-b border-slate-200 flex items-center gap-3 bg-[#0e2720] text-white">
              <img src="/logo.png" alt="شعار الغرفة" className="w-11 h-11 rounded-full border-2 border-[#c59b27] object-cover bg-white shadow-sm" />
              <div>
                <h1 className="font-bold text-sm text-white leading-tight">Share COC</h1>
                <p className="text-[10px] text-[#ecd58a] font-semibold">غرفة تجارة كربلاء المقدسة</p>
              </div>
            </div>

            {/* الروابط التنقلية المنظمة */}
            <nav className="p-3 space-y-1 text-xs">
              <Link 
                href="/files" 
                className="flex items-center gap-3 px-3 py-2.5 rounded-lg text-slate-700 hover:bg-slate-100 font-bold transition"
              >
                <Files className="w-4 h-4 text-[#107c41]" />
                <span>المستندات والأقسام</span>
              </Link>

              <Link 
                href="/" 
                className="flex items-center gap-3 px-3 py-2.5 rounded-lg text-slate-700 hover:bg-slate-100 font-semibold transition"
              >
                <HardDrive className="w-4 h-4 text-[#0f6cbd]" />
                <span>نظرة عامة والتخزين</span>
              </Link>

              <Link 
                href="/devices" 
                className="flex items-center gap-3 px-3 py-2.5 rounded-lg text-slate-700 hover:bg-slate-100 font-semibold transition"
              >
                <Laptop className="w-4 h-4 text-[#a4373a]" />
                <span>الأجهزة المعتمدة</span>
              </Link>

              <Link 
                href="/audit" 
                className="flex items-center gap-3 px-3 py-2.5 rounded-lg text-slate-700 hover:bg-slate-100 font-semibold transition"
              >
                <History className="w-4 h-4 text-slate-600" />
                <span>سجل التدقيق والمزامنة</span>
              </Link>

              <Link 
                href="/users" 
                className="flex items-center gap-3 px-3 py-2.5 rounded-lg text-slate-700 hover:bg-slate-100 font-semibold transition"
              >
                <Users className="w-4 h-4 text-indigo-600" />
                <span>المستخدمين والصلاحيات</span>
              </Link>
            </nav>
          </div>

          {/* حالة السحابة المنظمة في الأسفل */}
          <div className="p-3.5 m-3 bg-[#f0f6f4] rounded-xl border border-[#d5dfdb] text-xs">
            <div className="flex items-center justify-between mb-2">
              <span className="font-bold text-[#14372e] text-[11px]">السحابة المشتركة</span>
              <span className="text-emerald-800 bg-emerald-100 px-2 py-0.5 rounded-full text-[10px] font-bold border border-emerald-300">
                🟢 متصلة
              </span>
            </div>
            <p className="text-slate-600 text-[10px] leading-relaxed">
              مرتبطة لحظياً بتطبيق ويندوز المكتبي في الغرفة.
            </p>
          </div>
        </aside>

        {/* 3. مساحة المحتوى الرئيسية */}
        <main className="flex-1 flex flex-col overflow-y-auto bg-slate-100 pb-20 md:pb-6">
          {children}
        </main>

        {/* 4. شريط التنقل السفلي للهواتف المحمولة (Mobile Bottom Navigation Bar) */}
        <nav className="md:hidden fixed bottom-0 left-0 right-0 bg-white/95 backdrop-blur-md border-t border-slate-200 z-40 px-3 py-1.5 flex items-center justify-around shadow-lg">
          <Link 
            href="/files" 
            className="flex flex-col items-center gap-0.5 text-[#14372e] font-bold text-[10px] py-1 px-3 rounded-lg"
          >
            <Files className="w-5 h-5 text-[#14372e]" />
            <span>المستندات</span>
          </Link>

          <Link 
            href="/" 
            className="flex flex-col items-center gap-0.5 text-slate-500 hover:text-slate-800 font-semibold text-[10px] py-1 px-3 rounded-lg"
          >
            <HardDrive className="w-5 h-5" />
            <span>التخزين</span>
          </Link>

          <Link 
            href="/devices" 
            className="flex flex-col items-center gap-0.5 text-slate-500 hover:text-slate-800 font-semibold text-[10px] py-1 px-3 rounded-lg"
          >
            <Laptop className="w-5 h-5" />
            <span>الأجهزة</span>
          </Link>

          <Link 
            href="/audit" 
            className="flex flex-col items-center gap-0.5 text-slate-500 hover:text-slate-800 font-semibold text-[10px] py-1 px-3 rounded-lg"
          >
            <History className="w-5 h-5" />
            <span>السجل</span>
          </Link>
        </nav>
      </body>
    </html>
  );
}
