'use client';

import React, { useState, useEffect, useRef, useMemo } from 'react';
import Link from 'next/link';
import {
  Database,
  Search,
  Plus,
  Edit2,
  Trash2,
  Download,
  RefreshCw,
  Layers,
  FileSpreadsheet,
  AlertCircle,
  CheckCircle,
  X,
  ChevronRight,
  ChevronLeft,
  ArrowUpDown,
  Filter,
  Eye,
  Save,
  Clock,
  Sparkles,
  ShieldCheck
} from 'lucide-react';

interface FileInfo {
  name: string;
  tables: string[];
  table_counts: Record<string, number>;
  total_rows: number;
  size_kb: number;
}

interface ApiResponse {
  success: boolean;
  sig: string;
  files: FileInfo[];
  total_records: number;
  active_file: string;
  active_table: string;
  available_tables: string[];
  columns: string[];
  total_matches: number;
  page: number;
  limit: number;
  total_pages: number;
  rows: any[];
  error?: string;
}

export default function AccessHubPage() {
  // Navigation & View States
  const [activeFile, setActiveFile] = useState<string>('all');
  const [activeTable, setActiveTable] = useState<string>('');
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [page, setPage] = useState<number>(1);
  const [limit, setLimit] = useState<number>(50);

  // Data States
  const [data, setData] = useState<ApiResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [lastSig, setLastSig] = useState<string>('');
  const [autoSyncMessage, setAutoSyncMessage] = useState<string | null>(null);

  // Modals States
  const [isAddModalOpen, setIsAddModalOpen] = useState<boolean>(false);
  const [isEditModalOpen, setIsEditModalOpen] = useState<boolean>(false);
  const [selectedRecord, setSelectedRecord] = useState<any | null>(null);
  const [formData, setFormData] = useState<Record<string, any>>({});
  const [deleteConfirmId, setDeleteConfirmId] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);

  // Fetch data
  const fetchData = async (isBackground = false) => {
    if (!isBackground) setLoading(true);
    setError(null);

    try {
      const params = new URLSearchParams({
        file: activeFile,
        table: activeTable,
        search: searchQuery,
        page: page.toString(),
        limit: limit.toString(),
      });

      const res = await fetch(`/api/access-hub?${params.toString()}`);
      const json: ApiResponse = await res.json();

      if (json.success) {
        setData(json);
        setLastSig(json.sig);
        if (!activeTable && json.active_table) {
          setActiveTable(json.active_table);
        }
      } else {
        setError(json.error || 'فشل جلب البيانات');
      }
    } catch (err: any) {
      setError('خطأ في الاتصال بالسحابة: ' + err.message);
    } finally {
      if (!isBackground) setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, [activeFile, activeTable, page, limit]);

  // Handle Search Debounce
  useEffect(() => {
    const handler = setTimeout(() => {
      setPage(1);
      fetchData();
    }, 350);
    return () => clearTimeout(handler);
  }, [searchQuery]);

  // Realtime Cloud Auto-Sync Polling (كل 5 ثوانٍ للتحقق من أي تعديل قام به موظف آخر)
  useEffect(() => {
    const interval = setInterval(async () => {
      if (!lastSig) return;
      try {
        const res = await fetch(`/api/access-hub?sig=${lastSig}`);
        const check = await res.json();
        if (check.changed) {
          // يوجد تعديل جديد من جهاز آخر!
          setAutoSyncMessage('تم استلام تحديث حي فوري من السحابة!');
          fetchData(true);
          setTimeout(() => setAutoSyncMessage(null), 4000);
        }
      } catch (e) {
        // Silent fail on background check
      }
    }, 5000);

    return () => clearInterval(interval);
  }, [lastSig, activeFile, activeTable, page, limit, searchQuery]);

  // Export to Excel / CSV
  const handleExportCSV = () => {
    if (!data || !data.rows || data.rows.length === 0) return;
    const cols = data.columns;
    const headerRow = cols.join(',');
    const rowsText = data.rows.map((row) =>
      cols
        .map((col) => {
          let v = row[col] || '';
          v = String(v).replace(/"/g, '""');
          return `"${v}"`;
        })
        .join(',')
    );

    const csvContent = '\uFEFF' + [headerRow, ...rowsText].join('\n');
    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.setAttribute('download', `${activeFile}_${activeTable || 'الكل'}.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  // Submit Add
  const handleAddSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!activeTable) return;
    setIsSubmitting(true);
    try {
      const res = await fetch('/api/access-hub', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          file: activeFile === 'all' ? (data?.files[0]?.name || '') : activeFile,
          table: activeTable,
          record: formData,
        }),
      });
      const resJson = await res.json();
      if (resJson.success) {
        setIsAddModalOpen(false);
        setFormData({});
        fetchData();
        setAutoSyncMessage('تمت إضافة القيد بنجاح ومزامنته سحابياً مع الجميع');
        setTimeout(() => setAutoSyncMessage(null), 3000);
      } else {
        alert(resJson.error || 'فشل حفظ القيد');
      }
    } catch (err: any) {
      alert('خطأ: ' + err.message);
    } finally {
      setIsSubmitting(false);
    }
  };

  // Submit Edit
  const handleEditSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedRecord) return;
    setIsSubmitting(true);
    try {
      const res = await fetch('/api/access-hub', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          file: selectedRecord._adh_file,
          table: selectedRecord._adh_table,
          id: selectedRecord._adh_id,
          updates: formData,
        }),
      });
      const resJson = await res.json();
      if (resJson.success) {
        setIsEditModalOpen(false);
        setSelectedRecord(null);
        setFormData({});
        fetchData();
        setAutoSyncMessage('تم تعديل السجل ومزامنته سحابياً لجميع الموظفين');
        setTimeout(() => setAutoSyncMessage(null), 3000);
      } else {
        alert(resJson.error || 'فشل حفظ التعديلات');
      }
    } catch (err: any) {
      alert('خطأ: ' + err.message);
    } finally {
      setIsSubmitting(false);
    }
  };

  // Submit Delete
  const handleDelete = async (record: any) => {
    try {
      const res = await fetch(
        `/api/access-hub?file=${encodeURIComponent(record._adh_file)}&table=${encodeURIComponent(record._adh_table)}&id=${encodeURIComponent(record._adh_id)}`,
        { method: 'DELETE' }
      );
      const resJson = await res.json();
      if (resJson.success) {
        setDeleteConfirmId(null);
        fetchData();
        setAutoSyncMessage('تم حذف السجل ومزامنته مع النظام السحابي');
        setTimeout(() => setAutoSyncMessage(null), 3000);
      } else {
        alert(resJson.error || 'فشل حذف السجل');
      }
    } catch (err: any) {
      alert('خطأ: ' + err.message);
    }
  };

  return (
    <div className="flex flex-col h-full bg-[#F7F8FA] overflow-y-auto">
      {/* 1. الترويسة العليا للمنظومة */}
      <div className="bg-white border-b border-[#E4E7EC] px-6 py-4 flex flex-col md:flex-row md:items-center justify-between gap-4 sticky top-0 z-30 shadow-xs">
        <div className="flex items-center gap-3.5">
          <div className="w-11 h-11 rounded-xl bg-[#14372e] flex items-center justify-center text-[#ecd58a] shadow-sm shrink-0">
            <Database className="w-6 h-6" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h1 className="font-bold text-lg text-[#1B1F24]">مركز قواعد بيانات آكسس الموحد</h1>
              <span className="text-[11px] bg-emerald-50 text-emerald-700 font-semibold px-2.5 py-0.5 rounded-full border border-emerald-200 flex items-center gap-1">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse"></span>
                سحابي وتشاركي 100%
              </span>
            </div>
            <p className="text-xs text-[#667085] mt-0.5">
              دمج كامل لكافة ملفات Access مع البحث، التعديل، والحذف اللحظي لجميع الموظفين
            </p>
          </div>
        </div>

        {/* مؤشرات الإحصائيات والإشعارات السحابية */}
        <div className="flex items-center gap-3">
          {autoSyncMessage && (
            <div className="bg-emerald-50 text-emerald-800 text-xs px-3 py-1.5 rounded-lg border border-emerald-200 flex items-center gap-1.5 animate-bounce">
              <ShieldCheck className="w-4 h-4 text-emerald-600" />
              <span>{autoSyncMessage}</span>
            </div>
          )}

          <div className="bg-[#F7F8FA] px-3 py-1.5 rounded-lg border border-[#E4E7EC] text-right">
            <div className="text-[11px] text-[#667085]">إجمالي السجلات المركزية</div>
            <div className="text-sm font-bold text-[#14372e]">
              {data?.total_records ? data.total_records.toLocaleString('ar-IQ') : '29,927'} قيد
            </div>
          </div>

          <button
            onClick={() => fetchData()}
            disabled={loading}
            className="p-2.5 rounded-lg border border-[#E4E7EC] bg-white hover:bg-[#F7F8FA] text-[#1B1F24] transition disabled:opacity-50"
            title="تحديث فوري"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin text-[#14372e]' : ''}`} />
          </button>
        </div>
      </div>

      {/* 2. شريط الخانات الرئيسي (الدمج الشامل + الخانات بالأسماء الحقيقية للملفات) */}
      <div className="bg-white border-b border-[#E4E7EC] px-6 pt-2 overflow-x-auto scrollbar-none sticky top-[73px] z-20">
        <div className="flex items-center gap-2 min-w-max pb-2">
          {/* الخانة الأولى: الدمج الشامل */}
          <button
            onClick={() => {
              setActiveFile('all');
              setActiveTable('');
              setPage(1);
            }}
            className={`flex items-center gap-2 px-4 py-2.5 rounded-xl text-xs font-bold transition ${
              activeFile === 'all'
                ? 'bg-[#14372e] text-white shadow-sm'
                : 'bg-[#F7F8FA] text-[#475467] hover:bg-[#ECEFF3] border border-[#E4E7EC]'
            }`}
          >
            <Sparkles className="w-4 h-4 text-[#ecd58a]" />
            <span>🌐 الدمج الشامل (كافة الملفات)</span>
            <span
              className={`text-[10px] px-2 py-0.5 rounded-full ${
                activeFile === 'all' ? 'bg-[#1a473b] text-[#ecd58a]' : 'bg-gray-200 text-gray-700'
              }`}
            >
              {data?.total_records ? data.total_records.toLocaleString('ar-IQ') : '29,927'}
            </span>
          </button>

          {/* باقي الخانات: مشتقة ديناميكياً من الأسماء الحقيقية للملفات بدون أي اسم وهمي */}
          {data?.files?.map((file) => {
            const isActive = activeFile === file.name;
            return (
              <button
                key={file.name}
                onClick={() => {
                  setActiveFile(file.name);
                  setActiveTable(file.tables[0] || '');
                  setPage(1);
                }}
                className={`flex items-center gap-2 px-4 py-2.5 rounded-xl text-xs font-bold transition ${
                  isActive
                    ? 'bg-[#14372e] text-white shadow-sm'
                    : 'bg-[#F7F8FA] text-[#475467] hover:bg-[#ECEFF3] border border-[#E4E7EC]'
                }`}
              >
                <Layers className="w-4 h-4 text-[#c59b27]" />
                <span>📁 {file.name}</span>
                <span
                  className={`text-[10px] px-2 py-0.5 rounded-full ${
                    isActive ? 'bg-[#1a473b] text-[#ecd58a]' : 'bg-gray-200 text-gray-700'
                  }`}
                >
                  {file.total_rows.toLocaleString('ar-IQ')}
                </span>
              </button>
            );
          })}
        </div>
      </div>

      {/* 3. شريط التحكم الداخلي: اختيار الجداول، البحث، والإجراءات */}
      <div className="p-6 space-y-4">
        {/* اختيار الجدول الداخلي إذا كنا في خانة ملف محدد */}
        {activeFile !== 'all' && data?.available_tables && data.available_tables.length > 0 && (
          <div className="flex items-center gap-2 overflow-x-auto pb-1">
            <span className="text-xs font-semibold text-[#667085] ml-2 shrink-0">جداول هذا الملف:</span>
            {data.available_tables.map((tbl) => {
              const isTblActive = activeTable === tbl;
              const count =
                data.files.find((f) => f.name === activeFile)?.table_counts[tbl] || 0;
              return (
                <button
                  key={tbl}
                  onClick={() => {
                    setActiveTable(tbl);
                    setPage(1);
                  }}
                  className={`px-3 py-1.5 rounded-lg text-xs font-medium transition shrink-0 ${
                    isTblActive
                      ? 'bg-[#c59b27] text-white shadow-xs font-bold'
                      : 'bg-white text-[#475467] hover:bg-[#F7F8FA] border border-[#E4E7EC]'
                  }`}
                >
                  {tbl} ({count.toLocaleString('ar-IQ')})
                </button>
              );
            })}
          </div>
        )}

        {/* شريط البحث والأزرار */}
        <div className="bg-white p-4 rounded-xl border border-[#E4E7EC] flex flex-col md:flex-row md:items-center justify-between gap-3 shadow-xs">
          {/* حقل البحث الفوري */}
          <div className="relative flex-1 max-w-md">
            <Search className="w-4 h-4 text-[#98A2B3] absolute right-3.5 top-1/2 -translate-y-1/2" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder={
                activeFile === 'all'
                  ? 'بحث شامل في كافة السجلات والتجار والشركات...'
                  : `بحث في جدول (${activeTable || 'البيانات'})...`
              }
              className="w-full pl-9 pr-10 py-2.5 text-xs bg-[#F7F8FA] border border-[#E4E7EC] rounded-lg text-[#1B1F24] focus:outline-none focus:border-[#14372e] transition"
            />
            {searchQuery && (
              <button
                onClick={() => setSearchQuery('')}
                className="absolute left-3 top-1/2 -translate-y-1/2 text-[#98A2B3] hover:text-[#1B1F24]"
              >
                <X className="w-4 h-4" />
              </button>
            )}
          </div>

          {/* أزرار العمليات */}
          <div className="flex items-center gap-2">
            <span className="text-xs text-[#667085] ml-2">
              نتائج البحث:{' '}
              <strong className="text-[#14372e]">
                {data?.total_matches ? data.total_matches.toLocaleString('ar-IQ') : 0}
              </strong>{' '}
              سجل
            </span>

            {/* تصدير إلى Excel */}
            <button
              onClick={handleExportCSV}
              className="flex items-center gap-1.5 px-3 py-2 bg-white hover:bg-[#F7F8FA] border border-[#E4E7EC] rounded-lg text-xs font-semibold text-[#1B1F24] transition"
              title="تصدير إلى ملف Excel / CSV"
            >
              <Download className="w-4 h-4 text-[#14372e]" />
              <span>تصدير Excel</span>
            </button>

            {/* إضافة قيد جديد */}
            {activeFile !== 'all' && (
              <button
                onClick={() => {
                  setFormData({});
                  setIsAddModalOpen(true);
                }}
                className="flex items-center gap-1.5 px-3.5 py-2 bg-[#14372e] hover:bg-[#1a473b] text-white rounded-lg text-xs font-semibold transition shadow-xs"
              >
                <Plus className="w-4 h-4 text-[#ecd58a]" />
                <span>إضافة قيد جديد</span>
              </button>
            )}
          </div>
        </div>

        {/* 4. الجدول المركزي لعرض البيانات */}
        <div className="bg-white rounded-xl border border-[#E4E7EC] shadow-xs overflow-hidden">
          {loading ? (
            <div className="p-12 flex flex-col items-center justify-center text-center gap-3">
              <RefreshCw className="w-8 h-8 text-[#14372e] animate-spin" />
              <p className="text-sm font-semibold text-[#1B1F24]">جاري جلب السجلات السحابية...</p>
              <p className="text-xs text-[#667085]">يتم استخراج ومزامنة السجلات من السحابة المركزية</p>
            </div>
          ) : error ? (
            <div className="p-8 text-center text-red-600 space-y-2">
              <AlertCircle className="w-8 h-8 mx-auto text-red-500" />
              <p className="font-semibold text-sm">{error}</p>
            </div>
          ) : data?.rows && data.rows.length > 0 ? (
            <div className="overflow-x-auto">
              <table className="w-full text-right text-xs">
                <thead>
                  <tr className="bg-[#F7F8FA] border-b border-[#E4E7EC] text-[#475467] font-bold">
                    <th className="py-3.5 px-4 w-12 text-center">#</th>
                    {activeFile === 'all' && (
                      <th className="py-3.5 px-4 whitespace-nowrap">الملف الحقيقي المصدر</th>
                    )}
                    {data.columns.map((col) => (
                      <th key={col} className="py-3.5 px-4 whitespace-nowrap">
                        {col}
                      </th>
                    ))}
                    <th className="py-3.5 px-4 text-center w-28 whitespace-nowrap">الإجراءات</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[#E4E7EC]">
                  {data.rows.map((row, idx) => {
                    const rowNum = (page - 1) * limit + idx + 1;
                    return (
                      <tr key={row._adh_id || idx} className="hover:bg-[#F9FAFB] transition">
                        <td className="py-3 px-4 text-center text-[#98A2B3] font-mono">{rowNum}</td>

                        {/* إظهار اسم الملف في خانة الدمج الشامل */}
                        {activeFile === 'all' && (
                          <td className="py-3 px-4 whitespace-nowrap">
                            <span className="inline-flex items-center gap-1 bg-[#14372e]/5 text-[#14372e] font-semibold px-2.5 py-1 rounded-md text-[11px] border border-[#14372e]/10">
                              <Layers className="w-3 h-3 text-[#c59b27]" />
                              {row._adh_file}
                            </span>
                          </td>
                        )}

                        {/* خلايا البيانات */}
                        {data.columns.map((col) => (
                          <td key={col} className="py-3 px-4 text-[#1B1F24] whitespace-nowrap max-w-xs truncate">
                            {row[col] !== null && row[col] !== undefined && row[col] !== '' ? (
                              String(row[col])
                            ) : (
                              <span className="text-[#D0D5DD]">-</span>
                            )}
                          </td>
                        ))}

                        {/* أزرار التعديل والحذف */}
                        <td className="py-3 px-4 text-center whitespace-nowrap">
                          <div className="flex items-center justify-center gap-1.5">
                            <button
                              onClick={() => {
                                setSelectedRecord(row);
                                setFormData({ ...row });
                                setIsEditModalOpen(true);
                              }}
                              className="p-1.5 rounded-md hover:bg-emerald-50 text-[#14372e] transition"
                              title="تعديل هذا السجل"
                            >
                              <Edit2 className="w-3.5 h-3.5" />
                            </button>

                            {deleteConfirmId === row._adh_id ? (
                              <div className="flex items-center gap-1">
                                <button
                                  onClick={() => handleDelete(row)}
                                  className="px-2 py-0.5 bg-red-600 text-white rounded text-[10px] font-bold"
                                >
                                  تأكيد
                                </button>
                                <button
                                  onClick={() => setDeleteConfirmId(null)}
                                  className="px-1 py-0.5 text-[#667085] text-[10px]"
                                >
                                  إلغاء
                                </button>
                              </div>
                            ) : (
                              <button
                                onClick={() => setDeleteConfirmId(row._adh_id)}
                                className="p-1.5 rounded-md hover:bg-red-50 text-red-500 transition"
                                title="حذف هذا السجل"
                              >
                                <Trash2 className="w-3.5 h-3.5" />
                              </button>
                            )}
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="p-12 text-center text-[#667085]">
              <AlertCircle className="w-8 h-8 mx-auto text-[#98A2B3] mb-2" />
              <p className="text-sm font-semibold">لا توجد سجلات مطابقة للبحث</p>
              <p className="text-xs mt-1">تأكد من كتابة الكلمة الصحيحة أو قم بتفريغ شريط البحث</p>
            </div>
          )}

          {/* 5. شريط الترقيم والتنقل بين الصفحات */}
          {data && data.total_pages > 1 && (
            <div className="p-4 border-t border-[#E4E7EC] flex items-center justify-between text-xs bg-white">
              <span className="text-[#667085]">
                الصفحة <strong>{page}</strong> من <strong>{data.total_pages}</strong> (إجمالي{' '}
                {data.total_matches.toLocaleString('ar-IQ')} قيد)
              </span>

              <div className="flex items-center gap-1.5">
                <button
                  disabled={page <= 1}
                  onClick={() => setPage((p) => Math.max(1, p - 1))}
                  className="px-3 py-1.5 rounded-lg border border-[#E4E7EC] text-[#1B1F24] hover:bg-[#F7F8FA] disabled:opacity-40 font-medium transition"
                >
                  السابق
                </button>
                <button
                  disabled={page >= data.total_pages}
                  onClick={() => setPage((p) => Math.min(data.total_pages, p + 1))}
                  className="px-3 py-1.5 rounded-lg border border-[#E4E7EC] text-[#1B1F24] hover:bg-[#F7F8FA] disabled:opacity-40 font-medium transition"
                >
                  التالي
                </button>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* 6. نافذة الإضافة (Add Modal) */}
      {isAddModalOpen && (
        <div className="fixed inset-0 z-50 bg-black/40 backdrop-blur-xs flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl w-full max-w-2xl max-h-[85vh] flex flex-col shadow-2xl border border-[#E4E7EC]">
            <div className="p-4 border-b border-[#E4E7EC] flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Plus className="w-5 h-5 text-[#14372e]" />
                <h3 className="font-bold text-sm text-[#1B1F24]">
                  إضافة قيد جديد إلى جدول ({activeTable})
                </h3>
              </div>
              <button onClick={() => setIsAddModalOpen(false)} className="text-[#667085] hover:text-[#1B1F24]">
                <X className="w-5 h-5" />
              </button>
            </div>

            <form onSubmit={handleAddSubmit} className="flex-1 overflow-y-auto p-5 space-y-3.5">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3.5">
                {data?.columns.map((col) => (
                  <div key={col} className="space-y-1">
                    <label className="text-xs font-semibold text-[#475467]">{col}</label>
                    <input
                      type="text"
                      value={formData[col] || ''}
                      onChange={(e) => setFormData({ ...formData, [col]: e.target.value })}
                      className="w-full px-3 py-2 text-xs bg-[#F7F8FA] border border-[#E4E7EC] rounded-lg text-[#1B1F24] focus:outline-none focus:border-[#14372e]"
                    />
                  </div>
                ))}
              </div>

              <div className="pt-4 border-t border-[#E4E7EC] flex justify-end gap-2">
                <button
                  type="button"
                  onClick={() => setIsAddModalOpen(false)}
                  className="px-4 py-2 text-xs font-semibold text-[#475467] bg-[#F7F8FA] rounded-lg border border-[#E4E7EC]"
                >
                  إلغاء
                </button>
                <button
                  type="submit"
                  disabled={isSubmitting}
                  className="px-5 py-2 text-xs font-bold text-white bg-[#14372e] hover:bg-[#1a473b] rounded-lg transition"
                >
                  {isSubmitting ? 'جاري الحفظ...' : 'حفظ ومزامنة سحابية'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* 7. نافذة التعديل (Edit Modal) */}
      {isEditModalOpen && selectedRecord && (
        <div className="fixed inset-0 z-50 bg-black/40 backdrop-blur-xs flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl w-full max-w-2xl max-h-[85vh] flex flex-col shadow-2xl border border-[#E4E7EC]">
            <div className="p-4 border-b border-[#E4E7EC] flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Edit2 className="w-5 h-5 text-[#c59b27]" />
                <h3 className="font-bold text-sm text-[#1B1F24]">
                  تعديل القيد (الملف: {selectedRecord._adh_file})
                </h3>
              </div>
              <button onClick={() => setIsEditModalOpen(false)} className="text-[#667085] hover:text-[#1B1F24]">
                <X className="w-5 h-5" />
              </button>
            </div>

            <form onSubmit={handleEditSubmit} className="flex-1 overflow-y-auto p-5 space-y-3.5">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3.5">
                {Object.keys(selectedRecord)
                  .filter((k) => !k.startsWith('_adh_') && !k.startsWith('Field'))
                  .map((col) => (
                    <div key={col} className="space-y-1">
                      <label className="text-xs font-semibold text-[#475467]">{col}</label>
                      <input
                        type="text"
                        value={formData[col] || ''}
                        onChange={(e) => setFormData({ ...formData, [col]: e.target.value })}
                        className="w-full px-3 py-2 text-xs bg-[#F7F8FA] border border-[#E4E7EC] rounded-lg text-[#1B1F24] focus:outline-none focus:border-[#14372e]"
                      />
                    </div>
                  ))}
              </div>

              <div className="pt-4 border-t border-[#E4E7EC] flex justify-end gap-2">
                <button
                  type="button"
                  onClick={() => setIsEditModalOpen(false)}
                  className="px-4 py-2 text-xs font-semibold text-[#475467] bg-[#F7F8FA] rounded-lg border border-[#E4E7EC]"
                >
                  إلغاء
                </button>
                <button
                  type="submit"
                  disabled={isSubmitting}
                  className="px-5 py-2 text-xs font-bold text-white bg-[#14372e] hover:bg-[#1a473b] rounded-lg transition"
                >
                  {isSubmitting ? 'جاري الحفظ...' : 'تطبيق التعديلات السحابية'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
