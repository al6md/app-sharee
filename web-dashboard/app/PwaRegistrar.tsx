'use client';

import { useEffect, useState } from 'react';
import { Download, X, Smartphone, Share } from 'lucide-react';

export default function PwaRegistrar() {
  const [deferredPrompt, setDeferredPrompt] = useState<any>(null);
  const [showInstallBanner, setShowInstallBanner] = useState(false);
  const [isIOS, setIsIOS] = useState(false);
  const [showIosGuide, setShowIosGuide] = useState(false);

  useEffect(() => {
    // 1. تسجيل Service Worker للـ PWA
    if ('serviceWorker' in navigator) {
      window.addEventListener('load', () => {
        navigator.serviceWorker.register('/sw.js').then(
          (reg) => {
            console.log('[PWA] ServiceWorker registered with scope:', reg.scope);
            reg.onupdatefound = () => {
              const installingWorker = reg.installing;
              if (installingWorker) {
                installingWorker.onstatechange = () => {
                  if (installingWorker.state === 'installed' && navigator.serviceWorker.controller) {
                    window.location.reload();
                  }
                };
              }
            };
          },
          (err) => {
            console.log('[PWA] ServiceWorker registration failed:', err);
          }
        );
      });
    }

    // 2. الكشف عن أجهزة iPhone/iPad
    const userAgent = window.navigator.userAgent.toLowerCase();
    const isIosDevice = /iphone|ipad|ipod/.test(userAgent);
    setIsIOS(isIosDevice);

    // التحقق مما إذا كان التطبيق مثبتاً ويعمل بالفعل كـ Standalone
    const isStandalone = window.matchMedia('(display-mode: standalone)').matches || (window.navigator as any).standalone;
    if (isStandalone) {
      return; // لا تظهر الإعلان إذا كان التطبيق مفتوحاً بالفعل كـ PWA
    }

    // 3. التقاط حدث التثبيت لأجهزة Android / Chrome
    const handleBeforeInstall = (e: any) => {
      e.preventDefault();
      setDeferredPrompt(e);
      setShowInstallBanner(true);
    };

    window.addEventListener('beforeinstallprompt', handleBeforeInstall);

    // إذا كان آيفون ولم يكن مضافاً للشاشة، أظهر الزر للمستخدم
    if (isIosDevice && !isStandalone) {
      setShowInstallBanner(true);
    }

    return () => {
      window.removeEventListener('beforeinstallprompt', handleBeforeInstall);
    };
  }, []);

  const handleInstallClick = async () => {
    if (isIOS) {
      setShowIosGuide(true);
      return;
    }

    if (!deferredPrompt) return;
    deferredPrompt.prompt();
    const { outcome } = await deferredPrompt.userChoice;
    if (outcome === 'accepted') {
      setShowInstallBanner(false);
    }
    setDeferredPrompt(null);
  };

  if (!showInstallBanner) return null;

  return (
    <>
      {/* شريط تثبيت PWA المنبثق على الجوال */}
      <div className="fixed top-2 left-2 right-2 md:left-auto md:right-4 md:w-96 z-50 bg-[#14372e] text-white p-3.5 rounded-2xl shadow-2xl border border-[#c59b27]/40 flex items-center justify-between gap-3 animate-in fade-in slide-in-from-top-4 duration-300">
        <div className="flex items-center gap-3 min-w-0">
          <img 
            src="/logo.png" 
            alt="شعار Share COC" 
            className="w-10 h-10 rounded-full border border-[#c59b27] bg-white p-0.5 object-cover shrink-0" 
          />
          <div className="min-w-0">
            <h4 className="font-bold text-xs text-white leading-snug truncate">تثبيت تطبيق Share COC</h4>
            <p className="text-[10px] text-[#ecd58a] truncate">نسخة الجوال السحابية الرسمية</p>
          </div>
        </div>

        <div className="flex items-center gap-1.5 shrink-0">
          <button
            onClick={handleInstallClick}
            className="flex items-center gap-1.5 bg-[#c59b27] hover:bg-[#b0871d] text-[#0e2720] font-black text-xs px-3 py-1.5 rounded-lg transition active:scale-95 shadow-sm"
          >
            <Smartphone className="w-3.5 h-3.5" />
            <span>تثبيت</span>
          </button>
          <button
            onClick={() => setShowInstallBanner(false)}
            className="p-1.5 text-slate-300 hover:text-white rounded-lg transition"
            title="إغلاق"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
      </div>

      {/* نافذة توجيه لمستخدمي آيفون / Safari */}
      {showIosGuide && (
        <div className="fixed inset-0 bg-black/70 backdrop-blur-sm z-50 flex items-end sm:items-center justify-center p-4">
          <div className="bg-white text-slate-800 rounded-3xl p-6 max-w-sm w-full space-y-4 shadow-2xl border border-slate-200 animate-in slide-in-from-bottom duration-300">
            <div className="flex items-center justify-between border-b pb-3">
              <div className="flex items-center gap-2">
                <img src="/logo.png" alt="لوغو" className="w-8 h-8 rounded-full" />
                <h3 className="font-bold text-sm text-[#14372e]">تثبيت التطبيق على الآيفون (iOS)</h3>
              </div>
              <button onClick={() => setShowIosGuide(false)} className="text-slate-400 hover:text-slate-600">
                <X className="w-5 h-5" />
              </button>
            </div>

            <p className="text-xs text-slate-600 leading-relaxed">
              لتثبيت منظومة <strong className="text-[#14372e]">Share COC</strong> كتطبيق رسمي على شاشة جوالك:
            </p>

            <div className="space-y-3 bg-slate-50 p-3.5 rounded-2xl border border-slate-100 text-xs">
              <div className="flex items-center gap-3">
                <span className="w-6 h-6 rounded-full bg-[#14372e] text-white flex items-center justify-center font-bold text-xs shrink-0">1</span>
                <span>اضغط على زر المشاركة <Share className="w-4 h-4 inline text-blue-600 mx-1" /> في شريط متصفح سفاري بالأسفل.</span>
              </div>
              <div className="flex items-center gap-3">
                <span className="w-6 h-6 rounded-full bg-[#14372e] text-white flex items-center justify-center font-bold text-xs shrink-0">2</span>
                <span>مرر للأسفل واختر <strong>(إضافة إلى الشاشة الرئيسية)</strong> أو <strong>Add to Home Screen</strong>.</span>
              </div>
              <div className="flex items-center gap-3">
                <span className="w-6 h-6 rounded-full bg-[#c59b27] text-[#0e2720] flex items-center justify-center font-bold text-xs shrink-0">3</span>
                <span>اضغط على <strong>(إضافة / Add)</strong> وسيظهر التطبيق فوراً على شاشتك.</span>
              </div>
            </div>

            <button
              onClick={() => setShowIosGuide(false)}
              className="w-full bg-[#14372e] text-white font-bold py-2.5 rounded-xl text-xs hover:bg-[#1a473b] transition"
            >
              فهمت ذلك
            </button>
          </div>
        </div>
      )}
    </>
  );
}
