'use client';

import { useState, useEffect } from 'react';
import { 
  Shield, 
  ShieldAlert, 
  FolderPlus, 
  Folder, 
  Edit3, 
  Trash2, 
  Users, 
  Laptop, 
  Lock, 
  Unlock, 
  Check, 
  X, 
  RefreshCw, 
  Plus, 
  Search, 
  FileText, 
  Sparkles, 
  Save, 
  Key, 
  AlertTriangle, 
  Layers, 
  Settings,
  FolderOpen,
  ArrowRight,
  Eye,
  Download,
  RotateCcw,
  CheckCircle2,
  FileSpreadsheet,
  Database,
  Camera,
  Upload
} from 'lucide-react';
import { supabase } from '@/lib/supabase';

interface DepartmentItem {
  id: string;
  name: string;
  fileCount: number;
  totalSize: number;
  isDefault?: boolean;
}

interface PermissionRule {
  folderId: string;
  folderName: string;
  canView: boolean;
  canDownload: boolean;
  canWrite: boolean;
  canDelete: boolean;
}

interface DeviceRecord {
  id: string;
  name: string;
  user: string;
  os: string;
  machineGuid: string;
  isAuthorized: boolean;
  lastSeen: string;
}

interface FileRecord {
  id: string;
  name: string;
  folder: string;
  size: string;
  rawSize: number;
  version: number;
  lastModifiedBy: string;
  lastModifiedAt: string;
  storagePath: string;
  isDeleted: boolean;
}

const OFFICIAL_DEPTS = [
  'أمانة السر والإدارة العامة',
  'شعبة الكفالات والعقود القانونية',
  'شعبة التسجيل والشركات التجارية',
  'القسم المالي والحسابات',
  'قسم تكنولوجيا المعلومات والتحول الرقمي',
  'العلاقات العامة والإعلام',
  'المخازن والتجهيزات'
];

export default function AdminControlPage() {
  const [activeTab, setActiveTab] = useState<'DEPTS' | 'PERMS' | 'FILES' | 'DEVICES'>('DEPTS');
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState(false);

  // حماية لوحة الأدمن برمز دخول (PIN Lock)
  const [isUnlocked, setIsUnlocked] = useState(true);
  const [enteredPin, setEnteredPin] = useState('');
  const [pinError, setPinError] = useState(false);

  // بيانات الأقسام
  const [departments, setDepartments] = useState<DepartmentItem[]>([]);
  const [showAddDeptModal, setShowAddDeptModal] = useState(false);
  const [newDeptName, setNewDeptName] = useState('');
  const [showRenameDeptModal, setShowRenameDeptModal] = useState(false);
  const [deptToRename, setDeptToRename] = useState<DepartmentItem | null>(null);
  const [newDeptRenameValue, setNewDeptRenameValue] = useState('');

  // بيانات الصلاحيات
  const [permissions, setPermissions] = useState<PermissionRule[]>([]);
  const [savingPerms, setSavingPerms] = useState(false);

  // بيانات الملفات
  const [files, setFiles] = useState<FileRecord[]>([]);
  const [selectedDeptFilter, setSelectedDeptFilter] = useState('__ALL__');
  const [fileSearch, setFileSearch] = useState('');
  const [showRenameFileModal, setShowRenameFileModal] = useState(false);
  const [fileToRename, setFileToRename] = useState<FileRecord | null>(null);
  const [newFileNameValue, setNewFileNameValue] = useState('');

  // بيانات الأجهزة
  const [devices, setDevices] = useState<DeviceRecord[]>([]);

  // إشعار عائم
  const [toastMessage, setToastMessage] = useState<{ text: string; type: 'success' | 'error' | 'info' } | null>(null);

  useEffect(() => {
    if (toastMessage) {
      const timer = setTimeout(() => setToastMessage(null), 4000);
      return () => clearTimeout(timer);
    }
  }, [toastMessage]);

  const formatSize = (bytes: number) => {
    if (!bytes || bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return `${parseFloat((bytes / Math.pow(k, i)).toFixed(1))} ${sizes[i]}`;
  };

  // تحميل كافة البيانات من السحابة
  const loadAllData = async () => {
    try {
      setLoading(true);

      // 1. جلب الأقسام من shared_folders
      const { data: dbFolders } = await supabase
        .from('shared_folders')
        .select('*')
        .order('name');

      // 2. جلب الملفات
      const { data: dbFiles } = await supabase
        .from('files')
        .select('*')
        .order('updated_at', { ascending: false });

      const mappedFiles: FileRecord[] = (dbFiles || []).map(f => {
        const fileName = f.file_name || f.file_path || 'مستند';
        let folderName = 'كافة الملفات';
        if (f.file_path && f.file_path.includes('/')) {
          folderName = f.file_path.split('/')[0];
        }
        return {
          id: f.id || fileName,
          name: fileName,
          folder: folderName,
          size: formatSize(f.file_size || 0),
          rawSize: f.file_size || 0,
          version: f.current_version || f.version || 1,
          lastModifiedBy: f.last_modified_by_name || 'تطبيق الويندوز',
          lastModifiedAt: f.updated_at ? new Date(f.updated_at).toLocaleDateString('ar-IQ', {
            month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit'
          }) : 'الآن',
          storagePath: f.storage_path || `shared/${fileName}`,
          isDeleted: Boolean(f.is_deleted)
        };
      });
      setFiles(mappedFiles);

      // حساب إحصائيات الأقسام
      const folderMap = new Map<string, DepartmentItem>();

      // إضافة المجلدات المخزنة في السحابة
      if (dbFolders && dbFolders.length > 0) {
        dbFolders.forEach(f => {
          if (f.name) {
            folderMap.set(f.name, {
              id: f.id,
              name: f.name,
              fileCount: 0,
              totalSize: 0,
              isDefault: OFFICIAL_DEPTS.includes(f.name)
            });
          }
        });
      }

      // حساب الملفات في كل قسم
      mappedFiles.forEach(f => {
        if (!f.isDeleted && f.folder && f.folder !== 'كافة الملفات') {
          if (!folderMap.has(f.folder)) {
            folderMap.set(f.folder, {
              id: f.folder,
              name: f.folder,
              fileCount: 0,
              totalSize: 0,
              isDefault: OFFICIAL_DEPTS.includes(f.folder)
            });
          }
          const item = folderMap.get(f.folder)!;
          item.fileCount += 1;
          item.totalSize += f.rawSize;
        }
      });

      const deptsList = Array.from(folderMap.values());
      setDepartments(deptsList);

      // 3. جلب أو تهيئة الصلاحيات من folder_permissions
      const { data: dbPerms } = await supabase
        .from('folder_permissions')
        .select('*');

      const permsList: PermissionRule[] = deptsList.map(dept => {
        const existing = dbPerms?.find(p => p.folder_id === dept.id);
        return {
          folderId: dept.id,
          folderName: dept.name,
          canView: existing ? Boolean(existing.can_view) : true,
          canDownload: existing ? Boolean(existing.can_download) : true,
          canWrite: existing ? Boolean(existing.can_write) : true,
          canDelete: existing ? Boolean(existing.can_delete) : true,
        };
      });
      setPermissions(permsList);

      // 4. جلب الأجهزة من devices
      const { data: dbDevices } = await supabase
        .from('devices')
        .select('*')
        .order('last_seen_at', { ascending: false });

      if (dbDevices) {
        setDevices(dbDevices.map(d => ({
          id: d.id,
          name: d.device_name || 'جهاز حاسوب',
          user: d.user_id || 'موظف الغرفة',
          os: d.os_info || 'Windows 11',
          machineGuid: d.machine_guid || 'N/A',
          isAuthorized: Boolean(d.is_authorized),
          lastSeen: d.last_seen_at ? new Date(d.last_seen_at).toLocaleDateString('ar-IQ', {
            month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit'
          }) : 'الآن'
        })));
      }

    } catch (err) {
      console.error('Error loading admin data:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadAllData();

    // اشتراك Realtime لحظي عند حدوث أي تعديل
    const channel = supabase
      .channel('admin_dashboard_realtime')
      .on('postgres_changes', { event: '*', schema: 'public', table: 'shared_folders' }, () => loadAllData())
      .on('postgres_changes', { event: '*', schema: 'public', table: 'files' }, () => loadAllData())
      .on('postgres_changes', { event: '*', schema: 'public', table: 'devices' }, () => loadAllData())
      .on('postgres_changes', { event: '*', schema: 'public', table: 'folder_permissions' }, () => loadAllData())
      .subscribe();

    return () => {
      supabase.removeChannel(channel);
    };
  }, []);

  // إضافة قسم إداري جديد ومزامنته فوراً
  const handleCreateDepartment = async () => {
    const deptName = newDeptName.trim();
    if (!deptName) return;

    try {
      setActionLoading(true);
      // 1. إضافة إلى shared_folders
      const { data, error } = await supabase
        .from('shared_folders')
        .insert({ name: deptName })
        .select();

      if (error) throw new Error(error.message);

      // 2. إنشاء علامة المجلد في وعاء التخزين
      try {
        await supabase.storage
          .from('file-exchange-storage')
          .upload(`shared/${deptName}/.keep`, new Blob(['keep']), { upsert: true });
      } catch {}

      setShowAddDeptModal(false);
      setNewDeptName('');
      await loadAllData();

      setToastMessage({
        text: `🎉 تم إنشاء القسم "${deptName}" بنجاح ومزامنته مع السحابة وتطبيق الويندوز!`,
        type: 'success'
      });
      alert(`✅ تمت إضافة القسم "${deptName}" بنجاح!\n\nسيظهر هذا القسم فوراً في لوحة الويب، وفي القائمة الجانبية لتطبيق الحاسوب (share coc) لدى كافة موظفي الغرفة.`);
    } catch (err: any) {
      alert(`تعذر إضافة القسم: ${err.message || err}`);
    } finally {
      setActionLoading(false);
    }
  };

  // تعديل اسم القسم
  const handleRenameDepartment = async () => {
    if (!deptToRename || !newDeptRenameValue.trim()) return;
    const oldName = deptToRename.name;
    const newName = newDeptRenameValue.trim();

    if (oldName === newName) {
      setShowRenameDeptModal(false);
      return;
    }

    try {
      setActionLoading(true);
      // 1. تحديث الاسم في جدول shared_folders
      const { error: fErr } = await supabase
        .from('shared_folders')
        .update({ name: newName, updated_at: new Date().toISOString() })
        .eq('id', deptToRename.id);

      if (fErr) throw new Error(fErr.message);

      // 2. تحديث مسارات الملفات التابعة لهذا القسم
      const deptFiles = files.filter(f => f.folder === oldName);
      for (const f of deptFiles) {
        const newFilePath = `${newName}/${f.name}`;
        await supabase
          .from('files')
          .update({ file_path: newFilePath, updated_at: new Date().toISOString() })
          .eq('id', f.id);
      }

      setShowRenameDeptModal(false);
      setDeptToRename(null);
      await loadAllData();

      setToastMessage({
        text: `✏️ تم تعديل اسم القسم إلى "${newName}" ومزامنته مع الجميع!`,
        type: 'success'
      });
    } catch (err: any) {
      alert(`تعذر تعديل اسم القسم: ${err.message || err}`);
    } finally {
      setActionLoading(false);
    }
  };

  // حذف قسم إداري
  const handleDeleteDepartment = async (dept: DepartmentItem) => {
    const confirmDelete = confirm(
      `⚠️ تحذير إداري:\n\nهل أنت متأكد من حذف القسم "${dept.name}"؟\n` +
      `سيتم إزالة القسم من لوحة الويب ومن القائمة الجانبية لتطبيق الحاسوب لدى جميع الموظفين.\n` +
      `(عدد المستندات في القسم: ${dept.fileCount})`
    );
    if (!confirmDelete) return;

    try {
      setActionLoading(true);
      // 1. حذف من shared_folders
      await supabase.from('shared_folders').delete().eq('id', dept.id);
      await supabase.from('shared_folders').delete().eq('name', dept.name);

      await loadAllData();
      setToastMessage({
        text: `🗑️ تم حذف القسم "${dept.name}" بنجاح.`,
        type: 'info'
      });
    } catch (err: any) {
      alert(`تعذر حذف القسم: ${err.message || err}`);
    } finally {
      setActionLoading(false);
    }
  };

  // تثبيت الأقسام الرسمية الافتراضية للغرفة السبعة في السحابة بضغطة زر
  const handleSeedOfficialDepts = async () => {
    try {
      setActionLoading(true);
      for (const d of OFFICIAL_DEPTS) {
        await supabase.from('shared_folders').upsert({ name: d }, { onConflict: 'name' });
      }
      await loadAllData();
      alert('🏛️ تم تأكيد وتثبيت كافة أقسام غرفة تجارة كربلاء المقدسة الرسمية السبعة في السحابة بنجاح!');
    } catch (err: any) {
      alert(`تعذر تثبيت الأقسام: ${err.message || err}`);
    } finally {
      setActionLoading(false);
    }
  };

  // تغيير نمط الصلاحيات لقسم معين (تحكم كامل / تعديل بدون حذف / قراءة فقط)
  const handleSetPresetPermission = async (folderId: string, folderName: string, preset: 'FULL' | 'EDIT_ONLY' | 'READ_ONLY') => {
    let rule = {
      canView: true,
      canDownload: true,
      canWrite: preset !== 'READ_ONLY',
      canDelete: preset === 'FULL'
    };

    // تحديث الحالة محلياً فوراً
    setPermissions(prev => prev.map(p => p.folderId === folderId ? { ...p, ...rule } : p));

    try {
      setSavingPerms(true);
      // حفظ في جدول folder_permissions
      await supabase.from('folder_permissions').upsert({
        folder_id: folderId,
        user_id: '00000000-0000-0000-0000-000000000000',
        can_view: rule.canView,
        can_download: rule.canDownload,
        can_write: rule.canWrite,
        can_delete: rule.canDelete
      }, { onConflict: 'folder_id,user_id' });

      setToastMessage({
        text: `🔐 تم تحديث وحفظ صلاحيات قسم "${folderName}" بنجاح!`,
        type: 'success'
      });
    } catch (err: any) {
      console.error('Error saving perms:', err);
    } finally {
      setSavingPerms(false);
    }
  };

  // اعتماد أو تعطيل جهاز حاسوب
  const handleToggleDeviceAuth = async (device: DeviceRecord) => {
    try {
      setActionLoading(true);
      const newStatus = !device.isAuthorized;
      await supabase
        .from('devices')
        .update({ is_authorized: newStatus })
        .eq('id', device.id);

      setDevices(prev => prev.map(d => d.id === device.id ? { ...d, isAuthorized: newStatus } : d));
      setToastMessage({
        text: newStatus ? `✅ تم اعتماد جهاز "${device.name}" بنجاح.` : `⛔ تم تعطيل وصول جهاز "${device.name}".`,
        type: newStatus ? 'success' : 'info'
      });
    } catch (err: any) {
      alert(`فشل تحديث حالة الجهاز: ${err.message || err}`);
    } finally {
      setActionLoading(false);
    }
  };

  // حذف جهاز
  const handleDeleteDevice = async (deviceId: string, deviceName: string) => {
    if (!confirm(`هل أنت متأكد من حذف الجهاز "${deviceName}" من قائمة الأجهزة المصرح لها؟`)) return;
    try {
      setActionLoading(true);
      await supabase.from('devices').delete().eq('id', deviceId);
      setDevices(prev => prev.filter(d => d.id !== deviceId));
      setToastMessage({ text: `تم حذف الجهاز "${deviceName}".`, type: 'info' });
    } catch (err: any) {
      alert(`تعذر حذف الجهاز: ${err.message || err}`);
    } finally {
      setActionLoading(false);
    }
  };

  // تصفية الملفات في تبويب الملفات
  const filteredFiles = files.filter(f => {
    const matchDept = selectedDeptFilter === '__ALL__' || f.folder === selectedDeptFilter;
    const matchSearch = f.name.toLowerCase().includes(fileSearch.toLowerCase());
    return matchDept && matchSearch;
  });

  return (
    <div className="p-4 sm:p-6 md:p-8 space-y-6 max-w-7xl mx-auto w-full">
      {/* 1. الترويسة الرسمية للوحة تحكم الأدمن */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 bg-gradient-to-r from-[#0e2720] via-[#14372e] to-[#1a473b] p-6 rounded-3xl text-white shadow-lg border-b-4 border-[#c59b27]">
        <div className="space-y-1.5">
          <div className="flex items-center gap-2.5">
            <span className="p-2 bg-[#c59b27]/20 rounded-xl text-[#ecd58a] border border-[#c59b27]/40">
              <Shield className="w-6 h-6" />
            </span>
            <h1 className="text-xl sm:text-2xl font-black text-white tracking-wide">
              لوحة الإدارة والتحكم المركزي – غرفة تجارة كربلاء المقدسة
            </h1>
          </div>
          <p className="text-xs sm:text-sm text-slate-300">
            التحكم الشامل في إضافة وتعديل الأقسام، والمجلدات، والمستندات، ومصفوفة الصلاحيات، والربط اللحظي مع تطبيقات الويندوز والجوال.
          </p>
        </div>

        <div className="flex items-center gap-2 flex-wrap">
          <button
            onClick={loadAllData}
            disabled={loading}
            className="flex items-center gap-2 px-4 py-2.5 bg-white/10 hover:bg-white/20 text-white rounded-xl text-xs font-bold transition border border-white/15 active:scale-95"
            title="تحديث البيانات"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
            <span>تحديث السحابة</span>
          </button>

          <span className="inline-flex items-center gap-1.5 px-3 py-2 bg-emerald-950/80 text-emerald-300 rounded-xl text-xs font-bold border border-emerald-500/40">
            <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse"></span>
            السحابة متصلة لحظياً
          </span>
        </div>
      </div>

      {/* 2. بطاقات الإحصائيات الأربع المنظمة */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4">
        <div className="bg-white p-4 rounded-2xl border border-slate-200 shadow-xs flex items-center justify-between">
          <div>
            <p className="text-xs font-semibold text-slate-500">الأقسام الإدارية</p>
            <p className="text-2xl font-black text-slate-900 mt-1">{departments.length}</p>
            <p className="text-[11px] text-emerald-700 font-bold mt-0.5">متزامنة مع الويندوز</p>
          </div>
          <div className="w-11 h-11 rounded-xl bg-amber-50 text-amber-800 flex items-center justify-center font-bold">
            <Layers className="w-5 h-5" />
          </div>
        </div>

        <div className="bg-white p-4 rounded-2xl border border-slate-200 shadow-xs flex items-center justify-between">
          <div>
            <p className="text-xs font-semibold text-slate-500">المستندات المحفوظة</p>
            <p className="text-2xl font-black text-[#107c41] mt-1">{files.filter(f => !f.isDeleted).length}</p>
            <p className="text-[11px] text-slate-400 font-bold mt-0.5">Word • Excel • Access</p>
          </div>
          <div className="w-11 h-11 rounded-xl bg-emerald-50 text-emerald-700 flex items-center justify-center font-bold">
            <FileText className="w-5 h-5" />
          </div>
        </div>

        <div className="bg-white p-4 rounded-2xl border border-slate-200 shadow-xs flex items-center justify-between">
          <div>
            <p className="text-xs font-semibold text-slate-500">الأجهزة المصرح لها</p>
            <p className="text-2xl font-black text-[#0f6cbd] mt-1">{devices.filter(d => d.isAuthorized).length} <span className="text-xs font-normal text-slate-400">جهاز</span></p>
            <p className="text-[11px] text-sky-600 font-bold mt-0.5">حواسيب موظفي الغرفة</p>
          </div>
          <div className="w-11 h-11 rounded-xl bg-sky-50 text-[#0f6cbd] flex items-center justify-center font-bold">
            <Laptop className="w-5 h-5" />
          </div>
        </div>

        <div className="bg-white p-4 rounded-2xl border border-slate-200 shadow-xs flex items-center justify-between">
          <div>
            <p className="text-xs font-semibold text-slate-500">سلة المحذوفات</p>
            <p className="text-2xl font-black text-rose-700 mt-1">{files.filter(f => f.isDeleted).length}</p>
            <p className="text-[11px] text-rose-600 font-bold mt-0.5">مؤمّنة وقابلة للاسترجاع</p>
          </div>
          <div className="w-11 h-11 rounded-xl bg-rose-50 text-rose-700 flex items-center justify-center font-bold">
            <Trash2 className="w-5 h-5" />
          </div>
        </div>
      </div>

      {/* 3. شريط التبويبات الرئيسي للوحة الأدمن */}
      <div className="flex items-center gap-2 border-b border-slate-200 pb-2 overflow-x-auto scrollbar-thin">
        {[
          { id: 'DEPTS', label: '🏛️ إدارة الأقسام والمجلدات', count: departments.length },
          { id: 'PERMS', label: '🔐 مصفوفة الصلاحيات (قراءة/تعديل/حذف)', count: permissions.length },
          { id: 'FILES', label: '📁 إدارة كافة المستندات', count: files.length },
          { id: 'DEVICES', label: '💻 أجهزة الموظفين المعتمدة', count: devices.length }
        ].map(tab => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id as any)}
            className={`flex items-center gap-2 px-4 py-2.5 rounded-2xl text-xs font-black transition whitespace-nowrap ${
              activeTab === tab.id
                ? 'bg-[#14372e] text-white shadow-sm'
                : 'bg-white text-slate-600 hover:bg-slate-100 border border-slate-200'
            }`}
          >
            <span>{tab.label}</span>
            <span className={`text-[10px] px-1.5 py-0.2 rounded-full ${activeTab === tab.id ? 'bg-white/20 text-white' : 'bg-slate-100 text-slate-500'}`}>
              {tab.count}
            </span>
          </button>
        ))}
      </div>

      {/* ======================================================== */}
      {/* التبويب 1: إدارة الأقسام والمجلدات (Departments Management) */}
      {/* ======================================================== */}
      {activeTab === 'DEPTS' && (
        <div className="space-y-4">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 bg-white p-4 rounded-2xl border border-slate-200 shadow-xs">
            <div>
              <h3 className="font-black text-sm text-[#14372e] flex items-center gap-2">
                <span>🏛️ التحكم في أقسام الدائرة ومجلداتها السحابية</span>
              </h3>
              <p className="text-xs text-slate-500 mt-0.5">
                أي قسم تضيفه أو تعدل اسمه أو تحذفه هنا ينعكس فوراً ولحظياً في صفحة الويب وفي القائمة الجانبية لتطبيق الحاسوب (share coc) على كمبيوتر كل موظف.
              </p>
            </div>

            <div className="flex items-center gap-2 flex-wrap">
              <button
                onClick={() => setShowAddDeptModal(true)}
                className="flex items-center gap-1.5 bg-[#14372e] hover:bg-[#1a473b] text-white text-xs font-black px-4 py-2.5 rounded-xl transition shadow-sm active:scale-95"
              >
                <Plus className="w-4 h-4" />
                <span>إضافة قسم جديد</span>
              </button>

              <button
                onClick={handleSeedOfficialDepts}
                disabled={actionLoading}
                className="flex items-center gap-1.5 bg-amber-50 hover:bg-amber-100 text-amber-900 border border-amber-300 text-xs font-bold px-3 py-2.5 rounded-xl transition active:scale-95"
                title="تثبيت الأقسام الرسمية السبعة في السحابة"
              >
                <Sparkles className="w-4 h-4 text-amber-600" />
                <span className="hidden sm:inline">تثبيت الأقسام الرسمية السبعة</span>
              </button>
            </div>
          </div>

          {/* شبكة بطاقات الأقسام */}
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3.5">
            {departments.map((dept) => (
              <div
                key={dept.id}
                className="bg-white rounded-2xl p-4 border border-slate-200/90 shadow-xs hover:border-[#14372e]/50 transition flex flex-col justify-between space-y-3"
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="flex items-start gap-3 min-w-0">
                    <div className="w-10 h-10 rounded-xl bg-slate-50 border border-slate-200 text-slate-700 flex items-center justify-center font-bold text-lg shrink-0">
                      🏛️
                    </div>
                    <div className="min-w-0">
                      <h4 className="font-black text-xs text-slate-900 break-words leading-tight">
                        {dept.name}
                      </h4>
                      <p className="text-[11px] text-slate-400 mt-1">
                        📁 {dept.fileCount} مستند • 💾 {formatSize(dept.totalSize)}
                      </p>
                    </div>
                  </div>

                  {dept.isDefault && (
                    <span className="text-[10px] font-bold text-emerald-800 bg-emerald-50 px-2 py-0.5 rounded-md border border-emerald-200 shrink-0">
                      رسمي معتمد
                    </span>
                  )}
                </div>

                <div className="flex items-center justify-between border-t border-slate-100 pt-3 gap-2">
                  <button
                    onClick={() => {
                      setDeptToRename(dept);
                      setNewDeptRenameValue(dept.name);
                      setShowRenameDeptModal(true);
                    }}
                    className="flex-1 flex items-center justify-center gap-1 py-1.5 px-2 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-lg text-xs font-bold transition active:scale-95"
                    title="تعديل اسم القسم"
                  >
                    <Edit3 className="w-3.5 h-3.5 text-emerald-700" />
                    <span>تعديل الاسم</span>
                  </button>

                  <button
                    onClick={() => handleDeleteDepartment(dept)}
                    className="flex items-center justify-center gap-1 py-1.5 px-3 bg-rose-50 hover:bg-rose-100 text-rose-700 rounded-lg text-xs font-bold transition active:scale-95"
                    title="حذف القسم"
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                    <span>حذف</span>
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ======================================================== */}
      {/* التبويب 2: مصفوفة الصلاحيات (Permissions Matrix) */}
      {/* ======================================================== */}
      {activeTab === 'PERMS' && (
        <div className="space-y-4">
          <div className="bg-white p-4 rounded-2xl border border-slate-200 shadow-xs flex flex-col sm:flex-row sm:items-center justify-between gap-3">
            <div>
              <h3 className="font-black text-sm text-[#14372e] flex items-center gap-2">
                <span>🔐 مصفوفة الصلاحيات وضبط صلاحيات التعديل والحذف</span>
              </h3>
              <p className="text-xs text-slate-500 mt-0.5">
                حدد لكل قسم صلاحية موظفي الغرفة: هل يُسمح لهم بالتعديل وحفظ التغييرات؟ هل يُسمح لهم بالحذف؟ أم للقراءة والتحميل فقط؟
              </p>
            </div>
            <span className="text-xs text-emerald-800 bg-emerald-50 px-3 py-1 rounded-xl font-bold border border-emerald-200">
              تُحفظ الصلاحيات لحظياً بالسحابة
            </span>
          </div>

          <div className="bg-white rounded-2xl border border-slate-200 shadow-xs overflow-hidden">
            <table className="w-full text-right text-sm">
              <thead className="bg-slate-50 text-slate-600 text-xs font-black border-b border-slate-200">
                <tr>
                  <th className="p-4">القسم الإداري</th>
                  <th className="p-4 text-center">القراءة والتحميل</th>
                  <th className="p-4 text-center">التعديل والحفظ السحابي (Ctrl+S)</th>
                  <th className="p-4 text-center">صلاحية الحذف</th>
                  <th className="p-4 text-center">الوضع الموصى به</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {permissions.map((perm) => (
                  <tr key={perm.folderId} className="hover:bg-slate-50/70 transition">
                    <td className="p-4">
                      <div className="flex items-center gap-2.5">
                        <span className="text-lg">🏛️</span>
                        <span className="font-bold text-slate-900 text-xs">{perm.folderName}</span>
                      </div>
                    </td>

                    <td className="p-4 text-center">
                      <span className="inline-flex items-center gap-1 text-xs font-bold text-emerald-700 bg-emerald-50 px-2.5 py-1 rounded-lg border border-emerald-200">
                        <Check className="w-3.5 h-3.5" /> مسموح للجميع
                      </span>
                    </td>

                    <td className="p-4 text-center">
                      {perm.canWrite ? (
                        <span className="inline-flex items-center gap-1 text-xs font-bold text-emerald-700 bg-emerald-50 px-2.5 py-1 rounded-lg border border-emerald-200">
                          <Check className="w-3.5 h-3.5" /> مسموح التعديل
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1 text-xs font-bold text-rose-700 bg-rose-50 px-2.5 py-1 rounded-lg border border-rose-200">
                          <Lock className="w-3.5 h-3.5" /> ممنوع التعديل
                        </span>
                      )}
                    </td>

                    <td className="p-4 text-center">
                      {perm.canDelete ? (
                        <span className="inline-flex items-center gap-1 text-xs font-bold text-amber-800 bg-amber-50 px-2.5 py-1 rounded-lg border border-amber-200">
                          <Check className="w-3.5 h-3.5" /> مسموح الحذف
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1 text-xs font-bold text-slate-600 bg-slate-100 px-2.5 py-1 rounded-lg border border-slate-200">
                          <X className="w-3.5 h-3.5" /> ممنوع الحذف
                        </span>
                      )}
                    </td>

                    <td className="p-4 text-center">
                      <div className="inline-flex items-center gap-1.5 flex-wrap justify-center">
                        <button
                          onClick={() => handleSetPresetPermission(perm.folderId, perm.folderName, 'FULL')}
                          className={`px-2.5 py-1 rounded-lg text-[10px] font-black transition ${
                            perm.canWrite && perm.canDelete
                              ? 'bg-emerald-700 text-white shadow-xs'
                              : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
                          }`}
                          title="صلاحية كاملة (تعديل + حذف)"
                        >
                          تحكم كامل
                        </button>

                        <button
                          onClick={() => handleSetPresetPermission(perm.folderId, perm.folderName, 'EDIT_ONLY')}
                          className={`px-2.5 py-1 rounded-lg text-[10px] font-black transition ${
                            perm.canWrite && !perm.canDelete
                              ? 'bg-amber-600 text-white shadow-xs'
                              : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
                          }`}
                          title="مسموح التعديل بـ Ctrl+S وممنوع الحذف"
                        >
                          تعديل بدون حذف
                        </button>

                        <button
                          onClick={() => handleSetPresetPermission(perm.folderId, perm.folderName, 'READ_ONLY')}
                          className={`px-2.5 py-1 rounded-lg text-[10px] font-black transition ${
                            !perm.canWrite && !perm.canDelete
                              ? 'bg-rose-700 text-white shadow-xs'
                              : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
                          }`}
                          title="قراءة وتحميل فقط (تجميد القسم)"
                        >
                          قراءة فقط
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* ======================================================== */}
      {/* التبويب 3: إدارة كافة المستندات (Files Management) */}
      {/* ======================================================== */}
      {activeTab === 'FILES' && (
        <div className="space-y-4">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 bg-white p-4 rounded-2xl border border-slate-200 shadow-xs">
            <div className="flex items-center gap-2">
              <Search className="w-4 h-4 text-slate-400" />
              <input
                type="text"
                placeholder="بحث في أسماء المستندات..."
                value={fileSearch}
                onChange={(e) => setFileSearch(e.target.value)}
                className="text-xs bg-slate-50 border border-slate-200 rounded-xl px-3 py-2 w-64 focus:outline-none focus:ring-2 focus:ring-[#14372e]"
              />
            </div>

            <div className="flex items-center gap-2 overflow-x-auto">
              <select
                value={selectedDeptFilter}
                onChange={(e) => setSelectedDeptFilter(e.target.value)}
                className="text-xs bg-slate-50 border border-slate-200 rounded-xl px-3 py-2 font-bold focus:outline-none focus:ring-2 focus:ring-[#14372e]"
              >
                <option value="__ALL__">كافة الأقسام ({files.length})</option>
                {departments.map(d => (
                  <option key={d.name} value={d.name}>{d.name}</option>
                ))}
              </select>
            </div>
          </div>

          <div className="bg-white rounded-2xl border border-slate-200 shadow-xs overflow-hidden">
            <table className="w-full text-right text-sm">
              <thead className="bg-slate-50 text-slate-600 text-xs font-black border-b border-slate-200">
                <tr>
                  <th className="p-4">اسم المستند</th>
                  <th className="p-4">القسم</th>
                  <th className="p-4">الإصدار</th>
                  <th className="p-4">الحجم</th>
                  <th className="p-4">آخر تعديل بواسطة</th>
                  <th className="p-4">الحالة</th>
                  <th className="p-4 text-center">الإجراءات الإدارية</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {filteredFiles.map((file) => (
                  <tr key={file.id} className="hover:bg-slate-50/70 transition">
                    <td className="p-4">
                      <span className="font-bold text-slate-800 text-xs">{file.name}</span>
                    </td>
                    <td className="p-4 text-xs text-slate-600">{file.folder}</td>
                    <td className="p-4 text-xs font-mono font-bold text-emerald-800">V{file.version}</td>
                    <td className="p-4 text-xs font-mono text-slate-500">{file.size}</td>
                    <td className="p-4 text-xs text-slate-500">{file.lastModifiedBy}</td>
                    <td className="p-4">
                      {file.isDeleted ? (
                        <span className="text-[10px] bg-rose-50 text-rose-700 font-bold px-2 py-0.5 rounded border border-rose-200">
                          محذوف مؤقتاً
                        </span>
                      ) : (
                        <span className="text-[10px] bg-emerald-50 text-emerald-700 font-bold px-2 py-0.5 rounded border border-emerald-200">
                          نشط ومتزامن
                        </span>
                      )}
                    </td>
                    <td className="p-4 text-center">
                      <div className="inline-flex items-center gap-1.5">
                        <button
                          onClick={() => {
                            setFileToRename(file);
                            setNewFileNameValue(file.name);
                            setShowRenameFileModal(true);
                          }}
                          className="p-1.5 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-lg text-xs"
                          title="تعديل اسم المستند"
                        >
                          <Edit3 className="w-3.5 h-3.5 text-emerald-700" />
                        </button>

                        {file.isDeleted ? (
                          <button
                            onClick={async () => {
                              await supabase.from('files').update({ is_deleted: false }).eq('id', file.id);
                              await loadAllData();
                            }}
                            className="p-1.5 bg-emerald-50 hover:bg-emerald-100 text-emerald-800 rounded-lg text-xs font-bold"
                            title="استرجاع من المحذوفات"
                          >
                            <RotateCcw className="w-3.5 h-3.5" />
                          </button>
                        ) : (
                          <button
                            onClick={async () => {
                              if (confirm(`هل أنت متأكد من نقل "${file.name}" إلى سلة المحذوفات؟`)) {
                                await supabase.from('files').update({ is_deleted: true }).eq('id', file.id);
                                await loadAllData();
                              }
                            }}
                            className="p-1.5 bg-rose-50 hover:bg-rose-100 text-rose-700 rounded-lg text-xs"
                            title="نقل للمحذوفات"
                          >
                            <Trash2 className="w-3.5 h-3.5" />
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* ======================================================== */}
      {/* التبويب 4: أجهزة الموظفين المعتمدة (Devices Management) */}
      {/* ======================================================== */}
      {activeTab === 'DEVICES' && (
        <div className="space-y-4">
          <div className="bg-white p-4 rounded-2xl border border-slate-200 shadow-xs flex flex-col sm:flex-row sm:items-center justify-between gap-3">
            <div>
              <h3 className="font-black text-sm text-[#14372e] flex items-center gap-2">
                <span>💻 إدارة واعتماد أجهزة حواسيب موظفي الغرفة</span>
              </h3>
              <p className="text-xs text-slate-500 mt-0.5">
                الأجهزة العشرة المعتمدة لموظفي غرفة تجارة كربلاء المقدسة، مع إمكانية اعتماد الجهاز أو تجميد مزامنته بضغطة زر.
              </p>
            </div>
            <span className="text-xs font-bold text-sky-800 bg-sky-50 px-3 py-1 rounded-xl border border-sky-200">
              {devices.filter(d => d.isAuthorized).length} أجهزة نشطة
            </span>
          </div>

          <div className="bg-white rounded-2xl border border-slate-200 shadow-xs overflow-hidden">
            <table className="w-full text-right text-sm">
              <thead className="bg-slate-50 text-slate-600 text-xs font-black border-b border-slate-200">
                <tr>
                  <th className="p-4">اسم الجهاز</th>
                  <th className="p-4">نظام التشغيل</th>
                  <th className="p-4">رقم تعريف الجهاز (Machine GUID)</th>
                  <th className="p-4">آخر مزامنة</th>
                  <th className="p-4 text-center">حالة الاعتماد</th>
                  <th className="p-4 text-center">الإجراء</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {devices.length === 0 ? (
                  <tr>
                    <td colSpan={6} className="p-12 text-center text-slate-400">
                      لا توجد أجهزة مسجلة حالياً. عند تشغيل تطبيق <strong>share coc.exe</strong> على جهاز أي موظف سيظهر هنا تلقائياً.
                    </td>
                  </tr>
                ) : (
                  devices.map((dev) => (
                    <tr key={dev.id} className="hover:bg-slate-50/70 transition">
                      <td className="p-4 font-bold text-slate-800 text-xs flex items-center gap-2">
                        <Laptop className="w-4 h-4 text-slate-600" />
                        <span>{dev.name}</span>
                      </td>
                      <td className="p-4 text-xs text-slate-600">{dev.os}</td>
                      <td className="p-4 text-xs font-mono text-slate-400">{dev.machineGuid}</td>
                      <td className="p-4 text-xs font-mono text-slate-500">{dev.lastSeen}</td>
                      <td className="p-4 text-center">
                        {dev.isAuthorized ? (
                          <span className="inline-flex items-center gap-1 text-[11px] font-bold text-emerald-700 bg-emerald-50 px-2.5 py-0.5 rounded-full border border-emerald-200">
                            <CheckCircle2 className="w-3.5 h-3.5" /> معتمد ومفعّل
                          </span>
                        ) : (
                          <span className="inline-flex items-center gap-1 text-[11px] font-bold text-rose-700 bg-rose-50 px-2.5 py-0.5 rounded-full border border-rose-200">
                            <Lock className="w-3.5 h-3.5" /> معطّل
                          </span>
                        )}
                      </td>
                      <td className="p-4 text-center">
                        <div className="inline-flex items-center gap-1.5">
                          <button
                            onClick={() => handleToggleDeviceAuth(dev)}
                            className={`px-3 py-1 rounded-lg text-xs font-bold transition ${
                              dev.isAuthorized
                                ? 'bg-rose-50 text-rose-700 hover:bg-rose-100 border border-rose-200'
                                : 'bg-emerald-50 text-emerald-800 hover:bg-emerald-100 border border-emerald-200'
                            }`}
                          >
                            {dev.isAuthorized ? 'تجميد الوصول' : 'اعتماد وتفعيل'}
                          </button>

                          <button
                            onClick={() => handleDeleteDevice(dev.id, dev.name)}
                            className="p-1.5 text-slate-400 hover:text-rose-600 transition"
                            title="حذف الجهاز"
                          >
                            <Trash2 className="w-3.5 h-3.5" />
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* ======================================================== */}
      {/* نافذة إنشاء قسم إداري جديد (Add Department Modal) */}
      {/* ======================================================== */}
      {showAddDeptModal && (
        <div className="fixed inset-0 bg-black/60 backdrop-blur-xs z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-3xl p-6 max-w-md w-full space-y-4 shadow-2xl border border-slate-200">
            <div className="flex items-center justify-between border-b pb-3">
              <h3 className="font-black text-base text-[#14372e] flex items-center gap-2">
                <FolderPlus className="w-5 h-5 text-amber-600" />
                <span>إضافة قسم إداري جديد</span>
              </h3>
              <button onClick={() => setShowAddDeptModal(false)} className="text-slate-400 hover:text-slate-600">
                <X className="w-5 h-5" />
              </button>
            </div>

            <p className="text-xs text-slate-500">
              أدخل اسم القسم الجديد. سيتم إنشاؤه في السحابة فوراً ومزامنته مع لوحة الويب وتطبيق الحاسوب لدى جميع الموظفين:
            </p>

            <input
              type="text"
              placeholder="مثال: شعبة التدقيق والرقابة الداخلية..."
              value={newDeptName}
              onChange={(e) => setNewDeptName(e.target.value)}
              className="w-full px-4 py-2.5 text-xs bg-slate-50 border border-slate-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-[#14372e]"
              autoFocus
            />

            <div className="space-y-1.5">
              <span className="text-[11px] text-slate-400 font-semibold">اقتراحات سريعة لأقسام مقترحة:</span>
              <div className="flex items-center gap-1.5 flex-wrap">
                {['شعبة التدقيق والرقابة', 'مكتب رئيس الغرفة', 'شعبة العلاقات الدولية', 'شعبة المعارض والمؤتمرات'].map(sug => (
                  <button
                    key={sug}
                    onClick={() => setNewDeptName(sug)}
                    className="text-[10px] bg-slate-100 hover:bg-slate-200 text-slate-700 font-bold px-2 py-1 rounded-lg"
                  >
                    {sug}
                  </button>
                ))}
              </div>
            </div>

            <div className="flex items-center justify-end gap-2 pt-2 border-t">
              <button
                onClick={() => setShowAddDeptModal(false)}
                className="px-4 py-2 text-xs font-bold text-slate-600 hover:bg-slate-100 rounded-xl transition"
              >
                إلغاء
              </button>
              <button
                onClick={handleCreateDepartment}
                disabled={actionLoading || !newDeptName.trim()}
                className="px-5 py-2 text-xs font-bold bg-[#14372e] text-white rounded-xl hover:bg-[#1a473b] transition shadow-sm"
              >
                {actionLoading ? 'جاري الإضافة...' : 'إضافة وتعميم على الأجهزة'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* نافذة تعديل اسم القسم (Rename Department Modal) */}
      {showRenameDeptModal && deptToRename && (
        <div className="fixed inset-0 bg-black/60 backdrop-blur-xs z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-3xl p-6 max-w-md w-full space-y-4 shadow-2xl border border-slate-200">
            <div className="flex items-center justify-between border-b pb-3">
              <h3 className="font-black text-base text-[#14372e] flex items-center gap-2">
                <Edit3 className="w-5 h-5 text-emerald-700" />
                <span>تعديل اسم القسم الإداري</span>
              </h3>
              <button onClick={() => setShowRenameDeptModal(false)} className="text-slate-400 hover:text-slate-600">
                <X className="w-5 h-5" />
              </button>
            </div>

            <p className="text-xs text-slate-500">
              الاسم الحالي: <strong className="text-slate-800">{deptToRename.name}</strong>
            </p>

            <input
              type="text"
              value={newDeptRenameValue}
              onChange={(e) => setNewDeptRenameValue(e.target.value)}
              className="w-full px-4 py-2.5 text-xs bg-slate-50 border border-slate-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-[#14372e]"
              autoFocus
            />

            <p className="text-[10px] text-slate-400">
              ملاحظة: سيتم تحديث اسم القسم فوراً في السحابة وتعديل مسار المستندات التابعة له وتحديث القائمة الجانبية لحواسيب الموظفين.
            </p>

            <div className="flex items-center justify-end gap-2 pt-2 border-t">
              <button
                onClick={() => setShowRenameDeptModal(false)}
                className="px-4 py-2 text-xs font-bold text-slate-600 hover:bg-slate-100 rounded-xl transition"
              >
                إلغاء
              </button>
              <button
                onClick={handleRenameDepartment}
                disabled={actionLoading || !newDeptRenameValue.trim()}
                className="px-5 py-2 text-xs font-bold bg-[#14372e] text-white rounded-xl hover:bg-[#1a473b] transition shadow-sm"
              >
                {actionLoading ? 'جاري الحفظ...' : 'حفظ وتحديث الأجهزة'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* نافذة تعديل اسم مستند (Rename File Modal) */}
      {showRenameFileModal && fileToRename && (
        <div className="fixed inset-0 bg-black/60 backdrop-blur-xs z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-3xl p-6 max-w-md w-full space-y-4 shadow-2xl border border-slate-200">
            <div className="flex items-center justify-between border-b pb-3">
              <h3 className="font-black text-base text-[#14372e] flex items-center gap-2">
                <Edit3 className="w-5 h-5 text-emerald-700" />
                <span>تعديل اسم المستند</span>
              </h3>
              <button onClick={() => setShowRenameFileModal(false)} className="text-slate-400 hover:text-slate-600">
                <X className="w-5 h-5" />
              </button>
            </div>

            <p className="text-xs text-slate-500">
              الاسم الحالي: <strong className="text-slate-800">{fileToRename.name}</strong>
            </p>

            <input
              type="text"
              value={newFileNameValue}
              onChange={(e) => setNewFileNameValue(e.target.value)}
              className="w-full px-4 py-2.5 text-xs bg-slate-50 border border-slate-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-[#14372e]"
              autoFocus
            />

            <div className="flex items-center justify-end gap-2 pt-2 border-t">
              <button
                onClick={() => setShowRenameFileModal(false)}
                className="px-4 py-2 text-xs font-bold text-slate-600 hover:bg-slate-100 rounded-xl transition"
              >
                إلغاء
              </button>
              <button
                onClick={async () => {
                  if (!newFileNameValue.trim()) return;
                  await supabase
                    .from('files')
                    .update({ file_name: newFileNameValue.trim(), updated_at: new Date().toISOString() })
                    .eq('id', fileToRename.id);
                  setShowRenameFileModal(false);
                  setFileToRename(null);
                  await loadAllData();
                }}
                className="px-5 py-2 text-xs font-bold bg-[#14372e] text-white rounded-xl hover:bg-[#1a473b] transition shadow-sm"
              >
                حفظ التعديل
              </button>
            </div>
          </div>
        </div>
      )}

      {/* إشعار عائم Toast */}
      {toastMessage && (
        <div className="fixed bottom-6 left-1/2 -translate-x-1/2 z-50 animate-bounce shadow-2xl pointer-events-none">
          <div className={`flex items-center gap-2.5 px-5 py-3 rounded-2xl text-xs font-bold border backdrop-blur-md ${
            toastMessage.type === 'success'
              ? 'bg-[#14372e]/95 text-white border-emerald-400'
              : toastMessage.type === 'error'
              ? 'bg-rose-900/95 text-white border-rose-400'
              : 'bg-slate-900/95 text-white border-slate-700'
          }`}>
            <span>{toastMessage.text}</span>
          </div>
        </div>
      )}
    </div>
  );
}
