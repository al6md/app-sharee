'use client';

import { useState } from 'react';
import { 
  History, 
  Upload, 
  Download, 
  Lock, 
  Unlock, 
  Trash2, 
  AlertTriangle, 
  Filter, 
  Clock,
  Laptop,
  User,
  Inbox
} from 'lucide-react';

interface AuditItem {
  id: string;
  action: 'UPLOAD' | 'DOWNLOAD' | 'LOCK' | 'UNLOCK' | 'CONFLICT' | 'DELETE';
  entityName: string;
  userName: string;
  deviceName: string;
  timestamp: string;
  details: string;
}

export default function AuditPage() {
  const [filterAction, setFilterAction] = useState('ALL');
  const [logs, setLogs] = useState<AuditItem[]>([]);

  return (
    <div className="p-8 space-y-6">
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h2 className="text-2xl font-black text-slate-900">سجل العمليات والتدقيق الشامل (Audit Logs)</h2>
          <p className="text-slate-500 text-sm mt-1">
            توثيق دقيق لكل عملية حفظ، رفع، قفل، فك قفل، أو تعارض عبر أجهزة المؤسسة
          </p>
        </div>

        {/* أزرار التصفية */}
        <div className="flex items-center gap-2 overflow-x-auto">
          {['ALL', 'UPLOAD', 'DOWNLOAD', 'LOCK', 'UNLOCK', 'CONFLICT'].map((act) => (
            <button
              key={act}
              onClick={() => setFilterAction(act)}
              className={`px-3 py-1.5 rounded-lg text-xs font-bold transition whitespace-nowrap ${
                filterAction === act
                  ? 'bg-slate-900 text-white'
                  : 'bg-white border border-slate-200 text-slate-600 hover:bg-slate-100'
              }`}
            >
              {act === 'ALL' ? 'كافة العمليات' : act}
            </button>
          ))}
        </div>
      </div>

      <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
        {logs.length === 0 ? (
          <div className="p-16 text-center text-slate-400 flex flex-col items-center justify-center space-y-3">
            <div className="p-4 bg-slate-50 rounded-full text-slate-400">
              <Inbox className="w-10 h-10" />
            </div>
            <h4 className="text-base font-bold text-slate-700">لا توجد سجلات تدقيق سابقة</h4>
            <p className="text-xs text-slate-400 max-w-md leading-relaxed">
              يقوم النظام بتسجيل كل عملية تتم عبر أجهزة المستخدمين تلقائياً (اسم المستخدم، الجهاز، التوقيت، ونوع العملية) وحفظها في هذا السجل بصورة مشفرة وغير قابلة للتلاعب.
            </p>
          </div>
        ) : (
          <table className="w-full text-right text-sm">
            <thead className="bg-slate-50 text-slate-500 text-xs font-bold border-b border-slate-200">
              <tr>
                <th className="p-4">نوع العملية</th>
                <th className="p-4">اسم الملف / الكائن</th>
                <th className="p-4">المستخدم</th>
                <th className="p-4">الجهاز</th>
                <th className="p-4">التوقيت الدقيق</th>
                <th className="p-4">التفاصيل الفنية</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {logs.map((log) => (
                <tr key={log.id} className="hover:bg-slate-50/70 transition">
                  <td className="p-4 font-bold">{log.action}</td>
                  <td className="p-4 font-semibold text-slate-800">{log.entityName}</td>
                  <td className="p-4 text-xs font-medium text-slate-700">{log.userName}</td>
                  <td className="p-4 text-xs font-mono text-slate-500">{log.deviceName}</td>
                  <td className="p-4 text-xs font-mono text-slate-400">{log.timestamp}</td>
                  <td className="p-4 text-xs text-slate-600 max-w-xs leading-relaxed">{log.details}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
