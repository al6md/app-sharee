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
  Smartphone
} from 'lucide-react';
import { supabase } from '@/lib/supabase';

interface FileItem {
  id: string;
  name: string;
  folder: string;
  type: 'word' | 'excel' | 'access' | 'pdf' | 'image' | 'file';
  size: string;
  rawSize: number;
  version: number;
  lastModifiedBy: string;
  lastModifiedAt: string;
  storagePath: string;
  isDeleted: boolean;
}

const DEFAULT_DEPARTMENTS = [
  'أمانة السر والإدارة العامة',
  'شعبة الكفالات والعقود القانونية',
  'شعبة التسجيل والشركات التجارية',
  'القسم المالي والحسابات',
  'قسم تكنولوجيا المعلومات والتحول الرقمي',
  'العلاقات العامة والإعلام',
  'المخازن والتجهيزات'
];

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
  const [folders, setFolders] = useState<string[]>([]);
  const [departments, setDepartments] = useState<string[]>(DEFAULT_DEPARTMENTS);
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState(false);

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

  // مراجع رفع الملفات والكاميرا
  const fileInputRef = useRef<HTMLInputElement>(null);
  const cameraInputRef = useRef<HTMLInputElement>(null);

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

      // 1. جلب المجلدات من جدول shared_folders
      const { data: dbFolders } = await supabase
        .from('shared_folders')
        .select('name')
        .order('name');

      const loadedFolders: string[] = [];
      if (dbFolders && dbFolders.length > 0) {
        dbFolders.forEach(f => {
          if (f.name && !loadedFolders.includes(f.name)) {
            loadedFolders.push(f.name);
          }
        });
      }
      setFolders(loadedFolders);

      // دمج الأقسام الافتراضية مع أي مجلدات جديدة
      const allDepts = Array.from(new Set([...DEFAULT_DEPARTMENTS, ...loadedFolders]));
      setDepartments(allDepts);

      // 2. جلب كافة الملفات من السحابة (النشطة والمحذوفة)
      const { data: dbFiles } = await supabase
        .from('files')
        .select('*')
        .order('updated_at', { ascending: false });

      if (dbFiles) {
        const mapped: FileItem[] = dbFiles.map(f => {
          const fileName = f.file_name || f.file_path || 'مستند';
          let folderName = 'كافة الملفات';
          if (f.file_path && f.file_path.includes('/')) {
            folderName = f.file_path.split('/')[0];
          }

          return {
            id: f.id || fileName,
            name: fileName,
            folder: folderName,
            type: getFileType(fileName),
            size: formatSize(f.file_size || 0),
            rawSize: f.file_size || 0,
            version: f.version || f.current_version || 1,
            lastModifiedBy: f.last_modified_by_name || 'تطبيق الويندوز',
            lastModifiedAt: f.updated_at ? new Date(f.updated_at).toLocaleDateString('ar-IQ', {
              month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit'
            }) : 'الآن',
            storagePath: f.storage_path || `shared/${fileName}`,
            isDeleted: Boolean(f.is_deleted)
          };
        });
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

    // الاشتراك في التغييرات اللحظية (Real-time)
    const channel = supabase
      .channel('mobile_files_realtime')
      .on('postgres_changes', { event: '*', schema: 'public', table: 'files' }, () => {
        loadData();
      })
      .on('postgres_changes', { event: '*', schema: 'public', table: 'shared_folders' }, () => {
        loadData();
      })
      .subscribe();

    return () => {
      supabase.removeChannel(channel);
    };
  }, []);

  // رفع ملف من الجوال أو من الكاميرا
  const handleFileUpload = async (event: React.ChangeEvent<HTMLInputElement>, isCameraCapture = false) => {
    const file = event.target.files?.[0];
    if (!file) return;

    try {
      setActionLoading(true);
      const timestamp = new Date().toISOString().replace(/[:.]/g, '-');
      let fileName = cleanFileNameString(file.name);

      if (isCameraCapture) {
        fileName = `كتاب_رسمي_مصور_${timestamp}.jpg`;
      }

      // تحديد مسار المجلد النشط وتوليد المسار الآمن للتخزين
      const targetDept = selectedDept !== '__ALL__' ? selectedDept : 'المجلد العام';
      const safeStoragePath = getSafeStorageKey(fileName);

      // 1. الرفع الفعلي إلى وعاء التخزين السحابي بالمسار الآمن
      const { error: uploadErr } = await supabase.storage
        .from('file-exchange-storage')
        .upload(safeStoragePath, file, { upsert: true });

      if (uploadErr) {
        throw new Error(`فشل رفع محتوى الملف إلى التخزين السحابي: ${uploadErr.message}`);
      }

      // 2. التسجيل في جدول files
      const { error: dbErr } = await supabase.from('files').upsert({
        file_name: fileName,
        file_path: `${targetDept}/${fileName}`,
        storage_path: safeStoragePath,
        file_size: file.size,
        last_modified_by_name: isCameraCapture ? 'كاميرا الجوال' : 'تطبيق الجوال',
        is_deleted: false,
        updated_at: new Date().toISOString()
      }, { onConflict: 'file_name' });

      if (dbErr) {
        throw new Error(`فشل حفظ بيانات الملف في قاعدة البيانات: ${dbErr.message}`);
      }

      await loadData();
      alert(`✅ تم رفع المستند "${fileName}" بنجاح إلى سحابة الغرفة وسيبدأ المزامنة فوراً.`);
    } catch (e: any) {
      alert(`تعذر رفع المستند: ${e.message || e}`);
    } finally {
      setActionLoading(false);
      if (event.target) event.target.value = '';
    }
  };

  // نقل الملف لسلة المحذوفات
  const handleMoveToTrash = async (file: FileItem) => {
    if (!confirm(`هل أنت متأكد من نقل المستند "${file.name}" إلى سلة المحذوفات؟`)) return;
    try {
      setActionLoading(true);
      await supabase
        .from('files')
        .update({ is_deleted: true, updated_at: new Date().toISOString() })
        .eq('id', file.id);

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
      await supabase
        .from('files')
        .update({ is_deleted: false, updated_at: new Date().toISOString() })
        .eq('id', file.id);

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
      const ids = trashItems.map(f => f.id);
      await supabase
        .from('files')
        .update({ is_deleted: false, updated_at: new Date().toISOString() })
        .in('id', ids);

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
    if (!confirm(`⚠️ تحذير: سيتم حذف المستند "${file.name}" نهائياً من السحابة ولا يمكن استرجاعه. هل تود المتابعة؟`)) return;
    try {
      setActionLoading(true);
      await supabase.from('files').delete().eq('id', file.id);
      await supabase.storage.from('file-exchange-storage').remove([file.storagePath, `shared/${file.name}`]);
      setFiles(prev => prev.filter(f => f.id !== file.id));
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
      const ids = trashItems.map(f => f.id);
      await supabase.from('files').delete().in('id', ids);
      await loadData();
      alert('🧹 تم إفراغ سلة المحذوفات بنجاح.');
    } catch (e: any) {
      alert(`تعذر إفراغ السلة: ${e.message || e}`);
    } finally {
      setActionLoading(false);
    }
  };

  // استخراج الرابط الموقع الآمن للمستند (Signed URL) لضمان إمكانية تنزيله وفتحه بنجاح
  const getFileDirectUrl = async (file: FileItem): Promise<string> => {
    try {
      const cleanPath = file.storagePath.startsWith('/') ? file.storagePath.slice(1) : file.storagePath;
      const { data, error } = await supabase.storage
        .from('file-exchange-storage')
        .createSignedUrl(cleanPath, 3600);
      if (data?.signedUrl) {
        return data.signedUrl;
      }
    } catch (e) {
      console.error('Signed URL generation failed:', e);
    }
    const baseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL || 'https://bjcillpivgcntzbwmpsm.supabase.co';
    return `${baseUrl}/storage/v1/object/public/file-exchange-storage/${encodeURIComponent(file.storagePath)}`;
  };

  // 1. فتح المستند مباشرة في برنامج Office الأصلي (سواء على الهاتف أو الحاسوب)
  const handleOpenFile = async (file: FileItem) => {
    const isOffice = ['word', 'excel', 'access'].includes(file.type);
    const officeName = file.type === 'word' ? 'Word' : file.type === 'excel' ? 'Excel' : file.type === 'access' ? 'Access' : 'البرنامج الأصلي';

    // فحص ما إذا كان المستخدم يتصفح من هاتف محمول (Android أو iOS)
    const isMobile = typeof navigator !== 'undefined' && /Android|iPhone|iPad|iPod/i.test(navigator.userAgent);

    if (isMobile) {
      if (['word', 'excel'].includes(file.type)) {
        // فتح قائمة خيارات الجوال فوراً لتمرير الملف محلياً وتفادي قفل خوادم مايكروسوفت
        setSelectedMobileFile(file);
        return;
      } else if (file.type === 'access') {
        alert('ملفات Microsoft Access (.accdb) مخصصة لحواسيب الويندوز فقط.');
        return;
      } else {
        // PDF أو صورة أو ملف عام: فتح مباشر في المتصفح أو تطبيق العرض الافتراضي
        const directUrl = await getFileDirectUrl(file);
        window.open(directUrl, '_blank');
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

  // فتح المستند في تطبيق الهاتف (Word / Excel) بتمريره محلياً لتجاوز خطأ خادم مايكروسوفت
  const handleLaunchMobileApp = async (file: FileItem) => {
    try {
      setPreparingMobileOpen(true);
      setToastMessage({
        text: `⏳ جاري تجهيز "${file.name}" لتطبيق الهاتف...`,
        type: 'info'
      });

      const directUrl = await getFileDirectUrl(file);
      const res = await fetch(directUrl);
      if (!res.ok) throw new Error('فشل جلب الملف من السحابة');
      const blob = await res.blob();

      let mimeType = 'application/octet-stream';
      if (file.type === 'word') {
        mimeType = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document';
      } else if (file.type === 'excel') {
        mimeType = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet';
      } else if (file.type === 'pdf') {
        mimeType = 'application/pdf';
      }

      const fileObj = new File([blob], file.name, {
        type: mimeType,
        lastModified: Date.now()
      });

      setSelectedMobileFile(null);

      // استخدام مشاركة النظام الرسمية (Web Share API) لتمرير الملف محلياً إلى تطبيق Word
      // هذا هو الحل المعتمد لتفادي خطأ "تم تخزين الملف على خادم لا يعتمده هذا الإصدار من Office"
      if (typeof navigator !== 'undefined' && navigator.canShare && navigator.canShare({ files: [fileObj] })) {
        await navigator.share({
          files: [fileObj],
          title: file.name
        });
        setToastMessage({
          text: `✅ اختر تطبيق ${file.type === 'word' ? 'Word' : 'Excel'} من القائمة لفتحه فوراً.`,
          type: 'success'
        });
        return;
      }

      // إذا كان المتصفح لا يدعم canShare، يتم حفظ وتنزيل الملف Blob محلياً
      const blobUrl = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = blobUrl;
      a.download = file.name;
      document.body.appendChild(a);
      a.click();
      setTimeout(() => {
        try { document.body.removeChild(a); } catch {}
        URL.revokeObjectURL(blobUrl);
      }, 3000);

      setToastMessage({
        text: `💾 تم تنزيل المستند، اضغط عليه في التنزيلات لفتحه في Word فوراً.`,
        type: 'success'
      });
    } catch (e: any) {
      if (e.name !== 'AbortError') {
        alert(`تعذر فتح المستند: ${e.message || e}`);
      }
    } finally {
      setPreparingMobileOpen(false);
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

  // 3. تنزيل نسخة عادية من الملف
  const handleDownloadFile = async (file: FileItem) => {
    try {
      const directUrl = await getFileDirectUrl(file);
      window.open(directUrl, '_blank');
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

  // إنشاء مجلد جديد
  const handleCreateFolder = async () => {
    const fName = newFolderName.trim();
    if (!fName) return;
    try {
      setActionLoading(true);
      await supabase.from('shared_folders').insert({ name: fName });
      setShowNewFolderModal(false);
      setNewFolderName('');
      await loadData();
      alert(`📁 تم إنشاء المجلد "${fName}" في السحابة بنجاح.`);
    } catch (e: any) {
      alert(`تعذر إنشاء المجلد: ${e.message || e}`);
    } finally {
      setActionLoading(false);
    }
  };

  // تعديل اسم المستند
  const handleSaveRename = async () => {
    if (!itemToRename || !newRenameValue.trim()) return;
    const oldName = itemToRename.name;
    let newName = newRenameValue.trim();

    // الحفاظ على الامتداد
    const oldExt = oldName.includes('.') ? '.' + oldName.split('.').pop() : '';
    if (oldExt && !newName.includes('.')) {
      newName += oldExt;
    }

    if (newName === oldName) {
      setShowRenameModal(false);
      return;
    }

    try {
      setActionLoading(true);
      await supabase
        .from('files')
        .update({ 
          file_name: newName,
          file_path: newName,
          updated_at: new Date().toISOString() 
        })
        .eq('id', itemToRename.id);

      setShowRenameModal(false);
      setItemToRename(null);
      await loadData();
      alert(`✏️ تم تعديل الاسم إلى "${newName}" بنجاح في السحابة.`);
    } catch (e: any) {
      alert(`تعذر تعديل الاسم: ${e.message || e}`);
    } finally {
      setActionLoading(false);
    }
  };

  // تصفية الملفات حسب التبويب (نشط / محذوف)، القسم، البحث، والنوع
  const activeFiles = files.filter(f => !f.isDeleted);
  const trashFiles = files.filter(f => f.isDeleted);

  const displayedList = (activeTab === 'ACTIVE' ? activeFiles : trashFiles).filter(f => {
    const matchDept = selectedDept === '__ALL__' || f.folder.includes(selectedDept) || f.name.includes(selectedDept);
    const matchSearch = f.name.toLowerCase().includes(searchTerm.toLowerCase());
    const matchType = filterType === 'ALL' || f.type.toUpperCase() === filterType;
    return matchDept && matchSearch && matchType;
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

          {/* زر رفع ملف من ذاكرة الجوال */}
          <button
            onClick={() => fileInputRef.current?.click()}
            disabled={actionLoading}
            className="flex items-center gap-1.5 bg-[#14372e] hover:bg-[#1b4b3e] text-white text-xs font-bold px-3 py-2 rounded-xl transition shadow-sm active:scale-95 shrink-0"
            title="رفع مستند من الهاتف"
          >
            <Upload className="w-4 h-4" />
            <span>رفع ملف</span>
          </button>
          <input 
            type="file" 
            ref={fileInputRef} 
            className="hidden" 
            onChange={(e) => handleFileUpload(e, false)} 
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
          onClick={() => setSelectedDept('__ALL__')}
          className={`px-3.5 py-1.5 rounded-xl text-xs font-bold transition whitespace-nowrap shrink-0 border ${
            selectedDept === '__ALL__'
              ? 'bg-[#14372e] text-white border-[#14372e] shadow-sm'
              : 'bg-white text-slate-700 border-slate-200 hover:bg-slate-100'
          }`}
        >
          🗂️ كافة الأقسام ({files.length})
        </button>

        {departments.map((dept) => {
          const count = files.filter(f => f.folder.includes(dept) || f.name.includes(dept)).length;
          return (
            <button
              key={dept}
              onClick={() => setSelectedDept(dept)}
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

      {/* 5. عرض الملفات: بطاقات للموبايل وجدول للشاشات الكبيرة */}
      {displayedList.length === 0 ? (
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
                    className="flex-1 min-w-[120px] flex items-center justify-center gap-1.5 bg-[#14372e] text-white text-xs font-bold py-2 px-3 rounded-xl hover:bg-[#1a473b] transition active:scale-95 shadow-sm"
                    title="فتح في برنامج Office الأصلي"
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
                    onClick={() => handleShareFile(file)}
                    className="p-2 text-emerald-800 bg-emerald-50 hover:bg-emerald-100 rounded-xl transition"
                    title="فتح عبر تطبيقات الهاتف أو مشاركة المستند"
                  >
                    <Share2 className="w-4 h-4" />
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
          <div className="hidden lg:block bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden">
            <table className="w-full text-right text-sm">
              <thead className="bg-[#f8fafc] text-slate-600 text-xs font-bold border-b border-slate-200">
                <tr>
                  <th className="p-4">اسم المستند</th>
                  <th className="p-4">القسم / المجلد</th>
                  <th className="p-4">النوع</th>
                  <th className="p-4">الحجم</th>
                  <th className="p-4">تاريخ الاعتماد</th>
                  <th className="p-4">المصدر</th>
                  <th className="p-4 text-center">الإجراءات</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {displayedList.map((file) => (
                  <tr key={file.id} className="hover:bg-slate-50/80 transition">
                    <td className="p-4">
                      <div className="flex items-center gap-3">
                        {getFileIcon(file.type)}
                        <span className="font-bold text-slate-800 text-xs">{file.name}</span>
                      </div>
                    </td>
                    <td className="p-4 text-xs text-slate-600">{file.folder}</td>
                    <td className="p-4">{getFileBadge(file.type)}</td>
                    <td className="p-4 text-xs font-mono text-slate-600">{file.size}</td>
                    <td className="p-4 text-xs text-slate-500 font-mono">{file.lastModifiedAt}</td>
                    <td className="p-4 text-xs">
                      <span className="bg-slate-100 text-slate-700 font-bold px-2 py-0.5 rounded text-[10px]">
                        {file.lastModifiedBy}
                      </span>
                    </td>
                    <td className="p-4 text-center">
                      <div className="inline-flex items-center gap-1.5">
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

      {/* 8. نافذة خيارات فتح المستند على الهاتف الذكي (Mobile Sheet) */}
      {selectedMobileFile && (
        <div className="fixed inset-0 bg-black/60 backdrop-blur-xs z-50 flex items-end sm:items-center justify-center p-0 sm:p-4">
          <div className="bg-white rounded-t-3xl sm:rounded-3xl p-6 max-w-md w-full space-y-4 shadow-2xl border border-slate-200 animate-in slide-in-from-bottom duration-200">
            <div className="flex items-center justify-between border-b pb-3">
              <div className="flex items-center gap-2.5 min-w-0">
                {getFileIcon(selectedMobileFile.type)}
                <div className="min-w-0">
                  <h3 className="font-bold text-sm text-[#14372e] truncate">
                    {selectedMobileFile.name}
                  </h3>
                  <p className="text-[11px] text-slate-500">
                    خيارات فتح المستند على الهاتف
                  </p>
                </div>
              </div>
              <button 
                onClick={() => setSelectedMobileFile(null)} 
                className="text-slate-400 hover:text-slate-600 p-1.5 rounded-full hover:bg-slate-100"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <p className="text-xs text-slate-600 leading-relaxed">
              اختر طريقة الفتح المناسبة لهاتفك:
            </p>

            <div className="space-y-2.5">
              {/* الخيار 1: الفتح في تطبيق Word أو Office عبر التمرير المحلي */}
              <button
                onClick={() => handleLaunchMobileApp(selectedMobileFile)}
                disabled={preparingMobileOpen}
                className="w-full flex items-start gap-3 p-3.5 bg-[#14372e] hover:bg-[#1a473b] text-white rounded-2xl transition active:scale-98 shadow-sm text-right"
              >
                <div className="p-2 bg-white/10 rounded-xl shrink-0 mt-0.5">
                  <Smartphone className="w-5 h-5 text-amber-300" />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center justify-between">
                    <span className="font-bold text-xs">
                      {preparingMobileOpen ? '⏳ جاري التجهيز...' : `فتح في تطبيق ${selectedMobileFile.type === 'word' ? 'Word' : 'Excel'} بالهاتف`}
                    </span>
                    <span className="text-[10px] bg-amber-400/20 text-amber-300 px-2 py-0.5 rounded-full font-bold">موصى به</span>
                  </div>
                  <p className="text-[11px] text-emerald-100/80 mt-1 leading-normal">
                    يتم تمرير الملف محلياً إلى تطبيق Word/Office لتجاوز قيد الخوادم وفتحه فوراً.
                  </p>
                </div>
              </button>

              {/* الخيار 2: المعاينة السريعة عبر المتصفح (Office Online) */}
              <button
                onClick={() => {
                  const f = selectedMobileFile;
                  setSelectedMobileFile(null);
                  handleOpenOfficeOnline(f);
                }}
                className="w-full flex items-start gap-3 p-3.5 bg-blue-50 hover:bg-blue-100 text-blue-900 rounded-2xl transition active:scale-98 border border-blue-200 text-right"
              >
                <div className="p-2 bg-blue-600 text-white rounded-xl shrink-0 mt-0.5">
                  <Eye className="w-5 h-5" />
                </div>
                <div className="flex-1 min-w-0">
                  <span className="font-bold text-xs block text-blue-950">
                    معاينة مباشرة في المتصفح (Office Online)
                  </span>
                  <p className="text-[11px] text-blue-700/80 mt-1 leading-normal">
                    قراءة المستند فوراً في المتصفح دون الحاجة لتثبيت أي تطبيقات إضافية.
                  </p>
                </div>
              </button>

              {/* الخيار 3: تنزيل نسخة للملف */}
              <button
                onClick={() => {
                  const f = selectedMobileFile;
                  setSelectedMobileFile(null);
                  handleDownloadFile(f);
                }}
                className="w-full flex items-start gap-3 p-3.5 bg-slate-50 hover:bg-slate-100 text-slate-800 rounded-2xl transition active:scale-98 border border-slate-200 text-right"
              >
                <div className="p-2 bg-slate-700 text-white rounded-xl shrink-0 mt-0.5">
                  <Download className="w-5 h-5" />
                </div>
                <div className="flex-1 min-w-0">
                  <span className="font-bold text-xs block text-slate-900">
                    حفظ وتنزيل في ذاكرة الهاتف
                  </span>
                  <p className="text-[11px] text-slate-500 mt-1 leading-normal">
                    تنزيل نسخة في مجلد التنزيلات والملفات في جهازك.
                  </p>
                </div>
              </button>
            </div>

            <div className="pt-2 border-t">
              <button
                onClick={() => setSelectedMobileFile(null)}
                className="w-full py-2.5 text-xs font-bold text-slate-500 hover:text-slate-800 rounded-xl transition"
              >
                إغلاق
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
