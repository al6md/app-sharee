import './globals.css';
import Link from 'next/link';
import { 
  Files, 
  Shield, 
  Download
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
      <body className="bg-[#F7F8FA] text-[#1B1F24] antialiased h-screen flex flex-col md:flex-row overflow-hidden">
        <PwaRegistrar />

        {/* 1. الترويسة العلوية للهواتف المحمولة */}
        <header className="md:hidden bg-white text-[#1B1F24] px-4 py-3 flex items-center justify-between border-b border-[#E4E7EC] sticky top-0 z-40 shrink-0">
          <div className="flex items-center gap-3">
            <img 
              src="/logo.png" 
              alt="شعار غرفة تجارة كربلاء" 
              className="w-9 h-9 rounded-full border border-[#c59b27] object-cover bg-white shrink-0" 
            />
            <div>
              <h1 className="font-bold text-sm text-[#1B1F24] leading-tight">Share COC</h1>
              <p className="text-[11px] text-[#667085]">غرفة تجارة كربلاء المقدسة</p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <span className="inline-flex items-center gap-1.5 text-[11px] bg-emerald-50 text-[#12B76A] font-semibold px-2.5 py-1 rounded-full border border-emerald-200">
              <span className="w-1.5 h-1.5 rounded-full bg-[#12B76A]"></span>
              متصل
            </span>
            <Link 
              href="/admin"
              className="inline-flex items-center gap-1.5 text-xs bg-[#14372e] text-white font-semibold px-3 py-1.5 rounded-lg transition active:scale-95"
            >
              <Shield className="w-3.5 h-3.5 text-[#ecd58a]" />
              <span>الإدارة</span>
            </Link>
          </div>
        </header>

        {/* 2. الشريط الجانبي للشاشات الكبيرة */}
        <aside className="hidden md:flex w-64 bg-white border-l border-[#E4E7EC] flex-col justify-between shrink-0 h-full overflow-y-auto">
          <div>
            {/* الشعار والهوية الرسمية مع مساحة حماية واضحة */}
            <div className="p-5 border-b border-[#E4E7EC] flex items-center gap-3.5 bg-white shrink-0">
              <img 
                src="/logo.png" 
                alt="شعار غرفة تجارة كربلاء" 
                className="w-11 h-11 rounded-full border border-[#c59b27] object-cover bg-white shrink-0" 
              />
              <div className="min-w-0">
                <h1 className="font-bold text-[15px] text-[#1B1F24] leading-tight">Share COC</h1>
                <p className="text-xs text-[#667085] font-medium mt-0.5 truncate">غرفة تجارة كربلاء المقدسة</p>
              </div>
            </div>

            {/* القائمة الرئيسية */}
            <nav className="p-3 space-y-1.5">
              <Link 
                href="/files" 
                className="flex items-center gap-3 px-3.5 py-2.5 rounded-lg text-[#1B1F24] hover:bg-[#F7F8FA] font-semibold text-[14px] transition border border-transparent hover:border-[#E4E7EC]"
              >
                <Files className="w-5 h-5 text-[#14372e]" />
                <span>المستندات والأقسام</span>
              </Link>

              <Link 
                href="/admin" 
                className="flex items-center gap-3 px-3.5 py-2.5 rounded-lg text-[#1B1F24] hover:bg-[#F7F8FA] font-semibold text-[14px] transition border border-transparent hover:border-[#E4E7EC]"
              >
                <Shield className="w-5 h-5 text-[#c59b27]" />
                <span>لوحة تحكم الإدارة</span>
              </Link>
            </nav>
          </div>

          {/* حالة الاتصال السحابي وتحميل تطبيق سطح المكتب */}
          <div className="p-4 m-3 bg-[#F7F8FA] rounded-xl border border-[#E4E7EC] space-y-3 shrink-0">
            <div className="flex items-center justify-between">
              <span className="font-semibold text-[#1B1F24] text-xs">السحابة المشتركة</span>
              <span className="inline-flex items-center gap-1.5 text-[#12B76A] bg-emerald-50 px-2 py-0.5 rounded-full text-[11px] font-semibold border border-emerald-200">
                <span className="w-1.5 h-1.5 rounded-full bg-[#12B76A]"></span>
                متصل
              </span>
            </div>
            <p className="text-[#667085] text-xs leading-relaxed">
              مزامنة فورية مع تطبيق الحاسوب المكتبي في الغرفة.
            </p>
            <a
              href="/share%20coc.exe"
              download="share coc.exe"
              className="flex items-center justify-center gap-2 w-full h-10 bg-[#14372e] hover:bg-[#1a473b] text-white text-xs font-semibold rounded-lg transition"
            >
              <Download className="w-4 h-4 text-[#ecd58a]" />
              <span>تحميل تطبيق الحاسوب</span>
            </a>
          </div>
        </aside>

        {/* 3. مساحة المحتوى الرئيسية */}
        <main className="flex-1 flex flex-col overflow-y-auto bg-[#F7F8FA] pb-20 md:pb-8 h-full">
          {children}
        </main>

        {/* 4. شريط التنقل السفلي للهواتف المحمولة */}
        <nav className="md:hidden fixed bottom-0 left-0 right-0 bg-white border-t border-[#E4E7EC] z-40 px-6 py-2 flex items-center justify-around">
          <Link 
            href="/files" 
            className="flex flex-col items-center gap-1 text-[#14372e] font-semibold text-xs py-1 px-4 rounded-lg active:bg-[#F7F8FA] transition"
          >
            <Files className="w-5 h-5 text-[#14372e]" />
            <span>المستندات</span>
          </Link>

          <Link 
            href="/admin" 
            className="flex flex-col items-center gap-1 text-[#667085] hover:text-[#1B1F24] font-semibold text-xs py-1 px-4 rounded-lg active:bg-[#F7F8FA] transition"
          >
            <Shield className="w-5 h-5 text-[#c59b27]" />
            <span>لوحة الإدارة</span>
          </Link>
        </nav>
      </body>
    </html>
  );
}
