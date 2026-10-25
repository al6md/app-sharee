'use client';

import { useState } from 'react';
import { 
  Laptop, 
  CheckCircle, 
  XCircle, 
  Clock, 
  ShieldCheck, 
  RefreshCw, 
  PowerOff,
  Activity,
  Inbox
} from 'lucide-react';

interface DeviceItem {
  id: string;
  name: string;
  user: string;
  os: string;
  machineGuid: string;
  lastSeen: string;
  isAuthorized: boolean;
  syncStatus: 'synced' | 'syncing' | 'idle';
}

export default function DevicesPage() {
  const [devices, setDevices] = useState<DeviceItem[]>([]);

  return (
    <div className="p-8 space-y-6">
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h2 className="text-2xl font-black text-slate-900">إدارة أجهزة المؤسسة المعتمدة (Windows 10 & 11)</h2>
          <p className="text-slate-500 text-sm mt-1">
            تسجيل الأجهزة، منح وتجميد صلاحية التبادل، ومراقبة حالة المزامنة اللحظية
          </p>
        </div>

        <div className="flex items-center gap-2">
          <span className="px-3 py-1.5 rounded-lg bg-sky-50 text-sky-700 text-xs font-bold border border-sky-200">
            السعة المصرح بها: حتى 10+ أجهزة
          </span>
        </div>
      </div>

      <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
        {devices.length === 0 ? (
          <div className="p-16 text-center text-slate-400 flex flex-col items-center justify-center space-y-3">
            <div className="p-4 bg-slate-50 rounded-full text-slate-400">
              <Laptop className="w-10 h-10" />
            </div>
            <h4 className="text-base font-bold text-slate-700">لا توجد أجهزة مسجلة حالياً</h4>
            <p className="text-xs text-slate-400 max-w-md leading-relaxed">
              عند تشغيل ملف التثبيت <code>FileExchangeSetup.exe</code> على أي جهاز من أجهزة المؤسسة وتسجيل الدخول، سيظهر الجهاز هنا مباشرة لاعتماده وتفعيله بضغطة زر.
            </p>
          </div>
        ) : (
          <table className="w-full text-right text-sm">
            <thead className="bg-slate-50 text-slate-500 text-xs font-bold border-b border-slate-200">
              <tr>
                <th className="p-4">اسم الجهاز</th>
                <th className="p-4">المستخدم المرتبط</th>
                <th className="p-4">نظام التشغيل</th>
                <th className="p-4">معرّف الجهاز (Machine GUID)</th>
                <th className="p-4">آخر ظهور</th>
                <th className="p-4">حالة المزامنة</th>
                <th className="p-4">حالة الاعتماد</th>
                <th className="p-4 text-center">الإجراء</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {devices.map((dev) => (
                <tr key={dev.id} className="hover:bg-slate-50/70 transition">
                  <td className="p-4">
                    <div className="flex items-center gap-2.5">
                      <Laptop className="w-4 h-4 text-slate-600" />
                      <span className="font-bold text-slate-800">{dev.name}</span>
                    </div>
                  </td>
                  <td className="p-4 text-xs font-medium text-slate-700">{dev.user}</td>
                  <td className="p-4 text-xs text-slate-500">{dev.os}</td>
                  <td className="p-4 text-xs font-mono text-slate-400">{dev.machineGuid}</td>
                  <td className="p-4 text-xs font-mono text-slate-500">{dev.lastSeen}</td>
                  <td className="p-4">
                    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-bold bg-emerald-50 text-emerald-700 border border-emerald-200">
                      🟢 متزامن
                    </span>
                  </td>
                  <td className="p-4">
                    <span className="inline-flex items-center gap-1 text-xs font-bold text-emerald-600">
                      <CheckCircle className="w-4 h-4" /> معتمد
                    </span>
                  </td>
                  <td className="p-4 text-center">
                    <button className="px-3 py-1 text-xs font-bold rounded-lg transition bg-rose-50 text-rose-700 border border-rose-200">
                      تعطيل
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
