'use client';

import { useState, useEffect, useRef } from 'react';
import { 
  Folder, 
  FileText, 
  Download, 
  Trash2, 
  Upload, 
  Camera,
  Search, 
  Check, 
  FileSpreadsheet,
  Database,
  Inbox,
  RefreshCw,
  FolderPlus,
  Edit3,
  RotateCcw,
  Sparkles,
  ArrowRight,
  ChevronLeft,
  X,
  FileCode,
  AlertCircle,
  ExternalLink,
  Eye,
  Monitor,
  FolderOpen,
  Share2,
  Smartphone,
  UploadCloud,
  CheckCircle2,
  Play
} from 'lucide-react';
// Google Drive Connected

interface FileItem {
  id: string;
  name: string;
  folder: string;
  department: string;
  subFolder: string;
  type: 'word' | 'excel' | 'access' | 'pdf' | 'image' | 'file';
  size: string;
  rawSize: number;
  version: number;
  lastModifiedBy: string;
  lastModifiedAt: string;
  storagePath: string;
  isDeleted: boolean;
  previewUrl?: string;
  downloadUrl?: string;
}

interface CloudFolderItem {
  id: string;
  name: string;
  path: string;
  parentPath: string;
  department: string;
}

const MIME_MAP: Record<string, string> = {
  docx: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
  doc: 'application/msword',
  xlsx: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  xls: 'application/vnd.ms-excel',
  pptx: 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
  ppt: 'application/vnd.ms-powerpoint',
  pdf: 'application/pdf',
  jpg: 'image/jpeg',
  jpeg: 'image/jpeg',
  png: 'image/png',
  webp: 'image/webp',
  accdb: 'application/msaccess',
  mdb: 'application/msaccess',
};

// دالة تنظيف اسم الملف من أي محارف مخفية أو محارف اتجاه غير مرئية (Bidi / Isolates)
const cleanFileNameString = (rawName: string): string => {
  return rawName.replace(/[\u200B-\u200F\u202A-\u202E\u2066-\u2069\uFEFF]/g, '').trim();
};

// دالة توليد مسار تخزين سحابي متوافق 100% مع معايير S3 لأسماء الملفات العربية والمسافات
const getSafeStorageKey = (rawName: string): string => {
  const clean = cleanFileNameString(rawName);
  const ext = clean.includes('.') ? '.' + clean.split('.').pop()?.toLowerCase() : '';
  const utf8Bytes = new TextEncoder().encode(clean);
  let binary = '';
  for (let i = 0; i < utf8Bytes.length; i++) {
    binary += String.fromCharCode(utf8Bytes[i]);
  }
  const b64 = btoa(binary).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
  return `shared/${b64}${ext}`;
};

export default function FilesPage() {
  const [activeTab, setActiveTab] = useState<'ACTIVE' | 'TRASH'>('ACTIVE');
  const [selectedDept, setSelectedDept] = useState<string>('__ALL__');
  const [currentFolder, setCurrentFolder] = useState<string | null>(null);
  const [searchTerm, setSearchTerm] = useState('');
  const [filterType, setFilterType] = useState<string>('ALL');

  const [files, setFiles] = useState<FileItem[]>([]);
  const [folderMap, setFolderMap] = useState<Record<string, string>>({});
  const [allFolders, setAllFolders] = useState<CloudFolderItem[]>([]);
  const [folders, setFolders] = useState<string[]>([]);
  const [departments, setDepartments] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState(false);
  const [permissionsMap, setPermissionsMap] = useState<Record<string, { canWrite: boolean; canDelete: boolean }>>({});

  const canDeleteFolder = (folderName?: string) => {
    if (!folderName || folderName === '__ALL__' || folderName === 'كافة الملفات') return true;
    return permissionsMap[folderName]?.canDelete !== false;
  };

  const canWriteFolder = (folderName?: string) => {
    if (!folderName || folderName === '__ALL__' || folderName === 'كافة الملفات') return true;
    return permissionsMap[folderName]?.canWrite !== false;
  };

  // نوافذ الحوار (Modals)
  const [showNewFolderModal, setShowNewFolderModal] = useState(false);
  const [newFolderName, setNewFolderName] = useState('');
  const [showRenameModal, setShowRenameModal] = useState(false);
  const [itemToRename, setItemToRename] = useState<{ id: string; name: string; isFolder?: boolean } | null>(null);
  const [newRenameValue, setNewRenameValue] = useState('');

  // نافذة خيارات فتح المستند على الهاتف المحمول (Mobile Action Sheet)
  const [selectedMobileFile, setSelectedMobileFile] = useState<FileItem | null>(null);
  const [preparingMobileOpen, setPreparingMobileOpen] = useState(false);

  // إشعار عائم للمستخدم عند فتح الملفات
  const [toastMessage, setToastMessage] = useState<{ text: string; type: 'success' | 'info' | 'error' } | null>(null);

  useEffect(() => {
    if (toastMessage) {
      const timer = setTimeout(() => setToastMessage(null), 4500);
      return () => clearTimeout(timer);
    }
  }, [toastMessage]);

  // مراجع رفع الملفات والكاميرا وتحديث المستندات المعدلة
  const fileInputRef = useRef<HTMLInputElement>(null);
  const folderInputRef = useRef<HTMLInputElement>(null);
  const cameraInputRef = useRef<HTMLInputElement>(null);
  const updateFileInputRef = useRef<HTMLInputElement>(null);
  const [fileToUpdate, setFileToUpdate] = useState<FileItem | null>(null);

  // حالة شريط تقدم الرفع المباشر
  const [uploadProgress, setUploadProgress] = useState<{
    show: boolean;
    total: number;
    current: number;
    currentFileName: string;
    percentage: number;
    completed: boolean;
  } | null>(null);

  // تشغيل نافذة اختيار الملف لتحديث مستند موجود بنسخة معدلة
  const triggerUpdateFile = (file: FileItem) => {
    setFileToUpdate(file);
    if (updateFileInputRef.current) {
      updateFileInputRef.current.value = '';
      updateFileInputRef.current.click();
    }
  };

  const formatSize = (bytes: number) => {
    if (!bytes || bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return `${parseFloat((bytes / Math.pow(k, i)).toFixed(1))} ${sizes[i]}`;
  };

  const getFileType = (name: string): 'word' | 'excel' | 'access' | 'pdf' | 'image' | 'file' => {
    const ext = name.split('.').pop()?.toLowerCase();
    if (ext === 'docx' || ext === 'doc') return 'word';
    if (ext === 'xlsx' || ext === 'xls' || ext === 'csv') return 'excel';
    if (ext === 'accdb' || ext === 'mdb') return 'access';
    if (ext === 'pdf') return 'pdf';
    if (['jpg', 'jpeg', 'png', 'webp', 'gif'].includes(ext || '')) return 'image';
    return 'file';
  };

  const loadData = async () => {
    try {
      setLoading(true);

      const res = await fetch('/api/drive/files');
      const data = await res.json();
      if (data.success) {
        const loadedFolders: string[] = (data.folders || []).map((f: any) => f.name);
        const fMap: Record<string, string> = {};
        (data.folders || []).forEach((f: any) => {
          if (f.name && f.id) fMap[f.name] = f.id;
        });
        const fullFolders: CloudFolderItem[] = (data.allFolders || []).map((f: any) => ({
          id: f.id,
          name: f.name,
          path: f.path || f.name,
          parentPath: f.parentPath || '',
          department: f.department || (f.path ? f.path.split('/')[0] : f.name),
        }));
        fullFolders.forEach((f) => {
          if (f.path && f.id) fMap[f.path] = f.id;
          if (!f.parentPath && f.name && f.id) fMap[f.name] = f.id;
        });
        setFolderMap(fMap);
        setAllFolders(fullFolders);
        setFolders(loadedFolders);
        setDepartments(loadedFolders);
        setSelectedDept(prev => (prev === '__ALL__' || loadedFolders.includes(prev)) ? prev : '__ALL__');

        const mapped: FileItem[] = (data.files || []).map((f: any) => ({
          id: f.id,
          name: f.name,
          folder: f.folder || 'القسم العام',
          department: f.department || (f.folder ? String(f.folder).split('/')[0] : 'القسم العام'),
          subFolder: f.subFolder || (f.folder && String(f.folder).includes('/') ? String(f.folder).split('/').slice(1).join('/') : ''),
          type: getFileType(f.name),
          size: formatSize(f.size || 0),
          rawSize: f.size || 0,
          version: 1,
          lastModifiedBy: 'سحابة Google Drive',
          lastModifiedAt: f.modifiedTime ? new Date(f.modifiedTime).toLocaleDateString('ar-IQ', {
            month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit'
          }) : 'الآن',
          storagePath: f.id,
          isDeleted: Boolean(f.isDeleted),
          previewUrl: f.previewUrl,
          downloadUrl: f.downloadUrl,
        }));
        setFiles(mapped);
      }
    } catch (err) {
      console.error('Error fetching files:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
    const interval = setInterval(() => {
      loadData();
    }, 10000);
    return () => clearInterval(interval);
  }, []);

  // تحديث محتوى مستند موجود بنسخة معدلة من الهاتف أو الكمبيوتر ومشاركتها فوراً
  const handleUpdateFile = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const selectedFile = event.target.files?.[0];
    if (!selectedFile || !fileToUpdate) return;

    const targetFile = fileToUpdate;

    try {
      setActionLoading(true);
      setToastMessage({
        text: `⏳ جاري رفع النسخة المعدلة لـ "${targetFile.name}" وحفظها في Google Drive...`,
        type: 'info'
      });

      const folderId = folderMap[targetFile.folder] || '';
      const formData = new FormData();
      formData.append('file', selectedFile, targetFile.name);
      if (folderId) {
        formData.append('folderId', folderId);
      }

      const res = await fetch('/api/drive/files', {
        method: 'POST',
        body: formData,
      });
      const data = await res.json();
      if (!data.success) {
        throw new Error(data.error || 'فشل تحديث المستند في Google Drive');
      }

      setSelectedMobileFile(null);
      setFileToUpdate(null);
      await loadData();

      setToastMessage({
        text: `🎉 تم حفظ التعديلات ومزامنتها فوراً مع كافة الأجهزة!`,
        type: 'success'
      });

      alert(
        `✅ تم حفظ التعديلات بنجاح في Google Drive!

` +
        `📄 المستند: ${targetFile.name}
` +
        `👥 تمت مزامنة التعديلات فوراً مع تطبيق الحاسوب وكافة المستخدمين.`
      );
    } catch (err: any) {
      console.error('Error updating file:', err);
      alert(`تعذر حفظ التعديلات في النظام: ${err.message || err}`);
    } finally {
      setActionLoading(false);
      if (event.target) event.target.value = '';
    }
  };

  // رفع ملفات متعددة مع شريط تقدم مباشر
  const handleFileUpload = async (event: React.ChangeEvent<HTMLInputElement>, isCameraCapture = false) => {
    const fileList = event.target.files;
    if (!fileList || fileList.length === 0) return;

    const filesToUpload = Array.from(fileList);
    const total = filesToUpload.length;

    const activeUploadDept = currentFolder || (selectedDept !== '__ALL__' ? selectedDept : 'القسم العام');
    const targetFolderId = folderMap[activeUploadDept] || '';

    setUploadProgress({
      show: true,
      total,
      current: 0,
      currentFileName: filesToUpload[0].name,
      percentage: 0,
      completed: false,
    });

    let successCount = 0;

    for (let i = 0; i < total; i++) {
      const file = filesToUpload[i];
      const timestamp = new Date().toISOString().replace(/[:.]/g, '-');
      let fileName = cleanFileNameString(file.name);

      if (isCameraCapture) {
        fileName = `كتاب_رسمي_مصور_${timestamp}.jpg`;
      }

      setUploadProgress({
        show: true,
        total,
        current: i + 1,
        currentFileName: fileName,
        percentage: Math.round((i / total) * 100),
        completed: false,
      });

      try {
        const formData = new FormData();
        formData.append('file', file, fileName);
        if (targetFolderId) {
          formData.append('folderId', targetFolderId);
        }

        const res = await fetch('/api/drive/files', {
          method: 'POST',
          body: formData,
        });
        const data = await res.json();
        if (data.success) {
          successCount++;
        }
      } catch (err) {
        console.error('Error uploading file:', fileName, err);
      }

      setUploadProgress({
        show: true,
        total,
        current: i + 1,
        currentFileName: fileName,
        percentage: Math.round(((i + 1) / total) * 100),
        completed: i + 1 === total,
      });
    }

    await loadData();
    setTimeout(() => {
      setUploadProgress(null);
    }, 2200);

    if (event.target) event.target.value = '';
  };

  // رفع مجلد كامل مع الحفاظ على هيكلية المجلدات الفرعية
  const handleFolderUpload = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const fileList = event.target.files;
    if (!fileList || fileList.length === 0) return;

    const filesToUpload = Array.from(fileList);
    const total = filesToUpload.length;

    const activeUploadDept = currentFolder || (selectedDept !== '__ALL__' ? selectedDept : 'القسم العام');
    const baseParentId = folderMap[activeUploadDept] || '';

    setUploadProgress({
      show: true,
      total,
      current: 0,
      currentFileName: 'جاري إنشاء المجلدات الفرعية...',
      percentage: 0,
      completed: false,
    });

    const createdFolderIds: Record<string, string> = {};
    let successCount = 0;

    for (let i = 0; i < total; i++) {
      const file = filesToUpload[i];
      const relPath = (file as any).webkitRelativePath || file.name;
      const parts = relPath.split('/');
      const fileName = cleanFileNameString(parts.pop() || file.name);

      setUploadProgress({
        show: true,
        total,
        current: i + 1,
        currentFileName: `${parts.length > 0 ? parts.join('/') + ' / ' : ''}${fileName}`,
        percentage: Math.round((i / total) * 100),
        completed: false,
      });

      let currentParentId = baseParentId;
      let pathAcc = '';

      for (const seg of parts) {
        pathAcc = pathAcc ? `${pathAcc}/${seg}` : seg;
        if (!createdFolderIds[pathAcc]) {
          try {
            const createRes = await fetch('/api/drive/files', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({
                action: 'CREATE_FOLDER',
                name: seg,
                parentId: currentParentId || undefined,
              }),
            });
            const createData = await createRes.json();
            if (createData.success && createData.folder) {
              createdFolderIds[pathAcc] = createData.folder.id;
            }
          } catch (createErr) {
            console.error('Error creating folder:', seg, createErr);
          }
        }
        if (createdFolderIds[pathAcc]) {
          currentParentId = createdFolderIds[pathAcc];
        }
      }

      try {
        const formData = new FormData();
        formData.append('file', file, fileName);
        if (currentParentId) {
          formData.append('folderId', currentParentId);
        }

        const res = await fetch('/api/drive/files', {
          method: 'POST',
          body: formData,
        });
        const data = await res.json();
        if (data.success) {
          successCount++;
        }
      } catch (err) {
        console.error('Error uploading file in folder:', fileName, err);
      }

      setUploadProgress({
        show: true,
        total,
        current: i + 1,
        currentFileName: fileName,
        percentage: Math.round(((i + 1) / total) * 100),
        completed: i + 1 === total,
      });
    }

    await loadData();
    setTimeout(() => {
      setUploadProgress(null);
    }, 2200);

    if (event.target) event.target.value = '';
  };
  // نقل الملف لسلة المحذوفات
  const handleMoveToTrash = async (file: FileItem) => {
    if (!confirm(`هل أنت متأكد من نقل المستند "${file.name}" إلى سلة المحذوفات؟`)) return;
    try {
      setActionLoading(true);
      const res = await fetch(`/api/drive/files?id=${file.id}`, { method: 'DELETE' });
      const data = await res.json();
      if (!data.success) throw new Error(data.error);
      await loadData();
    } catch (e: any) {
      alert(`تعذر نقل الملف: ${e.message || e}`);
    } finally {
      setActionLoading(false);
    }
  };

  // استرجاع المستند من سلة المحذوفات
  const handleRestoreFile = async (file: FileItem) => {
    try {
      setActionLoading(true);
      const res = await fetch('/api/drive/files', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'RESTORE', id: file.id }),
      });
      const data = await res.json();
      if (!data.success) throw new Error(data.error);
      await loadData();
      alert(`♻️ تم استرجاع المستند "${file.name}" بنجاح.`);
    } catch (e: any) {
      alert(`تعذر الاسترجاع: ${e.message || e}`);
    } finally {
      setActionLoading(false);
    }
  };

  // استرجاع كافة محذوفات القسم
  const handleRestoreAll = async () => {
    const trashItems = files.filter(f => f.isDeleted && (selectedDept === '__ALL__' || f.folder === selectedDept));
    if (trashItems.length === 0) return;
    if (!confirm(`هل أنت متأكد من استرجاع كافة المحذوفات (${trashItems.length} مستندات)؟`)) return;

    try {
      setActionLoading(true);
      for (const item of trashItems) {
        await fetch('/api/drive/files', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ action: 'RESTORE', id: item.id }),
        });
      }
      await loadData();
      alert(`✅ تم استرجاع كافة المحذوفات بنجاح.`);
    } catch (e: any) {
      alert(`تعذر استرجاع المحذوفات: ${e.message || e}`);
    } finally {
      setActionLoading(false);
    }
  };

  // حذف نهائي للمستند
  const handlePermanentDelete = async (file: FileItem) => {
    if (!confirm(`⚠️ تحذير: سيتم حذف المستند "${file.name}" نهائياً من Google Drive ولا يمكن استرجاعه. هل تود المتابعة؟`)) return;
    try {
      setActionLoading(true);
      const res = await fetch(`/api/drive/files?id=${file.id}&permanent=true`, { method: 'DELETE' });
      const data = await res.json();
      if (!data.success) throw new Error(data.error);
      setFiles(prev => prev.filter(f => f.id !== file.id));
      await loadData();
    } catch (e: any) {
      alert(`فشل الحذف النهائي: ${e.message || e}`);
    } finally {
      setActionLoading(false);
    }
  };

  // إفراغ سلة المحذوفات
  const handleEmptyTrash = async () => {
    const trashItems = files.filter(f => f.isDeleted && (selectedDept === '__ALL__' || f.folder === selectedDept));
    if (trashItems.length === 0) return;
    if (!confirm(`⚠️ هل أنت متأكد من إفراغ سلة المحذوفات نهائياً (${trashItems.length} مستندات)؟`)) return;

    try {
      setActionLoading(true);
      for (const item of trashItems) {
        await fetch(`/api/drive/files?id=${item.id}&permanent=true`, { method: 'DELETE' });
      }
      await loadData();
      alert('🧹 تم إفراغ سلة المحذوفات بنجاح.');
    } catch (e: any) {
      alert(`تعذر إفراغ السلة: ${e.message || e}`);
    } finally {
      setActionLoading(false);
    }
  };

  // رابط تنزيل مباشر
  const getFileDirectUrl = async (file: FileItem): Promise<string> => {
    if (file.downloadUrl) return file.downloadUrl;
    if (file.previewUrl) return file.previewUrl;
    return `https://drive.google.com/uc?id=${file.id}&export=download`;
  };

  // 1. فتح المستند مباشرة في برنامج Office الأصلي (سواء على الهاتف أو الحاسوب)
  const handleOpenFile = async (file: FileItem) => {
    const isOffice = ['word', 'excel', 'access'].includes(file.type);
    const officeName = file.type === 'word' ? 'Word' : file.type === 'excel' ? 'Excel' : file.type === 'access' ? 'Access' : 'البرنامج الأصلي';

    // فحص ما إذا كان المستخدم يتصفح من هاتف محمول (Android أو iOS)
    const isMobile = typeof navigator !== 'undefined' && /Android|iPhone|iPad|iPod/i.test(navigator.userAgent);

    if (isMobile) {
      if (['word', 'excel'].includes(file.type)) {
        // فتح بطاقة الإرشاد والتشغيل التفاعلية للهاتف
        setSelectedMobileFile(file);
        // تشغيل فوري للتطبيق عبر Web Share مع نوع MIME دقيق لفتح Word/Excel فوراً
        handleOpenInMobileApp(file);
        return;
      } else if (file.type === 'access') {
        alert('ملفات Microsoft Access (.accdb) مخصصة لحواسيب الويندوز فقط.');
        return;
      } else {
        // PDF أو صورة أو ملف عام: فتح مباشر في المتصفح أو تطبيق العرض الافتراضي
        const inlineUrl = `/api/storage/download?path=${encodeURIComponent(file.storagePath)}&name=${encodeURIComponent(file.name)}&inline=true`;
        window.open(inlineUrl, '_blank');
        return;
      }
    }

    // --- في حال العمل على جهاز حاسوب (Desktop Windows) ---
    setToastMessage({
      text: `⏳ جاري فتح "${file.name}" في برنامج ${officeName}...`,
      type: 'info'
    });

    // أولاً: استدعاء خادم الجسر المحلي لتطبيق الويندوز share coc على المنفذ 18290
    try {
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 4000);
      const bridgeUrl = `http://127.0.0.1:18290/open?file=${encodeURIComponent(file.name)}&folder=${encodeURIComponent(file.folder)}&storage_path=${encodeURIComponent(file.storagePath)}`;
      const res = await fetch(bridgeUrl, { signal: controller.signal });
      clearTimeout(timeoutId);

      if (res.ok) {
        const result = await res.json();
        if (result.success) {
          setToastMessage({
            text: `🚀 تم تشغيل برنامج ${officeName} الأصلي وفتح المستند بنجاح!`,
            type: 'success'
          });
          return;
        }
      }
    } catch {
      // إذا لم يكن الجسر المحلي يعمل أو تأخر
    }

    // ثانياً: استدعاء بروتوكول الويندوز المسجل sharecoc:// لتشغيل التطبيق والملف
    try {
      const iframe = document.createElement('iframe');
      iframe.style.display = 'none';
      iframe.src = `sharecoc://open?file=${encodeURIComponent(file.name)}&folder=${encodeURIComponent(file.folder)}&storage_path=${encodeURIComponent(file.storagePath)}`;
      document.body.appendChild(iframe);
      setTimeout(() => {
        try { document.body.removeChild(iframe); } catch {}
      }, 2500);
    } catch {}

    // إذا على حاسوب شخصي والجسر غير نشط، نبلغ المستخدم
    setTimeout(() => {
      setToastMessage({
        text: `💡 نصيحة: تطبيق share coc يقوم بفتح ملفات Office على الكمبيوتر فوراً وبدون تحميل.`,
        type: 'info'
      });
    }, 1800);
  };

  // تشغيل المستند في تطبيق الهاتف الأصلي (Word / Excel / WPS) عبر Web Share مع نوع MIME دقيق
  const handleOpenInMobileApp = async (file: FileItem) => {
    try {
      setPreparingMobileOpen(true);
      setToastMessage({
        text: `⏳ جاري تحضير وفتح "${file.name}" في التطبيق...`,
        type: 'info'
      });

      const directUrl = await getFileDirectUrl(file);
      const response = await fetch(directUrl);
      const blob = await response.blob();
      const ext = file.name.split('.').pop()?.toLowerCase() || '';
      const mimeType = MIME_MAP[ext] || blob.type || 'application/octet-stream';
      const fileObj = new File([blob], file.name, {
        type: mimeType,
        lastModified: Date.now()
      });

      if (typeof navigator !== 'undefined' && navigator.canShare && navigator.canShare({ files: [fileObj] })) {
        await navigator.share({
          files: [fileObj],
          title: file.name,
          text: `مستند: ${file.name}`
        });
        setToastMessage({
          text: `🚀 تم فتح قائمة تطبيقات الهاتف للمستند بنجاح!`,
          type: 'success'
        });
        return;
      }

      // إذا لم يكن Web Share مدعوماً، نجرب بروتوكول Microsoft 365 المباشر
      if (['word', 'excel'].includes(file.type)) {
        const scheme = file.type === 'word' ? 'ms-word' : 'ms-excel';
        window.location.href = `${scheme}:ofe|u|${directUrl}`;
        return;
      }

      // كخيار أخير: تنزيل مباشر
      handleDownloadFile(file);
    } catch (err: any) {
      if (err.name !== 'AbortError') {
        const directUrl = await getFileDirectUrl(file);
        if (['word', 'excel'].includes(file.type)) {
          const scheme = file.type === 'word' ? 'ms-word' : 'ms-excel';
          window.location.href = `${scheme}:ofe|u|${directUrl}`;
        }
      }
    } finally {
      setPreparingMobileOpen(false);
    }
  };

  // استدعاء بروتوكول Microsoft Office المباشر (ms-word / ms-excel)
  const handleLaunchOfficeProtocol = async (file: FileItem) => {
    try {
      setToastMessage({
        text: `⏳ جاري استدعاء تطبيق Microsoft Office...`,
        type: 'info'
      });
      const directUrl = await getFileDirectUrl(file);
      const ext = file.name.split('.').pop()?.toLowerCase() || '';
      let scheme = 'ms-word';
      if (ext === 'xlsx' || ext === 'xls') scheme = 'ms-excel';
      if (ext === 'pptx' || ext === 'ppt') scheme = 'ms-powerpoint';

      window.location.href = `${scheme}:ofe|u|${directUrl}`;
    } catch (e: any) {
      alert(`تعذر استدعاء التطبيق: ${e.message || e}`);
    }
  };

  // 2. فتح المستند في تطبيقات الهاتف المختلفة أو مشاركته (Web Share API)
  const handleShareFile = async (file: FileItem) => {
    try {
      setToastMessage({
        text: `⏳ جاري تجهيز "${file.name}" للهاتف...`,
        type: 'info'
      });
      const directUrl = await getFileDirectUrl(file);
      const response = await fetch(directUrl);
      const blob = await response.blob();
      const fileObj = new File([blob], file.name, {
        type: blob.type || 'application/octet-stream',
        lastModified: Date.now()
      });

      if (typeof navigator !== 'undefined' && navigator.canShare && navigator.canShare({ files: [fileObj] })) {
        await navigator.share({
          files: [fileObj],
          title: file.name,
          text: `مستند من غرفة تجارة كربلاء المقدسة: ${file.name}`
        });
        setToastMessage({
          text: `✅ تم فتح قائمة تطبيقات الهاتف للمستند بنجاح.`,
          type: 'success'
        });
        return;
      } else {
        // إذا لم يكن المتصفح يدعم مشاركة الملفات، فتحه في نافذة جديدة
        window.open(directUrl, '_blank');
      }
    } catch (err: any) {
      if (err.name !== 'AbortError') {
        const directUrl = await getFileDirectUrl(file);
        window.open(directUrl, '_blank');
      }
    }
  };

  // 2. معاينة المستند عبر متصفح الويب باستخدام Microsoft Office Online
  const handleOpenOfficeOnline = async (file: FileItem) => {
    try {
      const directUrl = await getFileDirectUrl(file);
      const viewerUrl = `https://view.officeapps.live.com/op/view.aspx?src=${encodeURIComponent(directUrl)}`;
      window.open(viewerUrl, '_blank');
    } catch (e: any) {
      alert(`تعذر فتح المعاينة: ${e.message || e}`);
    }
  };

  // 3. تنزيل نسخة عادية من الملف بالاسم العربي الصريح
  const handleDownloadFile = async (file: FileItem) => {
    try {
      const downloadUrl = file.downloadUrl || (await getFileDirectUrl(file));
      window.open(downloadUrl, '_blank');

      setToastMessage({
        text: `📥 جاري تنزيل "${file.name}"...`,
        type: 'info'
      });
    } catch (e: any) {
      alert(`فشل التحميل: ${e.message || e}`);
    }
  };
  // 4. إظهار الملف داخل مجلد الويندوز (Reveal in Explorer)
  const handleRevealInExplorer = async (file: FileItem) => {
    try {
      const res = await fetch(`http://127.0.0.1:18290/reveal?file=${encodeURIComponent(file.name)}&folder=${encodeURIComponent(file.folder)}`);
      if (res.ok) {
        setToastMessage({
          text: `📂 تم إظهار المستند في مجلد الويندوز FileExchangeShared.`,
          type: 'success'
        });
        return;
      }
    } catch {}
    setToastMessage({
      text: `المستند مخزن محلياً في مجلد: C:\\Users\\...\\FileExchangeShared`,
      type: 'info'
    });
  };

  // إنشاء مجلد جديد (في القسم الرئيسي أو داخل المجلد الفرعي المفتوح حالياً)
  const handleCreateFolder = async () => {
    const fName = newFolderName.trim();
    if (!fName) return;
    try {
      setActionLoading(true);
      const targetParentPath = currentFolder || (selectedDept !== '__ALL__' ? selectedDept : '');
      const parentId = targetParentPath ? folderMap[targetParentPath] : undefined;
      const res = await fetch('/api/drive/files', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'CREATE_FOLDER', name: fName, parentId }),
      });
      const data = await res.json();
      if (!data.success) throw new Error(data.error);

      setShowNewFolderModal(false);
      setNewFolderName('');
      await loadData();
      alert(`📁 تم إنشاء المجلد "${fName}" في Google Drive بنجاح.`);
    } catch (e: any) {
      alert(`تعذر إنشاء المجلد: ${e.message || e}`);
    } finally {
      setActionLoading(false);
    }
  };

  // نقل مجلد إلى سلة المحذوفات
  const handleMoveFolderToTrash = async (folder: CloudFolderItem) => {
    if (!confirm(`هل أنت متأكد من نقل المجلد "${folder.name}" ومحتوياته إلى سلة المحذوفات؟`)) return;
    try {
      setActionLoading(true);
      const res = await fetch(`/api/drive/files?id=${folder.id}&permanent=false`, {
        method: 'DELETE',
      });
      const data = await res.json();
      if (!data.success) throw new Error(data.error);
      if (currentFolder === folder.path || (currentFolder && currentFolder.startsWith(folder.path + '/'))) {
        setCurrentFolder(folder.parentPath || null);
      }
      await loadData();
    } catch (e: any) {
      alert(`تعذر حذف المجلد: ${e.message || e}`);
    } finally {
      setActionLoading(false);
    }
  };

  // تعديل اسم المستند أو المجلد
  const handleSaveRename = async () => {
    if (!itemToRename || !newRenameValue.trim()) return;
    const oldName = itemToRename.name;
    let newName = newRenameValue.trim();

    // الحفاظ على الامتداد للمستندات فقط (وليس المجلدات)
    if (!itemToRename.isFolder) {
      const oldExt = oldName.includes('.') ? '.' + oldName.split('.').pop() : '';
      if (oldExt && !newName.includes('.')) {
        newName += oldExt;
      }
    }

    if (newName === oldName) {
      setShowRenameModal(false);
      return;
    }

    try {
      setActionLoading(true);
      const res = await fetch('/api/drive/files', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'RENAME', id: itemToRename.id, name: newName }),
      });
      const data = await res.json();
      if (!data.success) throw new Error(data.error);

      setShowRenameModal(false);
      setItemToRename(null);
      await loadData();
      alert(`✏️ تم تعديل الاسم إلى "${newName}" بنجاح في Google Drive.`);
    } catch (e: any) {
      alert(`تعذر تعديل الاسم: ${e.message || e}`);
    } finally {
      setActionLoading(false);
    }
  };

  // تصفية الملفات والمجلدات حسب التبويب (نشط / محذوف)، القسم، المجلد المفتوح، البحث، والنوع
  const activeFiles = files.filter(f => !f.isDeleted);
  const trashFiles = files.filter(f => f.isDeleted);

  const activeBrowsePath = currentFolder || (selectedDept !== '__ALL__' ? selectedDept : '');
  const visibleSubfolders = activeTab === 'ACTIVE' && !searchTerm.trim()
    ? allFolders.filter(folder => folder.parentPath === activeBrowsePath)
    : [];

  const displayedList = (activeTab === 'ACTIVE' ? activeFiles : trashFiles).filter(f => {
    const matchSearch = !searchTerm.trim() ||
      f.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
      f.folder.toLowerCase().includes(searchTerm.toLowerCase());
    const matchType = filterType === 'ALL' || f.type.toUpperCase() === filterType;

    if (searchTerm.trim()) {
      const matchDeptSearch = selectedDept === '__ALL__' || f.department === selectedDept || f.folder === selectedDept || f.folder.startsWith(selectedDept + '/');
      return matchDeptSearch && matchSearch && matchType;
    }

    if (currentFolder) {
      return f.folder === currentFolder && matchType;
    }

    if (selectedDept !== '__ALL__') {
      // في حال وجود مجلدات فرعية معروضة بالأعلى، اعرض المستندات المباشرة في هذا المستوى أو كافة المستندات إذا لم توجد مجلدات فرعية
      if (visibleSubfolders.length > 0) {
        return f.folder === selectedDept && matchType;
      }
      return (f.department === selectedDept || f.folder === selectedDept || f.folder.startsWith(selectedDept + '/')) && matchType;
    }

    return matchSearch && matchType;
  });

  const getFileBadge = (type: string) => {
    switch (type) {
      case 'word':
        return <span className="bg-sky-50 text-sky-700 border border-sky-200 text-[10px] font-bold px-2 py-0.5 rounded">Word</span>;
      case 'excel':
        return <span className="bg-emerald-50 text-emerald-700 border border-emerald-200 text-[10px] font-bold px-2 py-0.5 rounded">Excel</span>;
      case 'access':
        return <span className="bg-amber-50 text-amber-800 border border-amber-200 text-[10px] font-bold px-2 py-0.5 rounded">Access</span>;
      case 'pdf':
        return <span className="bg-rose-50 text-rose-700 border border-rose-200 text-[10px] font-bold px-2 py-0.5 rounded">PDF</span>;
      case 'image':
        return <span className="bg-purple-50 text-purple-700 border border-purple-200 text-[10px] font-bold px-2 py-0.5 rounded">صورة/كاميرا</span>;
      default:
        return <span className="bg-slate-50 text-slate-700 border border-slate-200 text-[10px] font-bold px-2 py-0.5 rounded">مستند</span>;
    }
  };

  const getFileIcon = (type: string) => {
    switch (type) {
      case 'word': return <FileText className="w-5 h-5 text-sky-600" />;
      case 'excel': return <FileSpreadsheet className="w-5 h-5 text-emerald-600" />;
      case 'access': return <Database className="w-5 h-5 text-amber-700" />;
      case 'pdf': return <FileText className="w-5 h-5 text-rose-600" />;
      case 'image': return <Camera className="w-5 h-5 text-purple-600" />;
      default: return <FileCode className="w-5 h-5 text-slate-500" />;
    }
  };

  return (
    <div className="p-3 sm:p-6 md:p-8 space-y-4 max-w-7xl mx-auto w-full">
      {/* 1. الترويسة وأزرار الإجراءات السريعة (متجاوبة تماماً مع الجوال) */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 bg-white p-4 rounded-2xl border border-slate-200 shadow-sm">
        <div>
          <div className="flex items-center gap-2">
            <span className="text-xl sm:text-2xl font-black text-[#14372e]">
              {selectedDept === '__ALL__' ? 'كافة المستندات والمجلدات' : selectedDept}
            </span>
            <span className="text-xs bg-[#14372e]/10 text-[#14372e] font-bold px-2 py-0.5 rounded-full border border-[#14372e]/20">
              {displayedList.length} مستند
            </span>
          </div>
          <p className="text-xs text-slate-500 mt-0.5">
            مزامنة سحابية مباشرة مع أجهزة الويندوز لغرفة تجارة كربلاء المقدسة
          </p>
        </div>

        {/* أزرار العمليات السريعة */}
        <div className="flex items-center gap-1.5 sm:gap-2 flex-wrap">
          {/* زر تصوير كتاب رسمي بالكاميرا (مخصص للهواتف) */}
          <button
            onClick={() => cameraInputRef.current?.click()}
            disabled={actionLoading}
            className="flex items-center gap-1.5 bg-[#c59b27] hover:bg-[#b0871d] text-[#0e2720] text-xs font-black px-3 py-2 rounded-xl transition shadow-sm active:scale-95 shrink-0"
            title="تصوير كتاب رسمي بالكاميرا"
          >
            <Camera className="w-4 h-4" />
            <span>تصوير كتاب</span>
          </button>
          <input 
            type="file" 
            ref={cameraInputRef} 
            accept="image/*" 
            capture="environment" 
            className="hidden" 
            onChange={(e) => handleFileUpload(e, true)} 
          />

          {/* زر رفع ملفات متعددة */}
          <button
            onClick={() => fileInputRef.current?.click()}
            disabled={actionLoading}
            className="flex items-center gap-1.5 bg-[#14372e] hover:bg-[#1b4b3e] text-white text-xs font-bold px-3 py-2 rounded-xl transition shadow-sm active:scale-95 shrink-0"
            title="رفع ملفات متعددة دفعة واحدة"
          >
            <Upload className="w-4 h-4" />
            <span>رفع ملفات</span>
          </button>
          <input 
            type="file" 
            ref={fileInputRef} 
            multiple
            className="hidden" 
            onChange={(e) => handleFileUpload(e, false)} 
          />

          {/* زر رفع مجلد كامل */}
          <button
            onClick={() => folderInputRef.current?.click()}
            disabled={actionLoading}
            className="flex items-center gap-1.5 bg-emerald-50 hover:bg-emerald-100 text-emerald-800 text-xs font-bold px-3 py-2 rounded-xl transition border border-emerald-200 active:scale-95 shrink-0"
            title="رفع مجلد كامل بمحتوياته"
          >
            <FolderOpen className="w-4 h-4 text-emerald-700" />
            <span>رفع مجلد</span>
          </button>
          <input 
            type="file" 
            ref={folderInputRef} 
            {...({ webkitdirectory: '', directory: '' } as any)}
            multiple
            className="hidden" 
            onChange={handleFolderUpload} 
          />

          {/* مدخل رفع تحديث المستند بنسخة معدلة */}
          <input 
            type="file" 
            ref={updateFileInputRef} 
            className="hidden" 
            onChange={handleUpdateFile} 
          />

          {/* زر إنشاء مجلد جديد */}
          <button
            onClick={() => setShowNewFolderModal(true)}
            className="flex items-center gap-1.5 bg-slate-100 hover:bg-slate-200 text-slate-700 text-xs font-bold px-3 py-2 rounded-xl transition active:scale-95 shrink-0"
            title="إنشاء مجلد إداري"
          >
            <FolderPlus className="w-4 h-4 text-amber-600" />
            <span className="hidden sm:inline">مجلد جديد</span>
          </button>

          {/* زر التحديث اللحظي */}
          <button
            onClick={loadData}
            disabled={loading}
            className="p-2 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-xl transition active:scale-95"
            title="تحديث البيانات"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
          </button>
        </div>
      </div>

      {/* 2. شريط التبويب: المستندات النشطة مقابل سلة المحذوفات */}
      <div className="flex items-center justify-between border-b border-slate-200 pb-1">
        <div className="flex items-center gap-2">
          <button
            onClick={() => setActiveTab('ACTIVE')}
            className={`flex items-center gap-2 px-4 py-2 text-xs font-bold rounded-xl transition ${
              activeTab === 'ACTIVE'
                ? 'bg-[#14372e] text-white shadow-sm'
                : 'text-slate-600 hover:bg-slate-200'
            }`}
          >
            <Folder className="w-4 h-4" />
            <span>المستندات النشطة ({activeFiles.length})</span>
          </button>

          <button
            onClick={() => setActiveTab('TRASH')}
            className={`flex items-center gap-2 px-4 py-2 text-xs font-bold rounded-xl transition ${
              activeTab === 'TRASH'
                ? 'bg-rose-700 text-white shadow-sm'
                : 'text-slate-600 hover:bg-slate-200'
            }`}
          >
            <Trash2 className="w-4 h-4" />
            <span>المحذوفات 🗑️ ({trashFiles.length})</span>
          </button>
        </div>

        {/* أزرار سلة المحذوفات الشاملة (استرجاع الكل / إفراغ) */}
        {activeTab === 'TRASH' && trashFiles.length > 0 && (
          <div className="flex items-center gap-2">
            <button
              onClick={handleRestoreAll}
              className="flex items-center gap-1 px-3 py-1.5 bg-emerald-700 hover:bg-emerald-800 text-white rounded-lg text-xs font-bold transition shadow-sm"
            >
              <RotateCcw className="w-3.5 h-3.5" />
              <span>استرجاع الكل</span>
            </button>
            <button
              onClick={handleEmptyTrash}
              className="flex items-center gap-1 px-3 py-1.5 bg-rose-100 hover:bg-rose-200 text-rose-800 rounded-lg text-xs font-bold transition"
            >
              <Trash2 className="w-3.5 h-3.5" />
              <span>إفراغ السلة</span>
            </button>
          </div>
        )}
      </div>

      {/* 3. شريط الأقسام الأفقية المخصصة للمس بالجوال (Horizontal Department Chips) */}
      <div className="flex items-center gap-2 overflow-x-auto pb-1.5 scrollbar-thin">
        <button
          onClick={() => {
            setSelectedDept('__ALL__');
            setCurrentFolder(null);
          }}
          className={`px-3.5 py-1.5 rounded-xl text-xs font-bold transition whitespace-nowrap shrink-0 border ${
            selectedDept === '__ALL__'
              ? 'bg-[#14372e] text-white border-[#14372e] shadow-sm'
              : 'bg-white text-slate-700 border-slate-200 hover:bg-slate-100'
          }`}
        >
          🗂️ كافة الأقسام ({activeFiles.length})
        </button>

        {departments.map((dept) => {
          const count = activeFiles.filter(f => f.department === dept || f.folder === dept || f.folder.startsWith(dept + '/')).length;
          return (
            <button
              key={dept}
              onClick={() => {
                setSelectedDept(dept);
                setCurrentFolder(null);
              }}
              className={`px-3 py-1.5 rounded-xl text-xs font-bold transition whitespace-nowrap shrink-0 border flex items-center gap-1.5 ${
                selectedDept === dept
                  ? 'bg-[#14372e] text-white border-[#14372e] shadow-sm'
                  : 'bg-white text-slate-700 border-slate-200 hover:bg-slate-100'
              }`}
            >
              <span>🏛️ {dept}</span>
              <span className={`text-[10px] px-1.5 py-0.2 rounded-full ${selectedDept === dept ? 'bg-white/20 text-white' : 'bg-slate-100 text-slate-600'}`}>
                {count}
              </span>
            </button>
          );
        })}
      </div>

      {/* 4. شريط البحث وفلاتر صيغ الملفات (Word, Excel, PDF, etc.) */}
      <div className="flex flex-col sm:flex-row items-center justify-between gap-2.5 bg-white p-2.5 rounded-2xl border border-slate-200">
        <div className="relative w-full sm:w-80">
          <Search className="w-4 h-4 text-slate-400 absolute right-3 top-2.5" />
          <input
            type="text"
            placeholder="بحث سريع في أسماء المستندات..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            className="w-full pl-3 pr-9 py-2 text-xs bg-slate-50 border border-slate-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-[#14372e]"
          />
        </div>

        {/* تصفية سريعة بالصيغة */}
        <div className="flex items-center gap-1 overflow-x-auto w-full sm:w-auto pb-1 sm:pb-0">
          {[
            { tag: 'ALL', label: 'الكل' },
            { tag: 'WORD', label: 'Word' },
            { tag: 'EXCEL', label: 'Excel' },
            { tag: 'ACCESS', label: 'Access' },
            { tag: 'PDF', label: 'PDF' },
            { tag: 'IMAGE', label: 'صور' },
          ].map(t => (
            <button
              key={t.tag}
              onClick={() => setFilterType(t.tag)}
              className={`px-2.5 py-1 rounded-lg text-[11px] font-bold transition whitespace-nowrap ${
                filterType === t.tag
                  ? 'bg-slate-800 text-white'
                  : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
              }`}
            >
              {t.label}
            </button>
          ))}
        </div>
      </div>

      {/* 4.5. شريط مسار المجلدات (Breadcrumb) والمجلدات الفرعية المتداخلة */}
      {activeTab === 'ACTIVE' && (currentFolder || visibleSubfolders.length > 0) && (
        <div className="bg-white rounded-2xl border border-slate-200 p-3.5 space-y-3 shadow-xs">
          {/* شريط المسار (Breadcrumb) */}
          <div className="flex items-center justify-between flex-wrap gap-2">
            <div className="flex items-center gap-1.5 flex-wrap text-xs font-bold">
              <button
                onClick={() => {
                  setSelectedDept('__ALL__');
                  setCurrentFolder(null);
                }}
                className="text-slate-600 hover:text-[#14372e] px-2 py-1 rounded-lg hover:bg-slate-100 transition"
              >
                🗂️ كافة الأقسام
              </button>
              {activeBrowsePath && activeBrowsePath.split('/').map((part, idx, arr) => {
                const targetPath = arr.slice(0, idx + 1).join('/');
                const isLast = idx === arr.length - 1;
                return (
                  <div key={targetPath} className="flex items-center gap-1.5">
                    <ChevronLeft className="w-3.5 h-3.5 text-slate-400" />
                    <button
                      onClick={() => {
                        setSelectedDept(arr[0]);
                        setCurrentFolder(idx === 0 ? null : targetPath);
                      }}
                      className={`px-2.5 py-1 rounded-lg transition ${
                        isLast
                          ? 'bg-[#14372e] text-white shadow-xs'
                          : 'text-slate-700 hover:bg-slate-100'
                      }`}
                    >
                      {idx === 0 ? `🏛️ ${part}` : `📁 ${part}`}
                    </button>
                  </div>
                );
              })}
            </div>

            {currentFolder && (
              <button
                onClick={() => {
                  const parts = currentFolder.split('/');
                  if (parts.length <= 2) {
                    setCurrentFolder(null);
                  } else {
                    setCurrentFolder(parts.slice(0, -1).join('/'));
                  }
                }}
                className="flex items-center gap-1.5 px-3 py-1.5 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-xl text-xs font-bold transition"
              >
                <ArrowRight className="w-3.5 h-3.5" />
                <span>رجوع للمجلد السابق</span>
              </button>
            )}
          </div>

          {/* شبكة المجلدات الفرعية */}
          {visibleSubfolders.length > 0 && (
            <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-2.5 pt-1">
              {visibleSubfolders.map((sub) => {
                const subFilesCount = activeFiles.filter(
                  f => f.folder === sub.path || f.folder.startsWith(sub.path + '/')
                ).length;
                const childFoldersCount = allFolders.filter(
                  cf => cf.parentPath === sub.path
                ).length;
                return (
                  <div
                    key={sub.id}
                    onClick={() => {
                      setSelectedDept(sub.department);
                      setCurrentFolder(sub.path);
                    }}
                    className="group cursor-pointer bg-amber-50/50 hover:bg-amber-50 border border-amber-200/80 hover:border-amber-400 rounded-xl p-3 flex items-center justify-between gap-2 transition shadow-2xs"
                  >
                    <div className="flex items-center gap-2.5 min-w-0">
                      <div className="p-2 bg-amber-100/80 text-amber-700 rounded-xl shrink-0">
                        <Folder className="w-5 h-5 fill-amber-400/40" />
                      </div>
                      <div className="min-w-0">
                        <h4 className="font-bold text-xs text-slate-800 truncate" title={sub.name}>
                          {sub.name}
                        </h4>
                        <p className="text-[10px] text-slate-500 mt-0.5">
                          {subFilesCount} مستند{childFoldersCount > 0 ? ` • ${childFoldersCount} مجلد فرعي` : ''}
                        </p>
                      </div>
                    </div>

                    <div className="flex items-center gap-1 shrink-0" onClick={(e) => e.stopPropagation()}>
                      <button
                        onClick={() => {
                          setItemToRename({ id: sub.id, name: sub.name, isFolder: true });
                          setNewRenameValue(sub.name);
                          setShowRenameModal(true);
                        }}
                        className="p-1.5 text-slate-500 hover:text-emerald-700 hover:bg-white rounded-lg transition"
                        title="تعديل اسم المجلد"
                      >
                        <Edit3 className="w-3.5 h-3.5" />
                      </button>
                      <button
                        onClick={() => handleMoveFolderToTrash(sub)}
                        className="p-1.5 text-slate-500 hover:text-rose-600 hover:bg-white rounded-lg transition"
                        title="نقل المجلد للمحذوفات"
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}

      {/* 5. عرض الملفات: بطاقات للموبايل وجدول للشاشات الكبيرة */}
      {displayedList.length === 0 ? (
        visibleSubfolders.length === 0 ? (
          <div className="bg-white rounded-2xl border border-slate-200 p-12 text-center flex flex-col items-center justify-center space-y-3">
            <div className="p-4 bg-slate-50 rounded-full text-slate-400">
              <Inbox className="w-10 h-10" />
            </div>
            <h4 className="text-sm font-bold text-slate-700">لا توجد مستندات تطابق هذا الاختيار</h4>
            <p className="text-xs text-slate-400 max-w-sm leading-relaxed">
              {activeTab === 'TRASH' 
                ? 'سلة المحذوفات فارغة حالياً.'
                : 'يمكنك إضافة ملف جديد أو تصوير كتاب رسمي بالكاميرا فوراً من الأزرار بالأعلى.'}
            </p>
          </div>
        ) : null
      ) : (
        <>
          {/* نمط بطاقات الجوال (Mobile Touch Cards) */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:hidden gap-3">
            {displayedList.map((file) => (
              <div 
                key={file.id} 
                className="bg-white rounded-2xl p-4 border border-slate-200/90 shadow-sm flex flex-col justify-between space-y-3 hover:border-[#14372e]/50 transition"
              >
                <div className="flex items-start gap-3">
                  <div className="p-2.5 bg-slate-50 rounded-xl shrink-0 border border-slate-100">
                    {getFileIcon(file.type)}
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-1.5 flex-wrap">
                      <h4 className="font-bold text-xs text-slate-800 break-words leading-tight">
                        {file.name}
                      </h4>
                      {getFileBadge(file.type)}
                    </div>
                    <p className="text-[11px] text-slate-500 mt-1 truncate">
                      📂 {file.folder}
                    </p>
                    <div className="flex items-center gap-3 text-[10px] text-slate-400 mt-1 font-mono">
                      <span>💾 {file.size}</span>
                      <span>📅 {file.lastModifiedAt}</span>
                    </div>
                  </div>
                </div>

                {/* أزرار العمليات على بطاقة الجوال */}
                <div className="flex items-center justify-between border-t border-slate-100 pt-2.5 gap-1.5 flex-wrap">
                  {/* زر الفتح بالبرنامج الأصلي */}
                  <button
                    onClick={() => handleOpenFile(file)}
                    className="flex-1 min-w-[110px] flex items-center justify-center gap-1.5 bg-[#14372e] text-white text-xs font-bold py-2 px-3 rounded-xl hover:bg-[#1a473b] transition active:scale-95 shadow-sm"
                    title="تشغيل في برنامج Office الأصلي على الهاتف"
                  >
                    {file.type === 'word' && <FileText className="w-3.5 h-3.5 text-blue-300" />}
                    {file.type === 'excel' && <FileSpreadsheet className="w-3.5 h-3.5 text-emerald-300" />}
                    {file.type === 'access' && <Database className="w-3.5 h-3.5 text-rose-300" />}
                    {!['word', 'excel', 'access'].includes(file.type) && <ExternalLink className="w-3.5 h-3.5 text-amber-300" />}
                    <span>
                      {file.type === 'word' ? 'فتح Word' :
                       file.type === 'excel' ? 'فتح Excel' :
                       file.type === 'access' ? 'فتح Access' : 'فتح المستند'}
                    </span>
                  </button>

                  {/* زر حفظ التعديلات المباشر من الهاتف ومشاركتها مع الجميع */}
                  {activeTab === 'ACTIVE' && ['word', 'excel', 'file', 'pdf'].includes(file.type) && (
                    <button
                      onClick={() => triggerUpdateFile(file)}
                      disabled={actionLoading}
                      className="flex items-center justify-center gap-1 bg-amber-500 hover:bg-amber-600 text-slate-950 text-xs font-black py-2 px-2.5 rounded-xl transition active:scale-95 shadow-sm shrink-0"
                      title="حفظ التعديلات التي أجريتها في الهاتف ومشاركتها فوراً مع النظام"
                    >
                      <UploadCloud className="w-3.5 h-3.5 text-slate-950" />
                      <span>حفظ التعديلات</span>
                    </button>
                  )}

                  {/* زر معاينة Office Online */}
                  {['word', 'excel'].includes(file.type) && (
                    <button
                      onClick={() => handleOpenOfficeOnline(file)}
                      className="p-2 text-blue-700 bg-blue-50 hover:bg-blue-100 rounded-xl transition"
                      title="معاينة في المتصفح عبر Office Online"
                    >
                      <Eye className="w-4 h-4" />
                    </button>
                  )}

                  {/* زر فتح عبر تطبيقات الهاتف (Word / Excel / WPS / Google Docs) */}
                  <button
                    onClick={() => handleOpenInMobileApp(file)}
                    className="p-2 text-emerald-800 bg-emerald-50 hover:bg-emerald-100 rounded-xl transition"
                    title="تشغيل في تطبيقات الهاتف أو مشاركة المستند"
                  >
                    <Smartphone className="w-4 h-4" />
                  </button>

                  {/* زر تنزيل نسخة */}
                  <button
                    onClick={() => handleDownloadFile(file)}
                    className="p-2 text-slate-600 bg-slate-100 hover:bg-slate-200 rounded-xl transition"
                    title="تنزيل نسخة للملف"
                  >
                    <Download className="w-4 h-4" />
                  </button>

                  {activeTab === 'ACTIVE' ? (
                    <>
                      <button
                        onClick={() => {
                          setItemToRename({ id: file.id, name: file.name });
                          setNewRenameValue(file.name);
                          setShowRenameModal(true);
                        }}
                        className="p-2 text-slate-600 bg-slate-100 hover:bg-slate-200 rounded-xl transition"
                        title="تعديل الاسم"
                      >
                        <Edit3 className="w-4 h-4 text-emerald-700" />
                      </button>

                      <button
                        onClick={() => handleMoveToTrash(file)}
                        className="p-2 text-rose-600 bg-rose-50 hover:bg-rose-100 rounded-xl transition"
                        title="نقل للمحذوفات"
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                    </>
                  ) : (
                    <>
                      <button
                        onClick={() => handleRestoreFile(file)}
                        className="p-2 text-emerald-700 bg-emerald-50 hover:bg-emerald-100 rounded-xl transition font-bold text-xs flex items-center gap-1"
                        title="استرجاع المستند"
                      >
                        <RotateCcw className="w-4 h-4" />
                        <span>استرجاع</span>
                      </button>

                      <button
                        onClick={() => handlePermanentDelete(file)}
                        className="p-2 text-rose-700 bg-rose-50 hover:bg-rose-100 rounded-xl transition"
                        title="حذف نهائي"
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                    </>
                  )}
                </div>
              </div>
            ))}
          </div>

          {/* نمط الجدول للشاشات الكبيرة (Desktop Table View) */}
          <div className="hidden lg:block bg-white rounded-2xl border border-slate-200 shadow-sm overflow-x-auto relative">
            <table className="w-full text-right text-sm min-w-[950px]">
              <thead className="bg-[#f8fafc] text-slate-600 text-xs font-bold border-b border-slate-200">
                <tr>
                  <th className="p-4 whitespace-nowrap min-w-[200px]">اسم المستند</th>
                  <th className="p-4 whitespace-nowrap">القسم / المجلد</th>
                  <th className="p-4 whitespace-nowrap">النوع</th>
                  <th className="p-4 whitespace-nowrap">الحجم</th>
                  <th className="p-4 whitespace-nowrap">تاريخ الاعتماد</th>
                  <th className="p-4 whitespace-nowrap">المصدر</th>
                  <th className="p-4 text-center sticky left-0 bg-[#f8fafc] z-20 shadow-[-4px_0_8px_-2px_rgba(0,0,0,0.06)] min-w-[270px] whitespace-nowrap">الإجراءات</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {displayedList.map((file) => (
                  <tr key={file.id} className="group hover:bg-slate-50/80 transition">
                    <td className="p-4 max-w-[260px] xl:max-w-[360px]">
                      <div className="flex items-center gap-2.5">
                        <span className="shrink-0">{getFileIcon(file.type)}</span>
                        <span 
                          className="font-bold text-slate-800 text-xs truncate block"
                          title={file.name}
                        >
                          {file.name}
                        </span>
                      </div>
                    </td>
                    <td className="p-4 text-xs text-slate-600 whitespace-nowrap">{file.folder}</td>
                    <td className="p-4 whitespace-nowrap">{getFileBadge(file.type)}</td>
                    <td className="p-4 text-xs font-mono text-slate-600 whitespace-nowrap">{file.size}</td>
                    <td className="p-4 text-xs text-slate-500 font-mono whitespace-nowrap">{file.lastModifiedAt}</td>
                    <td className="p-4 text-xs whitespace-nowrap">
                      <span className="bg-slate-100 text-slate-700 font-bold px-2 py-0.5 rounded text-[10px]">
                        {file.lastModifiedBy}
                      </span>
                    </td>
                    <td className="p-4 text-center sticky left-0 bg-white group-hover:bg-slate-50 transition z-10 shadow-[-4px_0_8px_-2px_rgba(0,0,0,0.06)] min-w-[270px] whitespace-nowrap">
                      <div className="inline-flex items-center gap-1.5 justify-center">
                        {/* زر الفتح بالبرنامج الأصلي (Word / Excel / Access) */}
                        <button
                          onClick={() => handleOpenFile(file)}
                          className="flex items-center gap-1.5 bg-[#14372e] hover:bg-[#1a473b] text-white text-xs font-bold py-1.5 px-3 rounded-lg transition active:scale-95 shadow-xs"
                          title="فتح في برنامج Office الأصلي على الحاسوب"
                        >
                          {file.type === 'word' && <FileText className="w-3.5 h-3.5 text-blue-300" />}
                          {file.type === 'excel' && <FileSpreadsheet className="w-3.5 h-3.5 text-emerald-300" />}
                          {file.type === 'access' && <Database className="w-3.5 h-3.5 text-rose-300" />}
                          {!['word', 'excel', 'access'].includes(file.type) && <ExternalLink className="w-3.5 h-3.5 text-amber-300" />}
                          <span>
                            {file.type === 'word' ? 'فتح Word' :
                             file.type === 'excel' ? 'فتح Excel' :
                             file.type === 'access' ? 'فتح Access' : 'فتح'}
                          </span>
                        </button>

                        {/* زر حفظ التعديلات بنسخة جديدة ومشاركتها مع الجميع */}
                        {activeTab === 'ACTIVE' && ['word', 'excel', 'file', 'pdf'].includes(file.type) && (
                          <button
                            onClick={() => triggerUpdateFile(file)}
                            className="flex items-center gap-1 bg-amber-500 hover:bg-amber-600 text-slate-950 text-xs font-bold py-1.5 px-2 rounded-lg transition active:scale-95 shadow-xs"
                            title="رفع نسخة معدلة وتحديث المستند في السحابة ومشاركته فوراً"
                          >
                            <UploadCloud className="w-3.5 h-3.5 text-slate-950" />
                            <span>حفظ التعديلات</span>
                          </button>
                        )}

                        {/* زر معاينة Office Online */}
                        {['word', 'excel'].includes(file.type) && (
                          <button
                            onClick={() => handleOpenOfficeOnline(file)}
                            className="p-1.5 text-slate-500 hover:text-blue-700 hover:bg-blue-50 rounded-lg transition"
                            title="معاينة في المتصفح عبر Office Online"
                          >
                            <Eye className="w-4 h-4" />
                          </button>
                        )}

                        {/* زر تنزيل نسخة من الملف */}
                        <button
                          onClick={() => handleDownloadFile(file)}
                          className="p-1.5 text-slate-500 hover:text-slate-800 hover:bg-slate-100 rounded-lg transition"
                          title="تنزيل نسخة للملف"
                        >
                          <Download className="w-4 h-4" />
                        </button>

                        {/* زر إظهار في مجلد الويندوز */}
                        <button
                          onClick={() => handleRevealInExplorer(file)}
                          className="p-1.5 text-slate-500 hover:text-amber-700 hover:bg-amber-50 rounded-lg transition"
                          title="إظهار المستند في مجلد الويندوز المحلي"
                        >
                          <FolderOpen className="w-4 h-4" />
                        </button>

                        {/* زر فتح عبر تطبيقات الهاتف أو مشاركة */}
                        <button
                          onClick={() => handleShareFile(file)}
                          className="p-1.5 text-slate-500 hover:text-emerald-700 hover:bg-emerald-50 rounded-lg transition"
                          title="فتح عبر تطبيقات الهاتف أو مشاركة المستند"
                        >
                          <Share2 className="w-4 h-4" />
                        </button>

                        {activeTab === 'ACTIVE' ? (
                          <>
                            <button
                              onClick={() => {
                                setItemToRename({ id: file.id, name: file.name });
                                setNewRenameValue(file.name);
                                setShowRenameModal(true);
                              }}
                              className="p-1.5 text-slate-600 hover:text-emerald-700 hover:bg-emerald-50 rounded-lg transition"
                              title="تعديل الاسم"
                            >
                              <Edit3 className="w-4 h-4" />
                            </button>

                            <button
                              onClick={() => handleMoveToTrash(file)}
                              className="p-1.5 text-slate-500 hover:text-rose-600 hover:bg-rose-50 rounded-lg transition"
                              title="نقل للمحذوفات"
                            >
                              <Trash2 className="w-4 h-4" />
                            </button>
                          </>
                        ) : (
                          <>
                            <button
                              onClick={() => handleRestoreFile(file)}
                              className="p-1.5 text-emerald-700 bg-emerald-50 hover:bg-emerald-100 rounded-lg transition font-bold text-xs"
                              title="استرجاع المستند"
                            >
                              <RotateCcw className="w-4 h-4 inline" />
                            </button>

                            <button
                              onClick={() => handlePermanentDelete(file)}
                              className="p-1.5 text-rose-600 hover:text-rose-800 hover:bg-rose-50 rounded-lg transition"
                              title="حذف نهائي"
                            >
                              <Trash2 className="w-4 h-4" />
                            </button>
                          </>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}

      {/* شريط تقدم الرفع التفاعلي (Upload Progress Dialog) */}
      {uploadProgress && uploadProgress.show && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-xs p-4 animate-in fade-in">
          <div className="bg-white rounded-3xl shadow-2xl border border-slate-100 max-w-md w-full p-6 text-center space-y-4">
            <div className="flex items-center justify-center w-16 h-16 mx-auto rounded-2xl bg-emerald-50 text-emerald-600 shadow-inner">
              {uploadProgress.completed ? (
                <CheckCircle2 className="w-9 h-9 text-emerald-600 animate-bounce" />
              ) : (
                <UploadCloud className="w-9 h-9 text-emerald-600 animate-pulse" />
              )}
            </div>

            <div className="space-y-1">
              <h3 className="text-base font-black text-slate-800">
                {uploadProgress.completed ? '✅ اكتمل الرفع بنجاح!' : 'جاري رفع المستندات إلى السحابة...'}
              </h3>
              <p className="text-xs text-slate-500 font-semibold truncate max-w-xs mx-auto" dir="ltr">
                {uploadProgress.currentFileName}
              </p>
            </div>

            {/* شريط التحميل المباشر */}
            <div className="space-y-1.5 pt-1">
              <div className="w-full bg-slate-100 rounded-full h-3.5 overflow-hidden p-0.5 border border-slate-200">
                <div 
                  className="bg-gradient-to-r from-emerald-500 to-teal-500 h-full rounded-full transition-all duration-300 ease-out shadow-sm"
                  style={{ width: `${uploadProgress.percentage}%` }}
                />
              </div>
              <div className="flex justify-between items-center text-[11px] font-bold text-slate-500 px-1">
                <span className="text-emerald-700 font-black">{uploadProgress.percentage}% مكتمل</span>
                <span>{uploadProgress.current} من {uploadProgress.total} ملفات</span>
              </div>
            </div>

            {uploadProgress.completed && (
              <p className="text-xs text-emerald-700 font-bold bg-emerald-50 py-2.5 px-3 rounded-xl border border-emerald-100 animate-in fade-in">
                تمت مزامنة جميع المستندات مع سحابة Google Drive بنجاح
              </p>
            )}
          </div>
        </div>
      )}

      {/* 6. نافذة إنشاء مجلد جديد (New Folder Modal) */}
      {showNewFolderModal && (
        <div className="fixed inset-0 bg-black/60 backdrop-blur-xs z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-3xl p-6 max-w-md w-full space-y-4 shadow-2xl border border-slate-200">
            <div className="flex items-center justify-between border-b pb-3">
              <h3 className="font-bold text-base text-[#14372e] flex items-center gap-2">
                <FolderPlus className="w-5 h-5 text-amber-600" />
                <span>إنشاء مجلد إداري جديد</span>
              </h3>
              <button onClick={() => setShowNewFolderModal(false)} className="text-slate-400 hover:text-slate-600">
                <X className="w-5 h-5" />
              </button>
            </div>

            <p className="text-xs text-slate-500">
              أدخل اسم المجلد لتنظيم الكتب الرسمية والمستندات في السحابة:
            </p>

            <input
              type="text"
              placeholder="مثال: الكتب الصادرة 2026..."
              value={newFolderName}
              onChange={(e) => setNewFolderName(e.target.value)}
              className="w-full px-4 py-2.5 text-xs bg-slate-50 border border-slate-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-[#14372e]"
              autoFocus
            />

            <div className="space-y-1.5">
              <span className="text-[11px] text-slate-400 font-semibold">اقتراحات سريعة لأقسام الغرفة:</span>
              <div className="flex items-center gap-1.5 flex-wrap">
                {['الكتب الصادرة', 'الكتب الواردة', 'أضابير الكفالات', 'التقارير المالية'].map(sug => (
                  <button
                    key={sug}
                    onClick={() => setNewFolderName(sug)}
                    className="text-[10px] bg-slate-100 hover:bg-slate-200 text-slate-700 font-bold px-2 py-1 rounded-lg"
                  >
                    {sug}
                  </button>
                ))}
              </div>
            </div>

            <div className="flex items-center justify-end gap-2 pt-2 border-t">
              <button
                onClick={() => setShowNewFolderModal(false)}
                className="px-4 py-2 text-xs font-bold text-slate-600 hover:bg-slate-100 rounded-xl transition"
              >
                إلغاء
              </button>
              <button
                onClick={handleCreateFolder}
                className="px-5 py-2 text-xs font-bold bg-[#14372e] text-white rounded-xl hover:bg-[#1a473b] transition shadow-sm"
              >
                إنشاء المجلد
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 7. نافذة تعديل الاسم (Rename Modal) */}
      {showRenameModal && itemToRename && (
        <div className="fixed inset-0 bg-black/60 backdrop-blur-xs z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-3xl p-6 max-w-md w-full space-y-4 shadow-2xl border border-slate-200">
            <div className="flex items-center justify-between border-b pb-3">
              <h3 className="font-bold text-base text-[#14372e] flex items-center gap-2">
                <Edit3 className="w-5 h-5 text-emerald-700" />
                <span>تعديل اسم المستند</span>
              </h3>
              <button onClick={() => setShowRenameModal(false)} className="text-slate-400 hover:text-slate-600">
                <X className="w-5 h-5" />
              </button>
            </div>

            <p className="text-xs text-slate-500">
              الاسم الحالي: <strong className="text-slate-800">{itemToRename.name}</strong>
            </p>

            <input
              type="text"
              value={newRenameValue}
              onChange={(e) => setNewRenameValue(e.target.value)}
              className="w-full px-4 py-2.5 text-xs bg-slate-50 border border-slate-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-[#14372e]"
              autoFocus
            />

            <p className="text-[10px] text-slate-400">
              ملاحظة: سيتم الحفاظ على صيغة المستند تلقائياً، وتحديث الاسم فوراً على السحابة وتطبيق الكمبيوتر.
            </p>

            <div className="flex items-center justify-end gap-2 pt-2 border-t">
              <button
                onClick={() => setShowRenameModal(false)}
                className="px-4 py-2 text-xs font-bold text-slate-600 hover:bg-slate-100 rounded-xl transition"
              >
                إلغاء
              </button>
              <button
                onClick={handleSaveRename}
                className="px-5 py-2 text-xs font-bold bg-[#14372e] text-white rounded-xl hover:bg-[#1a473b] transition shadow-sm"
              >
                حفظ التعديل
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 8. نافذة إرشاد وتشغيل وحفظ المستند في تطبيقات الهاتف الأصلية (Mobile Sheet) */}
      {selectedMobileFile && (
        <div className="fixed inset-0 bg-black/60 backdrop-blur-xs z-50 flex items-end sm:items-center justify-center p-0 sm:p-4 animate-in fade-in duration-200">
          <div className="bg-white rounded-t-3xl sm:rounded-3xl p-5 sm:p-6 max-w-lg w-full space-y-4 shadow-2xl border border-slate-200 animate-in slide-in-from-bottom duration-200 max-h-[92vh] overflow-y-auto">
            {/* الترويسة */}
            <div className="flex items-center justify-between border-b pb-3">
              <div className="flex items-center gap-2.5 min-w-0">
                {getFileIcon(selectedMobileFile.type)}
                <div className="min-w-0">
                  <h3 className="font-bold text-sm text-[#14372e] truncate">
                    {selectedMobileFile.name}
                  </h3>
                  <div className="flex items-center gap-2 text-[11px] text-slate-500 mt-0.5">
                    <span>📂 {selectedMobileFile.folder}</span>
                    <span>•</span>
                    <span className="font-bold text-emerald-700 bg-emerald-50 px-1.5 py-0.2 rounded border border-emerald-200">
                      الإصدار V{selectedMobileFile.version}
                    </span>
                  </div>
                </div>
              </div>
              <button 
                onClick={() => setSelectedMobileFile(null)} 
                className="text-slate-400 hover:text-slate-600 p-1.5 rounded-full hover:bg-slate-100"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* 1. الخطوة الأولى: تشغيل وتعديل المستند في تطبيقات الهاتف */}
            <div className="bg-slate-50 border border-slate-200 rounded-2xl p-3.5 space-y-2.5">
              <div className="flex items-center justify-between">
                <span className="text-xs font-bold text-slate-800 flex items-center gap-1.5">
                  <span className="w-5 h-5 rounded-full bg-[#14372e] text-white flex items-center justify-center text-[10px]">1</span>
                  <span>الخطوة الأولى: فتح وتعديل المستند</span>
                </span>
                <span className="text-[10px] text-slate-500">اختر التطبيق</span>
              </div>

              {/* زر التشغيل في تطبيق الهاتف المثبت (Primary) */}
              <button
                onClick={() => handleOpenInMobileApp(selectedMobileFile)}
                disabled={preparingMobileOpen}
                className="w-full flex items-center justify-center gap-2 p-3 bg-[#14372e] hover:bg-[#1a473b] text-white rounded-xl font-bold text-xs transition active:scale-98 shadow-sm"
              >
                <Smartphone className="w-4 h-4 text-emerald-300" />
                <span>
                  {preparingMobileOpen ? '⏳ جاري تحضير التطبيق...' : `📱 تشغيل وتعديل في تطبيق ${selectedMobileFile.type === 'word' ? 'Word' : 'Excel'} بهاتفك`}
                </span>
              </button>

              {/* أزرار مساعدة سريعة */}
              <div className="grid grid-cols-2 gap-2 pt-1">
                <button
                  onClick={() => handleLaunchOfficeProtocol(selectedMobileFile)}
                  className="flex items-center justify-center gap-1.5 p-2 bg-white hover:bg-slate-100 text-slate-700 rounded-xl font-bold text-[11px] border border-slate-200 transition"
                  title="استدعاء بروتوكول Microsoft 365"
                >
                  <Sparkles className="w-3.5 h-3.5 text-blue-600" />
                  <span>بروتوكول Office</span>
                </button>

                <button
                  onClick={() => {
                    const f = selectedMobileFile;
                    setSelectedMobileFile(null);
                    handleOpenOfficeOnline(f);
                  }}
                  className="flex items-center justify-center gap-1.5 p-2 bg-white hover:bg-slate-100 text-slate-700 rounded-xl font-bold text-[11px] border border-slate-200 transition"
                  title="معاينة في المتصفح عبر Office Online"
                >
                  <Eye className="w-3.5 h-3.5 text-blue-600" />
                  <span>معاينة بالمتصفح</span>
                </button>
              </div>

              <button
                onClick={() => handleDownloadFile(selectedMobileFile)}
                className="w-full flex items-center justify-center gap-1.5 py-1.5 text-slate-500 hover:text-slate-800 text-[11px] font-medium transition"
              >
                <Download className="w-3.5 h-3.5" />
                <span>تنزيل نسخة عادية إلى الهاتف</span>
              </button>
            </div>

            {/* 2. الخطوة الثانية: حفظ التعديلات ومشاركتها في النظام (Core Feature) */}
            <div className="bg-gradient-to-br from-amber-50 to-emerald-50 border border-amber-300 rounded-2xl p-4 space-y-3 shadow-xs">
              <div className="flex items-center gap-2">
                <span className="w-5 h-5 rounded-full bg-amber-600 text-white flex items-center justify-center text-[10px] font-bold">2</span>
                <span className="text-xs font-bold text-slate-900">الخطوة الثانية: حفظ ومشاركة التعديلات</span>
              </div>

              <p className="text-xs text-slate-600 leading-relaxed">
                بعد فتح المستند في برنامج <strong>{selectedMobileFile.type === 'word' ? 'Word' : 'Excel'}</strong> وإجراء التعديلات وحفظها بهاتفك، اضغط الزر أدناه لاختيار الملف المعدل. سيتم حفظ التعديلات في النظام فوراً ومشاركتها مع جميع أجهزة الغرفة والمستخدمين.
              </p>

              <button
                onClick={() => triggerUpdateFile(selectedMobileFile)}
                disabled={actionLoading}
                className="w-full flex items-center justify-center gap-2 py-3 px-4 bg-amber-500 hover:bg-amber-600 text-slate-950 rounded-xl font-black text-xs transition active:scale-98 shadow-md"
              >
                <UploadCloud className="w-4 h-4 text-slate-950" />
                <span>📤 اضغط هنا لاختيار الملف المعدل وحفظ التعديلات في النظام</span>
              </button>
            </div>

            <div className="pt-2 border-t">
              <button
                onClick={() => setSelectedMobileFile(null)}
                className="w-full py-2.5 text-xs font-bold text-slate-500 hover:text-slate-800 rounded-xl transition"
              >
                إغلاق النافذة
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 9. إشعار عائم بتشغيل برامج Microsoft Office الأصلية */}
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
