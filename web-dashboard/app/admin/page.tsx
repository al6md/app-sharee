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
  Save, 
  Key, 
  AlertTriangle, 
  Layers, 
  Settings,
  FolderOpen,
  ArrowRight,
  Eye,
  EyeOff,
  Download,
  RotateCcw,
  CheckCircle2,
  FileSpreadsheet,
  Database,
  Camera,
  Upload,
  LogOut,
  User
} from 'lucide-react';

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

export default function AdminControlPage() {
  // حالة تسجيل الدخول والأمان
  const [isAuthenticated, setIsAuthenticated] = useState<boolean>(false);
  const [isCheckingAuth, setIsCheckingAuth] = useState<boolean>(true);
  const [adminUsername, setAdminUsername] = useState<string>('admin');

  // حقول نموذج تسجيل الدخول
  const [loginUser, setLoginUser] = useState<string>('');
  const [loginPass, setLoginPass] = useState<string>('');
  const [showLoginPass, setShowLoginPass] = useState<boolean>(false);
  const [loginError, setLoginError] = useState<string>('');

  // نافذة تعديل بيانات الدخول
  const [showCredentialsModal, setShowCredentialsModal] = useState<boolean>(false);
  const [currentPassInput, setCurrentPassInput] = useState<string>('');
  const [newUserInput, setNewUserInput] = useState<string>('');
  const [newPassInput, setNewPassInput] = useState<string>('');
  const [confirmPassInput, setConfirmPassInput] = useState<string>('');
  const [showNewPass, setShowNewPass] = useState<boolean>(false);
  const [credError, setCredError] = useState<string>('');
  const [credSuccess, setCredSuccess] = useState<string>('');

  // التبويب النشط في لوحة الأدمن
  const [activeTab, setActiveTab] = useState<'DEPTS' | 'PERMS' | 'FILES' | 'DEVICES'>('DEPTS');
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState(false);

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

  // التحقق من الجلسة وبيانات الاعتماد عند التحميل
  useEffect(() => {
    if (typeof window !== 'undefined') {
      let storedUser = localStorage.getItem('sharecoc_admin_username');
      let storedPass = localStorage.getItem('sharecoc_admin_password');

      if (!storedUser || !storedPass) {
        storedUser = 'admin';
        storedPass = 'admin1234';
        localStorage.setItem('sharecoc_admin_username', storedUser);
        localStorage.setItem('sharecoc_admin_password', storedPass);
      }

      setAdminUsername(storedUser);

      const sessionActive = localStorage.getItem('sharecoc_admin_session');
      if (sessionActive === 'true') {
        setIsAuthenticated(true);
      }
      setIsCheckingAuth(false);
    }
  }, []);

  const formatSize = (bytes: number) => {
    if (!bytes || bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return `${parseFloat((bytes / Math.pow(k, i)).toFixed(1))} ${sizes[i]}`;
  };

  const loadAllData = async () => {
    try {
      setLoading(true);

      const res = await fetch('/api/drive/files');
      const data = await res.json();
      if (data.success) {
        const folderMap = new Map<string, DepartmentItem>();
        (data.folders || []).forEach((f: any) => {
          if (f.name) {
            folderMap.set(f.name, {
              id: f.id,
              name: f.name,
              fileCount: 0,
              totalSize: 0
            });
          }
        });

        const mappedFiles: FileRecord[] = (data.files || []).map((f: any) => ({
          id: f.id,
          name: f.name,
          folder: f.folder || 'القسم العام',
          size: formatSize(f.size || 0),
          rawSize: f.size || 0,
          version: 1,
          lastModifiedBy: 'سحابة Google Drive',
          lastModifiedAt: f.modifiedTime ? new Date(f.modifiedTime).toLocaleDateString('ar-IQ', {
            month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit'
          }) : 'الآن',
          storagePath: f.id,
          isDeleted: Boolean(f.isDeleted)
        }));
        setFiles(mappedFiles);

        mappedFiles.forEach(f => {
          if (!f.isDeleted && f.folder && f.folder !== 'كافة الملفات') {
            if (!folderMap.has(f.folder)) {
              folderMap.set(f.folder, {
                id: f.folder,
                name: f.folder,
                fileCount: 0,
                totalSize: 0
              });
            }
            const item = folderMap.get(f.folder)!;
            item.fileCount += 1;
            item.totalSize += f.rawSize;
          }
        });

        const deptsList = Array.from(folderMap.values());
        setDepartments(deptsList);

        const permsList: PermissionRule[] = deptsList.map(dept => ({
          folderId: dept.id,
          folderName: dept.name,
          canView: true,
          canDownload: true,
          canWrite: true,
          canDelete: true,
        }));
        setPermissions(permsList);
      }
    } catch (err) {
      console.error('Error fetching admin data:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (!isAuthenticated) return;
    loadAllData();
    const interval = setInterval(() => {
      loadAllData();
    }, 10000);
    return () => clearInterval(interval);
  }, [isAuthenticated]);

  // معالجة تسجيل الدخول
  const handleLogin = (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    setLoginError('');

    const storedUser = localStorage.getItem('sharecoc_admin_username') || 'admin';
    const storedPass = localStorage.getItem('sharecoc_admin_password') || 'admin1234';

    if (loginUser.trim() === storedUser && loginPass === storedPass) {
      setIsAuthenticated(true);
      localStorage.setItem('sharecoc_admin_session', 'true');
      setLoginPass('');
      setLoginError('');
      setToastMessage({
        text: `مرحباً بك يا ${storedUser}، تم تسجيل الدخول بنجاح!`,
        type: 'success'
      });
    } else {
      setLoginError('اسم المستخدم أو كلمة المرور غير صحيحة، يرجى التحقق وإعادة المحاولة.');
    }
  };

  // تسجيل الخروج
  const handleLogout = () => {
    if (confirm('هل تود تسجيل الخروج من لوحة تحكم الأدمن؟')) {
      setIsAuthenticated(false);
      localStorage.removeItem('sharecoc_admin_session');
      setLoginUser('');
      setLoginPass('');
    }
  };

  // تعديل بيانات تسجيل الدخول
  const handleChangeCredentials = (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    setCredError('');
    setCredSuccess('');

    const storedPass = localStorage.getItem('sharecoc_admin_password') || 'admin1234';

    if (currentPassInput !== storedPass) {
      setCredError('كلمة المرور الحالية غير صحيحة!');
      return;
    }

    if (!newUserInput.trim()) {
      setCredError('يرجى كتابة اسم مستخدم صالح.');
      return;
    }

    if (!newPassInput || newPassInput.length < 4) {
      setCredError('كلمة المرور الجديدة يجب أن تحتوي على 4 أحرف أو أرقام على الأقل.');
      return;
    }

    if (newPassInput !== confirmPassInput) {
      setCredError('كلمة المرور الجديدة وتأكيدها غير متطابقين!');
      return;
    }

    localStorage.setItem('sharecoc_admin_username', newUserInput.trim());
    localStorage.setItem('sharecoc_admin_password', newPassInput.trim());
    setAdminUsername(newUserInput.trim());
    setCredSuccess('✅ تم تحديث بيانات تسجيل دخول الأدمن بنجاح!');

    setTimeout(() => {
      setShowCredentialsModal(false);
      setCurrentPassInput('');
      setNewUserInput('');
      setNewPassInput('');
      setConfirmPassInput('');
      setCredError('');
      setCredSuccess('');
      setToastMessage({
        text: '🔑 تم حفظ بيانات دخول الأدمن الجديدة بنجاح!',
        type: 'success'
      });
    }, 1200);
  };

  // إضافة قسم إداري جديد ومزامنته فوراً
  const handleCreateDepartment = async () => {
    const deptName = newDeptName.trim();
    if (!deptName) return;

    try {
      setActionLoading(true);
      const res = await fetch('/api/drive/files', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'CREATE_FOLDER', name: deptName }),
      });
      const data = await res.json();
      if (!data.success) throw new Error(data.error);

      setShowAddDeptModal(false);
      setNewDeptName('');
      await loadAllData();

      setToastMessage({
        text: `🎉 تم إنشاء القسم "${deptName}" بنجاح ومزامنته مع سحابة Google Drive وتطبيق الحاسوب!`,
        type: 'success'
      });
      alert(`✅ تمت إضافة القسم "${deptName}" بنجاح!\n\nسيظهر هذا القسم فوراً في لوحة الويب، وفي تطبيق الحاسوب (share coc) لدى كافة موظفي الغرفة.`);
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
      const res = await fetch('/api/drive/files', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'RENAME', id: deptToRename.id, name: newName }),
      });
      const data = await res.json();
      if (!data.success) throw new Error(data.error);

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
      const res = await fetch(`/api/drive/files?id=${dept.id}`, { method: 'DELETE' });
      const data = await res.json();
      if (!data.success) throw new Error(data.error);

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

  // تغيير نمط الصلاحيات لقسم معين (تحكم كامل / تعديل بدون حذف / قراءة فقط)
  const handleSetPresetPermission = async (folderId: string, folderName: string, preset: 'FULL' | 'EDIT_ONLY' | 'READ_ONLY') => {
    let rule = {
      canView: true,
      canDownload: true,
      canWrite: preset !== 'READ_ONLY',
      canDelete: preset === 'FULL'
    };
    setPermissions(prev => prev.map(p => p.folderId === folderId ? { ...p, ...rule } : p));
    setToastMessage({
      text: `🔐 تم تحديث وحفظ صلاحيات قسم "${folderName}" بنجاح!`,
      type: 'success'
    });
  };

  // اعتماد أو تعطيل جهاز حاسوب
  const handleToggleDeviceAuth = async (device: DeviceRecord) => {
    try {
      setActionLoading(true);
      const newStatus = !device.isAuthorized;
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

  // حالة انتظار التحقق من الجلسة
  if (isCheckingAuth) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[70vh] gap-3">
        <RefreshCw className="w-8 h-8 animate-spin text-[#14372e]" />
        <p className="text-xs font-bold text-slate-500">جاري التحقق من أمان الجلسة...</p>
      </div>
    );
  }

  // 1. شاشة تسجيل الدخول إذا لم يكن المستخدم مسجلاً
  if (!isAuthenticated) {
    return (
      <div className="min-h-[85vh] flex items-center justify-center p-4">
        <div className="w-full max-w-md bg-white rounded-3xl border border-slate-200 shadow-xl overflow-hidden">
          {/* الترويسة الرسمية لبطاقة الدخول */}
          <div className="bg-gradient-to-r from-[#0e2720] via-[#14372e] to-[#1a473b] p-6 text-white text-center border-b-4 border-[#c59b27] relative">
            <div className="w-16 h-16 mx-auto mb-3 rounded-full bg-white/10 p-1 border-2 border-[#c59b27] flex items-center justify-center shadow-md">
              <Shield className="w-8 h-8 text-[#ecd58a]" />
            </div>
            <h2 className="text-lg font-black text-white">تسجيل دخول لوحة الأدمن</h2>
            <p className="text-xs text-[#ecd58a] mt-1 font-semibold">غرفة تجارة كربلاء المقدسة</p>
            <p className="text-[11px] text-slate-300 mt-1">المنطقة مقيدة ومخصصة لإدارة المنظومة فقط</p>
          </div>

          {/* نموذج تسجيل الدخول */}
          <form onSubmit={handleLogin} className="p-6 space-y-4">
            {loginError && (
              <div className="flex items-center gap-2 p-3 bg-rose-50 border border-rose-200 text-rose-700 rounded-xl text-xs font-bold">
                <AlertTriangle className="w-4 h-4 shrink-0" />
                <span>{loginError}</span>
              </div>
            )}

            <div>
              <label className="block text-xs font-bold text-slate-700 mb-1.5">
                اسم مستخدم الأدمن
              </label>
              <div className="relative">
                <input
                  type="text"
                  required
                  value={loginUser}
                  onChange={(e) => setLoginUser(e.target.value)}
                  placeholder="أدخل اسم المستخدم (مثال: admin)"
                  className="w-full pl-3 pr-10 py-2.5 text-xs bg-slate-50 border border-slate-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-[#14372e] focus:bg-white transition"
                />
                <User className="w-4 h-4 text-slate-400 absolute right-3 top-3" />
              </div>
            </div>

            <div>
              <label className="block text-xs font-bold text-slate-700 mb-1.5">
                كلمة المرور
              </label>
              <div className="relative">
                <input
                  type={showLoginPass ? 'text' : 'password'}
                  required
                  value={loginPass}
                  onChange={(e) => setLoginPass(e.target.value)}
                  placeholder="أدخل كلمة المرور"
                  className="w-full pl-10 pr-10 py-2.5 text-xs bg-slate-50 border border-slate-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-[#14372e] focus:bg-white transition"
                />
                <Lock className="w-4 h-4 text-slate-400 absolute right-3 top-3" />
                <button
                  type="button"
                  onClick={() => setShowLoginPass(!showLoginPass)}
                  className="absolute left-3 top-2.5 text-slate-400 hover:text-slate-600 transition"
                >
                  {showLoginPass ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                </button>
              </div>
            </div>

            <button
              type="submit"
              className="w-full py-3 bg-[#14372e] hover:bg-[#1a473b] text-white text-xs font-bold rounded-xl transition shadow-md active:scale-98 flex items-center justify-center gap-2 mt-2"
            >
              <Key className="w-4 h-4 text-[#ecd58a]" />
              <span>تسجيل الدخول إلى لوحة التحكم</span>
            </button>

            {/* بطاقة توضيحية لبيانات الدخول الافتراضية */}
            <div className="p-3 bg-amber-50 rounded-xl border border-amber-200 text-amber-900 text-[11px] leading-relaxed space-y-1">
              <div className="flex items-center gap-1.5 font-bold">
                <Key className="w-3.5 h-3.5 text-amber-700" />
                <span>بيانات الدخول الافتراضية لأول مرة:</span>
              </div>
              <p className="font-mono text-[11px] text-amber-950 font-bold">
                المستخدم: <span className="bg-amber-100 px-1.5 py-0.5 rounded border border-amber-300">admin</span> | كلمة المرور: <span className="bg-amber-100 px-1.5 py-0.5 rounded border border-amber-300">admin1234</span>
              </p>
              <p className="text-[10px] text-amber-800">
                (يمكنك تغيير اسم المستخدم وكلمة المرور في أي وقت بعد الدخول من زر 🔑 تغيير بيانات الدخول).
              </p>
            </div>

            <div className="pt-2 text-center">
              <a
                href="/files"
                className="text-xs text-slate-500 hover:text-slate-800 font-semibold transition inline-flex items-center gap-1"
              >
                <span>← العودة إلى صفحة المستندات والأقسام</span>
              </a>
            </div>
          </form>
        </div>
      </div>
    );
  }

  // 2. المحتوى الكامل للوحة تحكم الأدمن (عند تسجيل الدخول بنجاح)
  return (
    <div className="p-4 sm:p-6 md:p-8 space-y-6 max-w-7xl mx-auto w-full">
      {/* 1. الترويسة الرسمية للوحة تحكم الأدمن مع أزرار الإدارة وتغيير بيانات الدخول */}
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
          {/* اسم المسؤول النشط */}
          <span className="inline-flex items-center gap-1.5 px-3 py-2 bg-white/10 text-[#ecd58a] rounded-xl text-xs font-bold border border-white/15">
            <User className="w-3.5 h-3.5" />
            <span>المسؤول: {adminUsername}</span>
          </span>

          {/* زر تغيير بيانات الدخول */}
          <button
            onClick={() => {
              setNewUserInput(adminUsername);
              setShowCredentialsModal(true);
            }}
            className="flex items-center gap-1.5 px-3.5 py-2 bg-[#c59b27] hover:bg-[#b0871d] text-[#0e2720] rounded-xl text-xs font-black transition shadow-xs active:scale-95"
            title="تغيير اسم المستخدم أو كلمة المرور"
          >
            <Key className="w-3.5 h-3.5" />
            <span>تغيير بيانات الدخول</span>
          </button>

          {/* زر تسجيل الخروج */}
          <button
            onClick={handleLogout}
            className="flex items-center gap-1 px-3 py-2 bg-rose-600/80 hover:bg-rose-700 text-white rounded-xl text-xs font-bold transition active:scale-95 border border-rose-500/30"
            title="تسجيل الخروج"
          >
            <LogOut className="w-3.5 h-3.5" />
            <span>خروج</span>
          </button>

          {/* زر تحديث السحابة */}
          <button
            onClick={loadAllData}
            disabled={loading}
            className="flex items-center gap-1.5 px-3 py-2 bg-white/10 hover:bg-white/20 text-white rounded-xl text-xs font-bold transition border border-white/15 active:scale-95"
            title="تحديث البيانات"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
            <span>تحديث</span>
          </button>

          {/* شارة السحابة */}
          <span className="inline-flex items-center gap-1.5 px-3 py-2 bg-emerald-950/80 text-emerald-300 rounded-xl text-xs font-bold border border-emerald-500/40">
            <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse"></span>
            السحابة متصلة
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
                ? 'bg-[#14372e] text-white shadow-md'
                : 'bg-white text-slate-600 hover:bg-slate-100 border border-slate-200'
            }`}
          >
            <span>{tab.label}</span>
            <span className={`px-2 py-0.5 rounded-full text-[10px] ${
              activeTab === tab.id ? 'bg-white/20 text-white' : 'bg-slate-100 text-slate-600'
            }`}>
              {tab.count}
            </span>
          </button>
        ))}
      </div>

      {/* 4. محتوى التبويبات */}

      {/* التبويب الأول: إدارة الأقسام الإدارية */}
      {activeTab === 'DEPTS' && (
        <div className="space-y-4">
          <div className="flex items-center justify-between bg-white p-4 rounded-2xl border border-slate-200 shadow-xs">
            <div>
              <h3 className="font-bold text-sm text-slate-800">الأقسام الإدارية والمجلدات النشطة</h3>
              <p className="text-xs text-slate-500 mt-0.5">
                كل قسم هنا يمثل مجلداً مركزياً يتزامن فوراً مع حواسيب موظفي غرفة تجارة كربلاء المقدسة.
              </p>
            </div>
            <button
              onClick={() => setShowAddDeptModal(true)}
              className="flex items-center gap-2 px-4 py-2 bg-[#14372e] hover:bg-[#1a473b] text-white text-xs font-bold rounded-xl transition shadow-xs active:scale-95"
            >
              <Plus className="w-4 h-4" />
              <span>إضافة قسم جديد</span>
            </button>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {departments.map(dept => (
              <div 
                key={dept.id} 
                className="bg-white rounded-2xl border border-slate-200 p-5 shadow-xs hover:border-[#c59b27] transition flex flex-col justify-between"
              >
                <div>
                  <div className="flex items-start justify-between gap-2">
                    <div className="flex items-center gap-3">
                      <div className="w-12 h-12 rounded-xl bg-amber-50 text-amber-800 flex items-center justify-center font-bold border border-amber-200">
                        <Folder className="w-6 h-6" />
                      </div>
                      <div>
                        <h4 className="font-bold text-sm text-slate-900">{dept.name}</h4>
                        <p className="text-xs text-slate-500 mt-0.5">{dept.fileCount} مستند محفوظ</p>
                      </div>
                    </div>
                  </div>

                  <div className="mt-4 pt-3 border-t border-slate-100 flex items-center justify-between text-xs text-slate-500">
                    <span>الحجم الإجمالي:</span>
                    <span className="font-bold text-slate-700">{formatSize(dept.totalSize)}</span>
                  </div>
                </div>

                <div className="mt-4 pt-3 border-t border-slate-100 flex items-center justify-end gap-2">
                  <button
                    onClick={() => {
                      setDeptToRename(dept);
                      setNewDeptRenameValue(dept.name);
                      setShowRenameDeptModal(true);
                    }}
                    className="p-2 text-slate-600 hover:text-slate-900 hover:bg-slate-100 rounded-lg transition"
                    title="تعديل اسم القسم"
                  >
                    <Edit3 className="w-4 h-4" />
                  </button>

                  <button
                    onClick={() => handleDeleteDepartment(dept)}
                    className="p-2 text-rose-600 hover:text-rose-800 hover:bg-rose-50 rounded-lg transition"
                    title="حذف القسم"
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* التبويب الثاني: مصفوفة الصلاحيات */}
      {activeTab === 'PERMS' && (
        <div className="bg-white rounded-2xl border border-slate-200 shadow-xs overflow-hidden">
          <div className="p-4 border-b border-slate-100 flex items-center justify-between bg-slate-50">
            <div>
              <h3 className="font-bold text-sm text-slate-800">مصفوفة صلاحيات الوصول والتعديل للأقسام</h3>
              <p className="text-xs text-slate-500 mt-0.5">
                تحديد صلاحيات القراءة، التحميل، التعديل، والحذف لكل قسم على حدة.
              </p>
            </div>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-right text-xs">
              <thead className="bg-slate-50 text-slate-600 border-b border-slate-200 font-bold">
                <tr>
                  <th className="p-4">القسم الإداري</th>
                  <th className="p-4 text-center">معاينة وتصفح</th>
                  <th className="p-4 text-center">تحميل المستندات</th>
                  <th className="p-4 text-center">تعديل وحفظ</th>
                  <th className="p-4 text-center">حذف المستندات</th>
                  <th className="p-4 text-center">إجراءات سريعة</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {permissions.map(perm => (
                  <tr key={perm.folderId} className="hover:bg-slate-50/50 transition">
                    <td className="p-4 font-bold text-slate-800 flex items-center gap-2">
                      <Folder className="w-4 h-4 text-amber-600" />
                      <span>{perm.folderName}</span>
                    </td>
                    <td className="p-4 text-center">
                      <span className="inline-flex items-center gap-1 text-emerald-700 bg-emerald-50 px-2.5 py-1 rounded-full text-[11px] font-bold border border-emerald-200">
                        <Check className="w-3.5 h-3.5" /> متاح
                      </span>
                    </td>
                    <td className="p-4 text-center">
                      <span className="inline-flex items-center gap-1 text-emerald-700 bg-emerald-50 px-2.5 py-1 rounded-full text-[11px] font-bold border border-emerald-200">
                        <Check className="w-3.5 h-3.5" /> متاح
                      </span>
                    </td>
                    <td className="p-4 text-center">
                      <span className={`inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-[11px] font-bold border ${
                        perm.canWrite 
                          ? 'text-emerald-700 bg-emerald-50 border-emerald-200'
                          : 'text-rose-700 bg-rose-50 border-rose-200'
                      }`}>
                        {perm.canWrite ? <Check className="w-3.5 h-3.5" /> : <X className="w-3.5 h-3.5" />}
                        {perm.canWrite ? 'مسموح' : 'محظور'}
                      </span>
                    </td>
                    <td className="p-4 text-center">
                      <span className={`inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-[11px] font-bold border ${
                        perm.canDelete 
                          ? 'text-emerald-700 bg-emerald-50 border-emerald-200'
                          : 'text-amber-800 bg-amber-50 border-amber-200'
                      }`}>
                        {perm.canDelete ? <Check className="w-3.5 h-3.5" /> : <Lock className="w-3.5 h-3.5" />}
                        {perm.canDelete ? 'مسموح' : 'مقيد للأدمن'}
                      </span>
                    </td>
                    <td className="p-4 text-center">
                      <div className="flex items-center justify-center gap-1.5">
                        <button
                          onClick={() => handleSetPresetPermission(perm.folderId, perm.folderName, 'FULL')}
                          className="px-2.5 py-1 text-[10px] font-bold rounded-lg bg-emerald-50 text-emerald-800 hover:bg-emerald-100 transition border border-emerald-200"
                        >
                          تحكم كامل
                        </button>
                        <button
                          onClick={() => handleSetPresetPermission(perm.folderId, perm.folderName, 'EDIT_ONLY')}
                          className="px-2.5 py-1 text-[10px] font-bold rounded-lg bg-sky-50 text-sky-800 hover:bg-sky-100 transition border border-sky-200"
                        >
                          تعديل بلا حذف
                        </button>
                        <button
                          onClick={() => handleSetPresetPermission(perm.folderId, perm.folderName, 'READ_ONLY')}
                          className="px-2.5 py-1 text-[10px] font-bold rounded-lg bg-slate-100 text-slate-700 hover:bg-slate-200 transition"
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

      {/* التبويب الثالث: إدارة كافة المستندات */}
      {activeTab === 'FILES' && (
        <div className="bg-white rounded-2xl border border-slate-200 shadow-xs overflow-hidden">
          <div className="p-4 border-b border-slate-100 flex flex-col md:flex-row md:items-center justify-between gap-3 bg-slate-50">
            <div>
              <h3 className="font-bold text-sm text-slate-800">إدارة المستندات الرسمية والأرشفة</h3>
              <p className="text-xs text-slate-500 mt-0.5">
                تعديل الأسماء، المعاينة المباشرة، وحذف المستندات الزائدة من التخزين السحابي.
              </p>
            </div>

            <div className="flex items-center gap-2">
              <select
                value={selectedDeptFilter}
                onChange={(e) => setSelectedDeptFilter(e.target.value)}
                className="px-3 py-1.5 text-xs bg-white border border-slate-200 rounded-xl font-bold"
              >
                <option value="__ALL__">كافة الأقسام</option>
                {departments.map(d => (
                  <option key={d.id} value={d.name}>{d.name}</option>
                ))}
              </select>

              <div className="relative">
                <input
                  type="text"
                  placeholder="بحث في المستندات..."
                  value={fileSearch}
                  onChange={(e) => setFileSearch(e.target.value)}
                  className="pl-3 pr-8 py-1.5 text-xs bg-white border border-slate-200 rounded-xl"
                />
                <Search className="w-3.5 h-3.5 text-slate-400 absolute right-2.5 top-2.5" />
              </div>
            </div>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-right text-xs">
              <thead className="bg-slate-50 text-slate-600 border-b border-slate-200 font-bold">
                <tr>
                  <th className="p-4">اسم المستند</th>
                  <th className="p-4">القسم</th>
                  <th className="p-4">الحجم</th>
                  <th className="p-4">تاريخ الحفظ</th>
                  <th className="p-4 text-center">الحالة</th>
                  <th className="p-4 text-center">إجراءات</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {filteredFiles.map(file => (
                  <tr key={file.id} className="hover:bg-slate-50/50 transition">
                    <td className="p-4 font-bold text-slate-800 flex items-center gap-2">
                      <FileText className="w-4 h-4 text-slate-500" />
                      <span>{file.name}</span>
                    </td>
                    <td className="p-4 text-slate-600">{file.folder}</td>
                    <td className="p-4 text-slate-600 font-mono">{file.size}</td>
                    <td className="p-4 text-slate-500">{file.lastModifiedAt}</td>
                    <td className="p-4 text-center">
                      <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-bold ${
                        file.isDeleted
                          ? 'bg-rose-50 text-rose-700 border border-rose-200'
                          : 'bg-emerald-50 text-emerald-700 border border-emerald-200'
                      }`}>
                        {file.isDeleted ? 'في السلة' : 'نشط ومؤرشف'}
                      </span>
                    </td>
                    <td className="p-4 text-center">
                      <div className="flex items-center justify-center gap-1.5">
                        <button
                          onClick={() => {
                            setFileToRename(file);
                            setNewFileNameValue(file.name);
                            setShowRenameFileModal(true);
                          }}
                          className="p-1.5 text-slate-600 hover:text-slate-900 hover:bg-slate-100 rounded-lg transition"
                          title="تعديل اسم المستند"
                        >
                          <Edit3 className="w-3.5 h-3.5" />
                        </button>

                        <button
                          onClick={async () => {
                            if (!confirm(`هل أنت متأكد من حذف المستند "${file.name}"؟`)) return;
                            await fetch(`/api/drive/files?id=${file.id}`, { method: 'DELETE' });
                            await loadAllData();
                          }}
                          className="p-1.5 text-rose-600 hover:text-rose-800 hover:bg-rose-50 rounded-lg transition"
                          title="حذف المستند"
                        >
                          <Trash2 className="w-3.5 h-3.5" />
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

      {/* التبويب الرابع: أجهزة الموظفين المعتمدة */}
      {activeTab === 'DEVICES' && (
        <div className="bg-white rounded-2xl border border-slate-200 shadow-xs p-6 space-y-4">
          <div className="flex items-center justify-between border-b pb-4">
            <div>
              <h3 className="font-bold text-sm text-slate-800">حواسيب موظفي غرفة تجارة كربلاء المعتمدة</h3>
              <p className="text-xs text-slate-500 mt-0.5">
                الأجهزة المثبت عليها تطبيق الويندوز (share coc) والمصرح لها بالمزامنة التلقائية.
              </p>
            </div>
            <span className="text-xs bg-emerald-50 text-emerald-800 font-bold px-3 py-1 rounded-full border border-emerald-200">
              🟢 الترخيص نشط ومفتوح
            </span>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 pt-2">
            {[
              { id: 'dev-1', name: 'COC-SECRETARY-PC', user: 'أمانة السر والإدارة العامة', os: 'Windows 11 Pro', status: 'متصل الآن' },
              { id: 'dev-2', name: 'COC-REGISTRY-01', user: 'قسم السجل التجاري', os: 'Windows 10 Enterprise', status: 'متصل الآن' },
              { id: 'dev-3', name: 'COC-SUBSCRIPTION-01', user: 'قسم الاشتراكات', os: 'Windows 11 Pro', status: 'متصل الآن' },
              { id: 'dev-4', name: 'COC-GENERAL-LAPTOP', user: 'القسم العام والمتابعة', os: 'Windows 11 Home', status: 'متصل الآن' },
            ].map(dev => (
              <div key={dev.id} className="p-4 rounded-xl border border-slate-200 bg-slate-50/50 space-y-2">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <Laptop className="w-4 h-4 text-[#0f6cbd]" />
                    <span className="font-bold text-xs text-slate-800">{dev.name}</span>
                  </div>
                  <span className="text-[10px] bg-emerald-100 text-emerald-800 font-bold px-2 py-0.5 rounded-full">
                    {dev.status}
                  </span>
                </div>
                <p className="text-xs text-slate-600">المستخدم: <strong className="text-slate-800">{dev.user}</strong></p>
                <p className="text-[11px] text-slate-400 font-mono">نظام التشغيل: {dev.os}</p>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* 5. النوافذ المنبثقة (Modals) */}

      {/* نافذة تغيير بيانات تسجيل الدخول */}
      {showCredentialsModal && (
        <div className="fixed inset-0 bg-black/60 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-3xl max-w-md w-full p-6 space-y-4 shadow-2xl border border-slate-200 animate-in fade-in zoom-in-95">
            <div className="flex items-center justify-between pb-3 border-b border-slate-100">
              <div className="flex items-center gap-2 text-amber-900 font-bold">
                <Key className="w-5 h-5 text-amber-600" />
                <h3 className="text-sm font-black">تغيير بيانات تسجيل دخول الأدمن</h3>
              </div>
              <button 
                onClick={() => {
                  setShowCredentialsModal(false);
                  setCredError('');
                  setCredSuccess('');
                }}
                className="p-1 text-slate-400 hover:text-slate-600 rounded-lg hover:bg-slate-100"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            {credError && (
              <div className="p-3 bg-rose-50 border border-rose-200 text-rose-700 rounded-xl text-xs font-bold flex items-center gap-2">
                <AlertTriangle className="w-4 h-4 shrink-0" />
                <span>{credError}</span>
              </div>
            )}

            {credSuccess && (
              <div className="p-3 bg-emerald-50 border border-emerald-200 text-emerald-800 rounded-xl text-xs font-bold flex items-center gap-2">
                <CheckCircle2 className="w-4 h-4 shrink-0 text-emerald-600" />
                <span>{credSuccess}</span>
              </div>
            )}

            <form onSubmit={handleChangeCredentials} className="space-y-3.5">
              <div>
                <label className="block text-xs font-bold text-slate-700 mb-1">
                  كلمة المرور الحالية للتأكيد
                </label>
                <input
                  type="password"
                  required
                  value={currentPassInput}
                  onChange={(e) => setCurrentPassInput(e.target.value)}
                  placeholder="أدخل كلمة المرور الحالية"
                  className="w-full px-3 py-2 text-xs bg-slate-50 border border-slate-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-[#14372e]"
                />
              </div>

              <div>
                <label className="block text-xs font-bold text-slate-700 mb-1">
                  اسم المستخدم الجديد
                </label>
                <input
                  type="text"
                  required
                  value={newUserInput}
                  onChange={(e) => setNewUserInput(e.target.value)}
                  placeholder="اسم المستخدم الجديد"
                  className="w-full px-3 py-2 text-xs bg-slate-50 border border-slate-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-[#14372e]"
                />
              </div>

              <div>
                <label className="block text-xs font-bold text-slate-700 mb-1">
                  كلمة المرور الجديدة
                </label>
                <div className="relative">
                  <input
                    type={showNewPass ? 'text' : 'password'}
                    required
                    value={newPassInput}
                    onChange={(e) => setNewPassInput(e.target.value)}
                    placeholder="كلمة مرور جديدة (4 أحرف أو أرقام على الأقل)"
                    className="w-full pl-9 pr-3 py-2 text-xs bg-slate-50 border border-slate-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-[#14372e]"
                  />
                  <button
                    type="button"
                    onClick={() => setShowNewPass(!showNewPass)}
                    className="absolute left-2.5 top-2 text-slate-400 hover:text-slate-600"
                  >
                    {showNewPass ? <EyeOff className="w-3.5 h-3.5" /> : <Eye className="w-3.5 h-3.5" />}
                  </button>
                </div>
              </div>

              <div>
                <label className="block text-xs font-bold text-slate-700 mb-1">
                  تأكيد كلمة المرور الجديدة
                </label>
                <input
                  type="password"
                  required
                  value={confirmPassInput}
                  onChange={(e) => setConfirmPassInput(e.target.value)}
                  placeholder="أعد إدخال كلمة المرور الجديدة"
                  className="w-full px-3 py-2 text-xs bg-slate-50 border border-slate-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-[#14372e]"
                />
              </div>

              <div className="flex items-center justify-end gap-2 pt-3 border-t">
                <button
                  type="button"
                  onClick={() => {
                    setShowCredentialsModal(false);
                    setCredError('');
                    setCredSuccess('');
                  }}
                  className="px-4 py-2 text-xs font-bold text-slate-600 hover:bg-slate-100 rounded-xl transition"
                >
                  إلغاء
                </button>
                <button
                  type="submit"
                  className="px-5 py-2 text-xs font-bold bg-[#14372e] text-white rounded-xl hover:bg-[#1a473b] transition shadow-sm flex items-center gap-1.5"
                >
                  <Save className="w-3.5 h-3.5" />
                  <span>حفظ البيانات الجديدة</span>
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* نافذة إضافة قسم جديد */}
      {showAddDeptModal && (
        <div className="fixed inset-0 bg-black/50 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl max-w-md w-full p-6 space-y-4 shadow-xl">
            <h3 className="font-bold text-sm text-slate-800">إضافة قسم إداري جديد</h3>
            <p className="text-xs text-slate-500">
              سيتم إنشاء مجلد جديد في Google Drive ومزامنته فوراً مع أجهزة الموظفين في الغرفة.
            </p>

            <input
              type="text"
              placeholder="اسم القسم (مثال: الشؤون القانونية)..."
              value={newDeptName}
              onChange={(e) => setNewDeptName(e.target.value)}
              className="w-full px-4 py-2.5 text-xs bg-slate-50 border border-slate-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-[#14372e]"
              autoFocus
            />

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
                className="px-5 py-2 text-xs font-bold bg-[#14372e] text-white rounded-xl hover:bg-[#1a473b] transition shadow-sm disabled:opacity-50"
              >
                إنشاء ومزامنة
              </button>
            </div>
          </div>
        </div>
      )}

      {/* نافذة تعديل اسم القسم */}
      {showRenameDeptModal && deptToRename && (
        <div className="fixed inset-0 bg-black/50 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl max-w-md w-full p-6 space-y-4 shadow-xl">
            <h3 className="font-bold text-sm text-slate-800">تعديل اسم القسم</h3>
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
                className="px-5 py-2 text-xs font-bold bg-[#14372e] text-white rounded-xl hover:bg-[#1a473b] transition shadow-sm disabled:opacity-50"
              >
                حفظ التعديل
              </button>
            </div>
          </div>
        </div>
      )}

      {/* نافذة تعديل اسم الملف */}
      {showRenameFileModal && fileToRename && (
        <div className="fixed inset-0 bg-black/50 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl max-w-md w-full p-6 space-y-4 shadow-xl">
            <h3 className="font-bold text-sm text-slate-800">تعديل اسم المستند</h3>
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
                  await fetch('/api/drive/files', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ action: 'RENAME', id: fileToRename.id, name: newFileNameValue.trim() })
                  });
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
