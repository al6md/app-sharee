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
  ArrowDown,
  ArrowUp,
  Filter,
  Eye,
  Save,
  Clock,
  Sparkles,
  ShieldCheck,
  Calendar,
  SlidersHorizontal,
  Columns,
  PlusCircle,
  Settings,
  Shield,
  Phone,
  Copy,
  MapPin,
  Briefcase,
  Building2,
  LayoutGrid,
  TableProperties
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
  date_columns?: string[];
  sort_col?: string;
  sort_dir?: string;
  total_matches: number;
  page: number;
  limit: number;
  total_pages: number;
  rows: any[];
  error?: string;
}

const TABLE_META: Record<string, { icon: string; title: string }> = {
  'التجار': { icon: '👥', title: 'التجار' },
  'الشركات': { icon: '🏢', title: 'الشركات' },
  'الدلالين': { icon: '🤝', title: 'الدلالين' },
  'دلالين': { icon: '🤝', title: 'الدلالين' },
  'التعديل': { icon: '✏️', title: 'التعديل' },
  'المعامل': { icon: '🏭', title: 'المعامل' },
  'الفنادق': { icon: '🏨', title: 'الفنادق' },
  'المطاعم': { icon: '🍽️', title: 'المطاعم' },
  'المقاهي': { icon: '☕', title: 'المقاهي' },
  'الصيدليات': { icon: '💊', title: 'الصيدليات' },
  'الساحات': { icon: '🚗', title: 'الساحات' },
  'الشطب': { icon: '🚫', title: 'الشطب' },
};

export default function AccessHubPage() {
  // Navigation & View States
  const [activeFile, setActiveFile] = useState<string>('all');
  const [activeTable, setActiveTable] = useState<string>('');
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [page, setPage] = useState<number>(1);
  const [limit, setLimit] = useState<number>(50);

  // Mobile & Responsive View States
  const [viewMode, setViewMode] = useState<'cards' | 'table'>('cards');
  const [viewingRecord, setViewingRecord] = useState<any | null>(null);
  const [copyFeedback, setCopyFeedback] = useState<string | null>(null);

  // أمان مركز بيانات Access وتسجيل الأجهزة لمرة واحدة
  const [accessHubSec, setAccessHubSec] = useState<any>(null);
  const [isSecChecking, setIsSecChecking] = useState<boolean>(true);
  const [isUnlocked, setIsUnlocked] = useState<boolean>(false);
  const [authInputUser, setAuthInputUser] = useState<string>('');
  const [authInputPass, setAuthInputPass] = useState<string>('');
  const [authInputDevName, setAuthInputDevName] = useState<string>('');
  const [authError, setAuthError] = useState<string>('');
  const [authLoading, setAuthLoading] = useState<boolean>(false);

  // التحقق الدوري من ترخيص هذا الجهاز لمركز بيانات Access
  const checkAccessSecurity = async () => {
    try {
      const res = await fetch('/api/drive/permissions?t=' + Date.now(), { cache: 'no-store' });
      const json = await res.json();
      if (json.success && json.accessHubSecurity) {
        setAccessHubSec(json.accessHubSecurity);
        const sec = json.accessHubSecurity;
        const guid = typeof window !== 'undefined' ? localStorage.getItem('sharecoc_device_guid') || '' : '';
        const hasCreds = Boolean(sec.username || sec.password || sec.pinCode);
        const isProtected = Boolean(sec.enabled !== false && hasCreds);
        if (!isProtected) {
          setIsUnlocked(true);
        } else {
          const authed = Boolean(guid && Array.isArray(sec.authorizedDevices) && sec.authorizedDevices.includes(guid));
          setIsUnlocked(authed);
        }
      } else {
        setIsUnlocked(true);
      }
    } catch {
      setIsUnlocked(true);
    } finally {
      setIsSecChecking(false);
    }
  };

  useEffect(() => {
    checkAccessSecurity();
  }, []);

  // معالجة تسجيل الدخول واعتماد الجهاز لمرة واحدة فقط للأبد
  const handleVerifyAccessAuth = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    try {
      setAuthLoading(true);
      setAuthError('');
      let guid = typeof window !== 'undefined' ? localStorage.getItem('sharecoc_device_guid') || '' : '';
      if (!guid) {
        guid = 'WEB-' + crypto.randomUUID();
        if (typeof window !== 'undefined') localStorage.setItem('sharecoc_device_guid', guid);
      }
      const devName = authInputDevName.trim() || (typeof window !== 'undefined' ? localStorage.getItem('sharecoc_device_name') || '' : '') || 'متصفح ويب';

      const res = await fetch('/api/drive/permissions', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          action: 'REGISTER_ACCESS_HUB_DEVICE',
          username: authInputUser.trim(),
          password: authInputPass.trim(),
          machineGuid: guid,
          deviceName: devName,
          os: typeof navigator !== 'undefined' ? navigator.userAgent : 'Web Browser',
          user: devName,
        }),
      });
      const data = await res.json();
      if (data.success && data.authorized) {
        if (typeof window !== 'undefined') {
          localStorage.setItem('sharecoc_device_guid', guid);
          localStorage.setItem('sharecoc_device_name', devName);
        }
        setIsUnlocked(true);
        if (data.accessHubSecurity) {
          setAccessHubSec(data.accessHubSecurity);
        }
      } else {
        setAuthError(data.error || 'بيانات الدخول لمركز بيانات Access غير صحيحة، يرجى مراجعة إدارة الغرفة.');
      }
    } catch (err: any) {
      setAuthError(`خطأ في التحقق: ${err.message}`);
    } finally {
      setAuthLoading(false);
    }
  };

  // Auto-detect mobile screen on mount
  useEffect(() => {
    if (typeof window !== 'undefined') {
      if (window.innerWidth >= 768) {
        setViewMode('table');
      } else {
        setViewMode('cards');
      }
    }
  }, []);

  const getShortFileName = (name: string) => {
    if (!name) return '';
    if (name.includes('جهاز الاشتراكات')) return 'جهاز الاشتراكات';
    if (name.includes('2025')) return '2025 - 2026';
    if (name.includes('2024')) return '2024';
    if (name.includes('2023')) return '2023';
    if (name.includes('2022')) return '2022';
    if (name.includes('1984')) return '1984 - 2021';
    if (name.includes('جديد') || name.includes('المبتكرة')) return 'الكلية والمبتكرة';
    return name;
  };

  const handleCopyRecord = (row: any) => {
    if (!row) return;
    const lines = Object.entries(row)
      .filter(([k]) => !k.startsWith('_adh_'))
      .map(([k, v]) => `${k}: ${v ?? ''}`)
      .join('\n');
    navigator.clipboard.writeText(lines);
    setCopyFeedback('تم نسخ تفاصيل القيد!');
    setTimeout(() => setCopyFeedback(null), 2500);
  };

  // Sorting States (ترتيب التواريخ من الجديد للقديم وبالعكس)
  const [sortDir, setSortDir] = useState<'none' | 'desc' | 'asc'>('none');
  const [sortCol, setSortCol] = useState<string>('date_auto');

  // Data States
  const [data, setData] = useState<ApiResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [lastSig, setLastSig] = useState<string>('');
  const [autoSyncMessage, setAutoSyncMessage] = useState<string | null>(null);

  // Modals States: Records (البيانات)
  const [isAddModalOpen, setIsAddModalOpen] = useState<boolean>(false);
  const [isEditModalOpen, setIsEditModalOpen] = useState<boolean>(false);
  const [selectedRecord, setSelectedRecord] = useState<any | null>(null);
  const [formData, setFormData] = useState<Record<string, any>>({});
  const [deleteConfirmId, setDeleteConfirmId] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);

  // Modals States: Columns Management (إضافة وحذف الحقول)
  const [isAddColModalOpen, setIsAddColModalOpen] = useState<boolean>(false);
  const [newColName, setNewColName] = useState<string>('');
  const [isManageColsModalOpen, setIsManageColsModalOpen] = useState<boolean>(false);
  const [deleteColConfirm, setDeleteColConfirm] = useState<string | null>(null);

  // قراءة معلمات الرابط عند الانتقال
  useEffect(() => {
    if (typeof window !== 'undefined') {
      const sp = new URLSearchParams(window.location.search);
      const f = sp.get('file');
      const t = sp.get('table');
      if (f) setActiveFile(f);
      if (t) setActiveTable(t);
    }
  }, []);

  // Fetch data with sorting & cloud params
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
        sort_dir: sortDir,
        sort_col: sortCol,
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
  }, [activeFile, activeTable, page, limit, sortDir, sortCol]);

  // Handle Search Debounce
  useEffect(() => {
    const handler = setTimeout(() => {
      setPage(1);
      fetchData();
    }, 350);
    return () => clearTimeout(handler);
  }, [searchQuery]);

  // Realtime Cloud Auto-Sync Polling
  useEffect(() => {
    const interval = setInterval(async () => {
      if (!lastSig) return;
      try {
        const res = await fetch(`/api/access-hub?sig=${lastSig}`);
        const check = await res.json();
        if (check.changed) {
          setAutoSyncMessage('تم استلام تحديث حي فوري من السحابة!');
          fetchData(true);
          setTimeout(() => setAutoSyncMessage(null), 4000);
        }
      } catch (e) {
        // Silent fail on background check
      }
    }, 5000);

    return () => clearInterval(interval);
  }, [lastSig, activeFile, activeTable, page, limit, searchQuery, sortDir, sortCol]);

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

  // Submit Add Record
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
        setTimeout(() => setAutoSyncMessage(null), 3500);
      } else {
        alert(resJson.error || 'فشل حفظ القيد');
      }
    } catch (err: any) {
      alert('خطأ: ' + err.message);
    } finally {
      setIsSubmitting(false);
    }
  };

  // Submit Edit Record
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
        setTimeout(() => setAutoSyncMessage(null), 3500);
      } else {
        alert(resJson.error || 'فشل حفظ التعديلات');
      }
    } catch (err: any) {
      alert('خطأ: ' + err.message);
    } finally {
      setIsSubmitting(false);
    }
  };

  // Submit Delete Record
  const handleDelete = async (record: any) => {
    try {
      const res = await fetch(
        `/api/access-hub?id=${encodeURIComponent(record._adh_id)}`,
        { method: 'DELETE' }
      );
      const resJson = await res.json();
      if (resJson.success) {
        setDeleteConfirmId(null);
        fetchData();
        setAutoSyncMessage('تم حذف السجل ومزامنته مع النظام السحابي');
        setTimeout(() => setAutoSyncMessage(null), 3500);
      } else {
        alert(resJson.error || 'فشل حذف السجل');
      }
    } catch (err: any) {
      alert('خطأ: ' + err.message);
    }
  };

  // Submit Add Column (إضافة حقل جديد للجدول)
  const handleAddColumn = async (e: React.FormEvent) => {
    e.preventDefault();
    const colTrimmed = newColName.trim();
    if (!colTrimmed) return;
    if (!activeTable) {
      alert('يرجى اختيار جدول أولاً لإضافة الحقل إليه');
      return;
    }
    setIsSubmitting(true);
    try {
      const res = await fetch('/api/access-hub', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          action: 'ADD_COLUMN',
          file: activeFile,
          table: activeTable,
          columnName: colTrimmed,
        }),
      });
      const resJson = await res.json();
      if (resJson.success) {
        setIsAddColModalOpen(false);
        setNewColName('');
        fetchData();
        setAutoSyncMessage(`تمت إضافة الحقل "${colTrimmed}" بنجاح وتعميمه سحابياً`);
        setTimeout(() => setAutoSyncMessage(null), 3500);
      } else {
        alert(resJson.error || 'فشل إضافة الحقل');
      }
    } catch (err: any) {
      alert('خطأ في إضافة الحقل: ' + err.message);
    } finally {
      setIsSubmitting(false);
    }
  };

  // Submit Delete Column (حذف حقل من الجدول)
  const handleDeleteColumn = async (colToDelete: string) => {
    if (!activeTable) return;
    setIsSubmitting(true);
    try {
      const res = await fetch('/api/access-hub', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          action: 'DELETE_COLUMN',
          file: activeFile,
          table: activeTable,
          columnName: colToDelete,
        }),
      });
      const resJson = await res.json();
      if (resJson.success) {
        setDeleteColConfirm(null);
        fetchData();
        setAutoSyncMessage(`تم حذف الحقل "${colToDelete}" سحابياً`);
        setTimeout(() => setAutoSyncMessage(null), 3500);
      } else {
        alert(resJson.error || 'فشل حذف الحقل');
      }
    } catch (err: any) {
      alert('خطأ في حذف الحقل: ' + err.message);
    } finally {
      setIsSubmitting(false);
    }
  };

  // Toggle Header Column Sort (الفرز عند النقر على رأس العمود)
  const handleColumnHeaderClick = (col: string) => {
    if (sortCol === col) {
      if (sortDir === 'none') setSortDir('desc');
      else if (sortDir === 'desc') setSortDir('asc');
      else {
        setSortDir('none');
        setSortCol('date_auto');
      }
    } else {
      setSortCol(col);
      setSortDir('desc');
    }
  };

  // دالة لتنسيق وتجميل محتوى الخلايا (الأصناف والأسماء وأرقام الهواتف)
  const renderCellContent = (col: string, val: any) => {
    if (val === null || val === undefined || val === '') {
      return <span className="text-[#D0D5DD] font-mono">-</span>;
    }
    const str = String(val).trim();

    // تمييز الأصناف والدرجات
    if (['Class', 'الصنف', 'الدرجة'].includes(col)) {
      if (str.includes('ممتاز') || str.toLowerCase().includes('excellent')) {
        return <span className="inline-flex items-center px-2 py-0.5 rounded text-[11px] font-bold bg-amber-50 text-amber-900 border border-amber-300">⭐ {str}</span>;
      }
      if (str.includes('أول') || str.includes('الاول') || str.toLowerCase().includes('first')) {
        return <span className="inline-flex items-center px-2 py-0.5 rounded text-[11px] font-bold bg-emerald-50 text-emerald-900 border border-emerald-300">🥇 {str}</span>;
      }
      if (str.includes('ثان') || str.toLowerCase().includes('second')) {
        return <span className="inline-flex items-center px-2 py-0.5 rounded text-[11px] font-bold bg-blue-50 text-blue-900 border border-blue-300">🥈 {str}</span>;
      }
      if (str.includes('ثالث') || str.toLowerCase().includes('third')) {
        return <span className="inline-flex items-center px-2 py-0.5 rounded text-[11px] font-bold bg-purple-50 text-purple-900 border border-purple-300">🥉 {str}</span>;
      }
      if (str.includes('رابع') || str.toLowerCase().includes('fourth')) {
        return <span className="inline-flex items-center px-2 py-0.5 rounded text-[11px] font-bold bg-slate-100 text-slate-900 border border-slate-300">4️⃣ {str}</span>;
      }
    }

    // تمييز أسماء التجار والشركات
    if (['ArabicName', 'اسم التاجر', 'الاسم التجاري', 'الإسم التجاري'].includes(col)) {
      return <span className="font-bold text-[#14372e] text-[12.5px]">{str}</span>;
    }

    // تمييز أرقام الهواتف
    if (['Mobile', 'الهاتف', 'رقم الهاتف'].includes(col)) {
      return <span className="font-mono text-[#344054] font-semibold text-[11px]">{str}</span>;
    }

    return str;
  };

  // استخراج الحقول الجوهرية لعرض بطاقة الجوال الذكية
  const extractCardFields = (row: any) => {
    const name =
      row.ArabicName ||
      row['اسم التاجر'] ||
      row['الاسم التجاري'] ||
      row['الإسم التجاري'] ||
      row.Name ||
      'قيد مسجل بدون اسم';
    const commercialName =
      (row['الاسم التجاري'] && row['الاسم التجاري'] !== name ? row['الاسم التجاري'] : null) ||
      (row['الإسم التجاري'] && row['الإسم التجاري'] !== name ? row['الإسم التجاري'] : null) ||
      (row.CommercialName && row.CommercialName !== name ? row.CommercialName : null) ||
      row['اسم المحل'] ||
      null;
    const activity =
      row['نوع النشاط'] ||
      row['النشاط'] ||
      row.Activity ||
      row['نوع المحل'] ||
      null;
    const phone =
      row.Mobile ||
      row['الهاتف'] ||
      row['رقم الهاتف'] ||
      row.Phone ||
      null;
    const address =
      row['العنوان'] ||
      row['عنوان المحل'] ||
      row.Address ||
      row['المنطقة'] ||
      null;
    const dateVal =
      row['تاريخ التسجيل'] ||
      row['تاريخ التجديد'] ||
      row['تاريخ انتهاء الإجازة'] ||
      row.Date ||
      row.RegDate ||
      null;
    const grade =
      row.Class ||
      row['الصنف'] ||
      row['الدرجة'] ||
      null;

    return { name, commercialName, activity, phone, address, dateVal, grade };
  };

  // مكون مشترك لرسم أزرار فئات الجداول الـ 11 بالأسماء الكاملة والأيقونات
  const renderCategoryButtons = () => {
    return (data?.available_tables || []).map((tbl) => {
      const isTblActive = activeTable === tbl;
      const meta = TABLE_META[tbl] || { icon: '🏷️', title: tbl };
      const count =
        activeFile === 'all'
          ? (data?.files || []).reduce((acc, f) => acc + (f.table_counts[tbl] || 0), 0)
          : data?.files.find((f) => f.name === activeFile)?.table_counts[tbl] || 0;
      return (
        <button
          key={tbl}
          onClick={() => {
            setActiveTable(tbl);
            setPage(1);
          }}
          title={`جدول ${meta.title} (${count.toLocaleString('ar-IQ')} قيد)`}
          className={`flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-bold whitespace-nowrap min-w-max transition cursor-pointer shrink-0 shadow-2xs ${
            isTblActive
              ? 'bg-[#14372e] text-white shadow-xs'
              : 'bg-white text-[#344054] hover:bg-[#F2F4F7] border border-[#E4E7EC]'
          }`}
        >
          <span className="flex items-center gap-1">
            <span>{meta.icon}</span>
            <span>{meta.title}</span>
          </span>
          <span
            className={`text-[10px] font-mono px-1.5 py-0.2 rounded-full ${
              isTblActive ? 'bg-[#c59b27] text-white' : 'bg-[#F2F4F7] text-[#667085] border border-[#E4E7EC]'
            }`}
          >
            {count.toLocaleString('ar-IQ')}
          </span>
        </button>
      );
    });
  };

  if (isSecChecking) {
    return (
      <div className="flex items-center justify-center min-h-screen bg-[#F7F8FA]" dir="rtl">
        <div className="flex flex-col items-center gap-3">
          <RefreshCw className="w-8 h-8 text-[#14372e] animate-spin" />
          <p className="text-xs font-bold text-slate-600">جاري التحقق من ترخيص الجهاز سحابياً...</p>
        </div>
      </div>
    );
  }

  if (!isUnlocked) {
    return (
      <div className="flex items-center justify-center min-h-screen bg-[#F7F8FA] p-4 text-right" dir="rtl">
        <div className="bg-white rounded-3xl border border-slate-200 shadow-2xl p-6 sm:p-8 max-w-md w-full animate-in zoom-in-95 duration-200">
          <div className="text-center mb-6">
            <div className="w-16 h-16 rounded-2xl bg-[#14372e] text-[#ecd58a] mx-auto flex items-center justify-center text-3xl shadow-lg shadow-[#14372e]/20 mb-3">
              🏛️
            </div>
            <h2 className="text-lg font-black text-slate-900">أمان مركز بيانات Access</h2>
            <p className="text-xs text-slate-500 mt-1.5 leading-relaxed">
              هذا المركز محمي برمز مرور وحساب خاص من إدارة الغرفة. يرجى تسجيل الدخول لمرة واحدة لاعتماد هذا الجهاز للأبد:
            </p>
          </div>

          {authError && (
            <div className="p-3 mb-4 rounded-xl bg-rose-50 border border-rose-200 text-rose-700 text-xs font-bold flex items-center gap-2">
              <AlertCircle className="w-4 h-4 shrink-0" />
              <span>{authError}</span>
            </div>
          )}

          <form onSubmit={handleVerifyAccessAuth} className="space-y-4">
            <div>
              <label className="block text-xs font-bold text-slate-700 mb-1.5">
                اسم مستخدم مركز Access:
              </label>
              <input
                type="text"
                required
                value={authInputUser}
                onChange={(e) => setAuthInputUser(e.target.value)}
                placeholder="أدخل اسم المستخدم..."
                className="w-full text-xs p-3 rounded-xl border border-slate-200 focus:outline-none focus:border-[#14372e] bg-slate-50/50"
              />
            </div>

            <div>
              <label className="block text-xs font-bold text-slate-700 mb-1.5">
                رمز / كلمة مرور مركز Access:
              </label>
              <input
                type="password"
                required
                value={authInputPass}
                onChange={(e) => setAuthInputPass(e.target.value)}
                placeholder="أدخل رمز المرور أو كلمة السر..."
                className="w-full text-xs p-3 rounded-xl border border-slate-200 focus:outline-none focus:border-[#14372e] bg-slate-50/50 font-mono"
              />
            </div>

            <div>
              <label className="block text-xs font-bold text-slate-700 mb-1.5">
                اسم هذا الجهاز (للتوثيق لدى الأدمن):
              </label>
              <input
                type="text"
                value={authInputDevName}
                onChange={(e) => setAuthInputDevName(e.target.value)}
                placeholder="مثال: حاسوب التراخيص - مكتب 3"
                className="w-full text-xs p-3 rounded-xl border border-slate-200 focus:outline-none focus:border-[#14372e] bg-slate-50/50"
              />
            </div>

            <button
              type="submit"
              disabled={authLoading}
              className="w-full py-3 bg-[#14372e] hover:bg-[#1a473b] text-white rounded-xl text-xs font-bold transition shadow-md shadow-[#14372e]/20 flex items-center justify-center gap-2 cursor-pointer disabled:opacity-50"
            >
              {authLoading ? (
                <>
                  <RefreshCw className="w-4 h-4 animate-spin text-[#ecd58a]" />
                  <span>جاري التحقق واعتماد الجهاز سحابياً...</span>
                </>
              ) : (
                <>
                  <ShieldCheck className="w-4 h-4 text-[#ecd58a]" />
                  <span>اعتماد هذا الجهاز ودخول مركز Access</span>
                </>
              )}
            </button>

            <div className="pt-2 text-center">
              <Link
                href="/files"
                className="text-xs font-bold text-slate-500 hover:text-slate-800 transition"
              >
                العودة إلى مستكشف المستندات
              </Link>
            </div>
          </form>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full bg-[#F7F8FA] overflow-hidden">
      {/* إشعار نسخ البيانات */}
      {copyFeedback && (
        <div className="fixed top-12 left-1/2 -translate-x-1/2 z-50 bg-[#14372e] text-white px-4 py-2 rounded-xl text-xs font-bold shadow-xl flex items-center gap-2 border border-[#ecd58a]/40 animate-in fade-in slide-in-from-top-2">
          <CheckCircle className="w-4 h-4 text-[#ecd58a]" />
          <span>{copyFeedback}</span>
        </div>
      )}

      {/* 1. الترويسة المزدوجة المتكيفة: سطح المكتب (Desktop) والجوال (Mobile) */}
      {/* نسخة سطح المكتب (Desktop Header - 44px) */}
      <header className="hidden md:flex h-[44px] bg-white border-b border-[#E4E7EC] px-4 items-center justify-between shrink-0 z-20">
        <div className="flex items-center gap-2.5">
          <div className="w-7 h-7 rounded-lg bg-[#14372e] flex items-center justify-center text-[#ecd58a] shrink-0">
            <Database className="w-4 h-4" />
          </div>
          <div className="flex items-center gap-2">
            <h1 className="font-bold text-sm text-[#1B1F24]">مركز قواعد بيانات Access الموحد</h1>
            <span className="text-[11px] font-mono font-bold bg-[#EDF5F2] text-[#14372e] px-2 py-0.5 rounded-full border border-[#14372e]/20">
              {data?.total_records ? data.total_records.toLocaleString('ar-IQ') : '88,987'} قيد
            </span>
            <span className="inline-flex items-center gap-1 text-[10px] text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded-full font-semibold border border-emerald-200">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse"></span>
              سحابي ومباشر
            </span>
          </div>
        </div>

        <div className="flex items-center gap-2">
          {autoSyncMessage && (
            <div className="text-[11px] bg-emerald-50 text-emerald-800 px-2.5 py-1 rounded-md border border-emerald-200 flex items-center gap-1 font-semibold animate-in fade-in">
              <CheckCircle className="w-3.5 h-3.5 text-emerald-600" />
              <span>{autoSyncMessage}</span>
            </div>
          )}

          <Link
            href="/admin"
            className="flex items-center gap-1.5 px-3 py-1.5 bg-[#14372e] hover:bg-[#1a473b] text-white rounded-lg text-xs font-semibold transition cursor-pointer"
            title="الانتقال إلى لوحة تحكم الإدارة والصلاحيات والحقول"
          >
            <Shield className="w-3.5 h-3.5 text-[#ecd58a]" />
            <span>لوحة تحكم الإدارة</span>
          </Link>

          <button
            onClick={() => fetchData()}
            disabled={loading}
            className="p-1.5 rounded-lg border border-[#E4E7EC] bg-white hover:bg-[#F7F8FA] text-[#1B1F24] transition disabled:opacity-50 cursor-pointer"
            title="تحديث فوري للسجلات"
          >
            <RefreshCw className={`w-3.5 h-3.5 text-[#667085] ${loading ? 'animate-spin text-[#14372e]' : ''}`} />
          </button>
        </div>
      </header>

      {/* نسخة الجوال النحيفة (Mobile Header - 40px) */}
      <header className="md:hidden h-[40px] bg-white border-b border-[#E4E7EC] px-3 flex items-center justify-between shrink-0 z-20">
        <div className="flex items-center gap-2 min-w-0">
          <div className="w-6 h-6 rounded-md bg-[#14372e] flex items-center justify-center text-[#ecd58a] shrink-0">
            <Database className="w-3.5 h-3.5" />
          </div>
          <span className="font-bold text-xs text-[#1B1F24] truncate">بيانات Access</span>
          <span className="text-[10px] font-mono font-bold bg-[#EDF5F2] text-[#14372e] px-1.5 py-0.2 rounded-full border border-[#14372e]/20 shrink-0">
            {data?.total_records ? data.total_records.toLocaleString('ar-IQ') : '88,987'}
          </span>
        </div>

        <div className="flex items-center gap-1.5 shrink-0">
          <Link
            href="/admin"
            className="flex items-center gap-1 px-2.5 py-1 bg-[#14372e] text-white rounded-lg text-[11px] font-semibold"
          >
            <Shield className="w-3 h-3 text-[#ecd58a]" />
            <span>الإدارة</span>
          </Link>

          <button
            onClick={() => fetchData()}
            disabled={loading}
            className="p-1 rounded-lg border border-[#E4E7EC] bg-white text-[#1B1F24]"
            title="تحديث"
          >
            <RefreshCw className={`w-3.5 h-3.5 text-[#667085] ${loading ? 'animate-spin text-[#14372e]' : ''}`} />
          </button>
        </div>
      </header>

      {/* 2. شريط التنقل للأقسام والفئات (Desktop: 42px سطر واحد، Mobile: صفان متناسقان) */}
      {/* نسخة سطح المكتب (Desktop Single-line Navigator) */}
      <div className="hidden md:flex h-[42px] bg-white border-b border-[#E4E7EC] px-4 items-center justify-between gap-3 shrink-0 overflow-x-auto text-xs z-10">
        <div className="flex items-center gap-2 shrink-0">
          <span className="text-[#667085] font-bold flex items-center gap-1 text-xs">
            <Layers className="w-3.5 h-3.5 text-[#c59b27]" />
            <span>القسم:</span>
          </span>
          <select
            value={activeFile}
            onChange={(e) => {
              setActiveFile(e.target.value);
              setActiveTable('');
              setPage(1);
            }}
            className="bg-[#F7F8FA] border border-[#D0D5DD] rounded-lg px-2.5 py-1 text-xs font-bold text-[#14372e] outline-none hover:border-[#14372e] focus:border-[#14372e] transition cursor-pointer max-w-[260px] truncate"
          >
            <option value="all">🌐 الدمج الشامل (كافة الملفات - 88,987 قيد)</option>
            {(data?.files || []).map((f) => (
              <option key={f.name} value={f.name}>
                📁 {f.name} ({f.total_rows.toLocaleString('ar-IQ')} قيد)
              </option>
            ))}
          </select>
        </div>

        <div className="flex items-center gap-1.5 overflow-x-auto py-1 scrollbar-thin scrollbar-thumb-emerald-800/20">
          {renderCategoryButtons()}
        </div>
      </div>

      {/* نسخة الجوال (Mobile Navigator: قائمة منسدلة بعرض كامل + شريط فئات أفقي حر) */}
      <div className="md:hidden bg-white border-b border-[#E4E7EC] px-3 py-1.5 shrink-0 space-y-1.5 z-10 shadow-2xs">
        <div className="relative">
          <select
            value={activeFile}
            onChange={(e) => {
              setActiveFile(e.target.value);
              setActiveTable('');
              setPage(1);
            }}
            className="w-full bg-[#F7F8FA] border border-[#D0D5DD] rounded-xl px-3 py-1.5 text-xs font-bold text-[#14372e] outline-none appearance-none pr-8 pl-3"
          >
            <option value="all">🌐 الدمج الشامل (كافة الملفات - 88,987 قيد)</option>
            {(data?.files || []).map((f) => (
              <option key={f.name} value={f.name}>
                📁 {f.name} ({f.total_rows.toLocaleString('ar-IQ')} قيد)
              </option>
            ))}
          </select>
          <Layers className="w-3.5 h-3.5 text-[#c59b27] absolute right-2.5 top-1/2 -translate-y-1/2 pointer-events-none" />
        </div>

        {/* شريط الفئات الـ 11 بالكامل قابل للتمرير بسلاسة دون حجب أي فئة */}
        <div className="flex items-center gap-1.5 overflow-x-auto pb-0.5 no-scrollbar scroll-smooth">
          {renderCategoryButtons()}
        </div>
      </div>

      {/* 3. شريط البحث والعمليات (Desktop: 46px سطر واحد، Mobile: صفان متكاملان) */}
      {/* نسخة سطح المكتب (Desktop Toolbar) */}
      <div className="hidden md:flex h-[46px] bg-[#F7F8FA] border-b border-[#E4E7EC] px-4 items-center justify-between gap-3 shrink-0 text-xs">
        <div className="relative flex-1 max-w-md">
          <Search className="w-3.5 h-3.5 text-[#98A2B3] absolute right-3 top-1/2 -translate-y-1/2" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="بحث فوري بالاسم، النشاط، العنوان، الهاتف..."
            className="w-full pl-8 pr-9 py-1.5 text-xs bg-white border border-[#D0D5DD] rounded-lg text-[#1B1F24] placeholder-[#98A2B3] outline-none focus:border-[#14372e] focus:ring-1 focus:ring-[#14372e] transition"
          />
          {searchQuery && (
            <button
              onClick={() => setSearchQuery('')}
              className="absolute left-2.5 top-1/2 -translate-y-1/2 text-[#98A2B3] hover:text-[#1B1F24]"
            >
              <X className="w-3.5 h-3.5" />
            </button>
          )}
        </div>

        <div className="flex items-center gap-2 shrink-0">
          <span className="text-[11px] text-[#667085] hidden lg:inline">
            النتائج: <strong className="text-[#14372e] font-mono">{data?.total_matches?.toLocaleString('ar-IQ') || 0}</strong>
          </span>

          <div className="inline-flex rounded-lg border border-[#D0D5DD] bg-white p-0.5">
            <button
              onClick={() => { setSortDir('desc'); setPage(1); }}
              className={`px-2.5 py-1 text-[11px] font-bold rounded-md transition flex items-center gap-1 cursor-pointer ${
                sortDir === 'desc' ? 'bg-[#14372e] text-white shadow-2xs' : 'text-[#344054] hover:bg-[#F7F8FA]'
              }`}
              title="فرز تنازلي (من الأحدث إلى الأقدم)"
            >
              <ArrowDown className="w-3 h-3 text-[#ecd58a]" />
              <span>الأحدث</span>
            </button>
            <button
              onClick={() => { setSortDir('asc'); setPage(1); }}
              className={`px-2.5 py-1 text-[11px] font-bold rounded-md transition flex items-center gap-1 cursor-pointer ${
                sortDir === 'asc' ? 'bg-[#14372e] text-white shadow-2xs' : 'text-[#344054] hover:bg-[#F7F8FA]'
              }`}
              title="فرز تصاعدي (من الأقدم إلى الأحدث)"
            >
              <ArrowUp className="w-3 h-3 text-[#ecd58a]" />
              <span>الأقدم</span>
            </button>
            <button
              onClick={() => { setSortDir('none'); setPage(1); }}
              className={`px-2 py-1 text-[11px] font-semibold rounded-md transition cursor-pointer ${
                sortDir === 'none' ? 'bg-slate-200 text-slate-800 font-bold' : 'text-[#667085] hover:bg-[#F7F8FA]'
              }`}
              title="الترتيب الأصلي لملف Access"
            >
              الأصلي
            </button>
          </div>

          {/* تبديل طريقة العرض */}
          <div className="inline-flex rounded-lg border border-[#D0D5DD] bg-white p-0.5">
            <button
              onClick={() => setViewMode('table')}
              className={`p-1.5 rounded-md transition cursor-pointer ${
                viewMode === 'table' ? 'bg-[#14372e] text-white shadow-2xs' : 'text-[#667085] hover:bg-[#F7F8FA]'
              }`}
              title="عرض كجدول بيانات"
            >
              <TableProperties className="w-3.5 h-3.5" />
            </button>
            <button
              onClick={() => setViewMode('cards')}
              className={`p-1.5 rounded-md transition cursor-pointer ${
                viewMode === 'cards' ? 'bg-[#14372e] text-white shadow-2xs' : 'text-[#667085] hover:bg-[#F7F8FA]'
              }`}
              title="عرض كبطاقات تفاعلية"
            >
              <LayoutGrid className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>

        <div className="flex items-center gap-2 shrink-0">
          <button
            onClick={() => { setFormData({}); setIsAddModalOpen(true); }}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-[#14372e] hover:bg-[#1a473b] text-white rounded-lg text-xs font-bold transition shadow-2xs cursor-pointer"
          >
            <Plus className="w-3.5 h-3.5 text-[#ecd58a]" />
            <span>إضافة قيد</span>
          </button>

          <button
            onClick={handleExportCSV}
            className="flex items-center gap-1.5 px-2.5 py-1.5 bg-white hover:bg-[#F7F8FA] border border-[#D0D5DD] text-[#344054] rounded-lg text-xs font-semibold transition cursor-pointer"
            title="تصدير السجلات إلى ملف Excel / CSV"
          >
            <Download className="w-3.5 h-3.5 text-[#14372e]" />
            <span>Excel</span>
          </button>

          <button
            onClick={() => setIsManageColsModalOpen(true)}
            className="p-1.5 bg-white hover:bg-[#F7F8FA] border border-[#D0D5DD] text-[#344054] rounded-lg transition cursor-pointer"
            title="إدارة وحذف الحقول"
          >
            <Columns className="w-3.5 h-3.5 text-[#14372e]" />
          </button>
        </div>
      </div>

      {/* نسخة الجوال (Mobile Toolbar: صفان منظميان وعمليان) */}
      <div className="md:hidden bg-[#F7F8FA] border-b border-[#E4E7EC] px-3 py-1.5 shrink-0 space-y-1.5 text-xs">
        {/* صف البحث بعرض الشاشة */}
        <div className="relative w-full">
          <Search className="w-3.5 h-3.5 text-[#98A2B3] absolute right-3 top-1/2 -translate-y-1/2" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="بحث فوري بالاسم، النشاط، العنوان، الهاتف..."
            className="w-full pl-8 pr-9 py-1.5 text-xs bg-white border border-[#D0D5DD] rounded-xl text-[#1B1F24] placeholder-[#98A2B3] outline-none shadow-2xs"
          />
          {searchQuery && (
            <button
              onClick={() => setSearchQuery('')}
              className="absolute left-2.5 top-1/2 -translate-y-1/2 text-[#98A2B3] hover:text-[#1B1F24]"
            >
              <X className="w-3.5 h-3.5" />
            </button>
          )}
        </div>

        {/* صف فرز التاريخ + وضع العرض + أزرار الإجراءات */}
        <div className="flex items-center justify-between gap-1 overflow-x-auto">
          {/* فرز التواريخ */}
          <div className="inline-flex rounded-lg border border-[#D0D5DD] bg-white p-0.5 shrink-0">
            <button
              onClick={() => { setSortDir('desc'); setPage(1); }}
              className={`px-2 py-0.5 text-[10.5px] font-bold rounded-md transition ${
                sortDir === 'desc' ? 'bg-[#14372e] text-white' : 'text-[#344054]'
              }`}
            >
              الأحدث
            </button>
            <button
              onClick={() => { setSortDir('asc'); setPage(1); }}
              className={`px-2 py-0.5 text-[10.5px] font-bold rounded-md transition ${
                sortDir === 'asc' ? 'bg-[#14372e] text-white' : 'text-[#344054]'
              }`}
            >
              الأقدم
            </button>
            <button
              onClick={() => { setSortDir('none'); setPage(1); }}
              className={`px-1.5 py-0.5 text-[10.5px] font-semibold rounded-md transition ${
                sortDir === 'none' ? 'bg-slate-200 text-slate-800 font-bold' : 'text-[#667085]'
              }`}
            >
              الأصلي
            </button>
          </div>

          {/* تبديل بطاقات / جدول */}
          <div className="inline-flex rounded-lg border border-[#D0D5DD] bg-white p-0.5 shrink-0">
            <button
              onClick={() => setViewMode('cards')}
              className={`flex items-center gap-1 px-2 py-0.5 text-[10.5px] font-bold rounded-md transition ${
                viewMode === 'cards' ? 'bg-[#14372e] text-white' : 'text-[#667085]'
              }`}
            >
              <LayoutGrid className="w-3 h-3" />
              <span>بطاقات</span>
            </button>
            <button
              onClick={() => setViewMode('table')}
              className={`flex items-center gap-1 px-2 py-0.5 text-[10.5px] font-bold rounded-md transition ${
                viewMode === 'table' ? 'bg-[#14372e] text-white' : 'text-[#667085]'
              }`}
            >
              <TableProperties className="w-3 h-3" />
              <span>جدول</span>
            </button>
          </div>

          {/* زر إضافة قيد وتصدير وإدارة */}
          <div className="flex items-center gap-1 shrink-0">
            <button
              onClick={() => { setFormData({}); setIsAddModalOpen(true); }}
              className="flex items-center gap-1 px-2.5 py-1 bg-[#14372e] text-white rounded-lg text-[11px] font-bold shadow-2xs shrink-0"
            >
              <Plus className="w-3.5 h-3.5 text-[#ecd58a]" />
              <span>قيد جديد</span>
            </button>
            <button
              onClick={handleExportCSV}
              className="p-1 bg-white border border-[#D0D5DD] text-[#344054] rounded-lg"
              title="تصدير Excel"
            >
              <Download className="w-3.5 h-3.5 text-[#14372e]" />
            </button>
            <button
              onClick={() => setIsManageColsModalOpen(true)}
              className="p-1 bg-white border border-[#D0D5DD] text-[#344054] rounded-lg"
              title="إدارة الحقول"
            >
              <Columns className="w-3.5 h-3.5 text-[#14372e]" />
            </button>
          </div>
        </div>
      </div>

      {/* 4. منطقة عرض البيانات: البطاقات الذكية (Cards) أو الجدول المركزي (Table) */}
      <div className="flex-1 overflow-auto min-h-0 bg-[#F7F8FA] relative pb-28 md:pb-4">
        {loading ? (
          <div className="h-full flex flex-col items-center justify-center text-center gap-3 p-12">
            <RefreshCw className="w-8 h-8 text-[#14372e] animate-spin" />
            <p className="text-sm font-bold text-[#1B1F24]">جاري جلب السجلات السحابية...</p>
            <p className="text-xs text-[#667085]">مزامنة فورية لكافة القيود وعرضها بأعلى وضوح</p>
          </div>
        ) : error ? (
          <div className="h-full flex flex-col items-center justify-center p-8 text-center text-red-600 space-y-2">
            <AlertCircle className="w-8 h-8 mx-auto text-red-500" />
            <p className="font-bold text-sm">{error}</p>
          </div>
        ) : !data?.rows || data.rows.length === 0 ? (
          <div className="h-full flex flex-col items-center justify-center p-12 text-center text-[#667085] gap-2">
            <AlertCircle className="w-8 h-8 text-[#98A2B3]" />
            <p className="text-sm font-bold">لا توجد سجلات مطابقة للبحث أو الجدول فارغ</p>
            <p className="text-xs text-[#98A2B3]">يمكنك كتابة كلمة بحث أخرى أو إضافة قيد جديد بالضغط على "إضافة قيد"</p>
          </div>
        ) : viewMode === 'cards' ? (
          /* عرض البطاقات الذكية العملي للجوال والشاشات المختلفة */
          <div className="p-3 md:p-4 grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
            {data.rows.map((row, idx) => {
              const rowNum = (page - 1) * limit + idx + 1;
              const { name, commercialName, activity, phone, address, dateVal, grade } = extractCardFields(row);
              const shortFile = getShortFileName(row._adh_file);

              return (
                <div
                  key={row._adh_id || idx}
                  className="bg-white rounded-2xl border border-[#E4E7EC] shadow-2xs hover:shadow-md transition flex flex-col justify-between overflow-hidden"
                >
                  {/* رأس البطاقة */}
                  <div className="p-3.5 space-y-2.5">
                    <div className="flex items-center justify-between gap-2">
                      <div className="flex items-center gap-1.5 flex-wrap">
                        <span className="font-mono text-[11px] font-bold text-[#667085] bg-[#F2F4F7] px-2 py-0.5 rounded-md">
                          #{rowNum}
                        </span>
                        {shortFile && (
                          <span className="text-[10.5px] font-semibold text-[#14372e] bg-[#EDF5F2] px-2 py-0.5 rounded-md border border-[#14372e]/10 truncate max-w-[150px]">
                            {shortFile}
                          </span>
                        )}
                        {grade && (
                          <span className="text-[10px] font-bold text-amber-900 bg-amber-50 px-2 py-0.5 rounded-md border border-amber-300">
                            ⭐ {grade}
                          </span>
                        )}
                      </div>

                      {dateVal && (
                        <span className="text-[10.5px] text-[#667085] font-mono flex items-center gap-1 shrink-0">
                          <Calendar className="w-3 h-3 text-[#98A2B3]" />
                          <span>{String(dateVal)}</span>
                        </span>
                      )}
                    </div>

                    {/* الاسم والنشاط */}
                    <div className="space-y-1">
                      <h3
                        onClick={() => setViewingRecord(row)}
                        className="text-sm font-bold text-[#14372e] cursor-pointer hover:underline line-clamp-1"
                        title={name}
                      >
                        {name}
                      </h3>

                      {commercialName && (
                        <div className="flex items-center gap-1.5 text-xs text-[#344054] font-medium">
                          <Building2 className="w-3.5 h-3.5 text-[#c59b27] shrink-0" />
                          <span className="truncate">{commercialName}</span>
                        </div>
                      )}

                      {activity && (
                        <div className="flex items-center gap-1.5 text-[11.5px] text-[#475467]">
                          <Briefcase className="w-3.5 h-3.5 text-[#14372e]/60 shrink-0" />
                          <span className="truncate">{activity}</span>
                        </div>
                      )}

                      {address && (
                        <div className="flex items-center gap-1.5 text-[11.5px] text-[#667085]">
                          <MapPin className="w-3.5 h-3.5 text-[#98A2B3] shrink-0" />
                          <span className="truncate">{address}</span>
                        </div>
                      )}
                    </div>
                  </div>

                  {/* أسفل البطاقة: الاتصال السريع والإجراءات */}
                  <div className="px-3.5 py-2.5 bg-[#FAFBFB] border-t border-[#F2F4F7] flex items-center justify-between gap-2">
                    <div>
                      {phone ? (
                        <a
                          href={`tel:${phone}`}
                          className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg bg-emerald-50 hover:bg-emerald-100 text-emerald-800 text-[11px] font-bold border border-emerald-200 transition"
                          title="اتصال فوري"
                        >
                          <Phone className="w-3 h-3 text-emerald-600" />
                          <span className="font-mono">{phone}</span>
                        </a>
                      ) : (
                        <span className="text-[11px] text-[#98A2B3] font-mono">بدون هاتف</span>
                      )}
                    </div>

                    <div className="flex items-center gap-1">
                      <button
                        onClick={() => setViewingRecord(row)}
                        className="p-1.5 rounded-lg bg-white border border-[#E4E7EC] hover:bg-[#F2F4F7] text-[#14372e] transition"
                        title="عرض كامل تفاصيل القيد"
                      >
                        <Eye className="w-3.5 h-3.5" />
                      </button>

                      <button
                        onClick={() => handleCopyRecord(row)}
                        className="p-1.5 rounded-lg bg-white border border-[#E4E7EC] hover:bg-[#F2F4F7] text-[#344054] transition"
                        title="نسخ بيانات القيد"
                      >
                        <Copy className="w-3.5 h-3.5" />
                      </button>

                      <button
                        onClick={() => {
                          setSelectedRecord(row);
                          setFormData({ ...row });
                          setIsEditModalOpen(true);
                        }}
                        className="p-1.5 rounded-lg bg-white border border-[#E4E7EC] hover:bg-emerald-50 text-[#14372e] transition"
                        title="تعديل هذا القيد"
                      >
                        <Edit2 className="w-3.5 h-3.5" />
                      </button>

                      {deleteConfirmId === row._adh_id ? (
                        <div className="flex items-center gap-1">
                          <button
                            onClick={() => handleDelete(row)}
                            className="px-2 py-1 bg-red-600 text-white rounded text-[10px] font-bold cursor-pointer"
                          >
                            تأكيد
                          </button>
                          <button
                            onClick={() => setDeleteConfirmId(null)}
                            className="px-1.5 py-1 text-[#667085] text-[10px] cursor-pointer"
                          >
                            إلغاء
                          </button>
                        </div>
                      ) : (
                        <button
                          onClick={() => setDeleteConfirmId(row._adh_id)}
                          className="p-1.5 rounded-lg bg-white border border-[#E4E7EC] hover:bg-red-50 text-red-500 transition"
                          title="حذف هذا القيد"
                        >
                          <Trash2 className="w-3.5 h-3.5" />
                        </button>
                      )}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        ) : (
          /* عرض الجدول المركزي عالي الدقة */
          <div className="w-full overflow-x-auto">
            <table className="w-full text-right text-xs border-collapse">
              <thead className="sticky top-0 z-10 bg-[#EDF2EF] border-b-2 border-[#D0D5DD] text-[#14372e] font-bold text-xs shadow-xs">
                <tr>
                  <th className="py-2.5 px-3 w-12 text-center border-l border-[#D0D5DD]/40 bg-[#EDF2EF]">#</th>
                  {activeFile === 'all' && (
                    <th className="py-2.5 px-3.5 whitespace-nowrap border-l border-[#D0D5DD]/40 bg-[#EDF2EF]">القسم</th>
                  )}
                  {data.columns.map((col) => {
                    const isSorted = sortCol === col || (sortCol === 'date_auto' && data.date_columns?.[0] === col);
                    return (
                      <th
                        key={col}
                        className="py-2.5 px-3.5 whitespace-nowrap border-l border-[#D0D5DD]/40 bg-[#EDF2EF] select-none group"
                      >
                        <div className="flex items-center justify-between gap-2">
                          <button
                            onClick={() => handleColumnHeaderClick(col)}
                            className="flex items-center gap-1 hover:text-[#c59b27] transition cursor-pointer font-bold"
                            title="اضغط للفرز حسب هذا العمود"
                          >
                            <span>{col}</span>
                            {isSorted && sortDir === 'desc' && (
                              <ArrowDown className="w-3 h-3 text-[#14372e]" />
                            )}
                            {isSorted && sortDir === 'asc' && (
                              <ArrowUp className="w-3 h-3 text-[#14372e]" />
                            )}
                            {!isSorted && (
                              <ArrowUpDown className="w-2.5 h-2.5 text-[#98A2B3] opacity-0 group-hover:opacity-100 transition" />
                            )}
                          </button>

                          <button
                            onClick={() => setDeleteColConfirm(col)}
                            className="text-[#98A2B3] hover:text-red-600 p-0.5 rounded transition opacity-0 group-hover:opacity-100 cursor-pointer"
                            title={`حذف حقل "${col}"`}
                          >
                            <X className="w-3 h-3" />
                          </button>
                        </div>
                      </th>
                    );
                  })}
                  <th className="py-2.5 px-3 text-center w-24 whitespace-nowrap bg-[#EDF2EF]">الإجراءات</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[#E4E7EC]">
                {data.rows.map((row, idx) => {
                  const rowNum = (page - 1) * limit + idx + 1;
                  return (
                    <tr
                      key={row._adh_id || idx}
                      onClick={(e) => {
                        // فتح التفاصيل عند النقر ما لم يكن الهدف زراً
                        if ((e.target as HTMLElement).closest('button, a')) return;
                        setViewingRecord(row);
                      }}
                      className="hover:bg-amber-50/50 even:bg-[#FAFAFA] odd:bg-white transition-colors group cursor-pointer"
                    >
                      <td className="py-2.5 px-3 text-center text-[#98A2B3] font-mono text-[11px] border-l border-[#E4E7EC]/60">{rowNum}</td>

                      {activeFile === 'all' && (
                        <td className="py-2.5 px-3.5 whitespace-nowrap border-l border-[#E4E7EC]/60">
                          <span className="inline-flex items-center gap-1 bg-[#14372e]/5 text-[#14372e] font-semibold px-2 py-0.5 rounded text-[11px] border border-[#14372e]/10">
                            {getShortFileName(row._adh_file)}
                          </span>
                        </td>
                      )}

                      {data.columns.map((col) => (
                        <td key={col} className="py-2.5 px-3.5 whitespace-nowrap max-w-xs truncate border-l border-[#E4E7EC]/40">
                          {renderCellContent(col, row[col])}
                        </td>
                      ))}

                      <td className="py-2 px-3 text-center whitespace-nowrap">
                        <div className="flex items-center justify-center gap-1">
                          <button
                            onClick={() => setViewingRecord(row)}
                            className="p-1 rounded hover:bg-slate-100 text-[#667085] transition cursor-pointer"
                            title="تفاصيل القيد"
                          >
                            <Eye className="w-3.5 h-3.5" />
                          </button>

                          <button
                            onClick={() => {
                              setSelectedRecord(row);
                              setFormData({ ...row });
                              setIsEditModalOpen(true);
                            }}
                            className="p-1 rounded hover:bg-emerald-100 text-[#14372e] transition cursor-pointer"
                            title="تعديل هذا القيد"
                          >
                            <Edit2 className="w-3.5 h-3.5" />
                          </button>

                          {deleteConfirmId === row._adh_id ? (
                            <div className="flex items-center gap-1">
                              <button
                                onClick={() => handleDelete(row)}
                                className="px-1.5 py-0.5 bg-red-600 text-white rounded text-[10px] font-bold cursor-pointer"
                              >
                                تأكيد
                              </button>
                              <button
                                onClick={() => setDeleteConfirmId(null)}
                                className="px-1 py-0.5 text-[#667085] text-[10px] cursor-pointer"
                              >
                                إلغاء
                              </button>
                            </div>
                          ) : (
                            <button
                              onClick={() => setDeleteConfirmId(row._adh_id)}
                              className="p-1 rounded hover:bg-red-100 text-red-500 transition cursor-pointer"
                              title="حذف هذا القيد"
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
        )}
      </div>

      {/* 5. شريط التصفح السفلي الرشيق والمدمج (Ultra-compact Pagination - 36px) مثبت فوق شريط الجوال مباشرة */}
      <footer className="h-[36px] md:h-[38px] fixed bottom-[56px] left-0 right-0 z-30 md:relative md:bottom-auto md:z-20 bg-white border-t border-[#E4E7EC] px-2.5 sm:px-4 flex items-center justify-between text-[#667085] shadow-xs select-none">
        {/* عداد السجلات بصيغة رشيقة ومختصرة */}
        <div className="flex items-center gap-1 font-mono text-[10.5px] sm:text-xs shrink-0">
          <span className="hidden sm:inline">عرض:</span>
          <strong className="text-[#14372e]">
            {data?.rows && data.rows.length > 0 ? ((page - 1) * limit + 1).toLocaleString('ar-IQ') : 0}
            -
            {data?.rows ? Math.min(page * limit, data.total_matches).toLocaleString('ar-IQ') : 0}
          </strong>
          <span className="text-[#98A2B3]">من</span>
          <strong className="text-[#14372e]">{data?.total_matches?.toLocaleString('ar-IQ') || 0}</strong>
        </div>

        {/* أزرار التنقل الرشيقة واختيار عدد السجلات في سطر واحد دون أي فراغ سفلي */}
        <div className="flex items-center gap-1 sm:gap-2 shrink-0">
          <select
            value={limit}
            onChange={(e) => { setLimit(Number(e.target.value)); setPage(1); }}
            className="bg-[#F7F8FA] border border-[#D0D5DD] rounded-md px-1.5 py-0.5 text-[10px] sm:text-xs font-bold text-[#14372e] outline-none cursor-pointer"
            title="عدد السجلات لكل صفحة"
          >
            <option value={25}>25</option>
            <option value={50}>50</option>
            <option value={100}>100</option>
            <option value={200}>200</option>
          </select>

          <div className="flex items-center gap-0.5 sm:gap-1">
            <button
              disabled={page <= 1}
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              className="px-2 py-0.5 rounded-md border border-[#E4E7EC] bg-white hover:bg-[#F7F8FA] disabled:opacity-30 disabled:cursor-not-allowed font-semibold text-[10.5px] sm:text-xs text-[#1B1F24] transition flex items-center gap-0.5 cursor-pointer shadow-2xs"
            >
              <ChevronRight className="w-3 h-3" />
              <span>السابق</span>
            </button>

            <span className="px-1.5 font-mono font-bold text-[10.5px] sm:text-xs text-[#14372e]">
              {page} / {data?.total_pages || 1}
            </span>

            <button
              disabled={page >= (data?.total_pages || 1)}
              onClick={() => setPage((p) => p + 1)}
              className="px-2 py-0.5 rounded-md border border-[#E4E7EC] bg-white hover:bg-[#F7F8FA] disabled:opacity-30 disabled:cursor-not-allowed font-semibold text-[10.5px] sm:text-xs text-[#1B1F24] transition flex items-center gap-0.5 cursor-pointer shadow-2xs"
            >
              <span>التالي</span>
              <ChevronLeft className="w-3 h-3" />
            </button>
          </div>
        </div>
      </footer>

      {/* 6. نافذة إضافة قيد جديد (Add Record Modal) */}
      {isAddModalOpen && (
        <div className="fixed inset-0 z-50 bg-black/40 backdrop-blur-xs flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl w-full max-w-2xl max-h-[85vh] flex flex-col shadow-2xl border border-[#E4E7EC]">
            <div className="p-4 border-b border-[#E4E7EC] flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Plus className="w-5 h-5 text-[#14372e]" />
                <h3 className="font-bold text-sm text-[#1B1F24]">
                  إضافة قيد جديد إلى جدول ({activeTable || 'البيانات'})
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

      {/* 7. نافذة تعديل قيد (Edit Record Modal) */}
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

      {/* 8. نافذة إضافة حقل جديد (Add Column Modal) */}
      {isAddColModalOpen && (
        <div className="fixed inset-0 z-50 bg-black/40 backdrop-blur-xs flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl w-full max-w-md flex flex-col shadow-2xl border border-[#E4E7EC]">
            <div className="p-4 border-b border-[#E4E7EC] flex items-center justify-between">
              <div className="flex items-center gap-2">
                <PlusCircle className="w-5 h-5 text-emerald-700" />
                <h3 className="font-bold text-sm text-[#1B1F24]">
                  إضافة حقل جديد لجدول ({activeTable || 'الجدول الحالي'})
                </h3>
              </div>
              <button onClick={() => setIsAddColModalOpen(false)} className="text-[#667085] hover:text-[#1B1F24]">
                <X className="w-5 h-5" />
              </button>
            </div>

            <form onSubmit={handleAddColumn} className="p-5 space-y-4">
              <p className="text-xs text-[#667085]">
                سيتم إنشاء الحقل الجديد سحابياً وإضافته لهذا الجدول، وسيظهر فوراً في نماذج الإضافة والتعديل لكافة الموظفين.
              </p>

              <div className="space-y-1.5">
                <label className="text-xs font-bold text-[#344054]">اسم الحقل / العمود الجديد:</label>
                <input
                  type="text"
                  required
                  autoFocus
                  value={newColName}
                  onChange={(e) => setNewColName(e.target.value)}
                  placeholder="مثال: رقم الهاتف، ملاحظات، تاريخ التجديد..."
                  className="w-full px-3.5 py-2.5 text-xs bg-[#F7F8FA] border border-[#E4E7EC] rounded-lg text-[#1B1F24] focus:outline-none focus:border-[#14372e]"
                />
              </div>

              <div className="pt-3 border-t border-[#E4E7EC] flex justify-end gap-2">
                <button
                  type="button"
                  onClick={() => setIsAddColModalOpen(false)}
                  className="px-4 py-2 text-xs font-semibold text-[#475467] bg-[#F7F8FA] rounded-lg border border-[#E4E7EC]"
                >
                  إلغاء
                </button>
                <button
                  type="submit"
                  disabled={isSubmitting || !newColName.trim()}
                  className="px-5 py-2 text-xs font-bold text-white bg-emerald-700 hover:bg-emerald-800 rounded-lg transition disabled:opacity-50"
                >
                  {isSubmitting ? 'جاري الإضافة...' : 'إضافة الحقل وتعميمه سحابياً'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* 9. نافذة إدارة وحذف الحقول (Manage & Delete Columns Modal) */}
      {isManageColsModalOpen && (
        <div className="fixed inset-0 z-50 bg-black/40 backdrop-blur-xs flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl w-full max-w-lg max-h-[80vh] flex flex-col shadow-2xl border border-[#E4E7EC]">
            <div className="p-4 border-b border-[#E4E7EC] flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Columns className="w-5 h-5 text-[#14372e]" />
                <h3 className="font-bold text-sm text-[#1B1F24]">
                  إدارة حقول جدول ({activeTable || 'الجدول الحالي'})
                </h3>
              </div>
              <button onClick={() => setIsManageColsModalOpen(false)} className="text-[#667085] hover:text-[#1B1F24]">
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="p-4 overflow-y-auto flex-1 space-y-2">
              <p className="text-xs text-[#667085] mb-3">
                يمكنك حذف أو إخفاء أي حقل غير مرغوب فيه من هذا الجدول، وسيتم تعميم الحذف سحابياً:
              </p>

              <div className="divide-y divide-[#E4E7EC] border border-[#E4E7EC] rounded-xl overflow-hidden">
                {data?.columns.map((col, idx) => (
                  <div key={col} className="p-3 flex items-center justify-between bg-white hover:bg-[#F9FAFB] transition">
                    <div className="flex items-center gap-2.5">
                      <span className="text-xs font-mono text-[#98A2B3] w-6">{idx + 1}</span>
                      <span className="text-xs font-semibold text-[#1B1F24]">{col}</span>
                    </div>

                    <button
                      onClick={() => setDeleteColConfirm(col)}
                      className="text-xs text-red-600 hover:text-red-700 bg-red-50 hover:bg-red-100 px-2.5 py-1 rounded-md transition flex items-center gap-1 font-semibold"
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                      <span>حذف الحقل</span>
                    </button>
                  </div>
                ))}
              </div>
            </div>

            <div className="p-4 border-t border-[#E4E7EC] flex justify-between items-center bg-[#F7F8FA]">
              <button
                onClick={() => {
                  setIsManageColsModalOpen(false);
                  setIsAddColModalOpen(true);
                }}
                className="text-xs text-emerald-800 font-bold hover:underline flex items-center gap-1"
              >
                <PlusCircle className="w-3.5 h-3.5 text-emerald-700" />
                <span>+ إضافة حقل جديد لهذا الجدول</span>
              </button>

              <button
                onClick={() => setIsManageColsModalOpen(false)}
                className="px-4 py-2 text-xs font-semibold text-[#344054] bg-white border border-[#E4E7EC] rounded-lg"
              >
                إغلاق
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 10. تأكيد حذف حقل (Delete Column Confirmation Dialog) */}
      {deleteColConfirm && (
        <div className="fixed inset-0 z-60 bg-black/50 backdrop-blur-xs flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl w-full max-w-sm p-5 shadow-2xl border border-red-200 text-right space-y-4 animate-in fade-in zoom-in-95">
            <div className="w-10 h-10 rounded-full bg-red-100 text-red-600 flex items-center justify-center mx-auto">
              <Trash2 className="w-5 h-5" />
            </div>

            <div className="text-center space-y-1">
              <h4 className="font-bold text-sm text-[#1B1F24]">تأكيد حذف الحقل</h4>
              <p className="text-xs text-[#667085]">
                هل أنت متأكد من حذف الحقل{' '}
                <strong className="text-red-600 font-bold">"{deleteColConfirm}"</strong>؟
              </p>
              <p className="text-[11px] text-[#98A2B3]">
                سيتم إخفاء هذا الحقل من الجدول السحابي ولن يظهر لجميع الموظفين.
              </p>
            </div>

            <div className="flex items-center gap-2 pt-2">
              <button
                type="button"
                onClick={() => setDeleteColConfirm(null)}
                className="flex-1 py-2 text-xs font-semibold text-[#475467] bg-[#F7F8FA] rounded-lg border border-[#E4E7EC]"
              >
                إلغاء
              </button>
              <button
                type="button"
                disabled={isSubmitting}
                onClick={() => handleDeleteColumn(deleteColConfirm)}
                className="flex-1 py-2 text-xs font-bold text-white bg-red-600 hover:bg-red-700 rounded-lg transition"
              >
                {isSubmitting ? 'جاري الحذف...' : 'نعم، احذف الحقل'}
              </button>
            </div>
          </div>
        </div>
      )}
      {/* 11. نافذة عرض تفاصيل القيد الكاملة (Mobile Bottom Sheet / Details Modal) */}
      {viewingRecord && (
        <div className="fixed inset-0 z-50 bg-black/50 backdrop-blur-xs flex items-end sm:items-center justify-center p-0 sm:p-4">
          <div className="bg-white rounded-t-2xl sm:rounded-2xl w-full max-w-2xl max-h-[90vh] sm:max-h-[85vh] flex flex-col shadow-2xl border border-[#E4E7EC] animate-in slide-in-from-bottom duration-200">
            {/* مقبض السحب للشاشات الصغيرة */}
            <div className="sm:hidden w-12 h-1 bg-[#D0D5DD] rounded-full mx-auto my-2 shrink-0" />

            {/* رأس النافذة */}
            <div className="px-4 py-3 border-b border-[#E4E7EC] flex items-center justify-between shrink-0">
              <div className="flex items-center gap-2 min-w-0">
                <div className="w-8 h-8 rounded-lg bg-[#14372e] flex items-center justify-center text-[#ecd58a] shrink-0">
                  <Eye className="w-4 h-4" />
                </div>
                <div className="min-w-0">
                  <h3 className="font-bold text-sm text-[#1B1F24] truncate">
                    {extractCardFields(viewingRecord).name}
                  </h3>
                  <div className="flex items-center gap-2 text-[11px] text-[#667085] flex-wrap">
                    <span>الملف: {viewingRecord._adh_file}</span>
                    <span>•</span>
                    <span>الجدول: {viewingRecord._adh_table || activeTable || 'الرئيسي'}</span>
                  </div>
                </div>
              </div>

              <button
                onClick={() => setViewingRecord(null)}
                className="p-1 rounded-lg text-[#667085] hover:text-[#1B1F24] hover:bg-[#F2F4F7] transition"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* شريط الإجراءات السريعة */}
            <div className="px-4 py-2 bg-[#F7F8FA] border-b border-[#E4E7EC] flex items-center justify-between gap-2 shrink-0 flex-wrap">
              <div className="flex items-center gap-2">
                {extractCardFields(viewingRecord).phone && (
                  <a
                    href={`tel:${extractCardFields(viewingRecord).phone}`}
                    className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-emerald-700 hover:bg-emerald-800 text-white text-xs font-bold transition shadow-2xs"
                  >
                    <Phone className="w-3.5 h-3.5" />
                    <span>اتصال فوري</span>
                  </a>
                )}

                <button
                  onClick={() => handleCopyRecord(viewingRecord)}
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-white border border-[#D0D5DD] hover:bg-[#F2F4F7] text-[#344054] text-xs font-semibold transition shadow-2xs"
                >
                  <Copy className="w-3.5 h-3.5" />
                  <span>نسخ البيانات</span>
                </button>
              </div>

              <div className="flex items-center gap-1.5">
                <button
                  onClick={() => {
                    const rec = viewingRecord;
                    setViewingRecord(null);
                    setSelectedRecord(rec);
                    setFormData({ ...rec });
                    setIsEditModalOpen(true);
                  }}
                  className="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-lg bg-[#14372e] hover:bg-[#1a473b] text-white text-xs font-bold transition shadow-2xs"
                >
                  <Edit2 className="w-3.5 h-3.5 text-[#ecd58a]" />
                  <span>تعديل</span>
                </button>

                <button
                  onClick={() => {
                    const rec = viewingRecord;
                    setViewingRecord(null);
                    setDeleteConfirmId(rec._adh_id);
                  }}
                  className="p-1.5 rounded-lg bg-white border border-[#E4E7EC] hover:bg-red-50 text-red-600 transition"
                  title="حذف هذا القيد"
                >
                  <Trash2 className="w-3.5 h-3.5" />
                </button>
              </div>
            </div>

            {/* محتوى بيانات القيد بالكامل دون استثناء */}
            <div className="p-4 overflow-y-auto flex-1 space-y-3">
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
                {Object.entries(viewingRecord)
                  .filter(([key]) => !key.startsWith('_adh_'))
                  .map(([key, val]) => {
                    const isFilled = val !== null && val !== undefined && String(val).trim() !== '';
                    const isNotesField = key.startsWith('Field') || key.includes('ملاحظ') || key.includes('Notes');

                    return (
                      <div
                        key={key}
                        className={`p-3 rounded-xl border text-right transition ${
                          isNotesField && isFilled
                            ? 'bg-amber-50/70 border-amber-200 col-span-1 sm:col-span-2'
                            : isFilled
                            ? 'bg-white border-[#E4E7EC]'
                            : 'bg-[#FAFBFB] border-[#F2F4F7] opacity-60'
                        }`}
                      >
                        <div className="flex items-center justify-between gap-1 text-[11px] font-bold text-[#667085] mb-1">
                          <span>{key}</span>
                          {isNotesField && isFilled && (
                            <span className="text-[10px] text-amber-800 bg-amber-100 px-1.5 py-0.2 rounded font-semibold">
                              ملاحظات هامة
                            </span>
                          )}
                        </div>

                        <div className="text-xs font-semibold text-[#1B1F24] break-words">
                          {renderCellContent(key, val)}
                        </div>
                      </div>
                    );
                  })}
              </div>
            </div>

            {/* زر الإغلاق السفلي */}
            <div className="p-3 border-t border-[#E4E7EC] bg-[#F7F8FA] flex justify-end shrink-0">
              <button
                onClick={() => setViewingRecord(null)}
                className="w-full sm:w-auto px-5 py-2 text-xs font-bold text-[#344054] bg-white border border-[#D0D5DD] rounded-xl hover:bg-[#F2F4F7] transition"
              >
                إغلاق التفاصيل
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
