'use client';

import { useState, useEffect, useRef } from 'react';
import {
  Shield,
  Folder,
  Edit3,
  Trash2,
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
  Eye,
  EyeOff,
  CheckCircle2,
  LogOut,
  User,
  RotateCcw,
  Database,
  Columns,
  Users,
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
  canUpload: boolean;
  canCreateFolder: boolean;
  canEdit: boolean;
  canRename: boolean;
  canMove: boolean;
  canDelete: boolean;
  canPermanentDelete: boolean;
  pinCode?: string;
}

interface DeviceRecord {
  id: string;
  name: string;
  user: string;
  os: string;
  machineGuid: string;
  isAuthorized: boolean;
  lastSeen: string;
  status?: string;
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
  // حالة تسجيل الدخول والأمان المتزامنة مع السحابة
  const [isAuthenticated, setIsAuthenticated] = useState<boolean>(false);
  const [isCheckingAuth, setIsCheckingAuth] = useState<boolean>(true);
  const [adminUsername, setAdminUsername] = useState<string>('admin');
  const [adminPassword, setAdminPassword] = useState<string>('admin1234');

  // حقول نموذج تسجيل الدخول
  const [loginUser, setLoginUser] = useState<string>('');
  const [loginPass, setLoginPass] = useState<string>('');
  const [showLoginPass, setShowLoginPass] = useState<boolean>(false);
  const [loginError, setLoginError] = useState<string>('');
  const [loggingIn, setLoggingIn] = useState<boolean>(false);

  // نافذة وتبويب تعديل بيانات الدخول (اليوزر والباسورد)
  const [showCredentialsModal, setShowCredentialsModal] = useState<boolean>(false);
  const [currentPassInput, setCurrentPassInput] = useState<string>('');
  const [newUserInput, setNewUserInput] = useState<string>('admin');
  const [newPassInput, setNewPassInput] = useState<string>('');
  const [confirmPassInput, setConfirmPassInput] = useState<string>('');
  const [showCurrentPass, setShowCurrentPass] = useState<boolean>(false);
  const [showNewPass, setShowNewPass] = useState<boolean>(false);
  const [savingCredentials, setSavingCredentials] = useState<boolean>(false);
  const [credError, setCredError] = useState<string>('');
  const [credSuccess, setCredSuccess] = useState<string>('');

  // التبويب النشط في لوحة الأدمن
  const [activeTab, setActiveTab] = useState<'DEPTS' | 'ACCESS_HUB' | 'PERMS' | 'FILES' | 'DEVICES' | 'ACCOUNT'>('DEPTS');
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState(false);

  // حالة مركز قواعد بيانات Access الموحدة
  const [accessHubSubTab, setAccessHubSubTab] = useState<'SECTIONS' | 'FIELDS' | 'ROLES' | 'TRASH'>('SECTIONS');
  const [accessFiles, setAccessFiles] = useState<any[]>([]);
  const [accessAllFiles, setAccessAllFiles] = useState<any[]>([]);
  const [accessDeletedSections, setAccessDeletedSections] = useState<string[]>([]);
  const [accessTrashBin, setAccessTrashBin] = useState<any[]>([]);
  const [accessRoles, setAccessRoles] = useState<Record<string, any>>({});
  const [accessTotalRecords, setAccessTotalRecords] = useState<number>(88987);
  const [accessLoading, setAccessLoading] = useState<boolean>(false);

  // اختيارات إدارة الحقول
  const [selectedAccessFile, setSelectedAccessFile] = useState<string>('');
  const [selectedAccessTable, setSelectedAccessTable] = useState<string>('');
  const [accessTablesList, setAccessTablesList] = useState<string[]>([]);
  const [accessColumnsList, setAccessColumnsList] = useState<string[]>([]);
  const [newColNameInput, setNewColNameInput] = useState<string>('');

  // نموذج إضافة جهاز Access Hub
  const [newRoleGuid, setNewRoleGuid] = useState<string>('');
  const [newRoleName, setNewRoleName] = useState<string>('');
  const [newRoleType, setNewRoleType] = useState<'admin' | 'data_entry' | 'viewer'>('data_entry');

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
  const [selectedPermDept, setSelectedPermDept] = useState<PermissionRule | null>(null);
  const [pinInput, setPinInput] = useState('');
  const lastPermSaveRef = useRef<number>(0);
  const isSavingPermsRef = useRef<boolean>(false);

  // بيانات الملفات
  const [files, setFiles] = useState<FileRecord[]>([]);
  const [selectedDeptFilter, setSelectedDeptFilter] = useState('__ALL__');
  const [fileSearch, setFileSearch] = useState('');
  const [showRenameFileModal, setShowRenameFileModal] = useState(false);
  const [fileToRename, setFileToRename] = useState<FileRecord | null>(null);
  const [newFileNameValue, setNewFileNameValue] = useState('');

  // بيانات الأجهزة المعتمدة
  const [devices, setDevices] = useState<DeviceRecord[]>([]);
  const [showAddDeviceModal, setShowAddDeviceModal] = useState(false);
  const [newDeviceName, setNewDeviceName] = useState('');
  const [newDeviceUser, setNewDeviceUser] = useState('');
  const [newDeviceOs, setNewDeviceOs] = useState('Windows 11 Pro');

  // إشعار عائم
  const [toastMessage, setToastMessage] = useState<{ text: string; type: 'success' | 'error' | 'info' } | null>(null);

  useEffect(() => {
    if (toastMessage) {
      const t = setTimeout(() => setToastMessage(null), 4500);
      return () => clearTimeout(t);
    }
  }, [toastMessage]);

  // إشعار تطبيق سطح المكتب المحلي بالمزامنة الفورية بعد أي تغيير في الصلاحيات أو الأقسام
  const notifyLocalDesktopSync = () => {
    try {
      fetch('http://127.0.0.1:18290/sync', { method: 'GET', mode: 'cors' }).catch(() => {});
    } catch {
      // تجاهل إن لم يكن تطبيق سطح المكتب يعمل على نفس الجهاز
    }
  };

  // التحقق من الجلسة ومزامنة بيانات دخول الأدمن من السحابة عند التحميل
  useEffect(() => {
    let mounted = true;
    const initAuth = async () => {
      try {
        if (typeof window !== 'undefined') {
          const localUser = localStorage.getItem('sharecoc_admin_username') || 'admin';
          const localPass = localStorage.getItem('sharecoc_admin_password') || 'admin1234';
          setAdminUsername(localUser);
          setAdminPassword(localPass);
          setNewUserInput(localUser);

          const sessionActive = localStorage.getItem('sharecoc_admin_session');
          if (sessionActive === 'true') {
            setIsAuthenticated(true);
          }

          const urlParams = new URLSearchParams(window.location.search);
          const tabParam = urlParams.get('tab');
          if (tabParam === 'access' || tabParam === 'access_hub' || tabParam === 'fields') {
            setActiveTab('ACCESS_HUB');
            if (tabParam === 'fields') {
              setAccessHubSubTab('FIELDS');
            }
          }
        }

        // جلب بيانات الاعتماد الحقيقية المحفوظة في السحابة
        const res = await fetch('/api/drive/permissions?force=1', { cache: 'no-store' });
        const data = await res.json();
        if (mounted && data.success && data.adminCredentials) {
          const cloudUser = data.adminCredentials.username || 'admin';
          const cloudPass = data.adminCredentials.password || 'admin1234';
          setAdminUsername(cloudUser);
          setAdminPassword(cloudPass);
          setNewUserInput(cloudUser);
          if (typeof window !== 'undefined') {
            localStorage.setItem('sharecoc_admin_username', cloudUser);
            localStorage.setItem('sharecoc_admin_password', cloudPass);
          }
        }
        if (mounted && data.success && Array.isArray(data.devices)) {
          setDevices(data.devices);
        }
      } catch (e) {
        console.error('Error syncing cloud admin credentials:', e);
      } finally {
        if (mounted) {
          setIsCheckingAuth(false);
        }
      }
    };
    initAuth();
    return () => {
      mounted = false;
    };
  }, []);

  const formatSize = (bytes: number) => {
    if (!bytes || bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return `${parseFloat((bytes / Math.pow(k, i)).toFixed(2))} ${sizes[i]}`;
  };

  const loadAllData = async (isBackgroundPoll: boolean = false) => {
    try {
      if (!isBackgroundPoll) {
        setLoading(true);
      }

      const res = await fetch('/api/drive/files', { cache: 'no-store' });
      const data = await res.json();
      if (data.success) {
        if (data.adminCredentials && !savingCredentials) {
          const cUser = data.adminCredentials.username || 'admin';
          const cPass = data.adminCredentials.password || 'admin1234';
          setAdminUsername(cUser);
          setAdminPassword(cPass);
          if (typeof window !== 'undefined') {
            localStorage.setItem('sharecoc_admin_username', cUser);
            localStorage.setItem('sharecoc_admin_password', cPass);
          }
        }

        if (Array.isArray(data.devices) && !actionLoading) {
          setDevices(data.devices);
        }

        const folderMap = new Map<string, DepartmentItem>();
        (data.folders || []).forEach((f: any) => {
          if (f.name) {
            folderMap.set(f.name, {
              id: f.id,
              name: f.name,
              fileCount: 0,
              totalSize: 0,
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
          lastModifiedAt: f.modifiedTime
            ? new Date(f.modifiedTime).toLocaleDateString('ar-IQ', {
                month: 'short',
                day: 'numeric',
                hour: '2-digit',
                minute: '2-digit',
              })
            : 'الآن',
          storagePath: f.id,
          isDeleted: Boolean(f.isDeleted),
        }));
        setFiles(mappedFiles);

        mappedFiles.forEach((f) => {
          if (!f.isDeleted && f.folder && f.folder !== 'كافة الملفات') {
            const deptName = f.folder.split('/')[0];
            if (!folderMap.has(deptName)) {
              folderMap.set(deptName, {
                id: deptName,
                name: deptName,
                fileCount: 0,
                totalSize: 0,
              });
            }
            const item = folderMap.get(deptName)!;
            item.fileCount += 1;
            item.totalSize += f.rawSize;
          }
        });

        const deptsList = Array.from(folderMap.values());
        setDepartments(deptsList);

        // عدم الكتابة فوق الصلاحيات أثناء الحفظ أو بعده مباشرة لمنع رجوع الأزرار لحالتها القديمة
        const recentlySaved = Date.now() - lastPermSaveRef.current < 8000;
        if (!isSavingPermsRef.current && (!isBackgroundPoll || !recentlySaved)) {
          const cloudPerms = data.permissions || {};
          const permsList: PermissionRule[] = deptsList.map((dept) => {
            const saved = cloudPerms[dept.name] || {};
            return {
              folderId: dept.id,
              folderName: dept.name,
              canView: saved.canView !== undefined ? Boolean(saved.canView) : true,
              canDownload: saved.canDownload !== undefined ? Boolean(saved.canDownload) : true,
              canUpload: saved.canUpload !== undefined ? Boolean(saved.canUpload) : true,
              canCreateFolder: saved.canCreateFolder !== undefined ? Boolean(saved.canCreateFolder) : true,
              canEdit: saved.canEdit !== undefined ? Boolean(saved.canEdit) : true,
              canRename: saved.canRename !== undefined ? Boolean(saved.canRename) : true,
              canMove: saved.canMove !== undefined ? Boolean(saved.canMove) : true,
              canDelete: saved.canDelete !== undefined ? Boolean(saved.canDelete) : true,
              canPermanentDelete: saved.canPermanentDelete !== undefined ? Boolean(saved.canPermanentDelete) : true,
              pinCode: saved.pinCode || '',
            };
          });
          setPermissions(permsList);
        }
      }
    } catch (err) {
      console.error('Error fetching admin data:', err);
    } finally {
      if (!isBackgroundPoll) {
        setLoading(false);
      }
    }
  };

  useEffect(() => {
    if (!isAuthenticated) return;
    loadAllData(false);
    loadAccessHubData();
    const interval = setInterval(() => {
      loadAllData(true);
    }, 15000);
    return () => clearInterval(interval);
  }, [isAuthenticated]);

  // جلب بيانات مركز قواعد بيانات Access
  const loadAccessHubData = async () => {
    try {
      setAccessLoading(true);
      const res = await fetch('/api/access-hub?file=all&limit=1', { cache: 'no-store' });
      const data = await res.json();
      if (data.success) {
        setAccessFiles(data.files || []);
        setAccessAllFiles(data.all_files || data.files || []);
        setAccessDeletedSections(data.deleted_sections || []);
        setAccessTrashBin(data.trash_bin || []);
        setAccessRoles(data.roles || {});
        setAccessTotalRecords(data.total_records || 88987);

        // ضبط القسم والجدول المختار افتراضياً
        const activeFiles = data.files || [];
        if (activeFiles.length > 0 && !selectedAccessFile) {
          const firstFile = activeFiles[0];
          setSelectedAccessFile(firstFile.name);
          setAccessTablesList(firstFile.tables || []);
          if (firstFile.tables && firstFile.tables.length > 0) {
            const firstTable = firstFile.tables[0];
            setSelectedAccessTable(firstTable);
            fetchColumnsForTable(firstFile.name, firstTable);
          }
        }
      }
    } catch (err) {
      console.error('Failed to load Access Hub data in admin:', err);
    } finally {
      setAccessLoading(false);
    }
  };

  // جلب أعمدة جدول معين
  const fetchColumnsForTable = async (fileName: string, tableName: string) => {
    if (!fileName || !tableName) return;
    try {
      const res = await fetch(`/api/access-hub?file=${encodeURIComponent(fileName)}&table=${encodeURIComponent(tableName)}&limit=1`, { cache: 'no-store' });
      const data = await res.json();
      if (data.success) {
        setAccessColumnsList(data.columns || []);
      }
    } catch (err) {
      console.error('Failed to fetch columns:', err);
    }
  };

  // حذف أو أرشفة قسم
  const handleDeleteSection = async (fileName: string) => {
    if (!confirm(`⚠️ تحذير أمني:\nهل أنت متأكد من حذف وأرشفة القسم "${fileName}"؟\nسيتم إخفاؤه فوراً عن كافة الموظفين وتطبيقات سطح المكتب.`)) {
      return;
    }
    try {
      setActionLoading(true);
      const res = await fetch('/api/access-hub', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'DELETE_SECTION', fileName }),
      });
      const data = await res.json();
      if (data.success) {
        setToastMessage({ text: `✅ تم حذف وأرشفة القسم "${fileName}" بنجاح`, type: 'success' });
        await loadAccessHubData();
      } else {
        alert(data.error || 'فشل حذف القسم');
      }
    } catch (err: any) {
      alert(`خطأ: ${err.message}`);
    } finally {
      setActionLoading(false);
    }
  };

  // استعادة قسم مؤرشف
  const handleRestoreSection = async (fileName: string) => {
    try {
      setActionLoading(true);
      const res = await fetch('/api/access-hub', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'RESTORE_SECTION', fileName }),
      });
      const data = await res.json();
      if (data.success) {
        setToastMessage({ text: `✅ تمت استعادة القسم "${fileName}" وإتاحته للجميع`, type: 'success' });
        await loadAccessHubData();
      }
    } catch (err: any) {
      alert(`خطأ: ${err.message}`);
    } finally {
      setActionLoading(false);
    }
  };

  // إضافة حقل جديد
  const handleAddAccessColumn = async () => {
    const colName = newColNameInput.trim();
    if (!colName) {
      alert('يرجى كتابة اسم الحقل أولاً');
      return;
    }
    if (!selectedAccessFile || !selectedAccessTable) {
      alert('يرجى تحديد القسم والجدول أولاً');
      return;
    }
    try {
      setActionLoading(true);
      const res = await fetch('/api/access-hub', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          action: 'ADD_COLUMN',
          file: selectedAccessFile,
          table: selectedAccessTable,
          columnName: colName,
        }),
      });
      const data = await res.json();
      if (data.success) {
        setToastMessage({ text: `✅ تمت إضافة الحقل "${colName}" سحابياً وتعميمه`, type: 'success' });
        setNewColNameInput('');
        await fetchColumnsForTable(selectedAccessFile, selectedAccessTable);
      } else {
        alert(data.error || 'فشلت إضافة الحقل');
      }
    } catch (err: any) {
      alert(`خطأ: ${err.message}`);
    } finally {
      setActionLoading(false);
    }
  };

  // حذف حقل
  const handleDeleteAccessColumn = async (colName: string) => {
    if (!confirm(`⚠️ تحذير أمني:\nهل أنت متأكد من حذف الحقل "${colName}" من جدول (${selectedAccessTable})؟\nسيتم إخفاؤه وحذفه من العرض لجميع المستخدمين.`)) {
      return;
    }
    try {
      setActionLoading(true);
      const res = await fetch('/api/access-hub', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          action: 'DELETE_COLUMN',
          file: selectedAccessFile,
          table: selectedAccessTable,
          columnName: colName,
        }),
      });
      const data = await res.json();
      if (data.success) {
        setToastMessage({ text: `✅ تم حذف الحقل "${colName}" بنجاح`, type: 'success' });
        await fetchColumnsForTable(selectedAccessFile, selectedAccessTable);
      } else {
        alert(data.error || 'فشل حذف الحقل');
      }
    } catch (err: any) {
      alert(`خطأ: ${err.message}`);
    } finally {
      setActionLoading(false);
    }
  };

  // استعادة قيد من سلة المهملات
  const handleRestoreTrashRecord = async (id: string) => {
    try {
      setActionLoading(true);
      const res = await fetch('/api/access-hub', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'RESTORE_RECORD', id }),
      });
      const data = await res.json();
      if (data.success) {
        setToastMessage({ text: '✅ تمت استعادة القيد من سلة المحذوفات بنجاح', type: 'success' });
        await loadAccessHubData();
      } else {
        alert(data.error || 'فشلت استعادة القيد');
      }
    } catch (err: any) {
      alert(`خطأ: ${err.message}`);
    } finally {
      setActionLoading(false);
    }
  };

  // حفظ صلاحية جهاز في Access Hub
  const handleSaveAccessRole = async (guid: string, name: string, role: 'admin' | 'data_entry' | 'viewer') => {
    try {
      setActionLoading(true);
      const res = await fetch('/api/access-hub', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'SET_ROLE', guid, name, role }),
      });
      const data = await res.json();
      if (data.success) {
        setToastMessage({ text: `✅ تم تحديث وتطبيق صلاحية الجهاز (${name}) إلى [${role}]`, type: 'success' });
        await loadAccessHubData();
      } else {
        alert(data.error || 'فشل حفظ الصلاحية');
      }
    } catch (err: any) {
      alert(`خطأ: ${err.message}`);
    } finally {
      setActionLoading(false);
    }
  };

  // معالجة تسجيل الدخول المتزامن مع السحابة
  const handleLogin = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    setLoginError('');
    const inputUser = loginUser.trim();
    const inputPass = loginPass;

    if (!inputUser || !inputPass) {
      setLoginError('يرجى إدخال اسم المستخدم وكلمة المرور');
      return;
    }

    setLoggingIn(true);
    try {
      // التحقق السحابي المباشر أولاً
      const res = await fetch('/api/drive/permissions', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          action: 'VERIFY_CREDENTIALS',
          username: inputUser,
          password: inputPass,
        }),
      });
      const data = await res.json();

      if (data.success && data.adminCredentials) {
        const cUser = data.adminCredentials.username || 'admin';
        const cPass = data.adminCredentials.password || 'admin1234';
        setAdminUsername(cUser);
        setAdminPassword(cPass);
        localStorage.setItem('sharecoc_admin_username', cUser);
        localStorage.setItem('sharecoc_admin_password', cPass);

        if (data.valid) {
          setIsAuthenticated(true);
          localStorage.setItem('sharecoc_admin_session', 'true');
          setNewUserInput(cUser);
          setLoginPass('');
          setLoginError('');
          setToastMessage({
            text: `✅ مرحباً بك يا ${cUser}، تم تسجيل الدخول إلى لوحة التحكم بنجاح!`,
            type: 'success',
          });
          return;
        }
      }

      // التحقق الاحتياطي المحلي في حال تعذر الاتصال اللحظي
      const storedUser = localStorage.getItem('sharecoc_admin_username') || adminUsername || 'admin';
      const storedPass = localStorage.getItem('sharecoc_admin_password') || adminPassword || 'admin1234';

      if (inputUser.toLowerCase() === storedUser.toLowerCase() && inputPass === storedPass) {
        setIsAuthenticated(true);
        localStorage.setItem('sharecoc_admin_session', 'true');
        setNewUserInput(storedUser);
        setLoginPass('');
        setLoginError('');
        setToastMessage({
          text: `✅ مرحباً بك يا ${storedUser}، تم تسجيل الدخول بنجاح!`,
          type: 'success',
        });
      } else {
        setLoginError('اسم المستخدم أو كلمة المرور غير صحيحة، يرجى التحقق وإعادة المحاولة.');
      }
    } catch {
      const storedUser = localStorage.getItem('sharecoc_admin_username') || adminUsername || 'admin';
      const storedPass = localStorage.getItem('sharecoc_admin_password') || adminPassword || 'admin1234';
      if (inputUser.toLowerCase() === storedUser.toLowerCase() && inputPass === storedPass) {
        setIsAuthenticated(true);
        localStorage.setItem('sharecoc_admin_session', 'true');
        setLoginPass('');
      } else {
        setLoginError('اسم المستخدم أو كلمة المرور غير صحيحة.');
      }
    } finally {
      setLoggingIn(false);
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

  // تعديل وحفظ بيانات تسجيل الدخول (اليوزر والباسورد) فعلياً في السحابة والمتصفح
  const handleChangeCredentials = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    setCredError('');
    setCredSuccess('');

    const targetUsername = (newUserInput || adminUsername).trim();
    const targetPassword = newPassInput.trim() ? newPassInput.trim() : adminPassword;

    if (!targetUsername) {
      setCredError('يرجى إدخال اسم مستخدم صالح.');
      return;
    }

    // إذا أدخل كلمة مرور حالية نتحقق منها، وإذا كان مسجلاً دخوله بالفعل نسمح له بالتحديث المباشر
    if (currentPassInput.trim() && currentPassInput !== adminPassword) {
      setCredError('كلمة المرور الحالية المدخلة غير مطابقة لكلمة المرور المسجلة!');
      return;
    }

    if (newPassInput.trim()) {
      if (newPassInput.trim().length < 4) {
        setCredError('كلمة المرور الجديدة يجب أن تتكون من 4 أحرف أو أرقام على الأقل.');
        return;
      }
      if (confirmPassInput.trim() && newPassInput.trim() !== confirmPassInput.trim()) {
        setCredError('كلمة المرور الجديدة وتأكيدها غير متطابقين!');
        return;
      }
    }

    try {
      setSavingCredentials(true);
      const res = await fetch('/api/drive/permissions', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          action: 'UPDATE_CREDENTIALS',
          username: targetUsername,
          password: targetPassword,
        }),
      });
      const data = await res.json();
      if (!data.success) {
        throw new Error(data.error || 'فشل حفظ بيانات الدخول في السحابة');
      }

      const savedUser = data.adminCredentials?.username || targetUsername;
      const savedPass = data.adminCredentials?.password || targetPassword;

      localStorage.setItem('sharecoc_admin_username', savedUser);
      localStorage.setItem('sharecoc_admin_password', savedPass);
      setAdminUsername(savedUser);
      setAdminPassword(savedPass);
      setNewUserInput(savedUser);
      setCurrentPassInput('');
      setNewPassInput('');
      setConfirmPassInput('');

      const msg = `✅ تم تحديث وحفظ بيانات الدخول في السحابة بنجاح! (المستخدم: ${savedUser})`;
      setCredSuccess(msg);
      setToastMessage({
        text: msg,
        type: 'success',
      });

      if (showCredentialsModal) {
        setTimeout(() => {
          setShowCredentialsModal(false);
          setCredError('');
          setCredSuccess('');
        }, 1200);
      }
    } catch (err: any) {
      setCredError(err.message || 'حدث خطأ أثناء حفظ بيانات الدخول في السحابة');
    } finally {
      setSavingCredentials(false);
    }
  };

  // إعادة ضبط اليوزر والباسورد إلى الافتراضي (admin / admin1234)
  const handleResetDefaultCredentials = async () => {
    if (!confirm('هل تريد إعادة ضبط اسم المستخدم إلى (admin) وكلمة المرور إلى (admin1234) وحفظها في السحابة؟')) {
      return;
    }
    try {
      setSavingCredentials(true);
      setCredError('');
      setCredSuccess('');
      const res = await fetch('/api/drive/permissions', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          action: 'UPDATE_CREDENTIALS',
          username: 'admin',
          password: 'admin1234',
        }),
      });
      const data = await res.json();
      if (!data.success) throw new Error(data.error);

      localStorage.setItem('sharecoc_admin_username', 'admin');
      localStorage.setItem('sharecoc_admin_password', 'admin1234');
      setAdminUsername('admin');
      setAdminPassword('admin1234');
      setNewUserInput('admin');
      setNewPassInput('');
      setConfirmPassInput('');
      setCredSuccess('✅ تمت استعادة بيانات الدخول الافتراضية (admin / admin1234) بنجاح!');
      setToastMessage({
        text: '🔑 تمت استعادة اليوزر والباسورد الافتراضي (admin / admin1234) في السحابة!',
        type: 'success',
      });
    } catch (err: any) {
      setCredError(err.message || 'تعذر إعادة ضبط بيانات الدخول');
    } finally {
      setSavingCredentials(false);
    }
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
      await loadAllData(false);
      notifyLocalDesktopSync();

      setToastMessage({
        text: `🎉 تم إنشاء القسم "${deptName}" بنجاح ومزامنته مع سحابة Google Drive وتطبيق الحاسوب!`,
        type: 'success',
      });
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
      await loadAllData(false);
      notifyLocalDesktopSync();

      setToastMessage({
        text: `✏️ تم تعديل اسم القسم إلى "${newName}" ومزامنته مع الجميع!`,
        type: 'success',
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
        `سيتم نقل القسم إلى سلة المحذوفات وإزالته من القائمة النشطة لدى الموظفين.\n` +
        `(عدد المستندات في القسم: ${dept.fileCount})`
    );
    if (!confirmDelete) return;

    try {
      setActionLoading(true);
      const res = await fetch(`/api/drive/files?id=${dept.id}`, { method: 'DELETE' });
      const data = await res.json();
      if (!data.success) throw new Error(data.error);

      await loadAllData(false);
      notifyLocalDesktopSync();
      setToastMessage({
        text: `🗑️ تم حذف القسم "${dept.name}" بنجاح.`,
        type: 'info',
      });
    } catch (err: any) {
      alert(`تعذر حذف القسم: ${err.message || err}`);
    } finally {
      setActionLoading(false);
    }
  };

  // حفظ صلاحيات قسم معين في سحابة Google Drive فوراً وبشكل ذري
  const persistPermissionRule = async (updatedRule: PermissionRule, customToast?: string) => {
    try {
      setSavingPerms(true);
      isSavingPermsRef.current = true;
      lastPermSaveRef.current = Date.now();

      const res = await fetch('/api/drive/permissions', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          departmentName: updatedRule.folderName,
          permission: {
            departmentName: updatedRule.folderName,
            canView: updatedRule.canView,
            canDownload: updatedRule.canDownload,
            canUpload: updatedRule.canUpload,
            canCreateFolder: updatedRule.canCreateFolder,
            canEdit: updatedRule.canEdit,
            canRename: updatedRule.canRename,
            canMove: updatedRule.canMove,
            canDelete: updatedRule.canDelete,
            canPermanentDelete: updatedRule.canPermanentDelete,
            pinCode: updatedRule.pinCode || '',
          },
        }),
      });
      const data = await res.json();
      if (!data.success) throw new Error(data.error || 'فشل الحفظ السحابي');
      lastPermSaveRef.current = Date.now();
      notifyLocalDesktopSync();

      setToastMessage({
        text: customToast || `🔐 تم حفظ وتطبيق صلاحيات قسم "${updatedRule.folderName}" في السحابة فوراً!`,
        type: 'success',
      });
    } catch (err: any) {
      setToastMessage({
        text: `❌ تعذر حفظ الصلاحيات في السحابة: ${err.message || err}`,
        type: 'error',
      });
    } finally {
      isSavingPermsRef.current = false;
      setSavingPerms(false);
    }
  };

  // حفظ جميع صلاحيات الأقسام دفعة واحدة
  const handleSaveAllPermissionsNow = async () => {
    try {
      setSavingPerms(true);
      isSavingPermsRef.current = true;
      lastPermSaveRef.current = Date.now();

      const mapPayload: Record<string, any> = {};
      permissions.forEach((p) => {
        mapPayload[p.folderName] = {
          departmentName: p.folderName,
          canView: p.canView,
          canDownload: p.canDownload,
          canUpload: p.canUpload,
          canCreateFolder: p.canCreateFolder,
          canEdit: p.canEdit,
          canRename: p.canRename,
          canMove: p.canMove,
          canDelete: p.canDelete,
          canPermanentDelete: p.canPermanentDelete,
          pinCode: p.pinCode || '',
        };
      });

      const res = await fetch('/api/drive/permissions', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ permissions: mapPayload }),
      });
      const data = await res.json();
      if (!data.success) throw new Error(data.error);
      lastPermSaveRef.current = Date.now();
      notifyLocalDesktopSync();

      setToastMessage({
        text: '✅ تم حفظ ومزامنة مصفوفة الصلاحيات بالكامل في السحابة وتطبيقها على الويب والحاسوب!',
        type: 'success',
      });
    } catch (err: any) {
      setToastMessage({
        text: `❌ فشل حفظ الصلاحيات: ${err.message || err}`,
        type: 'error',
      });
    } finally {
      isSavingPermsRef.current = false;
      setSavingPerms(false);
    }
  };

  // تبديل صلاحية مفردة من الصلاحيات التسع لقسم معين
  const handleTogglePermissionKey = async (
    folderId: string,
    key: keyof Omit<PermissionRule, 'folderId' | 'folderName' | 'pinCode'>
  ) => {
    const baseRule =
      selectedPermDept && selectedPermDept.folderId === folderId
        ? selectedPermDept
        : permissions.find((p) => p.folderId === folderId);
    if (!baseRule) return;

    const newVal = !baseRule[key];
    const updated: PermissionRule = {
      ...baseRule,
      [key]: newVal,
    };

    // إذا تم إلغاء صلاحية العرض (canView = false) أو تفعيلها، نحفظ الحالة مباشرة
    setPermissions((prev) => prev.map((p) => (p.folderId === folderId ? updated : p)));
    if (selectedPermDept?.folderId === folderId) {
      setSelectedPermDept(updated);
    }
    await persistPermissionRule(updated);
  };

  // تغيير نمط الصلاحيات لقسم معين عبر القوالب السريعة
  const handleSetPresetPermission = async (
    folderId: string,
    folderName: string,
    preset: 'FULL' | 'EDIT_NO_DELETE' | 'UPLOAD_ONLY' | 'READ_ONLY' | 'VIEW_ONLY' | 'LOCKED'
  ) => {
    const current =
      selectedPermDept && selectedPermDept.folderId === folderId
        ? selectedPermDept
        : permissions.find((p) => p.folderId === folderId);
    if (!current) return;

    let updated: PermissionRule = { ...current };
    if (preset === 'FULL') {
      updated = {
        ...current,
        canView: true,
        canDownload: true,
        canUpload: true,
        canCreateFolder: true,
        canEdit: true,
        canRename: true,
        canMove: true,
        canDelete: true,
        canPermanentDelete: true,
      };
    } else if (preset === 'EDIT_NO_DELETE') {
      updated = {
        ...current,
        canView: true,
        canDownload: true,
        canUpload: true,
        canCreateFolder: true,
        canEdit: true,
        canRename: true,
        canMove: true,
        canDelete: false,
        canPermanentDelete: false,
      };
    } else if (preset === 'UPLOAD_ONLY') {
      updated = {
        ...current,
        canView: true,
        canDownload: true,
        canUpload: true,
        canCreateFolder: true,
        canEdit: false,
        canRename: false,
        canMove: false,
        canDelete: false,
        canPermanentDelete: false,
      };
    } else if (preset === 'READ_ONLY') {
      updated = {
        ...current,
        canView: true,
        canDownload: true,
        canUpload: false,
        canCreateFolder: false,
        canEdit: false,
        canRename: false,
        canMove: false,
        canDelete: false,
        canPermanentDelete: false,
      };
    } else if (preset === 'VIEW_ONLY') {
      updated = {
        ...current,
        canView: true,
        canDownload: false,
        canUpload: false,
        canCreateFolder: false,
        canEdit: false,
        canRename: false,
        canMove: false,
        canDelete: false,
        canPermanentDelete: false,
      };
    } else if (preset === 'LOCKED') {
      updated = {
        ...current,
        canView: false,
        canDownload: false,
        canUpload: false,
        canCreateFolder: false,
        canEdit: false,
        canRename: false,
        canMove: false,
        canDelete: false,
        canPermanentDelete: false,
      };
    }

    setPermissions((prev) => prev.map((p) => (p.folderId === folderId ? updated : p)));
    if (selectedPermDept?.folderId === folderId) {
      setSelectedPermDept(updated);
    }
    await persistPermissionRule(updated, `🔐 تم تطبيق وحفظ قالب الصلاحيات لقسم "${folderName}" سحابياً!`);
  };

  // إعادة فتح كافة الصلاحيات لجميع الأقسام
  const handleResetAllPermissions = async () => {
    if (!confirm('هل تريد منح الصلاحيات الكاملة (تحكم كامل) لكافة الأقسام وحفظها في السحابة؟')) return;
    try {
      setSavingPerms(true);
      isSavingPermsRef.current = true;
      lastPermSaveRef.current = Date.now();

      const res = await fetch('/api/drive/permissions', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          action: 'RESET_ALL',
          departmentNames: departments.map((d) => d.name),
        }),
      });
      const data = await res.json();
      if (!data.success) throw new Error(data.error);

      setPermissions((prev) =>
        prev.map((p) => ({
          ...p,
          canView: true,
          canDownload: true,
          canUpload: true,
          canCreateFolder: true,
          canEdit: true,
          canRename: true,
          canMove: true,
          canDelete: true,
          canPermanentDelete: true,
          pinCode: '',
        }))
      );
      lastPermSaveRef.current = Date.now();
      notifyLocalDesktopSync();

      setToastMessage({
        text: '✅ تم منح الصلاحيات الكاملة لجميع الأقسام ومزامنتها سحابياً!',
        type: 'success',
      });
    } catch (err: any) {
      alert(`تعذر إعادة ضبط الصلاحيات: ${err.message || err}`);
    } finally {
      isSavingPermsRef.current = false;
      setSavingPerms(false);
    }
  };

  // حفظ قائمة الأجهزة في السحابة
  const persistDevicesToCloud = async (updatedDevices: DeviceRecord[], messageText: string) => {
    try {
      setActionLoading(true);
      setDevices(updatedDevices);
      const res = await fetch('/api/drive/permissions', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          action: 'SAVE_DEVICES',
          devices: updatedDevices,
        }),
      });
      const data = await res.json();
      if (!data.success) throw new Error(data.error);
      setToastMessage({ text: messageText, type: 'success' });
    } catch (err: any) {
      setToastMessage({ text: `تعذر حفظ حالة الأجهزة: ${err.message || err}`, type: 'error' });
    } finally {
      setActionLoading(false);
    }
  };

  // اعتماد أو تعطيل جهاز حاسوب
  const handleToggleDeviceAuth = async (device: DeviceRecord) => {
    const newStatus = !device.isAuthorized;
    const updated = devices.map((d) =>
      d.id === device.id
        ? { ...d, isAuthorized: newStatus, status: newStatus ? 'متصل الآن' : 'موقوف إدارياً' }
        : d
    );
    await persistDevicesToCloud(
      updated,
      newStatus ? `✅ تم اعتماد وتفعيل جهاز "${device.name}" بنجاح.` : `⛔ تم إيقاف صلاحية جهاز "${device.name}".`
    );
  };

  // إضافة جهاز جديد للقائمة المعتمدة
  const handleAddDevice = async () => {
    if (!newDeviceName.trim()) return;
    const newDev: DeviceRecord = {
      id: `dev-${Date.now()}`,
      name: newDeviceName.trim().toUpperCase(),
      user: newDeviceUser.trim() || 'موظف الغرفة',
      os: newDeviceOs.trim() || 'Windows 11 Pro',
      machineGuid: `COC-KARBALA-${Math.random().toString(36).substring(2, 8).toUpperCase()}`,
      isAuthorized: true,
      lastSeen: 'الآن',
      status: 'متصل الآن',
    };
    const updated = [...devices, newDev];
    setShowAddDeviceModal(false);
    setNewDeviceName('');
    setNewDeviceUser('');
    await persistDevicesToCloud(updated, `💻 تمت إضافة واعتماد الجهاز "${newDev.name}" في السحابة!`);
  };

  // حذف جهاز
  const handleDeleteDevice = async (deviceId: string, deviceName: string) => {
    if (!confirm(`هل أنت متأكد من حذف الجهاز "${deviceName}" من قائمة الأجهزة المصرح لها؟`)) return;
    const updated = devices.filter((d) => d.id !== deviceId);
    await persistDevicesToCloud(updated, `🗑️ تم حذف الجهاز "${deviceName}" من السحابة.`);
  };

  // تصفية الملفات في تبويب الملفات
  const filteredFiles = files.filter((f) => {
    const matchDept =
      selectedDeptFilter === '__ALL__' ||
      f.folder === selectedDeptFilter ||
      f.folder.startsWith(selectedDeptFilter + '/');
    const matchSearch =
      f.name.toLowerCase().includes(fileSearch.toLowerCase()) ||
      f.folder.toLowerCase().includes(fileSearch.toLowerCase());
    return matchDept && matchSearch;
  });

  // أيقونة مميزة لكل نوع ملف في جدول الأدمن
  const getAdminFileIcon = (fileName: string) => {
    const ext = fileName.includes('.') ? '.' + fileName.split('.').pop()?.toLowerCase() : '';
    if (['.doc', '.docx', '.rtf'].includes(ext)) {
      return (
        <div className="w-9 h-9 rounded-lg bg-[#2B579A] text-white flex items-center justify-center font-bold text-xs shrink-0 select-none">
          W
        </div>
      );
    }
    if (['.xls', '.xlsx', '.csv'].includes(ext)) {
      return (
        <div className="w-9 h-9 rounded-lg bg-[#217346] text-white flex items-center justify-center font-bold text-xs shrink-0 select-none">
          X
        </div>
      );
    }
    if (['.mdb', '.accdb'].includes(ext)) {
      return (
        <div className="w-9 h-9 rounded-lg bg-[#A4373A] text-white flex items-center justify-center font-bold text-xs shrink-0 select-none">
          A
        </div>
      );
    }
    if (ext === '.pdf') {
      return (
        <div className="w-9 h-9 rounded-lg bg-[#E5252A] text-white flex items-center justify-center font-bold text-[10px] tracking-tight shrink-0 select-none">
          PDF
        </div>
      );
    }
    if (['.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp', '.svg'].includes(ext)) {
      return (
        <div className="w-9 h-9 rounded-lg bg-[#7C3AED] text-white flex items-center justify-center font-bold text-[10px] shrink-0 select-none">
          IMG
        </div>
      );
    }
    if (['.mp4', '.mov', '.avi', '.mkv', '.webm'].includes(ext)) {
      return (
        <div className="w-9 h-9 rounded-lg bg-[#4F46E5] text-white flex items-center justify-center font-bold text-[10px] shrink-0 select-none">
          VID
        </div>
      );
    }
    if (['.mp3', '.wav', '.ogg', '.m4a'].includes(ext)) {
      return (
        <div className="w-9 h-9 rounded-lg bg-[#DB2777] text-white flex items-center justify-center font-bold text-[10px] shrink-0 select-none">
          AUD
        </div>
      );
    }
    if (['.zip', '.rar', '.7z', '.tar', '.gz'].includes(ext)) {
      return (
        <div className="w-9 h-9 rounded-lg bg-[#D97706] text-white flex items-center justify-center font-bold text-[10px] shrink-0 select-none">
          ZIP
        </div>
      );
    }
    return (
      <div className="w-9 h-9 rounded-lg bg-[#475467] text-white flex items-center justify-center shrink-0 select-none">
        <FileText className="w-4 h-4" />
      </div>
    );
  };

  // حالة انتظار التحقق من الجلسة
  if (isCheckingAuth) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[70vh] gap-3">
        <RefreshCw className="w-8 h-8 animate-spin text-[#14372e]" />
        <p className="text-[13px] font-medium text-[#667085]">جاري التحقق من أمان الجلسة ومزامنة السحابة...</p>
      </div>
    );
  }

  // 1. شاشة تسجيل الدخول إذا لم يكن المستخدم مسجلاً
  if (!isAuthenticated) {
    return (
      <div className="min-h-[85vh] flex items-center justify-center p-4">
        <div className="w-full max-w-md bg-white rounded-2xl border border-[#E4E7EC] shadow-sm overflow-hidden">
          {/* الترويسة الرسمية لبطاقة الدخول */}
          <div className="bg-white p-6 text-center border-b border-[#E4E7EC]">
            <div className="w-16 h-16 mx-auto mb-3 rounded-xl bg-[#F7F8FA] p-2 border border-[#E4E7EC] flex items-center justify-center">
              <img src="/logo.png" alt="شعار غرفة تجارة كربلاء" className="w-full h-full object-contain" />
            </div>
            <h2 className="text-[20px] font-bold text-[#1B1F24]">لوحة الإدارة والتحكم</h2>
            <p className="text-[13px] text-[#14372e] mt-1 font-semibold">غرفة تجارة كربلاء المقدسة</p>
            <p className="text-[12px] text-[#667085] mt-1">مخصصة لإدارة الأقسام والصلاحيات السحابية</p>
          </div>

          {/* نموذج تسجيل الدخول */}
          <form onSubmit={handleLogin} className="p-6 space-y-4">
            {loginError && (
              <div className="flex items-center gap-2 p-3 bg-rose-50 border border-rose-200 text-[#F04438] rounded-lg text-[13px] font-semibold">
                <AlertTriangle className="w-4 h-4 shrink-0" />
                <span>{loginError}</span>
              </div>
            )}

            <div>
              <label className="block text-[13px] font-semibold text-[#1B1F24] mb-1.5">اسم مستخدم الأدمن</label>
              <div className="relative">
                <input
                  type="text"
                  required
                  value={loginUser}
                  onChange={(e) => setLoginUser(e.target.value)}
                  placeholder={`أدخل اسم المستخدم (الحالي: ${adminUsername})`}
                  className="w-full pl-3 pr-9 py-2.5 text-[14px] bg-[#F7F8FA] border border-[#E4E7EC] rounded-lg focus:outline-none focus:border-[#14372e] focus:bg-white transition font-medium"
                />
                <User className="w-4 h-4 text-[#667085] absolute right-3 top-3" />
              </div>
            </div>

            <div>
              <label className="block text-[13px] font-semibold text-[#1B1F24] mb-1.5">كلمة المرور</label>
              <div className="relative">
                <input
                  type={showLoginPass ? 'text' : 'password'}
                  required
                  value={loginPass}
                  onChange={(e) => setLoginPass(e.target.value)}
                  placeholder="أدخل كلمة المرور"
                  className="w-full pl-10 pr-9 py-2.5 text-[14px] bg-[#F7F8FA] border border-[#E4E7EC] rounded-lg focus:outline-none focus:border-[#14372e] focus:bg-white transition font-medium"
                />
                <Lock className="w-4 h-4 text-[#667085] absolute right-3 top-3" />
                <button
                  type="button"
                  onClick={() => setShowLoginPass(!showLoginPass)}
                  className="absolute left-3 top-2.5 text-[#667085] hover:text-[#1B1F24] transition"
                >
                  {showLoginPass ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                </button>
              </div>
            </div>

            <button
              type="submit"
              disabled={loggingIn}
              className="w-full py-2.5 bg-[#14372e] hover:bg-[#1b493d] text-white text-[14px] font-semibold rounded-lg transition flex items-center justify-center gap-2 mt-2 disabled:opacity-60"
            >
              {loggingIn ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Key className="w-4 h-4 text-[#c59b27]" />}
              <span>{loggingIn ? 'جاري التحقق...' : 'تسجيل الدخول'}</span>
            </button>

            <div className="p-3 bg-[#F7F8FA] rounded-lg border border-[#E4E7EC] text-[#667085] text-[12px] leading-relaxed space-y-1">
              <div className="flex items-center justify-between">
                <span>اسم المستخدم النشط:</span>
                <span className="bg-white px-2 py-0.5 rounded border border-[#E4E7EC] font-mono font-semibold text-[#1B1F24]">
                  {adminUsername}
                </span>
              </div>
            </div>

            <div className="pt-1 text-center">
              <a
                href="/files"
                className="text-[13px] text-[#667085] hover:text-[#1B1F24] font-semibold transition inline-flex items-center gap-1"
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
    <div className="p-4 sm:p-6 space-y-5 max-w-[1440px] mx-auto w-full">
      {/* 1. الترويسة الرسمية النظيفة للوحة تحكم الأدمن */}
      <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4 bg-white p-5 rounded-xl border border-[#E4E7EC]">
        <div className="flex items-center gap-3.5">
          <div className="w-12 h-12 rounded-xl bg-[#F7F8FA] border border-[#E4E7EC] p-1.5 flex items-center justify-center shrink-0">
            <img src="/logo.png" alt="شعار الغرفة" className="w-full h-full object-contain" />
          </div>
          <div>
            <h1 className="text-[18px] sm:text-[22px] font-bold text-[#1B1F24] leading-snug">
              لوحة الإدارة والصلاحيات
            </h1>
            <p className="text-[13px] text-[#667085] mt-0.5">
              إدارة الأقسام، مصفوفة الصلاحيات السحابية، بيانات الدخول، والأجهزة المعتمدة
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2 flex-wrap">
          <span className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-[#F7F8FA] text-[#1B1F24] rounded-lg text-[13px] font-medium border border-[#E4E7EC]">
            <User className="w-4 h-4 text-[#14372e]" />
            <span>المسؤول: {adminUsername}</span>
          </span>

          <button
            onClick={() => {
              setNewUserInput(adminUsername);
              setNewPassInput('');
              setConfirmPassInput('');
              setCredError('');
              setCredSuccess('');
              setActiveTab('ACCOUNT');
            }}
            className="flex items-center gap-1.5 px-3.5 py-1.5 bg-[#EDF5F2] hover:bg-[#dfece7] text-[#14372e] rounded-lg text-[13px] font-semibold transition cursor-pointer"
          >
            <Key className="w-4 h-4" />
            <span>بيانات الدخول</span>
          </button>

          <button
            onClick={() => loadAllData(false)}
            disabled={loading}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-white hover:bg-[#F7F8FA] text-[#1B1F24] rounded-lg text-[13px] font-semibold transition border border-[#E4E7EC] cursor-pointer"
          >
            <RefreshCw className={`w-4 h-4 text-[#667085] ${loading ? 'animate-spin' : ''}`} />
            <span>تحديث</span>
          </button>

          <button
            onClick={handleLogout}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-rose-50 hover:bg-rose-100 text-[#F04438] rounded-lg text-[13px] font-semibold transition border border-rose-200 cursor-pointer"
          >
            <LogOut className="w-4 h-4" />
            <span>خروج</span>
          </button>
        </div>
      </div>

      {/* 2. بطاقات الإحصائيات المنظمة */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-3">
        <div
          onClick={() => setActiveTab('ACCESS_HUB')}
          className="bg-amber-50/70 p-4 rounded-xl border-2 border-amber-300 flex items-center justify-between cursor-pointer hover:border-amber-500 hover:shadow-md transition col-span-2 sm:col-span-1"
        >
          <div>
            <div className="flex items-center gap-1.5">
              <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse"></span>
              <p className="text-[12px] font-bold text-amber-950">قواعد بيانات Access</p>
            </div>
            <p className="text-xl font-bold text-[#14372e] mt-1 font-mono">{accessTotalRecords.toLocaleString()} قيد</p>
            <p className="text-[11px] font-semibold text-amber-800 underline mt-0.5">إدارة الحقول والأقسام ⚙️</p>
          </div>
          <div className="w-10 h-10 rounded-lg bg-amber-100 text-amber-800 flex items-center justify-center shrink-0">
            <Database className="w-5 h-5" />
          </div>
        </div>

        <div
          onClick={() => setActiveTab('DEPTS')}
          className="bg-white p-4 rounded-xl border border-[#E4E7EC] flex items-center justify-between cursor-pointer hover:border-[#14372e] transition"
        >
          <div>
            <p className="text-[13px] font-medium text-[#667085]">الأقسام الإدارية</p>
            <p className="text-2xl font-bold text-[#1B1F24] mt-1 font-mono">{departments.length}</p>
          </div>
          <div className="w-10 h-10 rounded-lg bg-[#EDF5F2] text-[#14372e] flex items-center justify-center shrink-0">
            <Layers className="w-5 h-5" />
          </div>
        </div>

        <div
          onClick={() => setActiveTab('FILES')}
          className="bg-white p-4 rounded-xl border border-[#E4E7EC] flex items-center justify-between cursor-pointer hover:border-[#14372e] transition"
        >
          <div>
            <p className="text-[13px] font-medium text-[#667085]">المستندات النشطة</p>
            <p className="text-2xl font-bold text-[#14372e] mt-1 font-mono">
              {files.filter((f) => !f.isDeleted).length}
            </p>
          </div>
          <div className="w-10 h-10 rounded-lg bg-[#EDF5F2] text-[#14372e] flex items-center justify-center shrink-0">
            <FileText className="w-5 h-5" />
          </div>
        </div>

        <div
          onClick={() => setActiveTab('DEVICES')}
          className="bg-white p-4 rounded-xl border border-[#E4E7EC] flex items-center justify-between cursor-pointer hover:border-[#14372e] transition"
        >
          <div>
            <p className="text-[13px] font-medium text-[#667085]">الأجهزة المعتمدة</p>
            <p className="text-2xl font-bold text-[#1B1F24] mt-1 font-mono">
              {devices.filter((d) => d.isAuthorized).length}
              <span className="text-[12px] font-normal text-[#667085]"> / {devices.length}</span>
            </p>
          </div>
          <div className="w-10 h-10 rounded-lg bg-[#F7F8FA] text-[#1B1F24] border border-[#E4E7EC] flex items-center justify-center shrink-0">
            <Laptop className="w-5 h-5" />
          </div>
        </div>

        <div
          onClick={() => setActiveTab('PERMS')}
          className="bg-white p-4 rounded-xl border border-[#E4E7EC] flex items-center justify-between cursor-pointer hover:border-[#14372e] transition"
        >
          <div>
            <p className="text-[13px] font-medium text-[#667085]">الأقسام المقيدة</p>
            <p className="text-2xl font-bold text-[#c59b27] mt-1 font-mono">
              {
                permissions.filter(
                  (p) =>
                    !p.canView ||
                    !p.canDelete ||
                    !p.canUpload ||
                    !p.canEdit ||
                    Boolean(p.pinCode && p.pinCode.trim())
                ).length
              }
            </p>
          </div>
          <div className="w-10 h-10 rounded-lg bg-amber-50 text-[#c59b27] flex items-center justify-center shrink-0">
            <Shield className="w-5 h-5" />
          </div>
        </div>
      </div>

      {/* 3. شريط التبويبات الرئيسي للوحة الأدمن */}
      <div className="flex items-center gap-2 border-b border-[#E4E7EC] pb-3 overflow-x-auto">
        {[
          { id: 'ACCESS_HUB', label: '🏛️ مركز وقواعد بيانات Access (إدارة الحقول والأقسام)', count: accessTotalRecords, highlight: true },
          { id: 'DEPTS', label: 'إدارة الأقسام والمجلدات', count: departments.length },
          { id: 'PERMS', label: 'مصفوفة الصلاحيات السحابية', count: permissions.length },
          { id: 'FILES', label: 'إدارة كافة المستندات', count: files.length },
          { id: 'DEVICES', label: 'الأجهزة المعتمدة', count: devices.length },
          { id: 'ACCOUNT', label: 'بيانات حساب الأدمن', count: null },
        ].map((tab: any) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id as any)}
            className={`flex items-center gap-2 px-4 py-2 rounded-lg text-[13px] font-semibold transition whitespace-nowrap cursor-pointer border ${
              activeTab === tab.id
                ? 'bg-[#14372e] text-white border-[#14372e]'
                : tab.highlight
                ? 'bg-amber-50/80 text-amber-950 border-amber-300 hover:bg-amber-100 font-bold'
                : 'bg-white text-[#1B1F24] hover:bg-[#F7F8FA] border-[#E4E7EC]'
            }`}
          >
            <span>{tab.label}</span>
            {tab.count !== null && (
              <span
                className={`px-2 py-0.5 rounded-full text-[11px] font-semibold font-mono ${
                  activeTab === tab.id ? 'bg-white/20 text-white' : tab.highlight ? 'bg-amber-200 text-amber-900 font-bold' : 'bg-[#F7F8FA] text-[#667085]'
                }`}
              >
                {tab.count}
              </span>
            )}
          </button>
        ))}
      </div>

      {/* 4. محتوى التبويبات */}

      {/* تبويب مركز تحكم وإدارة قواعد بيانات Access الموحدة */}
      {activeTab === 'ACCESS_HUB' && (
        <div className="space-y-6">
          {/* بنر العنوان الرئيسي */}
          <div className="bg-gradient-to-r from-[#14372e] to-[#1e4d41] text-white p-6 rounded-2xl shadow-sm border border-[#1b4438] flex flex-col md:flex-row md:items-center justify-between gap-4">
            <div>
              <div className="flex items-center gap-2 mb-1">
                <span className="px-2.5 py-0.5 rounded-full text-xs font-bold bg-[#c59b27] text-white">إدارة مركزية عليا</span>
                <span className="text-xs text-white/70">غرفة تجارة كربلاء المقدسة</span>
              </div>
              <h3 className="text-xl font-bold flex items-center gap-2">
                <Database className="w-6 h-6 text-[#c59b27]" />
                <span>مركز تحكم وإدارة قواعد بيانات Access الموحدة</span>
              </h3>
              <p className="text-sm text-white/80 mt-1 max-w-2xl leading-relaxed">
                لوحة التحكم الإدارية الحصرية لحذف وإضافة الأقسام، التحكم في الحقول، إدارة السجلات، مصفوفة صلاحيات الأجهزة، وسلة المحذوفات المركزية.
              </p>
            </div>
            <button
              onClick={loadAccessHubData}
              disabled={accessLoading}
              className="flex items-center gap-2 px-4 py-2 bg-white/10 hover:bg-white/20 text-white rounded-xl text-sm font-semibold transition border border-white/20 self-start md:self-auto cursor-pointer"
            >
              <RefreshCw className={`w-4 h-4 ${accessLoading ? 'animate-spin' : ''}`} />
              <span>تحديث البيانات السحابية</span>
            </button>
          </div>

          {/* شريط الإحصائيات السريعة */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
            <div className="bg-white p-4 rounded-xl border border-slate-200">
              <p className="text-xs font-bold text-slate-500">الأقسام النشطة</p>
              <p className="text-2xl font-black text-[#14372e] mt-1">{accessFiles.length}</p>
            </div>
            <div className="bg-white p-4 rounded-xl border border-slate-200">
              <p className="text-xs font-bold text-slate-500">إجمالي القيود الرسمية</p>
              <p className="text-2xl font-black text-[#14372e] mt-1">{accessTotalRecords.toLocaleString()}</p>
            </div>
            <div className="bg-white p-4 rounded-xl border border-slate-200">
              <p className="text-xs font-bold text-slate-500">الأقسام المؤرشفة/المحذوفة</p>
              <p className="text-2xl font-black text-rose-600 mt-1">{accessDeletedSections.length}</p>
            </div>
            <div className="bg-white p-4 rounded-xl border border-slate-200">
              <p className="text-xs font-bold text-slate-500">سجلات سلة المحذوفات</p>
              <p className="text-2xl font-black text-amber-600 mt-1">{accessTrashBin.length}</p>
            </div>
          </div>

          {/* أزرار التبويبات الفرعية لمركز Access */}
          <div className="flex items-center gap-2 border-b border-slate-200 pb-2 overflow-x-auto">
            {[
              { id: 'SECTIONS', label: '📁 إدارة الأقسام والملفات', count: accessFiles.length },
              { id: 'FIELDS', label: '📋 إدارة الحقول والهياكل', count: accessColumnsList.length },
              { id: 'ROLES', label: '👥 مصفوفة الصلاحيات والأجهزة', count: Object.keys(accessRoles).length },
              { id: 'TRASH', label: '🗑️ سلة المحذوفات الإدارية', count: accessTrashBin.length },
            ].map((sub) => (
              <button
                key={sub.id}
                onClick={() => setAccessHubSubTab(sub.id as any)}
                className={`flex items-center gap-2 px-4 py-2 rounded-xl text-xs font-bold transition cursor-pointer border whitespace-nowrap ${
                  accessHubSubTab === sub.id
                    ? 'bg-[#14372e] text-white border-[#14372e]'
                    : 'bg-white text-slate-700 hover:bg-slate-50 border-slate-200'
                }`}
              >
                <span>{sub.label}</span>
                <span className={`px-2 py-0.5 rounded-full text-[10px] font-mono ${accessHubSubTab === sub.id ? 'bg-white/20 text-white' : 'bg-slate-100 text-slate-600'}`}>
                  {sub.count}
                </span>
              </button>
            ))}
          </div>

          {/* محتوى القسم 1: إدارة الأقسام والملفات */}
          {accessHubSubTab === 'SECTIONS' && (
            <div className="space-y-4">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 bg-white p-5 rounded-2xl border border-slate-200 shadow-xs">
                <div>
                  <h4 className="font-bold text-base text-slate-900">الأقسام وملفات Access المدمجة</h4>
                  <p className="text-xs text-slate-600 mt-0.5">
                    يمكن للمدير حذف أو أرشفة أي قسم، وعند الحذف يتم إخفاؤه فوراً عن كافة حواسيب الموظفين لمنع العبث.
                  </p>
                </div>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                {accessAllFiles.map((f: any, idx: number) => {
                  const isDeleted = accessDeletedSections.includes(f.name);
                  return (
                    <div
                      key={idx}
                      className={`p-5 rounded-2xl border transition flex flex-col justify-between ${
                        isDeleted ? 'bg-rose-50/50 border-rose-200' : 'bg-white border-slate-200 shadow-xs'
                      }`}
                    >
                      <div>
                        <div className="flex items-center justify-between gap-2 mb-3">
                          <span className={`px-2.5 py-0.5 rounded-full text-[11px] font-bold ${
                            isDeleted ? 'bg-rose-100 text-rose-700' : 'bg-emerald-50 text-emerald-700 border border-emerald-200'
                          }`}>
                            {isDeleted ? '🚫 مؤرشف / محذوف عن الموظفين' : '✅ نشط ومتاح للجميع'}
                          </span>
                          <span className="text-xs text-slate-500 font-mono">{(f.tables || []).length} جداول</span>
                        </div>
                        <h5 className="font-bold text-slate-900 text-sm mb-1 leading-snug">📁 {f.name}</h5>
                        <p className="text-xs text-slate-500 line-clamp-2">
                          الجداول: {(f.tables || []).join('، ')}
                        </p>
                      </div>

                      <div className="pt-4 mt-4 border-t border-slate-100 flex items-center justify-end">
                        {isDeleted ? (
                          <button
                            onClick={() => handleRestoreSection(f.name)}
                            disabled={actionLoading}
                            className="flex items-center gap-1.5 px-3 py-1.5 bg-emerald-600 hover:bg-emerald-700 text-white rounded-lg text-xs font-bold transition cursor-pointer"
                          >
                            <RotateCcw className="w-3.5 h-3.5" />
                            <span>استعادة القسم للعمل</span>
                          </button>
                        ) : (
                          <button
                            onClick={() => handleDeleteSection(f.name)}
                            disabled={actionLoading}
                            className="flex items-center gap-1.5 px-3 py-1.5 bg-rose-50 hover:bg-rose-100 text-rose-700 border border-rose-200 rounded-lg text-xs font-bold transition cursor-pointer"
                          >
                            <Trash2 className="w-3.5 h-3.5" />
                            <span>حذف وأرشفة القسم</span>
                          </button>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* محتوى القسم 2: إدارة الحقول والهياكل */}
          {accessHubSubTab === 'FIELDS' && (
            <div className="space-y-4">
              <div className="bg-white p-5 rounded-2xl border border-slate-200 shadow-xs space-y-4">
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                  <div>
                    <h4 className="font-bold text-base text-slate-900">إدارة حقول وهياكل الجداول</h4>
                    <p className="text-xs text-slate-600 mt-0.5">
                      اختر القسم والجدول لاستعراض حقوله الأصلية، إضافة حقل جديد سحابياً، أو حذف حقل غير مرغوب فيه.
                    </p>
                  </div>
                </div>

                {/* شريط اختيار القسم والجدول */}
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 pt-2 border-t border-slate-100">
                  <div>
                    <label className="block text-xs font-bold text-slate-700 mb-1">📁 اختر القسم المستهدف:</label>
                    <select
                      value={selectedAccessFile}
                      onChange={(e) => {
                        const fname = e.target.value;
                        setSelectedAccessFile(fname);
                        const match = accessFiles.find((f: any) => f.name === fname);
                        if (match && match.tables && match.tables.length > 0) {
                          setSelectedAccessTable(match.tables[0]);
                          setAccessTablesList(match.tables);
                          fetchColumnsForTable(fname, match.tables[0]);
                        }
                      }}
                      className="w-full bg-slate-50 border border-slate-200 rounded-xl px-3 py-2 text-xs font-bold text-slate-800 outline-none focus:border-[#14372e]"
                    >
                      {accessFiles.map((f: any, i: number) => (
                        <option key={i} value={f.name}>{f.name}</option>
                      ))}
                    </select>
                  </div>

                  <div>
                    <label className="block text-xs font-bold text-slate-700 mb-1">🏷️ اختر الجدول المستهدف:</label>
                    <select
                      value={selectedAccessTable}
                      onChange={(e) => {
                        const tname = e.target.value;
                        setSelectedAccessTable(tname);
                        fetchColumnsForTable(selectedAccessFile, tname);
                      }}
                      className="w-full bg-slate-50 border border-slate-200 rounded-xl px-3 py-2 text-xs font-bold text-slate-800 outline-none focus:border-[#14372e]"
                    >
                      {accessTablesList.map((t: string, i: number) => (
                        <option key={i} value={t}>{t}</option>
                      ))}
                    </select>
                  </div>
                </div>

                {/* نموذج إضافة حقل جديد */}
                <div className="p-4 bg-emerald-50/60 border border-emerald-100 rounded-xl flex flex-col sm:flex-row items-center gap-3">
                  <div className="flex-1 w-full">
                    <label className="block text-xs font-bold text-[#14372e] mb-1">➕ إضافة حقل جديد لهذا الجدول:</label>
                    <input
                      type="text"
                      placeholder="اكتب اسم الحقل الجديد (مثال: البريد الإلكتروني، رقم الهوية، ملاحظات)..."
                      value={newColNameInput}
                      onChange={(e) => setNewColNameInput(e.target.value)}
                      onKeyDown={(e) => e.key === 'Enter' && handleAddAccessColumn()}
                      className="w-full bg-white border border-emerald-200 rounded-lg px-3 py-2 text-xs font-medium text-slate-800 outline-none focus:border-[#14372e]"
                    />
                  </div>
                  <button
                    onClick={handleAddAccessColumn}
                    disabled={actionLoading || !newColNameInput.trim()}
                    className="w-full sm:w-auto px-5 py-2.5 bg-[#14372e] hover:bg-[#1a473b] disabled:opacity-50 text-white text-xs font-bold rounded-lg transition shrink-0 cursor-pointer"
                  >
                    ➕ إضافة الحقل وتعميمه
                  </button>
                </div>
              </div>

              {/* قائمة الحقول المعروضة للجدول */}
              <div className="bg-white p-5 rounded-2xl border border-slate-200 shadow-xs">
                <h5 className="font-bold text-sm text-slate-900 mb-3 flex items-center justify-between">
                  <span>الحقول النشطة في جدول ({selectedAccessTable}):</span>
                  <span className="text-xs text-slate-500 font-mono">إجمالي: {accessColumnsList.length} حقل</span>
                </h5>

                <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3">
                  {accessColumnsList.map((col: string, idx: number) => (
                    <div
                      key={idx}
                      className="p-3 bg-slate-50 rounded-xl border border-slate-200 flex items-center justify-between gap-2 hover:bg-slate-100/80 transition"
                    >
                      <div className="flex items-center gap-2 min-w-0">
                        <span className="w-5 h-5 rounded-full bg-slate-200 text-slate-600 text-[10px] font-mono flex items-center justify-center shrink-0">
                          {idx + 1}
                        </span>
                        <span className="text-xs font-bold text-slate-800 truncate" title={col}>{col}</span>
                      </div>
                      <button
                        onClick={() => handleDeleteAccessColumn(col)}
                        title="حذف هذا الحقل"
                        className="p-1.5 rounded-lg text-slate-400 hover:text-rose-600 hover:bg-rose-50 transition cursor-pointer shrink-0"
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}

          {/* محتوى القسم 3: مصفوفة الصلاحيات والأجهزة */}
          {accessHubSubTab === 'ROLES' && (
            <div className="space-y-4">
              <div className="bg-white p-5 rounded-2xl border border-slate-200 shadow-xs">
                <h4 className="font-bold text-base text-slate-900 mb-1">مصفوفة الصلاحيات المؤسسية (RBAC Engine)</h4>
                <p className="text-xs text-slate-600">
                  تحديد صلاحيات كل جهاز وموظف لمنع أي عمليات غير مصرح بها وحماية سرية وسلامة سجلات التجار والدلالين.
                </p>

                {/* جدول مستويات الصلاحيات التوضيحي */}
                <div className="grid grid-cols-1 md:grid-cols-3 gap-3 my-4">
                  <div className="p-3 rounded-xl border border-amber-200 bg-amber-50/50">
                    <p className="text-xs font-bold text-amber-800 flex items-center gap-1">👑 مدير نظام (Super Admin)</p>
                    <p className="text-[11px] text-amber-900/80 mt-1">كامل الصلاحيات (إضافة، تعديل، حذف الأقسام والحقول والقيود، ومنح الصلاحيات).</p>
                  </div>
                  <div className="p-3 rounded-xl border border-emerald-200 bg-emerald-50/50">
                    <p className="text-xs font-bold text-emerald-800 flex items-center gap-1">✏️ مدخل بيانات (Data Entry)</p>
                    <p className="text-[11px] text-emerald-900/80 mt-1">البحث والاستعراض وتصدير Excel وإضافة وتعديل القيود. (الحذف محجوب تماماً).</p>
                  </div>
                  <div className="p-3 rounded-xl border border-blue-200 bg-blue-50/50">
                    <p className="text-xs font-bold text-blue-800 flex items-center gap-1">👁️ مستعلم فقط (Viewer)</p>
                    <p className="text-[11px] text-blue-900/80 mt-1">البحث والاستعراض وتصدير التقارير فقط للقراءة (Read-Only). كافة أزرار الإضافة والتعديل والحذف محجوبة.</p>
                  </div>
                </div>

                {/* قائمة الأجهزة وإمكانية تعديل صلاحياتها */}
                <div className="mt-4 border border-slate-200 rounded-xl overflow-hidden">
                  <table className="w-full text-right text-xs">
                    <thead className="bg-slate-50 border-b border-slate-200 text-slate-600 font-bold">
                      <tr>
                        <th className="p-3">اسم الجهاز</th>
                        <th className="p-3">معرّف العتاد (Machine GUID)</th>
                        <th className="p-3">المستخدم المعتمد</th>
                        <th className="p-3">الصلاحية الحالية</th>
                        <th className="p-3 text-center">الإجراء والتحكم</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100">
                      {devices.map((d: DeviceRecord, idx: number) => {
                        const currentRole = accessRoles[d.machineGuid]?.role || 'data_entry';
                        return (
                          <tr key={idx} className="hover:bg-slate-50/80 transition">
                            <td className="p-3 font-bold text-slate-900">💻 {d.name}</td>
                            <td className="p-3 font-mono text-[11px] text-slate-500">{d.machineGuid}</td>
                            <td className="p-3 text-slate-700">{d.user}</td>
                            <td className="p-3">
                              <span className={`px-2.5 py-1 rounded-full text-[10px] font-bold ${
                                currentRole === 'admin' ? 'bg-amber-100 text-amber-800 border border-amber-300' :
                                currentRole === 'viewer' ? 'bg-blue-100 text-blue-800 border border-blue-300' :
                                'bg-emerald-100 text-emerald-800 border border-emerald-300'
                              }`}>
                                {currentRole === 'admin' ? '👑 مدير نظام' : currentRole === 'viewer' ? '👁️ مستعلم فقط' : '✏️ مدخل بيانات'}
                              </span>
                            </td>
                            <td className="p-3 text-center">
                              <div className="flex items-center justify-center gap-1.5">
                                <button
                                  onClick={() => handleSaveAccessRole(d.machineGuid, d.name, 'data_entry')}
                                  className={`px-2 py-1 rounded text-[10px] font-bold transition cursor-pointer ${
                                    currentRole === 'data_entry' ? 'bg-[#14372e] text-white' : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
                                  }`}
                                >
                                  مدخل بيانات
                                </button>
                                <button
                                  onClick={() => handleSaveAccessRole(d.machineGuid, d.name, 'viewer')}
                                  className={`px-2 py-1 rounded text-[10px] font-bold transition cursor-pointer ${
                                    currentRole === 'viewer' ? 'bg-blue-600 text-white' : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
                                  }`}
                                >
                                  مستعلم فقط
                                </button>
                                <button
                                  onClick={() => handleSaveAccessRole(d.machineGuid, d.name, 'admin')}
                                  className={`px-2 py-1 rounded text-[10px] font-bold transition cursor-pointer ${
                                    currentRole === 'admin' ? 'bg-amber-600 text-white' : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
                                  }`}
                                >
                                  مدير
                                </button>
                              </div>
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          )}

          {/* محتوى القسم 4: سلة المحذوفات الإدارية */}
          {accessHubSubTab === 'TRASH' && (
            <div className="space-y-4">
              <div className="bg-white p-5 rounded-2xl border border-slate-200 shadow-xs">
                <div className="flex items-center justify-between gap-3 mb-3">
                  <div>
                    <h4 className="font-bold text-base text-slate-900">سلة محذوفات السجلات المركزية (Trash Bin)</h4>
                    <p className="text-xs text-slate-600 mt-0.5">
                      أي قيد يتم حذفه من المنظومة يُحفظ هنا مع توثيق التاريخ وهوية من قام بالحذف، مع إمكانية استعادته بضغطة زر واحدة.
                    </p>
                  </div>
                </div>

                {accessTrashBin.length === 0 ? (
                  <div className="p-8 text-center text-slate-400 bg-slate-50 rounded-xl border border-dashed border-slate-200">
                    <Trash2 className="w-8 h-8 mx-auto mb-2 opacity-40 text-slate-400" />
                    <p className="text-xs font-bold">سلة المحذوفات فارغة حالياً. لم يتم تسجيل أي قيود محذوفة.</p>
                  </div>
                ) : (
                  <div className="border border-slate-200 rounded-xl overflow-hidden">
                    <table className="w-full text-right text-xs">
                      <thead className="bg-slate-50 border-b border-slate-200 text-slate-600 font-bold">
                        <tr>
                          <th className="p-3">معرف القيد</th>
                          <th className="p-3">القسم / الملف</th>
                          <th className="p-3">الجدول</th>
                          <th className="p-3">تاريخ الحذف</th>
                          <th className="p-3">بواسطة</th>
                          <th className="p-3 text-center">الإجراء</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-100">
                        {accessTrashBin.map((item: any, idx: number) => (
                          <tr key={idx} className="hover:bg-slate-50/80 transition">
                            <td className="p-3 font-mono text-[11px] text-slate-600">{item.id}</td>
                            <td className="p-3 font-bold text-slate-900">{item.file}</td>
                            <td className="p-3 text-slate-700">{item.table}</td>
                            <td className="p-3 font-mono text-[11px] text-slate-500">
                              {new Date(item.deleted_at).toLocaleString('ar-IQ')}
                            </td>
                            <td className="p-3 font-bold text-[#14372e]">{item.deleted_by || 'الإدارة'}</td>
                            <td className="p-3 text-center">
                              <button
                                onClick={() => handleRestoreTrashRecord(item.id)}
                                disabled={actionLoading}
                                className="px-3 py-1.5 bg-emerald-600 hover:bg-emerald-700 text-white rounded-lg text-xs font-bold transition cursor-pointer flex items-center gap-1 mx-auto"
                              >
                                <RotateCcw className="w-3.5 h-3.5" />
                                <span>استعادة القيد</span>
                              </button>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      )}

      {/* التبويب الأول: إدارة الأقسام الإدارية */}
      {activeTab === 'DEPTS' && (
        <div className="space-y-4">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 bg-white p-5 rounded-2xl border border-slate-200 shadow-xs">
            <div>
              <h3 className="font-black text-base text-slate-900">الأقسام الإدارية والمجلدات النشطة</h3>
              <p className="text-sm text-slate-600 mt-0.5">
                كل قسم هنا يمثل مجلداً مركزياً يتزامن فوراً مع حواسيب موظفي غرفة تجارة كربلاء المقدسة ومنصة الويب.
              </p>
            </div>
            <button
              onClick={() => setShowAddDeptModal(true)}
              className="flex items-center justify-center gap-2 px-5 py-2.5 bg-[#14372e] hover:bg-[#1a473b] text-white text-sm font-bold rounded-xl transition shadow-xs active:scale-95 cursor-pointer shrink-0"
            >
              <Plus className="w-4 h-4" />
              <span>إضافة قسم جديد</span>
            </button>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {departments.map((dept) => {
              const perm = permissions.find((p) => p.folderName === dept.name);
              const isLocked = perm && !perm.canView;
              const isReadOnly = perm && perm.canView && !perm.canUpload && !perm.canEdit && !perm.canDelete;
              return (
                <div
                  key={dept.id}
                  className="bg-white rounded-2xl border border-slate-200 p-5 shadow-xs hover:border-[#c59b27] transition flex flex-col justify-between"
                >
                  <div>
                    <div className="flex items-start justify-between gap-3">
                      <div className="flex items-start gap-3 min-w-0 flex-1">
                        <div className="w-12 h-12 rounded-xl bg-amber-50 text-amber-800 flex items-center justify-center font-bold border border-amber-200 shrink-0">
                          <Folder className="w-6 h-6" />
                        </div>
                        <div className="min-w-0 flex-1">
                          <h4 className="font-black text-base text-slate-900 break-words whitespace-normal leading-snug">
                            {dept.name}
                          </h4>
                          <p className="text-xs font-semibold text-slate-500 mt-1">{dept.fileCount} مستند محفوظ</p>
                          <div className="flex flex-wrap gap-1.5 mt-2">
                            {isLocked ? (
                              <span className="px-2 py-0.5 rounded-md bg-rose-100 text-rose-800 text-xs font-bold">
                                ⛔ القسم مقفل
                              </span>
                            ) : isReadOnly ? (
                              <span className="px-2 py-0.5 rounded-md bg-slate-100 text-slate-700 text-xs font-bold">
                                👁️ قراءة فقط
                              </span>
                            ) : (
                              <span className="px-2 py-0.5 rounded-md bg-emerald-50 text-emerald-700 text-xs font-bold">
                                ✅ متاح ونشط
                              </span>
                            )}
                            {perm?.pinCode && (
                              <span className="px-2 py-0.5 rounded-md bg-amber-100 text-amber-900 text-xs font-bold">
                                🔑 محمي برمز PIN
                              </span>
                            )}
                          </div>
                        </div>
                      </div>
                    </div>

                    <div className="mt-4 pt-3 border-t border-slate-100 flex items-center justify-between text-sm text-slate-600">
                      <span>الحجم الإجمالي:</span>
                      <span className="font-bold text-slate-800">{formatSize(dept.totalSize)}</span>
                    </div>
                  </div>

                  <div className="mt-4 pt-3 border-t border-slate-100 flex items-center justify-between gap-2">
                    <button
                      onClick={() => {
                        const found = permissions.find((p) => p.folderName === dept.name);
                        if (found) {
                          setSelectedPermDept(found);
                          setPinInput(found.pinCode || '');
                        } else {
                          setActiveTab('PERMS');
                        }
                      }}
                      className="px-3.5 py-2 text-xs font-bold text-[#14372e] bg-emerald-50 hover:bg-emerald-100 border border-emerald-200 rounded-xl transition flex items-center gap-1.5 cursor-pointer"
                    >
                      <Shield className="w-4 h-4" />
                      <span>تعديل الصلاحيات</span>
                    </button>

                    <div className="flex items-center gap-1.5">
                      <button
                        onClick={() => {
                          setDeptToRename(dept);
                          setNewDeptRenameValue(dept.name);
                          setShowRenameDeptModal(true);
                        }}
                        className="p-2 text-slate-600 hover:text-slate-900 hover:bg-slate-100 rounded-lg transition cursor-pointer"
                        title="تعديل اسم القسم"
                      >
                        <Edit3 className="w-4 h-4" />
                      </button>

                      <button
                        onClick={() => handleDeleteDepartment(dept)}
                        className="p-2 text-rose-600 hover:text-rose-800 hover:bg-rose-50 rounded-lg transition cursor-pointer"
                        title="حذف القسم"
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* التبويب الثاني: مصفوفة الصلاحيات المفصلة */}
      {activeTab === 'PERMS' && (
        <div className="bg-white rounded-2xl border border-slate-200 shadow-xs overflow-hidden">
          <div className="p-5 border-b border-slate-100 flex flex-col lg:flex-row lg:items-center justify-between gap-4 bg-slate-50">
            <div>
              <h3 className="font-black text-base text-slate-900 flex items-center gap-2">
                <Shield className="w-5 h-5 text-[#0f6cbd]" />
                <span>مصفوفة الصلاحيات المفصلة للأقسام (تطبق فعلياً في الويب وتطبيق الحاسوب)</span>
              </h3>
              <p className="text-sm text-slate-600 mt-1">
                انقر مباشرة على أي زر (مسموح / محظور) لتبديل الصلاحية وحفظها فوراً في السحابة، أو اضغط «تخصيص» لضبط رمز PIN والقوالب.
              </p>
            </div>
            <div className="flex items-center gap-2.5 flex-wrap">
              {savingPerms && (
                <span className="text-xs font-bold text-sky-800 bg-sky-50 px-3.5 py-2 rounded-xl border border-sky-200 flex items-center gap-1.5">
                  <RefreshCw className="w-4 h-4 animate-spin" />
                  جاري الحفظ في السحابة...
                </span>
              )}
              <button
                onClick={handleSaveAllPermissionsNow}
                disabled={savingPerms}
                className="px-4 py-2.5 text-xs font-bold rounded-xl bg-[#14372e] text-white hover:bg-[#1a473b] transition flex items-center gap-1.5 shadow-xs cursor-pointer"
              >
                <Save className="w-4 h-4" />
                <span>حفظ ومزامنة الكل الآن</span>
              </button>
              <button
                onClick={handleResetAllPermissions}
                disabled={savingPerms}
                className="px-4 py-2.5 text-xs font-bold rounded-xl bg-emerald-600 text-white hover:bg-emerald-700 transition flex items-center gap-1.5 shadow-xs cursor-pointer"
              >
                <Unlock className="w-4 h-4" />
                <span>فتح كافة الصلاحيات للجميع</span>
              </button>
            </div>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-right text-sm">
              <thead className="bg-slate-100/80 text-slate-700 border-b border-slate-200 font-black text-xs">
                <tr>
                  <th className="p-4 min-w-[200px]">القسم الإداري</th>
                  <th className="p-3 text-center">تصفح وعرض</th>
                  <th className="p-3 text-center">تنزيل وفتح</th>
                  <th className="p-3 text-center">رفع ملفات</th>
                  <th className="p-3 text-center">إنشاء مجلدات</th>
                  <th className="p-3 text-center">تعديل وحفظ</th>
                  <th className="p-3 text-center">إعادة تسمية</th>
                  <th className="p-3 text-center">نقل ملفات</th>
                  <th className="p-3 text-center">حذف للسلة</th>
                  <th className="p-3 text-center">حذف نهائي</th>
                  <th className="p-4 text-center min-w-[230px]">قوالب سريعة وتخصيص</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {permissions.map((perm) => {
                  const permCols: {
                    key: keyof Omit<PermissionRule, 'folderId' | 'folderName' | 'pinCode'>;
                    label: string;
                  }[] = [
                    { key: 'canView', label: 'تصفح' },
                    { key: 'canDownload', label: 'تنزيل' },
                    { key: 'canUpload', label: 'رفع' },
                    { key: 'canCreateFolder', label: 'مجلدات' },
                    { key: 'canEdit', label: 'تعديل' },
                    { key: 'canRename', label: 'تسمية' },
                    { key: 'canMove', label: 'نقل' },
                    { key: 'canDelete', label: 'حذف' },
                    { key: 'canPermanentDelete', label: 'نهائي' },
                  ];
                  return (
                    <tr key={perm.folderId} className="hover:bg-slate-50/80 transition">
                      <td className="p-4 font-bold text-slate-900">
                        <div className="flex items-center gap-2.5">
                          <Folder className="w-5 h-5 text-amber-600 shrink-0" />
                          <span className="break-words whitespace-normal leading-snug text-sm font-black">
                            {perm.folderName}
                          </span>
                          {perm.pinCode && (
                            <span
                              className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-amber-100 text-amber-900 text-xs font-bold shrink-0"
                              title={`محمي برمز PIN: ${perm.pinCode}`}
                            >
                              <Key className="w-3 h-3" /> PIN
                            </span>
                          )}
                        </div>
                      </td>
                      {permCols.map((col) => {
                        const enabled = Boolean(perm[col.key]);
                        return (
                          <td key={col.key} className="p-2.5 text-center">
                            <button
                              type="button"
                              onClick={() => handleTogglePermissionKey(perm.folderId, col.key)}
                              title={`انقر لتبديل صلاحية (${col.label}) لقسم ${perm.folderName}`}
                              className={`inline-flex items-center gap-1 px-3 py-1.5 rounded-full text-xs font-bold border transition cursor-pointer active:scale-95 ${
                                enabled
                                  ? 'text-emerald-800 bg-emerald-50 border-emerald-300 hover:bg-emerald-100'
                                  : 'text-rose-800 bg-rose-50 border-rose-300 hover:bg-rose-100'
                              }`}
                            >
                              {enabled ? <Check className="w-3.5 h-3.5" /> : <X className="w-3.5 h-3.5" />}
                              <span>{enabled ? 'مسموح' : 'محظور'}</span>
                            </button>
                          </td>
                        );
                      })}
                      <td className="p-3 text-center">
                        <div className="flex items-center justify-center gap-1.5 flex-wrap">
                          <button
                            type="button"
                            onClick={() => handleSetPresetPermission(perm.folderId, perm.folderName, 'FULL')}
                            className="px-2.5 py-1.5 text-xs font-bold rounded-lg bg-emerald-50 text-emerald-800 hover:bg-emerald-100 transition border border-emerald-200 cursor-pointer"
                          >
                            كامل
                          </button>
                          <button
                            type="button"
                            onClick={() => handleSetPresetPermission(perm.folderId, perm.folderName, 'EDIT_NO_DELETE')}
                            className="px-2.5 py-1.5 text-xs font-bold rounded-lg bg-sky-50 text-sky-800 hover:bg-sky-100 transition border border-sky-200 cursor-pointer"
                          >
                            بلا حذف
                          </button>
                          <button
                            type="button"
                            onClick={() => handleSetPresetPermission(perm.folderId, perm.folderName, 'READ_ONLY')}
                            className="px-2.5 py-1.5 text-xs font-bold rounded-lg bg-slate-100 text-slate-700 hover:bg-slate-200 transition border border-slate-300 cursor-pointer"
                          >
                            قراءة فقط
                          </button>
                          <button
                            type="button"
                            onClick={() => handleSetPresetPermission(perm.folderId, perm.folderName, 'LOCKED')}
                            className="px-2.5 py-1.5 text-xs font-bold rounded-lg bg-rose-50 text-rose-800 hover:bg-rose-100 transition border border-rose-200 cursor-pointer"
                          >
                            قفل
                          </button>
                          <button
                            type="button"
                            onClick={() => {
                              setSelectedPermDept(perm);
                              setPinInput(perm.pinCode || '');
                            }}
                            className="px-3 py-1.5 text-xs font-bold rounded-lg bg-[#14372e] text-white hover:bg-[#1b4b3f] transition flex items-center gap-1 cursor-pointer"
                          >
                            <Settings className="w-3.5 h-3.5" />
                            <span>تخصيص و PIN</span>
                          </button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* التبويب الثالث (الجديد والمباشر): إدارة حساب الأدمن (اليوزر والباسورد) */}
      {activeTab === 'ACCOUNT' && (
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
          <div className="lg:col-span-7 bg-white rounded-3xl border border-slate-200 shadow-xs p-6 space-y-5">
            <div className="flex items-center justify-between border-b border-slate-100 pb-4">
              <div className="flex items-center gap-3">
                <div className="w-12 h-12 rounded-2xl bg-amber-50 text-amber-700 border border-amber-200 flex items-center justify-center">
                  <Key className="w-6 h-6" />
                </div>
                <div>
                  <h3 className="font-black text-base text-slate-900">
                    تغيير اسم المستخدم وكلمة المرور للوحة الأدمن
                  </h3>
                  <p className="text-sm text-slate-500 mt-0.5">
                    يتم حفظ اليوزر والباسورد الجديد في سحابة Google Drive فوراً ليعملا على جميع المتصفحات والأجهزة.
                  </p>
                </div>
              </div>
            </div>

            {credError && (
              <div className="p-4 bg-rose-50 border border-rose-200 text-rose-700 rounded-2xl text-sm font-bold flex items-center gap-2">
                <AlertTriangle className="w-5 h-5 shrink-0" />
                <span>{credError}</span>
              </div>
            )}

            {credSuccess && (
              <div className="p-4 bg-emerald-50 border border-emerald-200 text-emerald-800 rounded-2xl text-sm font-bold flex items-center gap-2">
                <CheckCircle2 className="w-5 h-5 shrink-0 text-emerald-600" />
                <span>{credSuccess}</span>
              </div>
            )}

            <form onSubmit={handleChangeCredentials} className="space-y-4">
              <div>
                <label className="block text-sm font-bold text-slate-800 mb-1.5">
                  اسم مستخدم الأدمن الجديد (Username)
                </label>
                <div className="relative">
                  <input
                    type="text"
                    required
                    value={newUserInput}
                    onChange={(e) => setNewUserInput(e.target.value)}
                    placeholder="أدخل اسم المستخدم الجديد (مثال: admin)"
                    className="w-full pl-4 pr-10 py-3 text-sm font-bold bg-slate-50 border border-slate-300 rounded-xl focus:outline-none focus:ring-2 focus:ring-[#14372e] focus:bg-white"
                  />
                  <User className="w-4 h-4 text-slate-400 absolute right-3.5 top-3.5" />
                </div>
              </div>

              <div>
                <label className="block text-sm font-bold text-slate-800 mb-1.5">
                  كلمة المرور الجديدة (Password)
                </label>
                <div className="relative">
                  <input
                    type={showNewPass ? 'text' : 'password'}
                    value={newPassInput}
                    onChange={(e) => setNewPassInput(e.target.value)}
                    placeholder="أدخل كلمة المرور الجديدة (أو اتركها فارغة للإبقاء على الحالية)"
                    className="w-full pl-10 pr-10 py-3 text-sm font-bold bg-slate-50 border border-slate-300 rounded-xl focus:outline-none focus:ring-2 focus:ring-[#14372e] focus:bg-white"
                  />
                  <Lock className="w-4 h-4 text-slate-400 absolute right-3.5 top-3.5" />
                  <button
                    type="button"
                    onClick={() => setShowNewPass(!showNewPass)}
                    className="absolute left-3 top-3 text-slate-400 hover:text-slate-700"
                  >
                    {showNewPass ? <EyeOff className="w-5 h-5" /> : <Eye className="w-5 h-5" />}
                  </button>
                </div>
              </div>

              <div>
                <label className="block text-sm font-bold text-slate-800 mb-1.5">
                  تأكيد كلمة المرور الجديدة
                </label>
                <input
                  type={showNewPass ? 'text' : 'password'}
                  value={confirmPassInput}
                  onChange={(e) => setConfirmPassInput(e.target.value)}
                  placeholder="أعد كتابة كلمة المرور الجديدة للتأكيد"
                  className="w-full px-4 py-3 text-sm font-bold bg-slate-50 border border-slate-300 rounded-xl focus:outline-none focus:ring-2 focus:ring-[#14372e] focus:bg-white"
                />
              </div>

              <div className="flex flex-wrap items-center justify-between gap-3 pt-4 border-t border-slate-100">
                <button
                  type="button"
                  onClick={handleResetDefaultCredentials}
                  disabled={savingCredentials}
                  className="px-4 py-2.5 text-xs font-bold text-amber-900 bg-amber-50 hover:bg-amber-100 border border-amber-200 rounded-xl transition flex items-center gap-1.5 cursor-pointer"
                >
                  <RotateCcw className="w-4 h-4" />
                  <span>استعادة الافتراضي (admin / admin1234)</span>
                </button>

                <button
                  type="submit"
                  disabled={savingCredentials}
                  className="px-6 py-3 text-sm font-black bg-[#14372e] text-white rounded-xl hover:bg-[#1a473b] transition shadow-md flex items-center gap-2 cursor-pointer disabled:opacity-50"
                >
                  {savingCredentials ? (
                    <RefreshCw className="w-4 h-4 animate-spin" />
                  ) : (
                    <Save className="w-4 h-4 text-[#ecd58a]" />
                  )}
                  <span>{savingCredentials ? 'جاري الحفظ في السحابة...' : 'حفظ اليوزر والباسورد الجديد'}</span>
                </button>
              </div>
            </form>
          </div>

          <div className="lg:col-span-5 space-y-4">
            <div className="bg-white rounded-3xl border border-slate-200 shadow-xs p-6 space-y-4">
              <h4 className="font-black text-base text-slate-900 flex items-center gap-2">
                <Shield className="w-5 h-5 text-[#14372e]" />
                <span>بيانات الدخول النشطة حالياً في السحابة</span>
              </h4>
              <div className="p-4 rounded-2xl bg-slate-50 border border-slate-200 space-y-3 text-sm">
                <div className="flex items-center justify-between">
                  <span className="text-slate-600 font-bold">اسم المستخدم الحالي:</span>
                  <span className="font-mono font-black text-slate-900 bg-white px-3 py-1 rounded-lg border border-slate-200">
                    {adminUsername}
                  </span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-slate-600 font-bold">كلمة المرور الحالية:</span>
                  <div className="flex items-center gap-2">
                    <span className="font-mono font-black text-slate-900 bg-white px-3 py-1 rounded-lg border border-slate-200">
                      {showCurrentPass ? adminPassword : '••••••••'}
                    </span>
                    <button
                      type="button"
                      onClick={() => setShowCurrentPass(!showCurrentPass)}
                      className="p-1.5 text-slate-500 hover:text-slate-800 bg-white rounded-lg border border-slate-200 cursor-pointer"
                      title={showCurrentPass ? 'إخفاء كلمة المرور' : 'إظهار كلمة المرور الحالية'}
                    >
                      {showCurrentPass ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                    </button>
                  </div>
                </div>
              </div>
              <p className="text-xs text-slate-500 leading-relaxed">
                💡 ملاحظة أمنية: يتم تشفير وحفظ بيانات الدخول في ملف الإعدادات المركزي داخل Google Drive لضمان عمل نفس اليوزر والباسورد عند فتح لوحة الأدمن من أي حاسوب أو هاتف.
              </p>
            </div>
          </div>
        </div>
      )}

      {/* التبويب الرابع: إدارة كافة المستندات */}
      {activeTab === 'FILES' && (
        <div className="bg-white rounded-xl border border-[#E4E7EC] overflow-hidden">
          <div className="p-4 border-b border-[#E4E7EC] flex flex-col md:flex-row md:items-center justify-between gap-3 bg-[#F7F8FA]">
            <div>
              <h3 className="font-bold text-[16px] text-[#1B1F24]">إدارة المستندات الرسمية والأرشفة</h3>
              <p className="text-[13px] text-[#667085] mt-0.5">
                عرض الأسماء الكاملة للمستندات مع أيقوناتها المميزة، تعديل الأسماء، أو حذف المستندات.
              </p>
            </div>

            <div className="flex items-center gap-2.5 flex-wrap">
              <select
                value={selectedDeptFilter}
                onChange={(e) => setSelectedDeptFilter(e.target.value)}
                className="px-3.5 py-2 text-[13px] bg-white border border-[#E4E7EC] rounded-lg font-semibold text-[#1B1F24] focus:outline-none focus:border-[#14372e]"
              >
                <option value="__ALL__">كافة الأقسام</option>
                {departments.map((d) => (
                  <option key={d.id} value={d.name}>
                    {d.name}
                  </option>
                ))}
              </select>

              <div className="relative">
                <input
                  type="text"
                  placeholder="بحث في المستندات..."
                  value={fileSearch}
                  onChange={(e) => setFileSearch(e.target.value)}
                  className="pl-3 pr-9 py-2 text-[13px] bg-white border border-[#E4E7EC] rounded-lg font-medium focus:outline-none focus:border-[#14372e]"
                />
                <Search className="w-4 h-4 text-[#667085] absolute right-3 top-2.5" />
              </div>
            </div>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-right">
              <thead className="bg-[#F7F8FA] text-[#667085] border-b border-[#E4E7EC] font-semibold text-[12px]">
                <tr>
                  <th className="py-3 px-4 min-w-[300px]">اسم المستند الكامل</th>
                  <th className="py-3 px-4 min-w-[180px]">القسم / المسار</th>
                  <th className="py-3 px-4">الحجم</th>
                  <th className="py-3 px-4">تاريخ الحفظ</th>
                  <th className="py-3 px-4 text-center">الحالة</th>
                  <th className="py-3 px-4 text-center">إجراءات</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[#E4E7EC]">
                {filteredFiles.map((file) => (
                  <tr key={file.id} className="hover:bg-[#F7F8FA] transition">
                    <td className="py-3.5 px-4">
                      <div className="flex items-start gap-3">
                        {getAdminFileIcon(file.name)}
                        <span className="break-words whitespace-normal leading-relaxed text-[15px] font-medium text-[#1B1F24] pt-0.5">
                          {file.name}
                        </span>
                      </div>
                    </td>
                    <td className="py-3.5 px-4 text-[13px] text-[#667085] font-medium break-words whitespace-normal">{file.folder}</td>
                    <td className="py-3.5 px-4 text-[13px] text-[#667085] font-mono" dir="ltr">{file.size}</td>
                    <td className="py-3.5 px-4 text-[13px] text-[#667085]">{file.lastModifiedAt}</td>
                    <td className="py-3.5 px-4 text-center">
                      <span
                        className={`inline-flex items-center px-2.5 py-0.5 rounded-md text-[12px] font-semibold ${
                          file.isDeleted
                            ? 'bg-rose-50 text-[#F04438] border border-rose-200'
                            : 'bg-[#EDF5F2] text-[#14372e]'
                        }`}
                      >
                        {file.isDeleted ? 'في السلة' : 'نشط'}
                      </span>
                    </td>
                    <td className="py-3.5 px-4 text-center">
                      <div className="flex items-center justify-center gap-1.5">
                        <button
                          onClick={() => {
                            setFileToRename(file);
                            setNewFileNameValue(file.name);
                            setShowRenameFileModal(true);
                          }}
                          className="p-2 text-[#667085] hover:text-[#1B1F24] hover:bg-[#F7F8FA] rounded-lg transition cursor-pointer"
                          title="تعديل اسم المستند"
                        >
                          <Edit3 className="w-4 h-4" />
                        </button>

                        <button
                          onClick={async () => {
                            if (!confirm(`هل أنت متأكد من حذف المستند "${file.name}"؟`)) return;
                            await fetch(`/api/drive/files?id=${file.id}`, { method: 'DELETE' });
                            await loadAllData(false);
                            notifyLocalDesktopSync();
                          }}
                          className="p-2 text-[#F04438] hover:bg-rose-50 rounded-lg transition cursor-pointer"
                          title="حذف المستند"
                        >
                          <Trash2 className="w-4 h-4" />
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

      {/* التبويب الخامس: أجهزة الموظفين المعتمدة */}
      {activeTab === 'DEVICES' && (
        <div className="bg-white rounded-2xl border border-slate-200 shadow-xs p-6 space-y-5">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b pb-4">
            <div>
              <h3 className="font-black text-base text-slate-900">حواسيب موظفي غرفة تجارة كربلاء المعتمدة</h3>
              <p className="text-sm text-slate-600 mt-0.5">
                إدارة الأجهزة المصرح لها بالمزامنة التلقائية عبر تطبيق الحاسوب (Share COC).
              </p>
            </div>
            <div className="flex items-center gap-2.5">
              <button
                onClick={() => setShowAddDeviceModal(true)}
                className="flex items-center gap-2 px-4 py-2.5 bg-[#14372e] hover:bg-[#1a473b] text-white text-sm font-bold rounded-xl transition cursor-pointer"
              >
                <Plus className="w-4 h-4" />
                <span>إضافة جهاز معتمد</span>
              </button>
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 pt-2">
            {devices.map((dev) => (
              <div
                key={dev.id}
                className={`p-5 rounded-2xl border space-y-3 transition ${
                  dev.isAuthorized
                    ? 'border-slate-200 bg-slate-50/60'
                    : 'border-rose-200 bg-rose-50/30 opacity-85'
                }`}
              >
                <div className="flex items-start justify-between gap-2">
                  <div className="flex items-center gap-2.5 min-w-0">
                    <Laptop className={`w-5 h-5 shrink-0 ${dev.isAuthorized ? 'text-[#0f6cbd]' : 'text-rose-600'}`} />
                    <span className="font-black text-sm text-slate-900 break-words">{dev.name}</span>
                  </div>
                  <span
                    className={`text-xs font-bold px-2.5 py-0.5 rounded-full shrink-0 ${
                      dev.isAuthorized ? 'bg-emerald-100 text-emerald-800' : 'bg-rose-100 text-rose-800'
                    }`}
                  >
                    {dev.isAuthorized ? '🟢 معتمد ونشط' : '⛔ موقوف'}
                  </span>
                </div>
                <p className="text-sm text-slate-700 break-words">
                  القسم / الموظف: <strong className="text-slate-900">{dev.user}</strong>
                </p>
                <p className="text-xs text-slate-500 font-mono">نظام التشغيل: {dev.os}</p>

                <div className="pt-3 border-t border-slate-200/80 flex items-center justify-between gap-2">
                  <button
                    onClick={() => handleToggleDeviceAuth(dev)}
                    disabled={actionLoading}
                    className={`px-3.5 py-1.5 rounded-xl text-xs font-bold transition cursor-pointer ${
                      dev.isAuthorized
                        ? 'bg-amber-100 text-amber-900 hover:bg-amber-200'
                        : 'bg-emerald-600 text-white hover:bg-emerald-700'
                    }`}
                  >
                    {dev.isAuthorized ? 'إيقاف الصلاحية مؤقتاً' : 'تفعيل واعتماد الجهاز'}
                  </button>

                  <button
                    onClick={() => handleDeleteDevice(dev.id, dev.name)}
                    disabled={actionLoading}
                    className="p-2 text-rose-600 hover:bg-rose-100 rounded-xl transition cursor-pointer"
                    title="حذف الجهاز"
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* 5. النوافذ المنبثقة (Modals) */}

      {/* نافذة إضافة جهاز جديد */}
      {showAddDeviceModal && (
        <div className="fixed inset-0 bg-black/50 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl max-w-md w-full p-6 space-y-4 shadow-xl">
            <h3 className="font-black text-base text-slate-900">إضافة جهاز حاسوب معتمد</h3>
            <div className="space-y-3">
              <div>
                <label className="block text-xs font-bold text-slate-700 mb-1">اسم الحاسوب (Computer Name)</label>
                <input
                  type="text"
                  placeholder="مثال: COC-LEGAL-01"
                  value={newDeviceName}
                  onChange={(e) => setNewDeviceName(e.target.value)}
                  className="w-full px-4 py-2.5 text-sm bg-slate-50 border border-slate-300 rounded-xl"
                />
              </div>
              <div>
                <label className="block text-xs font-bold text-slate-700 mb-1">القسم أو الموظف المسؤول</label>
                <input
                  type="text"
                  placeholder="مثال: القسم القانوني"
                  value={newDeviceUser}
                  onChange={(e) => setNewDeviceUser(e.target.value)}
                  className="w-full px-4 py-2.5 text-sm bg-slate-50 border border-slate-300 rounded-xl"
                />
              </div>
              <div>
                <label className="block text-xs font-bold text-slate-700 mb-1">نظام التشغيل</label>
                <input
                  type="text"
                  value={newDeviceOs}
                  onChange={(e) => setNewDeviceOs(e.target.value)}
                  className="w-full px-4 py-2.5 text-sm bg-slate-50 border border-slate-300 rounded-xl"
                />
              </div>
            </div>
            <div className="flex items-center justify-end gap-2 pt-3 border-t">
              <button
                onClick={() => setShowAddDeviceModal(false)}
                className="px-4 py-2 text-sm font-bold text-slate-600 hover:bg-slate-100 rounded-xl transition"
              >
                إلغاء
              </button>
              <button
                onClick={handleAddDevice}
                disabled={!newDeviceName.trim() || actionLoading}
                className="px-5 py-2 text-sm font-bold bg-[#14372e] text-white rounded-xl hover:bg-[#1a473b] transition"
              >
                إضافة واعتماد
              </button>
            </div>
          </div>
        </div>
      )}

      {/* نافذة إضافة قسم جديد */}
      {showAddDeptModal && (
        <div className="fixed inset-0 bg-black/50 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl max-w-md w-full p-6 space-y-4 shadow-xl">
            <h3 className="font-black text-base text-slate-900">إضافة قسم إداري جديد</h3>
            <p className="text-sm text-slate-600">
              سيتم إنشاء مجلد جديد في Google Drive ومزامنته فوراً مع أجهزة الموظفين في الغرفة.
            </p>

            <input
              type="text"
              placeholder="اسم القسم (مثال: الشؤون القانونية)..."
              value={newDeptName}
              onChange={(e) => setNewDeptName(e.target.value)}
              className="w-full px-4 py-3 text-sm font-bold bg-slate-50 border border-slate-300 rounded-xl focus:outline-none focus:ring-2 focus:ring-[#14372e]"
              autoFocus
            />

            <div className="flex items-center justify-end gap-2 pt-2 border-t">
              <button
                onClick={() => setShowAddDeptModal(false)}
                className="px-4 py-2 text-sm font-bold text-slate-600 hover:bg-slate-100 rounded-xl transition"
              >
                إلغاء
              </button>
              <button
                onClick={handleCreateDepartment}
                disabled={actionLoading || !newDeptName.trim()}
                className="px-5 py-2.5 text-sm font-bold bg-[#14372e] text-white rounded-xl hover:bg-[#1a473b] transition shadow-sm disabled:opacity-50"
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
            <h3 className="font-black text-base text-slate-900">تعديل اسم القسم</h3>
            <p className="text-sm text-slate-600">
              الاسم الحالي: <strong className="text-slate-900">{deptToRename.name}</strong>
            </p>

            <input
              type="text"
              value={newDeptRenameValue}
              onChange={(e) => setNewDeptRenameValue(e.target.value)}
              className="w-full px-4 py-3 text-sm font-bold bg-slate-50 border border-slate-300 rounded-xl focus:outline-none focus:ring-2 focus:ring-[#14372e]"
              autoFocus
            />

            <div className="flex items-center justify-end gap-2 pt-2 border-t">
              <button
                onClick={() => setShowRenameDeptModal(false)}
                className="px-4 py-2 text-sm font-bold text-slate-600 hover:bg-slate-100 rounded-xl transition"
              >
                إلغاء
              </button>
              <button
                onClick={handleRenameDepartment}
                disabled={actionLoading || !newDeptRenameValue.trim()}
                className="px-5 py-2.5 text-sm font-bold bg-[#14372e] text-white rounded-xl hover:bg-[#1a473b] transition shadow-sm disabled:opacity-50"
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
            <h3 className="font-black text-base text-slate-900">تعديل اسم المستند</h3>
            <p className="text-sm text-slate-600 break-words">
              الاسم الحالي: <strong className="text-slate-900">{fileToRename.name}</strong>
            </p>

            <input
              type="text"
              value={newFileNameValue}
              onChange={(e) => setNewFileNameValue(e.target.value)}
              className="w-full px-4 py-3 text-sm font-bold bg-slate-50 border border-slate-300 rounded-xl focus:outline-none focus:ring-2 focus:ring-[#14372e]"
              autoFocus
            />

            <div className="flex items-center justify-end gap-2 pt-2 border-t">
              <button
                onClick={() => setShowRenameFileModal(false)}
                className="px-4 py-2 text-sm font-bold text-slate-600 hover:bg-slate-100 rounded-xl transition"
              >
                إلغاء
              </button>
              <button
                onClick={async () => {
                  if (!newFileNameValue.trim()) return;
                  await fetch('/api/drive/files', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ action: 'RENAME', id: fileToRename.id, name: newFileNameValue.trim() }),
                  });
                  setShowRenameFileModal(false);
                  setFileToRename(null);
                  await loadAllData(false);
                  notifyLocalDesktopSync();
                }}
                className="px-5 py-2.5 text-sm font-bold bg-[#14372e] text-white rounded-xl hover:bg-[#1a473b] transition shadow-sm"
              >
                حفظ التعديل
              </button>
            </div>
          </div>
        </div>
      )}

      {/* نافذة التخصيص المفصل لصلاحيات قسم معين */}
      {selectedPermDept && (
        <div className="fixed inset-0 bg-black/60 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-3xl max-w-2xl w-full p-6 space-y-5 shadow-2xl border border-slate-200 max-h-[90vh] overflow-y-auto">
            <div className="flex items-center justify-between border-b border-slate-100 pb-4">
              <div className="flex items-center gap-3">
                <div className="w-12 h-12 rounded-2xl bg-emerald-50 text-[#14372e] border border-emerald-200 flex items-center justify-center shrink-0">
                  <Shield className="w-6 h-6" />
                </div>
                <div>
                  <h3 className="font-black text-base text-slate-900">
                    التخصيص المفصل لصلاحيات قسم:{' '}
                    <span className="text-[#0f6cbd]">{selectedPermDept.folderName}</span>
                  </h3>
                  <p className="text-xs text-slate-600 mt-0.5">
                    يتم حفظ التعديلات مباشرة في سحابة Google Drive وتطبق فوراً على منصة الويب وتطبيق سطح المكتب.
                  </p>
                </div>
              </div>
              <button
                onClick={() => setSelectedPermDept(null)}
                className="p-2 text-slate-400 hover:text-slate-700 hover:bg-slate-100 rounded-xl transition cursor-pointer"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* القوالب الجاهزة السريعة */}
            <div className="bg-slate-50 p-4 rounded-2xl border border-slate-200/80 space-y-2.5">
              <span className="text-xs font-bold text-slate-700 block">قوالب صلاحيات سريعة بنقرة واحدة:</span>
              <div className="flex flex-wrap gap-2">
                <button
                  type="button"
                  onClick={() =>
                    handleSetPresetPermission(selectedPermDept.folderId, selectedPermDept.folderName, 'FULL')
                  }
                  className="px-3.5 py-2 text-xs font-bold rounded-xl bg-emerald-600 text-white hover:bg-emerald-700 transition cursor-pointer"
                >
                  ✅ تحكم كامل (كل الصلاحيات)
                </button>
                <button
                  type="button"
                  onClick={() =>
                    handleSetPresetPermission(
                      selectedPermDept.folderId,
                      selectedPermDept.folderName,
                      'EDIT_NO_DELETE'
                    )
                  }
                  className="px-3.5 py-2 text-xs font-bold rounded-xl bg-sky-600 text-white hover:bg-sky-700 transition cursor-pointer"
                >
                  🛡️ إضافة وتعديل بدون حذف
                </button>
                <button
                  type="button"
                  onClick={() =>
                    handleSetPresetPermission(selectedPermDept.folderId, selectedPermDept.folderName, 'UPLOAD_ONLY')
                  }
                  className="px-3.5 py-2 text-xs font-bold rounded-xl bg-amber-600 text-white hover:bg-amber-700 transition cursor-pointer"
                >
                  📤 رفع وإضافة فقط
                </button>
                <button
                  type="button"
                  onClick={() =>
                    handleSetPresetPermission(selectedPermDept.folderId, selectedPermDept.folderName, 'READ_ONLY')
                  }
                  className="px-3.5 py-2 text-xs font-bold rounded-xl bg-slate-700 text-white hover:bg-slate-800 transition cursor-pointer"
                >
                  👁️ قراءة وتنزيل فقط
                </button>
                <button
                  type="button"
                  onClick={() =>
                    handleSetPresetPermission(selectedPermDept.folderId, selectedPermDept.folderName, 'VIEW_ONLY')
                  }
                  className="px-3.5 py-2 text-xs font-bold rounded-xl bg-purple-700 text-white hover:bg-purple-800 transition cursor-pointer"
                >
                  🔒 تصفح فقط (منع التنزيل والتعديل)
                </button>
                <button
                  type="button"
                  onClick={() =>
                    handleSetPresetPermission(selectedPermDept.folderId, selectedPermDept.folderName, 'LOCKED')
                  }
                  className="px-3.5 py-2 text-xs font-bold rounded-xl bg-rose-700 text-white hover:bg-rose-800 transition cursor-pointer"
                >
                  ⛔ قفل القسم بالكامل
                </button>
              </div>
            </div>

            {/* الصلاحيات التسع بالتفصيل */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              {[
                {
                  key: 'canView' as const,
                  title: '1. تصفح وعرض القسم (View)',
                  desc: 'السماح برؤية القسم واستعراض قائمة الملفات والمجلدات بداخله',
                },
                {
                  key: 'canDownload' as const,
                  title: '2. تنزيل وفتح الملفات (Download & Preview)',
                  desc: 'السماح بمعاينة الصور والملفات وتحميلها إلى الجهاز أو نسخ روابطها',
                },
                {
                  key: 'canUpload' as const,
                  title: '3. رفع وإضافة ملفات جديدة (Upload)',
                  desc: 'السماح برفع ملفات أو صور أو مستندات جديدة داخل هذا القسم',
                },
                {
                  key: 'canCreateFolder' as const,
                  title: '4. إنشاء مجلدات فرعية (Create Folders)',
                  desc: 'السماح بإنشاء مجلدات فرعية تنظيمية داخل القسم',
                },
                {
                  key: 'canEdit' as const,
                  title: '5. تعديل وحفظ المستندات (Edit & Update)',
                  desc: 'السماح بتعديل الملفات المكتبية الحالية وحفظ التعديلات في السحابة',
                },
                {
                  key: 'canRename' as const,
                  title: '6. إعادة تسمية الملفات والمجلدات (Rename)',
                  desc: 'السماح بتغيير أسماء الملفات والمجلدات الفرعية داخل القسم',
                },
                {
                  key: 'canMove' as const,
                  title: '7. نقل الملفات والمجلدات (Move)',
                  desc: 'السماح بنقل الملفات من أو إلى هذا القسم',
                },
                {
                  key: 'canDelete' as const,
                  title: '8. الحذف إلى سلة المهملات (Delete to Trash)',
                  desc: 'السماح بنقل ملفات ومجلدات القسم إلى سلة المهملات',
                },
                {
                  key: 'canPermanentDelete' as const,
                  title: '9. الحذف النهائي وتفريغ السلة (Permanent Delete)',
                  desc: 'السماح بالحذف النهائي غير القابل للاسترجاع لملفات هذا القسم',
                },
              ].map((item) => {
                const isEnabled = Boolean(selectedPermDept[item.key]);
                return (
                  <div
                    key={item.key}
                    onClick={() => handleTogglePermissionKey(selectedPermDept.folderId, item.key)}
                    className={`p-4 rounded-2xl border transition cursor-pointer flex items-center justify-between gap-3 ${
                      isEnabled
                        ? 'bg-emerald-50/50 border-emerald-200 hover:bg-emerald-50'
                        : 'bg-rose-50/40 border-rose-200 hover:bg-rose-50/70'
                    }`}
                  >
                    <div>
                      <h4 className="font-bold text-sm text-slate-900">{item.title}</h4>
                      <p className="text-xs text-slate-600 mt-0.5">{item.desc}</p>
                    </div>
                    <span
                      className={`shrink-0 px-3 py-1.5 rounded-full text-xs font-bold border flex items-center gap-1 ${
                        isEnabled
                          ? 'bg-emerald-600 text-white border-emerald-700'
                          : 'bg-rose-600 text-white border-rose-700'
                      }`}
                    >
                      {isEnabled ? <Check className="w-3.5 h-3.5" /> : <X className="w-3.5 h-3.5" />}
                      {isEnabled ? 'مسموح' : 'محظور'}
                    </span>
                  </div>
                );
              })}
            </div>

            {/* رمز القفل الاختياري للقسم (PIN) */}
            <div className="p-4 rounded-2xl bg-amber-50/60 border border-amber-200 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
              <div>
                <h4 className="text-sm font-bold text-amber-950 flex items-center gap-1.5">
                  <Key className="w-4 h-4 text-amber-700" />
                  <span>رمز حماية القسم الاختياري (Department PIN)</span>
                </h4>
                <p className="text-xs text-amber-800 mt-0.5">
                  اتركه فارغاً للوصول المباشر، أو ضع رمزاً سرياً يُطلب عند محاولة فتح القسم في الويب أو تطبيق الحاسوب.
                </p>
              </div>
              <div className="flex items-center gap-2">
                <input
                  type="text"
                  value={pinInput}
                  onChange={(e) => setPinInput(e.target.value)}
                  placeholder="بدون رمز PIN"
                  className="px-3.5 py-2 text-sm bg-white border border-amber-300 rounded-xl w-40 font-mono font-bold text-center focus:outline-none focus:ring-2 focus:ring-amber-600"
                />
                <button
                  type="button"
                  onClick={async () => {
                    const updated: PermissionRule = {
                      ...selectedPermDept,
                      pinCode: pinInput.trim(),
                    };
                    setSelectedPermDept(updated);
                    setPermissions((prev) => prev.map((p) => (p.folderId === updated.folderId ? updated : p)));
                    await persistPermissionRule(
                      updated,
                      pinInput.trim()
                        ? `🔑 تم تفعيل وحفظ رمز PIN لقسم "${updated.folderName}" في السحابة!`
                        : `🔓 تمت إزالة رمز PIN لقسم "${updated.folderName}"!`
                    );
                  }}
                  className="px-4 py-2 text-xs font-bold bg-amber-700 text-white rounded-xl hover:bg-amber-800 transition cursor-pointer"
                >
                  حفظ الرمز
                </button>
              </div>
            </div>

            <div className="flex items-center justify-end gap-2 pt-3 border-t border-slate-100">
              <button
                type="button"
                onClick={() => setSelectedPermDept(null)}
                className="px-6 py-2.5 text-sm font-bold bg-[#14372e] text-white rounded-xl hover:bg-[#1a473b] transition cursor-pointer"
              >
                إغلاق وتم الحفظ
              </button>
            </div>
          </div>
        </div>
      )}

      {/* إشعار عائم Toast */}
      {toastMessage && (
        <div className="fixed bottom-6 left-1/2 -translate-x-1/2 z-50 shadow-2xl pointer-events-none">
          <div
            className={`flex items-center gap-2.5 px-6 py-3.5 rounded-2xl text-sm font-bold border backdrop-blur-md ${
              toastMessage.type === 'success'
                ? 'bg-[#14372e]/95 text-white border-emerald-400'
                : toastMessage.type === 'error'
                ? 'bg-rose-900/95 text-white border-rose-400'
                : 'bg-slate-900/95 text-white border-slate-700'
            }`}
          >
            <span>{toastMessage.text}</span>
          </div>
        </div>
      )}
    </div>
  );
}
