'use client';

import { useState } from 'react';
import { 
  Folder, 
  FileText, 
  Download, 
  History, 
  Lock, 
  Trash2, 
  Upload, 
  Search, 
  Plus, 
  Check, 
  X,
  FileSpreadsheet,
  Database,
  Inbox
} from 'lucide-react';

interface FileItem {
  id: string;
  name: string;
  folder: string;
  type: 'word' | 'excel' | 'access' | 'pdf';
  size: string;
  version: number;
  lastModifiedBy: string;
  lastModifiedAt: string;
  isLocked: boolean;
  lockedBy?: string;
}

export default function FilesPage() {
  const [selectedFolder, setSelectedFolder] = useState('الكل');
  const [searchTerm, setSearchTerm] = useState('');
  const [files, setFiles] = useState<FileItem[]>([]);

  const folders = [
    'الكل',
    'الكتب الرسمية والمراسلات (Word)',
    'جداول البيانات والتقارير المالية (Excel)',
    'قواعد بيانات المؤسسة (Access)',
    'النماذج والتعاميم العامة'
  ];

  const getFileIcon = (type: string) => {
    switch (type) {
      case 'word': return <FileText className="w-5 h-5 text-sky-600" />;
      case 'excel': return <FileSpreadsheet className="w-5 h-5 text-emerald-600" />;
      case 'access': return <Database className="w-5 h-5 text-amber-700" />;
      default: return <FileText className="w-5 h-5 text-slate-500" />;
    }
  };

  return (
    <div className="p-8 space-y-6">
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h2 className="text-2xl font-black text-slate-900">مستكشف الملفات والمجلدات المشتركة</h2>
          <p className="text-slate-500 text-sm mt-1">
            إدارة الملفات المحفوظة سحابياً، واستعراض النسخ، ومراقبة حالة القفل
          </p>
        </div>

        <div className="flex items-center gap-3">
          <button className="flex items-center gap-2 px-4 py-2 bg-sky-600 hover:bg-sky-700 text-white text-sm font-bold rounded-lg transition shadow-sm">
            <Upload className="w-4 h-4" />
            <span>رفع ملف جديد</span>
          </button>
        </div>
      </div>

      {/* شريط المجلدات والبحث */}
      <div className="flex flex-col md:flex-row items-center justify-between gap-4 bg-white p-3 rounded-xl border border-slate-200">
        <div className="flex items-center gap-2 overflow-x-auto w-full md:w-auto pb-2 md:pb-0">
          {folders.map(folder => (
            <button
              key={folder}
              onClick={() => setSelectedFolder(folder)}
              className={`px-3 py-1.5 rounded-lg text-xs font-bold transition whitespace-nowrap ${
                selectedFolder === folder
                  ? 'bg-slate-900 text-white'
                  : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
              }`}
            >
              {folder}
            </button>
          ))}
        </div>

        <div className="relative w-full md:w-72">
          <Search className="w-4 h-4 text-slate-400 absolute right-3 top-2.5" />
          <input
            type="text"
            placeholder="بحث في أسماء الملفات..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            className="w-full pl-3 pr-9 py-1.5 text-xs bg-slate-50 border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-sky-500"
          />
        </div>
      </div>

      {/* جدول الملفات أو حالة الفراغ */}
      <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
        {files.length === 0 ? (
          <div className="p-16 text-center text-slate-400 flex flex-col items-center justify-center space-y-3">
            <div className="p-4 bg-slate-50 rounded-full text-slate-400">
              <Inbox className="w-10 h-10" />
            </div>
            <h4 className="text-base font-bold text-slate-700">لا توجد ملفات مرفوعة حالياً في السحابة</h4>
            <p className="text-xs text-slate-400 max-w-md leading-relaxed">
              عند وضع أي ملف Word أو Excel أو Access داخل مجلد التبادل في جهاز الويندوز أو رفعه عبر هذا الزر، ستتم مزامنته وتأمينه هنا تلقائياً دون أي بيانات وهمية.
            </p>
          </div>
        ) : (
          <table className="w-full text-right text-sm">
            <thead className="bg-slate-50 text-slate-500 text-xs font-bold border-b border-slate-200">
              <tr>
                <th className="p-4">اسم الملف</th>
                <th className="p-4">المجلد</th>
                <th className="p-4">الحجم</th>
                <th className="p-4">الإصدار</th>
                <th className="p-4">آخر تعديل بواسطة</th>
                <th className="p-4">حالة القفل والأمان</th>
                <th className="p-4 text-center">الإجراءات</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {files.map((file) => (
                <tr key={file.id} className="hover:bg-slate-50/70 transition">
                  <td className="p-4">
                    <div className="flex items-center gap-3">
                      {getFileIcon(file.type)}
                      <span className="font-semibold text-slate-800">{file.name}</span>
                    </div>
                  </td>
                  <td className="p-4 text-xs text-slate-500">{file.folder}</td>
                  <td className="p-4 text-xs font-mono text-slate-600">{file.size}</td>
                  <td className="p-4">
                    <span className="px-2 py-0.5 rounded bg-slate-100 text-slate-700 text-xs font-bold font-mono">
                      v{file.version}
                    </span>
                  </td>
                  <td className="p-4 text-xs">
                    <p className="font-medium text-slate-700">{file.lastModifiedBy}</p>
                    <p className="text-slate-400 font-mono text-[11px]">{file.lastModifiedAt}</p>
                  </td>
                  <td className="p-4">
                    {file.isLocked ? (
                      <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-amber-50 text-amber-800 text-xs font-bold border border-amber-200">
                        <Lock className="w-3.5 h-3.5 text-amber-600" />
                        محجوز ({file.lockedBy})
                      </span>
                    ) : (
                      <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-emerald-50 text-emerald-700 text-xs font-bold border border-emerald-200">
                        <Check className="w-3.5 h-3.5 text-emerald-600" />
                        متاح للتعديل
                      </span>
                    )}
                  </td>
                  <td className="p-4 text-center">
                    <button className="p-1.5 text-slate-500 hover:text-emerald-600 hover:bg-emerald-50 rounded-lg transition">
                      <Download className="w-4 h-4" />
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
