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
  Play,
  BarChart3,
  PieChart,
  Minimize2,
  Maximize2,
  Zap,
  Clock,
  Activity,
  Lock,
  Film,
  Music,
  Archive,
  Move
} from 'lucide-react';
// Google Drive Connected

interface FileItem {
  id: string;
  name: string;
  folder: string;
  department: string;
  subFolder: string;
  type: 'word' | 'excel' | 'access' | 'pdf' | 'image' | 'video' | 'audio' | 'archive' | 'file';
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

interface DepartmentPermConfig {
  departmentName: string;
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
  const [showStats, setShowStats] = useState(true);

  const [files, setFiles] = useState<FileItem[]>([]);
  const [folderMap, setFolderMap] = useState<Record<string, string>>({});
  const [allFolders, setAllFolders] = useState<CloudFolderItem[]>([]);
  const [folders, setFolders] = useState<string[]>([]);
  const [departments, setDepartments] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState(false);
  const [permissionsMap, setPermissionsMap] = useState<Record<string, DepartmentPermConfig>>({});
  const [unlockedDepts, setUnlockedDepts] = useState<string[]>([]);
  const [pinPromptDept, setPinPromptDept] = useState<string | null>(null);
  const [pinPromptTargetFolder, setPinPromptTargetFolder] = useState<string | null>(null);
  const [pinPromptInput, setPinPromptInput] = useState<string>('');
  const [pinPromptError, setPinPromptError] = useState<string>('');

  const resolveDeptName = (folderOrDept?: string | null): string => {
    if (!folderOrDept || folderOrDept === '__ALL__' || folderOrDept === 'كافة الملفات') return '';
    return folderOrDept.replace(/\\/g, '/').split('/')[0].trim();
  };

  const checkDeptPerm = (
    folderOrDept: string | null | undefined,
    key: keyof Omit<DepartmentPermConfig, 'departmentName' | 'pinCode'>
  ): boolean => {
    const dept = resolveDeptName(folderOrDept);
    if (!dept) return true;
    const perm = permissionsMap[dept];
    if (!perm) return true;
    return perm[key] !== false;
  };

  const isDeptPinProtected = (folderOrDept?: string | null): boolean => {
    const dept = resolveDeptName(folderOrDept);
    if (!dept) return false;
    const pin = permissionsMap[dept]?.pinCode;
    return Boolean(pin && String(pin).trim().length > 0);
  };

  const isDeptUnlocked = (folderOrDept?: string | null): boolean => {
    const dept = resolveDeptName(folderOrDept);
    if (!dept) return true;
    if (!isDeptPinProtected(dept)) return true;
    return unlockedDepts.includes(dept);
  };

  const handleSelectDepartment = (deptName: string, targetFolder: string | null = null) => {
    if (deptName === '__ALL__') {
      setSelectedDept('__ALL__');
      setCurrentFolder(null);
      return;
    }
    if (!canViewFolder(deptName)) {
      alert(`⛔ عذراً، تم قفل قسم "${deptName}" ومنع عرضه من قِبل الإدارة.`);
      return;
    }
    if (!isDeptUnlocked(deptName)) {
      setPinPromptDept(deptName);
      setPinPromptTargetFolder(targetFolder);
      setPinPromptInput('');
      setPinPromptError('');
      return;
    }
    setSelectedDept(deptName);
    setCurrentFolder(targetFolder);
  };

  const handleVerifyDeptPin = (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (!pinPromptDept) return;
    const expectedPin = String(permissionsMap[pinPromptDept]?.pinCode || '').trim();
    if (pinPromptInput.trim() === expectedPin) {
      setUnlockedDepts((prev) => (prev.includes(pinPromptDept) ? prev : [...prev, pinPromptDept]));
      setSelectedDept(pinPromptDept);
      setCurrentFolder(pinPromptTargetFolder);
      setPinPromptDept(null);
      setPinPromptTargetFolder(null);
      setPinPromptInput('');
      setPinPromptError('');
    } else {
      setPinPromptError('رمز الحماية (PIN) غير صحيح، يرجى المحاولة مرة أخرى.');
    }
  };

  const canViewFolder = (folderName?: string) => checkDeptPerm(folderName, 'canView');
  const canDownloadFolder = (folderName?: string) => checkDeptPerm(folderName, 'canDownload');
  const canUploadFolder = (folderName?: string) => checkDeptPerm(folderName, 'canUpload');
  const canCreateSubFolder = (folderName?: string) => checkDeptPerm(folderName, 'canCreateFolder');
  const canEditFolder = (folderName?: string) => checkDeptPerm(folderName, 'canEdit');
  const canRenameFolder = (folderName?: string) => checkDeptPerm(folderName, 'canRename');
  const canMoveFolder = (folderName?: string) => checkDeptPerm(folderName, 'canMove');
  const canDeleteFolder = (folderName?: string) => checkDeptPerm(folderName, 'canDelete');
  const canPermanentDeleteFolder = (folderName?: string) => checkDeptPerm(folderName, 'canPermanentDelete');

  // حالة التحديد المتعدد للملفات والمجلدات الفرعية
  const [selectedFileIds, setSelectedFileIds] = useState<string[]>([]);
  const [selectedFolderIds, setSelectedFolderIds] = useState<string[]>([]);

  // نافذة نقل الملفات والمجلدات (Single & Bulk Move Modal)
  const [showMoveModal, setShowMoveModal] = useState(false);
  const [itemsToMove, setItemsToMove] = useState<{
    fileIds: string[];
    folderIds: string[];
    label: string;
    sourceDept?: string;
  } | null>(null);
  const [moveTargetDept, setMoveTargetDept] = useState<string>('');
  const [moveTargetSubfolder, setMoveTargetSubfolder] = useState<string>('');
  const [moveCustomSubfolder, setMoveCustomSubfolder] = useState<string>('');

  // مؤشر تقدم تفريغ / استرجاع سلة المهملات والعمليات الجماعية
  const [trashProgress, setTrashProgress] = useState<{
    show: boolean;
    title: string;
    current: number;
    total: number;
    currentName: string;
    percentage: number;
  } | null>(null);

  // نافذة معاينة الصور والوسائط وملفات PDF المدمجة (Built-in Lightbox Preview)
  const [previewFile, setPreviewFile] = useState<FileItem | null>(null);

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
  const [isDraggingOver, setIsDraggingOver] = useState<boolean>(false);
  const dragCounterRef = useRef<number>(0);

  // حالة شريط ومؤشر تقدم الرفع والتنزيل السحابي الحقيقي واللحظي (النسبة % + الميغابايت MB + سرعة الإنترنت MB/s)
  interface PreciseUploadProgress {
    show: boolean;
    minimized: boolean;
    mode?: 'upload' | 'download';
    total: number;
    current: number;
    currentFileName: string;
    currentFileSize: number;
    currentFileUploaded: number;
    currentFilePercentage: number;
    totalBatchSize: number;
    totalBatchUploaded: number;
    percentage: number;
    speedFormatted: string;
    megabytesFormatted: string;
    batchMegabytesFormatted: string;
    timeRemainingFormatted: string;
    chunkText: string;
    completed: boolean;
    statusText?: string;
  }
  const [uploadProgress, setUploadProgress] = useState<PreciseUploadProgress | null>(null);
  const activeTransferXhrRef = useRef<XMLHttpRequest | null>(null);
  const transferAbortedRef = useRef<boolean>(false);

  // دوال حساب وتنسيق أحجام الملفات بالميغابايت (MB) والسرعة والوقت المتبقي بدقة عالية
  const formatBytes = (bytes: number, decimals = 2): string => {
    if (!bytes || bytes <= 0) return '0.00 MB';
    const k = 1024;
    const dm = decimals < 0 ? 0 : decimals;
    const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    const val = parseFloat((bytes / Math.pow(k, i)).toFixed(dm));
    return `${val} ${sizes[i]}`;
  };

  // تنسيق صريح بالميغابايت (MB) كما طلب المستخدم (مثال: 4.25 MB / 12.80 MB)
  const formatMegabytes = (bytes: number): string => {
    if (!bytes || bytes <= 0) return '0.00 MB';
    const mb = bytes / (1024 * 1024);
    if (mb >= 0.01) {
      return `${mb.toFixed(2)} MB`;
    }
    return `${mb.toFixed(3)} MB (${(bytes / 1024).toFixed(1)} KB)`;
  };

  const formatSpeed = (bytesPerSec: number): string => {
    if (!bytesPerSec || bytesPerSec <= 0) return 'جاري القياس...';
    const mbPerSec = bytesPerSec / (1024 * 1024);
    if (mbPerSec >= 0.1) {
      return `${mbPerSec.toFixed(2)} MB/s`;
    }
    return `${Math.max(1, Math.round(bytesPerSec / 1024))} KB/s`;
  };

  const formatETA = (seconds: number | null): string => {
    if (seconds === null || !isFinite(seconds) || seconds <= 0) return 'جاري الحساب...';
    if (seconds < 3) return 'أوشك على الانتهاء...';
    if (seconds < 60) return `متبقي ${Math.ceil(seconds)} ثانية`;
    const mins = Math.floor(seconds / 60);
    const secs = Math.round(seconds % 60);
    if (mins < 60) {
      return secs > 0 ? `متبقي ${mins} د و ${secs} ث` : `متبقي ${mins} دقيقة`;
    }
    const hours = Math.floor(mins / 60);
    const remMins = mins % 60;
    return `متبقي ${hours} س و ${remMins} د`;
  };

  // مولّد ومتابع مؤشر التقدم الحقيقي للرفع أو التنزيل بناءً على البايتات الفعلية المنقولة عبر الشبكة
  const createProgressUpdater = (
    totalFiles: number,
    totalBatchBytes: number,
    mode: 'upload' | 'download' = 'upload',
    initialStatusText?: string
  ) => {
    const fileBytesMap = new Map<number, number>();
    let firstByteTime: number | null = null;
    let smoothedSpeed = 0;
    const speedSamples: { t: number; b: number }[] = [];

    // عند بدء أي عملية نقل جديدة، نظهر النافذة بالحجم الطبيعي غير المصغر فوراً لتكون واضحة وجلية للمستخدم
    setUploadProgress({
      show: true,
      minimized: false,
      mode,
      total: totalFiles,
      current: 1,
      currentFileName: 'جاري التحضير وبدء النقل...',
      currentFileSize: 0,
      currentFileUploaded: 0,
      currentFilePercentage: 0,
      totalBatchSize: totalBatchBytes,
      totalBatchUploaded: 0,
      percentage: 0,
      speedFormatted: 'جاري البدء...',
      megabytesFormatted: `0.00 MB / ${formatMegabytes(totalBatchBytes)}`,
      batchMegabytesFormatted: `0.00 MB / ${formatMegabytes(totalBatchBytes)}`,
      timeRemainingFormatted: 'جاري الحساب...',
      chunkText: initialStatusText || (mode === 'download' ? 'تنزيل سحابي مباشر' : 'رفع سحابي مؤكد'),
      completed: false,
      statusText: initialStatusText,
    });

    return (
      fileIndex: number,
      fileName: string,
      currentFileSize: number,
      currentFileUploaded: number,
      chunkInfo?: { currentChunk: number; totalChunks: number; chunkSize: number },
      isFinished = false,
      hasError = false,
      statusOverride?: string
    ) => {
      const now = performance.now();
      const safeFileSize = Math.max(1, currentFileSize);
      const clampedCurrentUploaded = isFinished && !hasError
        ? safeFileSize
        : Math.min(safeFileSize, Math.max(0, currentFileUploaded));

      fileBytesMap.set(fileIndex, clampedCurrentUploaded);

      let totalUploadedSoFar = 0;
      fileBytesMap.forEach((bytes) => {
        totalUploadedSoFar += bytes;
      });
      totalUploadedSoFar = Math.min(
        Math.max(1, totalBatchBytes),
        Math.max(0, totalUploadedSoFar)
      );

      if (totalUploadedSoFar > 0 && firstByteTime === null) {
        firstByteTime = now;
      }

      speedSamples.push({ t: now, b: totalUploadedSoFar });
      // الاحتفاظ بآخر 3 ثوانٍ لحساب سرعة الإنترنت اللحظية الحقيقية
      while (speedSamples.length > 2 && now - speedSamples[0].t > 3000) {
        speedSamples.shift();
      }

      let measuredSpeed = 0;
      if (speedSamples.length >= 2) {
        const oldest = speedSamples[0];
        const dtSec = (now - oldest.t) / 1000;
        const db = totalUploadedSoFar - oldest.b;
        if (dtSec > 0.05 && db >= 0) {
          measuredSpeed = db / dtSec;
        }
      }
      if (measuredSpeed <= 0 && firstByteTime !== null) {
        const totalElapsedSec = Math.max(0.15, (now - firstByteTime) / 1000);
        measuredSpeed = totalUploadedSoFar / totalElapsedSec;
      }

      if (measuredSpeed > 0) {
        smoothedSpeed = smoothedSpeed === 0 ? measuredSpeed : smoothedSpeed * 0.65 + measuredSpeed * 0.35;
      }

      const remainingBytes = Math.max(0, totalBatchBytes - totalUploadedSoFar);
      const etaSeconds = smoothedSpeed > 256 ? remainingBytes / smoothedSpeed : null;

      const rawPct = totalBatchBytes > 0 ? (totalUploadedSoFar / totalBatchBytes) * 100 : 0;
      const percentage = isFinished && !hasError && fileIndex + 1 >= totalFiles
        ? 100
        : Math.min(99.9, Math.max(0, parseFloat(rawPct.toFixed(1))));

      const currentFilePercentage = safeFileSize > 0
        ? isFinished && !hasError
          ? 100
          : Math.min(99.9, Math.max(0, parseFloat(((clampedCurrentUploaded / safeFileSize) * 100).toFixed(1))))
        : 0;

      let chunkText = '';
      if (statusOverride) {
        chunkText = statusOverride;
      } else if (chunkInfo && chunkInfo.totalChunks > 1) {
        chunkText = `الجزء ${chunkInfo.currentChunk} من ${chunkInfo.totalChunks} (${formatMegabytes(chunkInfo.chunkSize)})`;
      } else {
        chunkText = mode === 'download' ? 'تنزيل سحابي مباشر' : 'رفع سحابي مؤكد';
      }

      setUploadProgress((prev) => ({
        show: true,
        minimized: prev ? prev.minimized : false,
        mode,
        total: totalFiles,
        current: fileIndex + 1,
        currentFileName: fileName,
        currentFileSize,
        currentFileUploaded: clampedCurrentUploaded,
        currentFilePercentage,
        totalBatchSize: totalBatchBytes,
        totalBatchUploaded: totalUploadedSoFar,
        percentage,
        speedFormatted: formatSpeed(smoothedSpeed),
        megabytesFormatted: `${formatMegabytes(clampedCurrentUploaded)} / ${formatMegabytes(currentFileSize)}`,
        batchMegabytesFormatted: `${formatMegabytes(totalUploadedSoFar)} / ${formatMegabytes(totalBatchBytes)}`,
        timeRemainingFormatted: formatETA(etaSeconds),
        chunkText,
        completed: isFinished && !hasError && fileIndex + 1 >= totalFiles,
        statusText: statusOverride || prev?.statusText,
      }));
    };
  };

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

  const getFileType = (
    name: string
  ): 'word' | 'excel' | 'access' | 'pdf' | 'image' | 'video' | 'audio' | 'archive' | 'file' => {
    const ext = name.split('.').pop()?.toLowerCase() || '';
    if (['docx', 'doc', 'rtf', 'odt'].includes(ext)) return 'word';
    if (['xlsx', 'xls', 'csv', 'ods'].includes(ext)) return 'excel';
    if (['accdb', 'mdb'].includes(ext)) return 'access';
    if (ext === 'pdf') return 'pdf';
    if (['jpg', 'jpeg', 'png', 'webp', 'gif', 'bmp', 'svg', 'ico', 'tiff'].includes(ext)) return 'image';
    if (['mp4', 'webm', 'mov', 'avi', 'mkv', 'wmv', 'flv'].includes(ext)) return 'video';
    if (['mp3', 'wav', 'ogg', 'm4a', 'aac', 'flac'].includes(ext)) return 'audio';
    if (['zip', 'rar', '7z', 'tar', 'gz', 'bz2'].includes(ext)) return 'archive';
    return 'file';
  };

  const loadData = async () => {
    try {
      setLoading(true);

      const res = await fetch('/api/drive/files');
      const data = await res.json();
      if (data.success) {
        if (data.permissions && typeof data.permissions === 'object') {
          setPermissionsMap(data.permissions);
        }
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

  // إشعار تطبيق سطح المكتب المحلي بالمزامنة الفورية بعد أي عملية رفع أو تعديل عبر الويب
  const notifyLocalDesktopSync = () => {
    try {
      fetch('http://127.0.0.1:18290/sync', { method: 'GET', mode: 'cors' }).catch(() => {});
    } catch {
      // تجاهل في حال كان المستخدم يتصفح من الهاتف أو جهاز آخر
    }
  };

  const isIgnoredUploadFile = (name: string): boolean => {
    if (!name) return true;
    const low = name.toLowerCase();
    if (low === 'desktop.ini' || low === 'thumbs.db' || low === '.ds_store') return true;
    if (name.startsWith('~$') || name.startsWith('.') || name.startsWith('~WRL')) return true;
    return ['.tmp', '.laccdb', '.ldb', '.crdownload', '.partial'].some((ext) => low.endsWith(ext));
  };

  // إلغاء عملية الرفع أو التنزيل الجارية
  const handleAbortActiveTransfer = () => {
    transferAbortedRef.current = true;
    if (activeTransferXhrRef.current) {
      try {
        activeTransferXhrRef.current.abort();
      } catch {}
      activeTransferXhrRef.current = null;
    }
    setUploadProgress(null);
    setToastMessage({
      text: '⏹️ تم إلغاء عملية النقل بناءً على طلبك.',
      type: 'info',
    });
  };

  // دالة مساعدة لإرسال FormData عبر XMLHttpRequest مع تتبع حقيقي ولحظي للبايتات المرفوعة
  const sendFormDataWithProgress = (
    url: string,
    formData: FormData,
    onLoadedBytes?: (loaded: number, total: number) => void
  ): Promise<any> => {
    return new Promise((resolve, reject) => {
      if (transferAbortedRef.current) {
        reject(new Error('تم إلغاء العملية'));
        return;
      }
      const xhr = new XMLHttpRequest();
      activeTransferXhrRef.current = xhr;
      xhr.open('POST', url, true);
      xhr.upload.onprogress = (evt) => {
        if (evt.lengthComputable && onLoadedBytes) {
          onLoadedBytes(evt.loaded, evt.total);
        }
      };
      xhr.onload = () => {
        activeTransferXhrRef.current = null;
        let parsed: any = null;
        try {
          parsed = JSON.parse(xhr.responseText || '{}');
        } catch {
          parsed = null;
        }
        if (xhr.status >= 200 && xhr.status < 300 && parsed && parsed.success !== false) {
          resolve(parsed);
        } else {
          reject(new Error(parsed?.error || `HTTP ${xhr.status}`));
        }
      };
      xhr.onabort = () => {
        activeTransferXhrRef.current = null;
        reject(new Error('تم إلغاء العملية'));
      };
      xhr.onerror = () => {
        activeTransferXhrRef.current = null;
        reject(new Error('انقطع الاتصال أثناء رفع البيانات'));
      };
      xhr.ontimeout = () => {
        activeTransferXhrRef.current = null;
        reject(new Error('انتهت مهلة الاتصال أثناء الرفع'));
      };
      xhr.send(formData);
    });
  };

  // دالة رفع ذكية ومحصنة تدعم كافة أحجام الملفات عبر التجزئة السحابية الحقيقية (Resumable Chunked Upload)
  // مع تتبع فعلي للبايتات والسرعة والميغابايت وعدم القفز الوهمي إلى 100% قبل تأكيد Google Drive
  const uploadFileRobustly = async (
    file: File,
    fileName: string,
    options: { folderId?: string; folderPath?: string },
    onByteProgress?: (
      uploadedBytes: number,
      totalBytes: number,
      chunkInfo?: { currentChunk: number; totalChunks: number; chunkSize: number }
    ) => void
  ) => {
    transferAbortedRef.current = false;
    const totalSize = Math.max(1, file.size);

    // اختيار حجم الجزء (مضاعفات 256KB = 262,144 بايت القياسية في Google Drive)
    // تم تحسين الأحجام لتسريع نقل الملفات الكبيرة والضخمة (عشرات ومئات الميغابايت) بأعلى أداء ممكن
    const KB256 = 256 * 1024;
    let CHUNK_SIZE = KB256 * 4; // 1 MB للملفات حتى 8 ميجابايت
    if (file.size > 128 * 1024 * 1024) {
      CHUNK_SIZE = KB256 * 32; // 8 MB للملفات الضخمة (> 128 MB) لتسريع النقل وتقليل طلبات HTTP
    } else if (file.size > 32 * 1024 * 1024) {
      CHUNK_SIZE = KB256 * 16; // 4 MB للملفات الكبيرة (32 MB إلى 128 MB)
    } else if (file.size > 8 * 1024 * 1024) {
      CHUNK_SIZE = KB256 * 8; // 2 MB للملفات المتوسطة (8 MB إلى 32 MB)
    }

    // تهيئة جلسة رفع مجزأة قابلة للاستئناف في Google Drive لجميع الملفات (> 0 بايت)
    if (file.size > 0) {
      const initRes = await fetch('/api/drive/files', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          action: 'INIT_UPLOAD',
          fileName,
          mimeType: file.type || 'application/octet-stream',
          fileSize: file.size,
          folderId: options.folderId || undefined,
          folderPath: options.folderPath || undefined,
        }),
      });
      const initData = await initRes.json();
      if (!initRes.ok || !initData.success || !initData.sessionUri) {
        throw new Error(initData.error || 'تعذر بدء جلسة الرفع السحابي إلى Google Drive');
      }

      const sessionUri: string = initData.sessionUri;
      let offset = 0;
      let uploadedFileResult: any = null;
      const totalChunks = Math.max(1, Math.ceil(file.size / CHUNK_SIZE));

      while (offset < file.size) {
        if (transferAbortedRef.current) {
          throw new Error('تم إلغاء العملية');
        }
        const currentChunkIndex = Math.min(totalChunks, Math.floor(offset / CHUNK_SIZE) + 1);
        const endExclusive = Math.min(offset + CHUNK_SIZE, file.size);
        const chunkByteLen = endExclusive - offset;
        const chunkBlob = file.slice(offset, endExclusive);
        const chunkInfo = {
          currentChunk: currentChunkIndex,
          totalChunks,
          chunkSize: chunkByteLen,
        };

        let chunkSent = false;
        let lastErr: any = null;

        for (let attempt = 0; attempt < 4; attempt++) {
          if (transferAbortedRef.current) {
            throw new Error('تم إلغاء العملية');
          }

          // إذا كانت محاولة إعادة إرسال بعد انقطاع مؤقت، نستفسر من Google Drive عن البايتات المستلمة فعلياً
          if (attempt > 0) {
            try {
              const statusCheckRes = await fetch('/api/drive/files', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                  action: 'CHECK_UPLOAD_STATUS',
                  sessionUri,
                  totalSize: file.size,
                }),
              });
              const statusData = await statusCheckRes.json();
              if (statusData.success) {
                if (statusData.done && statusData.file) {
                  uploadedFileResult = statusData.file;
                  offset = file.size;
                  chunkSent = true;
                  if (onByteProgress) {
                    onByteProgress(file.size, totalSize, chunkInfo);
                  }
                  break;
                } else if (typeof statusData.nextOffset === 'number' && statusData.nextOffset > offset) {
                  offset = statusData.nextOffset;
                  chunkSent = true;
                  if (onByteProgress) {
                    onByteProgress(offset, totalSize, chunkInfo);
                  }
                  break;
                }
              }
            } catch (chkErr) {
              console.warn('Could not query upload status, retrying chunk send:', chkErr);
            }
          }

          try {
            const chunkForm = new FormData();
            chunkForm.append('action', 'UPLOAD_CHUNK');
            chunkForm.append('sessionUri', sessionUri);
            chunkForm.append('chunk', chunkBlob, fileName);
            chunkForm.append('start', String(offset));
            chunkForm.append('end', String(endExclusive - 1));
            chunkForm.append('total', String(file.size));

            const chunkData = await sendFormDataWithProgress(
              '/api/drive/files',
              chunkForm,
              (loaded, total) => {
                if (onByteProgress) {
                  // أثناء إرسال الجزء للخادم نصل إلى 90% من حجم الجزء، وعند تأكيد استلام السحابة نصل لـ 100%
                  const ratio = total > 0 ? Math.min(1, loaded / total) : 0;
                  const effectiveInChunk = Math.round(chunkByteLen * ratio * 0.90);
                  onByteProgress(
                    Math.min(file.size, offset + effectiveInChunk),
                    totalSize,
                    chunkInfo
                  );
                }
              }
            );
            if (chunkData.done) {
              uploadedFileResult = chunkData.file;
            }
            chunkSent = true;
            break;
          } catch (err: any) {
            if (transferAbortedRef.current || err?.message === 'تم إلغاء العملية') {
              throw err;
            }
            lastErr = err;
            await new Promise((r) => setTimeout(r, 800 * (attempt + 1)));
          }
        }

        if (!chunkSent) {
          throw lastErr || new Error('تعذر رفع جزء من الملف إلى السحابة بعد عدة محاولات');
        }

        if (uploadedFileResult && offset >= file.size) {
          break;
        }

        offset = endExclusive;
        if (onByteProgress) {
          onByteProgress(offset, totalSize, chunkInfo);
        }
      }

      return uploadedFileResult;
    }

    // للملفات الفارغة (0 بايت)
    const formData = new FormData();
    formData.append('file', file, fileName);
    formData.append('fileName', fileName);
    if (options.folderId) formData.append('folderId', options.folderId);
    if (options.folderPath) formData.append('folderPath', options.folderPath);
    const data = await sendFormDataWithProgress('/api/drive/files', formData);
    if (onByteProgress) {
      onByteProgress(1, 1, { currentChunk: 1, totalChunks: 1, chunkSize: 0 });
    }
    return data.file;
  };

  // تحديث محتوى مستند موجود بنسخة معدلة من الهاتف أو الكمبيوتر ومشاركتها فوراً
  const handleUpdateFile = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const selectedFile = event.target.files?.[0];
    if (!selectedFile || !fileToUpdate) return;

    const targetFile = fileToUpdate;
    const progressUpdater = createProgressUpdater(1, selectedFile.size);
    progressUpdater(0, targetFile.name, selectedFile.size, 0);

    try {
      setActionLoading(true);
      setToastMessage({
        text: `⏳ جاري رفع النسخة المعدلة لـ "${targetFile.name}" وحفظها في Google Drive...`,
        type: 'info'
      });

      const targetPath = targetFile.folder && targetFile.folder !== 'القسم العام' ? targetFile.folder : '';
      const folderId = (targetPath && folderMap[targetPath]) || '';

      await uploadFileRobustly(
        selectedFile,
        targetFile.name,
        {
          folderId: folderId || undefined,
          folderPath: targetPath || undefined,
        },
        (uploadedBytes, totalBytes, chunkInfo) => {
          progressUpdater(0, targetFile.name, selectedFile.size, uploadedBytes, chunkInfo);
        }
      );

      progressUpdater(0, targetFile.name, selectedFile.size, selectedFile.size, undefined, true);

      notifyLocalDesktopSync();
      setSelectedMobileFile(null);
      setFileToUpdate(null);
      await loadData();

      setToastMessage({
        text: `🎉 تم حفظ التعديلات ومزامنتها فوراً مع كافة الأجهزة!`,
        type: 'success'
      });

      setTimeout(() => {
        setUploadProgress(null);
      }, 2200);

      alert(
        `✅ تم حفظ التعديلات بنجاح في Google Drive!\n\n` +
        `📄 المستند: ${targetFile.name}\n` +
        `👥 تمت مزامنة التعديلات فوراً مع تطبيق الحاسوب وكافة المستخدمين.`
      );
    } catch (err: any) {
      console.error('Error updating file:', err);
      progressUpdater(0, targetFile.name, selectedFile.size, 0, undefined, true, true);
      setTimeout(() => {
        setUploadProgress(null);
      }, 3000);
      alert(`تعذر حفظ التعديلات في النظام: ${err.message || err}`);
    } finally {
      setActionLoading(false);
      if (event.target) event.target.value = '';
    }
  };

  // دالة ذكية لمسح واستخراج الملفات والمجلدات المسحوبة (Drag & Drop) مع الحفاظ على الهيكلية الشجرية
  const scanFilesFromDataTransfer = async (
    items: DataTransferItemList
  ): Promise<{ file: File; relativePath: string }[]> => {
    const result: { file: File; relativePath: string }[] = [];

    const readEntriesAsync = (dirReader: any): Promise<any[]> => {
      return new Promise((resolve) => {
        dirReader.readEntries(
          (entries: any[]) => resolve(entries || []),
          () => resolve([])
        );
      });
    };

    const traverseEntry = async (entry: any, path = ''): Promise<void> => {
      if (!entry) return;
      if (entry.isFile) {
        await new Promise<void>((resolve) => {
          entry.file(
            (file: File) => {
              if (!isIgnoredUploadFile(file.name)) {
                result.push({
                  file,
                  relativePath: path ? `${path}/${file.name}` : file.name,
                });
              }
              resolve();
            },
            () => resolve()
          );
        });
      } else if (entry.isDirectory) {
        const dirReader = entry.createReader();
        let allBatchEntries: any[] = [];
        let batch: any[] = [];
        do {
          batch = await readEntriesAsync(dirReader);
          allBatchEntries = allBatchEntries.concat(batch);
        } while (batch.length > 0);

        const nextPath = path ? `${path}/${entry.name}` : entry.name;
        for (const child of allBatchEntries) {
          await traverseEntry(child, nextPath);
        }
      }
    };

    const promises: Promise<void>[] = [];
    for (let i = 0; i < items.length; i++) {
      const item = items[i];
      if (item.kind === 'file') {
        const entry = item.webkitGetAsEntry ? item.webkitGetAsEntry() : null;
        if (entry) {
          promises.push(traverseEntry(entry));
        } else {
          const file = item.getAsFile();
          if (file && !isIgnoredUploadFile(file.name)) {
            result.push({ file, relativePath: file.name });
          }
        }
      }
    }

    await Promise.all(promises);
    return result;
  };

  // معالج رفع موحد فائق القوة للملفات والمجلدات والسحب والإفلات مع مؤشر دقيق ولحظي
  const processUploadedFiles = async (
    items: { file: File; relativePath: string }[],
    isCameraCapture = false
  ) => {
    if (!items || items.length === 0) return;

    const activeUploadPath = currentFolder || (selectedDept !== '__ALL__' ? selectedDept : '');
    if (activeUploadPath && !canUploadFolder(activeUploadPath)) {
      alert(`⛔ عذراً، صلاحية رفع الملفات والمجلدات معطلة لهذا القسم من قِبل الإدارة.`);
      return;
    }

    const rawFiles = items.filter((item) => {
      if (isCameraCapture) return true;
      const baseName = item.relativePath.split('/').pop() || item.file.name;
      return !isIgnoredUploadFile(baseName);
    });

    if (rawFiles.length === 0) return;

    const total = rawFiles.length;
    const totalBatchBytes = rawFiles.reduce((acc, it) => acc + it.file.size, 0);

    const initialStatus = total > 1
      ? 'جاري بدء رفع حزمة المستندات والمجلدات...'
      : 'جاري بدء الرفع السحابي للمستند...';

    const progressUpdater = createProgressUpdater(total, totalBatchBytes, 'upload', initialStatus);
    progressUpdater(0, rawFiles[0].file.name, rawFiles[0].file.size, 0);

    try {
      setActionLoading(true);
      const resolvedFolderIds: Record<string, string> = { ...folderMap };

      // استخراج كافة مسارات المجلدات الفرعية إن وجدت لإنشائها دفعة واحدة في السحابة
      const uniqueFolderPaths = new Set<string>();
      for (const item of rawFiles) {
        const parts = item.relativePath.replace(/\\/g, '/').split('/').filter(Boolean);
        parts.pop();
        const relSubFolder = parts.join('/');
        const fullCloudFolderPath = activeUploadPath
          ? (relSubFolder ? `${activeUploadPath}/${relSubFolder}` : activeUploadPath)
          : relSubFolder;
        if (fullCloudFolderPath && !resolvedFolderIds[fullCloudFolderPath]) {
          uniqueFolderPaths.add(fullCloudFolderPath);
        }
      }

      if (uniqueFolderPaths.size > 0) {
        progressUpdater(
          0,
          'جاري تهيئة وهيكلة المجلدات في Google Drive...',
          rawFiles[0].file.size,
          0,
          undefined,
          false,
          false,
          'جاري إنشاء المجلدات السحابية...'
        );
        try {
          const batchFolderRes = await fetch('/api/drive/files', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              action: 'ENSURE_FOLDER_PATHS_BATCH',
              folderPaths: Array.from(uniqueFolderPaths),
            }),
          });
          const batchFolderData = await batchFolderRes.json();
          if (batchFolderData.success && batchFolderData.folderMap) {
            Object.assign(resolvedFolderIds, batchFolderData.folderMap);
          }
        } catch (e) {
          console.warn('Batch folder path creation fallback:', e);
        }
      }

      let successCount = 0;
      const failedFiles: string[] = [];

      for (let i = 0; i < total; i++) {
        const item = rawFiles[i];
        const file = item.file;
        const parts = item.relativePath.replace(/\\/g, '/').split('/').filter(Boolean);
        const originalName = parts.pop() || file.name;
        let fileName = cleanFileNameString(originalName);

        if (isCameraCapture) {
          const timestamp = new Date().toISOString().replace(/[:.]/g, '-');
          fileName = `كتاب_رسمي_مصور_${timestamp}.jpg`;
        }

        const relSubFolder = parts.join('/');
        const fullCloudFolderPath = activeUploadPath
          ? (relSubFolder ? `${activeUploadPath}/${relSubFolder}` : activeUploadPath)
          : relSubFolder;

        const displayPath = fullCloudFolderPath ? `${fullCloudFolderPath} / ${fileName}` : fileName;
        progressUpdater(i, displayPath, file.size, 0);

        let targetFolderId = fullCloudFolderPath ? resolvedFolderIds[fullCloudFolderPath] : '';
        if (fullCloudFolderPath && !targetFolderId) {
          try {
            const ensureRes = await fetch('/api/drive/files', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({
                action: 'ENSURE_FOLDER_PATH',
                folderPath: fullCloudFolderPath,
              }),
            });
            const ensureData = await ensureRes.json();
            if (ensureData.success && ensureData.folderId) {
              targetFolderId = ensureData.folderId;
              resolvedFolderIds[fullCloudFolderPath] = targetFolderId;
            }
          } catch (folderErr) {
            console.error('Error ensuring folder path:', fullCloudFolderPath, folderErr);
          }
        }

        try {
          await uploadFileRobustly(
            file,
            fileName,
            {
              folderId: targetFolderId || undefined,
              folderPath: fullCloudFolderPath || undefined,
            },
            (uploadedB, totalB, chunkInfo) => {
              progressUpdater(i, displayPath, file.size, uploadedB, chunkInfo);
            }
          );
          successCount++;
          progressUpdater(i, displayPath, file.size, file.size, undefined, true);
        } catch (err: any) {
          console.error('Error uploading file:', fileName, err);
          failedFiles.push(`${fileName} (${err?.message || 'خطأ'})`);
          progressUpdater(i, displayPath, file.size, 0, undefined, true, true);
        }
      }

      notifyLocalDesktopSync();
      await loadData();

      if (failedFiles.length > 0) {
        setTimeout(() => {
          setUploadProgress(null);
        }, 3500);
        setToastMessage({
          text: `❌ تعذر رفع (${failedFiles.length}) مستند إلى السحابة`,
          type: 'error',
        });
        alert(
          `⚠️ تم رفع ${successCount} من أصل ${total} مستند إلى السحابة.\n` +
          `تعذر رفع:\n- ${failedFiles.slice(0, 5).join('\n- ')}`
        );
      } else if (successCount > 0) {
        setTimeout(() => {
          setUploadProgress(null);
        }, 2200);
        setToastMessage({
          text: total > 1
            ? `✅ تم رفع الدفعة بالكامل (${successCount} مستند) وحفظها في السحابة ومزامنتها بنجاح!`
            : `✅ تم رفع وحفظ المستند (${rawFiles[0].file.name}) بنجاح ومزامنته سحابياً!`,
          type: 'success',
        });
      } else {
        setUploadProgress(null);
      }
    } finally {
      setActionLoading(false);
    }
  };

  // رفع ملفات متعددة مع شريط تقدم مباشر ومزامنة سحابية مؤكدة
  const handleFileUpload = async (event: React.ChangeEvent<HTMLInputElement>, isCameraCapture = false) => {
    const fileList = event.target.files;
    if (!fileList || fileList.length === 0) return;
    try {
      const items = Array.from(fileList).map((f) => ({
        file: f,
        relativePath: f.name,
      }));
      await processUploadedFiles(items, isCameraCapture);
    } finally {
      if (event.target) event.target.value = '';
    }
  };

  // رفع مجلد كامل مع الحفاظ على هيكلية المجلدات الفرعية ومزامنتها بالكامل في Google Drive
  const handleFolderUpload = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const fileList = event.target.files;
    if (!fileList || fileList.length === 0) return;
    try {
      const items = Array.from(fileList).map((f) => ({
        file: f,
        relativePath: (f as any).webkitRelativePath || f.name,
      }));
      await processUploadedFiles(items, false);
    } finally {
      if (event.target) event.target.value = '';
    }
  };

  // دوال التحديد المتعدد للملفات والمجلدات
  const toggleSelectFile = (id: string) => {
    setSelectedFileIds((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));
  };

  const toggleSelectFolder = (id: string) => {
    setSelectedFolderIds((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));
  };

  const clearSelection = () => {
    setSelectedFileIds([]);
    setSelectedFolderIds([]);
  };

  // فتح نافذة نقل عنصر مفرد أو مجموعة عناصر محددة
  const openMoveDialog = (params: {
    fileIds?: string[];
    folderIds?: string[];
    label: string;
    sourceDept?: string;
  }) => {
    if (params.sourceDept && !canMoveFolder(params.sourceDept)) {
      alert(`⛔ عذراً، صلاحية نقل الملفات معطلة لقسم "${params.sourceDept}" من قِبل الإدارة.`);
      return;
    }
    const defaultDept =
      (selectedDept !== '__ALL__' ? selectedDept : departments[0]) || 'القسم العام';
    setItemsToMove({
      fileIds: params.fileIds || [],
      folderIds: params.folderIds || [],
      label: params.label,
      sourceDept: params.sourceDept,
    });
    setMoveTargetDept(defaultDept);
    setMoveTargetSubfolder('');
    setMoveCustomSubfolder('');
    setShowMoveModal(true);
  };

  // تنفيذ النقل السحابي للعناصر المحددة (ملفات ومجلدات)
  const handleExecuteMove = async () => {
    if (!itemsToMove || !moveTargetDept) return;
    if (!canMoveFolder(moveTargetDept) || !canUploadFolder(moveTargetDept)) {
      alert(`⛔ عذراً، لا تملك صلاحية النقل إلى قسم "${moveTargetDept}".`);
      return;
    }

    const allIds = [...itemsToMove.fileIds, ...itemsToMove.folderIds];
    if (allIds.length === 0) return;

    const cleanCustomSub = moveCustomSubfolder.trim().replace(/^\/+|\/+$/g, '');
    const targetFolderPath = cleanCustomSub
      ? `${moveTargetDept}/${cleanCustomSub}`
      : moveTargetSubfolder
      ? moveTargetSubfolder
      : moveTargetDept;
    const targetFolderId = folderMap[targetFolderPath] || '';

    try {
      setActionLoading(true);
      setShowMoveModal(false);
      setTrashProgress({
        show: true,
        title: `جاري نقل العناصر إلى "${targetFolderPath}"...`,
        current: 0,
        total: allIds.length,
        currentName: itemsToMove.label,
        percentage: 15,
      });

      const CHUNK_SIZE = 8;
      let movedSoFar = 0;
      for (let i = 0; i < allIds.length; i += CHUNK_SIZE) {
        const chunkIds = allIds.slice(i, i + CHUNK_SIZE);
        const res = await fetch('/api/drive/files', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            action: 'BATCH_MOVE',
            ids: chunkIds,
            targetFolderId: targetFolderId || undefined,
            targetFolderPath,
          }),
        });
        const data = await res.json();
        if (!data.success) throw new Error(data.error || 'فشل النقل السحابي');
        movedSoFar += chunkIds.length;
        setTrashProgress({
          show: true,
          title: `جاري نقل العناصر إلى "${targetFolderPath}"...`,
          current: movedSoFar,
          total: allIds.length,
          currentName: `تم نقل ${movedSoFar} من ${allIds.length}`,
          percentage: Math.round((movedSoFar / allIds.length) * 100),
        });
      }

      clearSelection();
      setItemsToMove(null);
      notifyLocalDesktopSync();
      await loadData();
      setTrashProgress(null);
      setToastMessage({
        text: `📂 تم نقل (${allIds.length}) عنصر إلى "${targetFolderPath}" في السحابة وكافة المنصات بنجاح!`,
        type: 'success',
      });
    } catch (e: any) {
      setTrashProgress(null);
      alert(`تعذر نقل العناصر: ${e.message || e}`);
    } finally {
      setActionLoading(false);
    }
  };

  // حذف العناصر المحددة (نقل للسلة أو حذف نهائي إذا كنا في تبويب السلة) مع شريط تقدم
  const handleBulkDeleteSelected = async () => {
    const allIds = [...selectedFileIds, ...selectedFolderIds];
    if (allIds.length === 0) return;

    const isPermanent = activeTab === 'TRASH';
    const currentScopePath = currentFolder || (selectedDept !== '__ALL__' ? selectedDept : '');
    if (isPermanent && !canPermanentDeleteFolder(currentScopePath)) {
      alert('⛔ عذراً، صلاحية الحذف النهائي مقيدة لهذا القسم من قِبل الإدارة.');
      return;
    }
    if (!isPermanent && !canDeleteFolder(currentScopePath)) {
      alert('⛔ عذراً، صلاحية حذف الملفات معطلة لهذا القسم من قِبل الإدارة.');
      return;
    }

    const msg = isPermanent
      ? `⚠️ تحذير: سيتم حذف (${allIds.length}) عنصر نهائياً من Google Drive وكافة المنصات ولا يمكن استرجاعها. هل تريد المتابعة؟`
      : `هل أنت متأكد من نقل (${allIds.length}) عنصر محدد إلى سلة المحذوفات في السحابة وكافة الأجهزة؟`;
    if (!confirm(msg)) return;

    try {
      setActionLoading(true);
      const CHUNK_SIZE = 6;
      let processed = 0;

      setTrashProgress({
        show: true,
        title: isPermanent ? 'جاري الحذف النهائي للعناصر المحددة...' : 'جاري نقل العناصر المحددة إلى السلة...',
        current: 0,
        total: allIds.length,
        currentName: 'بدء العملية السحابية...',
        percentage: 5,
      });

      for (let i = 0; i < allIds.length; i += CHUNK_SIZE) {
        const chunk = allIds.slice(i, i + CHUNK_SIZE);
        const res = await fetch('/api/drive/files', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            action: isPermanent ? 'BATCH_PERMANENT_DELETE' : 'BATCH_DELETE',
            ids: chunk,
          }),
        });
        const data = await res.json();
        if (!data.success) throw new Error(data.error || 'فشل الحذف الجماعي');
        processed += chunk.length;
        setTrashProgress({
          show: true,
          title: isPermanent ? 'جاري الحذف النهائي للعناصر المحددة...' : 'جاري نقل العناصر المحددة إلى السلة...',
          current: processed,
          total: allIds.length,
          currentName: `تمت معالجة ${processed} من ${allIds.length}`,
          percentage: Math.round((processed / allIds.length) * 100),
        });
      }

      clearSelection();
      notifyLocalDesktopSync();
      await loadData();
      setTrashProgress(null);
      setToastMessage({
        text: isPermanent
          ? `🗑️ تم الحذف النهائي لـ (${allIds.length}) عنصر من السحابة بنجاح.`
          : `🗑️ تم نقل (${allIds.length}) عنصر إلى سلة المهملات ومزامنة الحذف مع كافة الأجهزة.`,
        type: 'success',
      });
    } catch (e: any) {
      setTrashProgress(null);
      alert(`تعذر إتمام الحذف الجماعي: ${e.message || e}`);
    } finally {
      setActionLoading(false);
    }
  };

  // نقل الملف لسلة المحذوفات
  const handleMoveToTrash = async (file: FileItem) => {
    if (!canDeleteFolder(file.folder)) {
      alert(`⛔ عذراً، صلاحية الحذف معطلة لقسم "${file.department}" من قِبل الإدارة.`);
      return;
    }
    if (!confirm(`هل أنت متأكد من نقل المستند "${file.name}" إلى سلة المحذوفات في السحابة وكافة الأجهزة؟`)) return;
    try {
      setActionLoading(true);
      const res = await fetch(`/api/drive/files?id=${file.id}`, { method: 'DELETE' });
      const data = await res.json();
      if (!data.success) throw new Error(data.error);
      setSelectedFileIds((prev) => prev.filter((id) => id !== file.id));
      notifyLocalDesktopSync();
      await loadData();
      setToastMessage({
        text: `🗑️ تم حذف "${file.name}" من السحابة ومزامنة الحذف مع كافة المنصات.`,
        type: 'info',
      });
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
      setSelectedFileIds((prev) => prev.filter((id) => id !== file.id));
      notifyLocalDesktopSync();
      await loadData();
      setToastMessage({
        text: `♻️ تم استرجاع المستند "${file.name}" بنجاح.`,
        type: 'success',
      });
    } catch (e: any) {
      alert(`تعذر الاسترجاع: ${e.message || e}`);
    } finally {
      setActionLoading(false);
    }
  };

  // استرجاع كافة محذوفات القسم بسرعة عالية مع شريط تقدم حي
  const handleRestoreAll = async () => {
    const trashItems = files.filter(
      (f) => f.isDeleted && (selectedDept === '__ALL__' || f.department === selectedDept || f.folder === selectedDept)
    );
    if (trashItems.length === 0) return;
    if (!confirm(`هل أنت متأكد من استرجاع كافة المحذوفات (${trashItems.length} مستندات)؟`)) return;

    try {
      setActionLoading(true);
      const total = trashItems.length;
      const CHUNK_SIZE = 6;
      let restoredCount = 0;

      setTrashProgress({
        show: true,
        title: 'جاري استرجاع الملفات من سلة المهملات...',
        current: 0,
        total,
        currentName: trashItems[0].name,
        percentage: 5,
      });

      for (let i = 0; i < total; i += CHUNK_SIZE) {
        const chunk = trashItems.slice(i, i + CHUNK_SIZE);
        const res = await fetch('/api/drive/files', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            action: 'BATCH_RESTORE',
            ids: chunk.map((item) => item.id),
          }),
        });
        const data = await res.json();
        if (!data.success) throw new Error(data.error || 'فشل الاسترجاع');
        restoredCount += chunk.length;
        setTrashProgress({
          show: true,
          title: 'جاري استرجاع الملفات من سلة المهملات...',
          current: restoredCount,
          total,
          currentName: chunk[chunk.length - 1].name,
          percentage: Math.round((restoredCount / total) * 100),
        });
      }

      clearSelection();
      notifyLocalDesktopSync();
      await loadData();
      setTrashProgress(null);
      setToastMessage({
        text: `✅ تم استرجاع كافة المحذوفات (${total} مستند) بنجاح!`,
        type: 'success',
      });
    } catch (e: any) {
      setTrashProgress(null);
      alert(`تعذر استرجاع المحذوفات: ${e.message || e}`);
    } finally {
      setActionLoading(false);
    }
  };

  // حذف نهائي للمستند
  const handlePermanentDelete = async (file: FileItem) => {
    if (!canPermanentDeleteFolder(file.folder)) {
      alert(`⛔ عذراً، صلاحية الحذف النهائي مقيدة لقسم "${file.department}" من قِبل الإدارة.`);
      return;
    }
    if (!confirm(`⚠️ تحذير: سيتم حذف المستند "${file.name}" نهائياً من Google Drive ولا يمكن استرجاعه. هل تود المتابعة؟`)) return;
    try {
      setActionLoading(true);
      const res = await fetch(`/api/drive/files?id=${file.id}&permanent=true`, { method: 'DELETE' });
      const data = await res.json();
      if (!data.success) throw new Error(data.error);
      setSelectedFileIds((prev) => prev.filter((id) => id !== file.id));
      setFiles((prev) => prev.filter((f) => f.id !== file.id));
      notifyLocalDesktopSync();
      await loadData();
    } catch (e: any) {
      alert(`فشل الحذف النهائي: ${e.message || e}`);
    } finally {
      setActionLoading(false);
    }
  };

  // إفراغ سلة المحذوفات بسرعة عالية بالتوازي مع شريط تقدم حي لمنع توقف المنصة
  const handleEmptyTrash = async () => {
    const trashItems = files.filter(
      (f) => f.isDeleted && (selectedDept === '__ALL__' || f.department === selectedDept || f.folder === selectedDept)
    );
    if (trashItems.length === 0) return;
    if (selectedDept !== '__ALL__' && !canPermanentDeleteFolder(selectedDept)) {
      alert(`⛔ عذراً، صلاحية تفريغ السلة والحذف النهائي مقيدة لقسم "${selectedDept}".`);
      return;
    }
    if (!confirm(`⚠️ هل أنت متأكد من إفراغ سلة المحذوفات نهائياً (${trashItems.length} مستندات) من السحابة؟`)) return;

    try {
      setActionLoading(true);
      const total = trashItems.length;
      const CHUNK_SIZE = 6;
      let deletedCount = 0;

      setTrashProgress({
        show: true,
        title: 'جاري تفريغ سلة المهملات نهائياً من السحابة...',
        current: 0,
        total,
        currentName: trashItems[0].name,
        percentage: 4,
      });

      for (let i = 0; i < total; i += CHUNK_SIZE) {
        const chunk = trashItems.slice(i, i + CHUNK_SIZE);
        const currentLabel = chunk.map((c) => c.name).join(' ، ');
        setTrashProgress({
          show: true,
          title: 'جاري تفريغ سلة المهملات نهائياً من السحابة...',
          current: deletedCount,
          total,
          currentName: currentLabel,
          percentage: Math.max(5, Math.round((deletedCount / total) * 100)),
        });

        const res = await fetch('/api/drive/files', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            action: 'BATCH_PERMANENT_DELETE',
            ids: chunk.map((item) => item.id),
          }),
        });
        const data = await res.json();
        if (!data.success) throw new Error(data.error || 'فشل حذف الدفعة');

        deletedCount += chunk.length;
        const purgedSet = new Set(chunk.map((item) => item.id));
        setFiles((prev) => prev.filter((f) => !purgedSet.has(f.id)));

        setTrashProgress({
          show: true,
          title: 'جاري تفريغ سلة المهملات نهائياً من السحابة...',
          current: deletedCount,
          total,
          currentName: chunk[chunk.length - 1].name,
          percentage: Math.round((deletedCount / total) * 100),
        });
      }

      clearSelection();
      notifyLocalDesktopSync();
      await loadData();
      setTrashProgress(null);
      setToastMessage({
        text: `🧹 تم تفريغ سلة المهملات نهائياً (${total} مستند) بنجاح!`,
        type: 'success',
      });
    } catch (e: any) {
      setTrashProgress(null);
      alert(`تعذر إفراغ السلة: ${e.message || e}`);
    } finally {
      setActionLoading(false);
    }
  };

  // رابط تنزيل/بث مباشر عبر خادم البث السحابي المدمج
  const getFileDirectUrl = async (file: FileItem): Promise<string> => {
    return `/api/drive/stream?id=${encodeURIComponent(file.id)}`;
  };

  // 1. فتح المستند أو الصورة أو الوسائط مباشرة (معاينة فورية للصور وPDF والفيديو أو تشغيل Office)
  const handleOpenFile = async (file: FileItem) => {
    if (!canDownloadFolder(file.folder)) {
      alert(`⛔ عذراً، صلاحية فتح وتنزيل الملفات معطلة لقسم "${file.department}" من قِبل الإدارة.`);
      return;
    }

    // إذا كان الملف صورة أو PDF أو فيديو أو صوت: فتح عارض الوسائط المدمج فوراً (Lightbox Preview)
    if (['image', 'pdf', 'video', 'audio'].includes(file.type)) {
      setPreviewFile(file);
      return;
    }

    const officeName = file.type === 'word' ? 'Word' : file.type === 'excel' ? 'Excel' : file.type === 'access' ? 'Access' : 'البرنامج الأصلي';

    // فحص ما إذا كان المستخدم يتصفح من هاتف محمول (Android أو iOS)
    const isMobile = typeof navigator !== 'undefined' && /Android|iPhone|iPad|iPod/i.test(navigator.userAgent);

    if (isMobile) {
      if (['word', 'excel'].includes(file.type)) {
        setSelectedMobileFile(file);
        handleOpenInMobileApp(file);
        return;
      } else if (file.type === 'access') {
        alert('ملفات Microsoft Access (.accdb) مخصصة لحواسيب الويندوز فقط.');
        return;
      } else {
        const inlineUrl = `/api/drive/stream?id=${encodeURIComponent(file.id)}`;
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

  // 3. تنزيل نسخة عادية من الملف بالاسم العربي الصريح مع مؤشر تقدم حقيقي (النسبة % + سرعة الإنترنت + الميغابايت MB)
  const handleDownloadFile = async (file: FileItem) => {
    if (!canDownloadFolder(file.folder)) {
      alert(`⛔ عذراً، صلاحية تنزيل الملفات معطلة لقسم "${file.department}" من قِبل الإدارة.`);
      return;
    }

    transferAbortedRef.current = false;
    const downloadUrl = `/api/drive/stream?id=${encodeURIComponent(file.id)}&download=1`;
    const initialSize = Math.max(1, file.rawSize || 0);
    const progressUpdater = createProgressUpdater(1, initialSize, 'download');
    progressUpdater(0, file.name, initialSize, 0);

    try {
      await new Promise<void>((resolve, reject) => {
        const xhr = new XMLHttpRequest();
        activeTransferXhrRef.current = xhr;
        xhr.open('GET', downloadUrl, true);
        xhr.responseType = 'blob';

        xhr.onprogress = (evt) => {
          const headerSize = Number(xhr.getResponseHeader('X-File-Size') || xhr.getResponseHeader('Content-Length') || 0);
          const totalBytes = evt.lengthComputable && evt.total > 0 ? evt.total : headerSize || initialSize;
          progressUpdater(0, file.name, totalBytes, evt.loaded);
        };

        xhr.onload = () => {
          activeTransferXhrRef.current = null;
          if (xhr.status >= 200 && xhr.status < 300 && xhr.response) {
            const blob: Blob = xhr.response;
            const finalSize = Math.max(1, blob.size || initialSize);
            progressUpdater(0, file.name, finalSize, finalSize, undefined, true);

            const blobUrl = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = blobUrl;
            a.download = file.name;
            document.body.appendChild(a);
            a.click();
            a.remove();
            setTimeout(() => URL.revokeObjectURL(blobUrl), 15000);
            resolve();
          } else {
            reject(new Error(`HTTP ${xhr.status}`));
          }
        };

        xhr.onabort = () => {
          activeTransferXhrRef.current = null;
          reject(new Error('تم إلغاء العملية'));
        };

        xhr.onerror = () => {
          activeTransferXhrRef.current = null;
          reject(new Error('انقطع الاتصال أثناء تنزيل الملف'));
        };

        xhr.send();
      });

      setToastMessage({
        text: `✅ اكتمل تنزيل "${file.name}" (${formatMegabytes(file.rawSize)}) بنجاح!`,
        type: 'success',
      });
      setTimeout(() => {
        setUploadProgress(null);
      }, 2000);
    } catch (e: any) {
      if (e?.message === 'تم إلغاء العملية' || transferAbortedRef.current) {
        return;
      }
      setUploadProgress(null);
      // في حال فشل XHR لأي سبب في متصفح قديم، نفتح الرابط المباشر كاحتياط
      window.open(downloadUrl, '_blank');
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
    const targetParentPath = currentFolder || (selectedDept !== '__ALL__' ? selectedDept : '');
    if (targetParentPath && !canCreateSubFolder(targetParentPath)) {
      alert(`⛔ عذراً، صلاحية إنشاء المجلدات الفرعية معطلة لهذا القسم من قِبل الإدارة.`);
      return;
    }
    try {
      setActionLoading(true);
      const parentId = targetParentPath ? folderMap[targetParentPath] : undefined;
      const fullPath = targetParentPath ? `${targetParentPath}/${fName}` : fName;
      const res = await fetch('/api/drive/files', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'CREATE_FOLDER', name: fName, parentId, folderPath: fullPath }),
      });
      const data = await res.json();
      if (!data.success) throw new Error(data.error);

      notifyLocalDesktopSync();
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
    if (!canDeleteFolder(folder.path)) {
      alert(`⛔ عذراً، صلاحية حذف المجلدات معطلة لقسم "${folder.department}" من قِبل الإدارة.`);
      return;
    }
    if (!confirm(`هل أنت متأكد من نقل المجلد "${folder.name}" ومحتوياته إلى سلة المحذوفات في السحابة وكافة الأجهزة؟`)) return;
    try {
      setActionLoading(true);
      const res = await fetch(`/api/drive/files?id=${folder.id}&permanent=false`, {
        method: 'DELETE',
      });
      const data = await res.json();
      if (!data.success) throw new Error(data.error);
      setSelectedFolderIds((prev) => prev.filter((id) => id !== folder.id));
      if (currentFolder === folder.path || (currentFolder && currentFolder.startsWith(folder.path + '/'))) {
        setCurrentFolder(folder.parentPath || null);
      }
      notifyLocalDesktopSync();
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

      notifyLocalDesktopSync();
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

  // تصفية الملفات والمجلدات حسب التبويب (نشط / محذوف)، القسم، المجلد المفتوح، البحث، النوع، وصلاحية العرض والرمز السري
  const visibleDepartments = departments.filter((d) => canViewFolder(d));
  const activeFiles = files.filter(
    (f) => !f.isDeleted && canViewFolder(f.department) && isDeptUnlocked(f.department)
  );
  const trashFiles = files.filter(
    (f) => f.isDeleted && canViewFolder(f.department) && isDeptUnlocked(f.department)
  );

  const activeBrowsePath = currentFolder || (selectedDept !== '__ALL__' ? selectedDept : '');
  const visibleSubfolders =
    activeTab === 'ACTIVE' && !searchTerm.trim()
      ? allFolders.filter(
          (folder) =>
            folder.parentPath === activeBrowsePath &&
            canViewFolder(folder.department) &&
            isDeptUnlocked(folder.department)
        )
      : [];

  const displayedList = (activeTab === 'ACTIVE' ? activeFiles : trashFiles).filter((f) => {
    const matchSearch =
      !searchTerm.trim() ||
      f.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
      f.folder.toLowerCase().includes(searchTerm.toLowerCase());
    const matchType =
      filterType === 'ALL' ||
      f.type.toUpperCase() === filterType ||
      (filterType === 'OTHER' && ['file', 'video', 'audio', 'archive'].includes(f.type));

    if (searchTerm.trim()) {
      const matchDeptSearch =
        selectedDept === '__ALL__' ||
        f.department === selectedDept ||
        f.folder === selectedDept ||
        f.folder.startsWith(selectedDept + '/');
      return matchDeptSearch && matchSearch && matchType;
    }

    if (currentFolder) {
      return f.folder === currentFolder && matchType;
    }

    if (selectedDept !== '__ALL__') {
      if (visibleSubfolders.length > 0) {
        return f.folder === selectedDept && matchType;
      }
      return (
        (f.department === selectedDept || f.folder === selectedDept || f.folder.startsWith(selectedDept + '/')) &&
        matchType
      );
    }

    return matchSearch && matchType;
  });

  const isAllDisplayedSelected =
    (displayedList.length > 0 || visibleSubfolders.length > 0) &&
    displayedList.every((f) => selectedFileIds.includes(f.id)) &&
    visibleSubfolders.every((sf) => selectedFolderIds.includes(sf.id));

  const toggleSelectAllDisplayed = () => {
    if (isAllDisplayedSelected) {
      clearSelection();
    } else {
      setSelectedFileIds(displayedList.map((f) => f.id));
      setSelectedFolderIds(visibleSubfolders.map((sf) => sf.id));
    }
  };

  // إحصائيات المستندات والمساحة التخزينية الإجمالية ولكل نوع
  const scopeFiles =
    activeTab === 'TRASH'
      ? trashFiles
      : currentFolder
      ? activeFiles.filter((f) => f.folder === currentFolder || f.folder.startsWith(currentFolder + '/'))
      : selectedDept === '__ALL__'
      ? activeFiles
      : activeFiles.filter(
          (f) => f.department === selectedDept || f.folder === selectedDept || f.folder.startsWith(selectedDept + '/')
        );

  const stats = {
    totalCount: scopeFiles.length,
    totalRawSize: scopeFiles.reduce((acc, f) => acc + (f.rawSize || 0), 0),
    word: {
      count: scopeFiles.filter((f) => f.type === 'word').length,
      size: scopeFiles.filter((f) => f.type === 'word').reduce((acc, f) => acc + (f.rawSize || 0), 0),
    },
    excel: {
      count: scopeFiles.filter((f) => f.type === 'excel').length,
      size: scopeFiles.filter((f) => f.type === 'excel').reduce((acc, f) => acc + (f.rawSize || 0), 0),
    },
    access: {
      count: scopeFiles.filter((f) => f.type === 'access').length,
      size: scopeFiles.filter((f) => f.type === 'access').reduce((acc, f) => acc + (f.rawSize || 0), 0),
    },
    pdf: {
      count: scopeFiles.filter((f) => f.type === 'pdf').length,
      size: scopeFiles.filter((f) => f.type === 'pdf').reduce((acc, f) => acc + (f.rawSize || 0), 0),
    },
    image: {
      count: scopeFiles.filter((f) => f.type === 'image').length,
      size: scopeFiles.filter((f) => f.type === 'image').reduce((acc, f) => acc + (f.rawSize || 0), 0),
    },
    other: {
      count: scopeFiles.filter((f) => ['file', 'video', 'audio', 'archive'].includes(f.type)).length,
      size: scopeFiles
        .filter((f) => ['file', 'video', 'audio', 'archive'].includes(f.type))
        .reduce((acc, f) => acc + (f.rawSize || 0), 0),
    },
    foldersCount:
      selectedDept === '__ALL__'
        ? allFolders.length
        : allFolders.filter((f) => f.department === selectedDept || f.path.startsWith(selectedDept + '/')).length,
  };

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
        return <span className="bg-purple-50 text-purple-700 border border-purple-200 text-[10px] font-bold px-2 py-0.5 rounded">صورة</span>;
      case 'video':
        return <span className="bg-indigo-50 text-indigo-700 border border-indigo-200 text-[10px] font-bold px-2 py-0.5 rounded">فيديو</span>;
      case 'audio':
        return <span className="bg-pink-50 text-pink-700 border border-pink-200 text-[10px] font-bold px-2 py-0.5 rounded">صوت</span>;
      case 'archive':
        return <span className="bg-orange-50 text-orange-700 border border-orange-200 text-[10px] font-bold px-2 py-0.5 rounded">مضغوط</span>;
      default:
        return <span className="bg-slate-50 text-slate-700 border border-slate-200 text-[10px] font-bold px-2 py-0.5 rounded">ملف عام</span>;
    }
  };

  const getFileIcon = (type: string) => {
    switch (type) {
      case 'word': return <FileText className="w-5 h-5 text-sky-600" />;
      case 'excel': return <FileSpreadsheet className="w-5 h-5 text-emerald-600" />;
      case 'access': return <Database className="w-5 h-5 text-amber-700" />;
      case 'pdf': return <FileText className="w-5 h-5 text-rose-600" />;
      case 'image': return <Camera className="w-5 h-5 text-purple-600" />;
      case 'video': return <Film className="w-5 h-5 text-indigo-600" />;
      case 'audio': return <Music className="w-5 h-5 text-pink-600" />;
      case 'archive': return <Archive className="w-5 h-5 text-orange-600" />;
      default: return <FileCode className="w-5 h-5 text-slate-500" />;
    }
  };

  return (
    <div
      className="p-3 sm:p-6 md:p-8 space-y-4 max-w-7xl mx-auto w-full relative"
      onDragEnter={(e) => {
        e.preventDefault();
        e.stopPropagation();
        dragCounterRef.current++;
        if (e.dataTransfer && e.dataTransfer.types && Array.from(e.dataTransfer.types).includes('Files')) {
          setIsDraggingOver(true);
        }
      }}
      onDragOver={(e) => {
        e.preventDefault();
        e.stopPropagation();
      }}
      onDragLeave={(e) => {
        e.preventDefault();
        e.stopPropagation();
        dragCounterRef.current--;
        if (dragCounterRef.current <= 0) {
          dragCounterRef.current = 0;
          setIsDraggingOver(false);
        }
      }}
      onDrop={async (e) => {
        e.preventDefault();
        e.stopPropagation();
        dragCounterRef.current = 0;
        setIsDraggingOver(false);
        if (e.dataTransfer && e.dataTransfer.items && e.dataTransfer.items.length > 0) {
          try {
            const droppedItems = await scanFilesFromDataTransfer(e.dataTransfer.items);
            if (droppedItems.length > 0) {
              await processUploadedFiles(droppedItems);
            }
          } catch (err: any) {
            console.error('Error processing dropped files:', err);
          }
        } else if (e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files.length > 0) {
          const rawFiles = Array.from(e.dataTransfer.files).map((f) => ({
            file: f,
            relativePath: f.name,
          }));
          await processUploadedFiles(rawFiles);
        }
      }}
    >
      {/* شاشة السحب والإفلات التفاعلية الفورية (Drag and Drop Visual Overlay) */}
      {isDraggingOver && (
        <div className="fixed inset-0 z-50 bg-[#14372e]/85 backdrop-blur-sm flex flex-col items-center justify-center p-6 text-white border-4 border-dashed border-emerald-400 m-4 rounded-3xl animate-in fade-in duration-200 pointer-events-none" dir="rtl">
          <div className="bg-emerald-500/20 p-6 rounded-3xl mb-4 border border-emerald-400/30 animate-bounce">
            <UploadCloud className="w-16 h-16 text-amber-300" />
          </div>
          <h3 className="text-2xl font-black mb-2 text-white">
            أفلت الملفات أو المجلدات هنا للرفع السحابي الفوري
          </h3>
          <p className="text-emerald-100 text-sm max-w-lg text-center font-bold leading-relaxed">
            يدعم النظام سحب الملفات الفردية، المجموعات، والمجلدات الكاملة بهيكليتها مع مؤشر دقيق للسرعة والميغابايت ودعم كامل للملفات الكبيرة.
          </p>
        </div>
      )}
      {/* 1. الترويسة وأزرار الإجراءات السريعة (متجاوبة تماماً مع الجوال) */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 bg-white p-4 rounded-2xl border border-slate-200 shadow-sm">
        <div className="min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-xl sm:text-2xl font-black text-[#14372e] break-words whitespace-normal">
              {selectedDept === '__ALL__' ? 'كافة المستندات والمجلدات' : selectedDept}
            </span>
            <span className="text-xs bg-[#14372e]/10 text-[#14372e] font-bold px-2.5 py-0.5 rounded-full border border-[#14372e]/20 shrink-0">
              {displayedList.length} مستند
            </span>
          </div>
          <p className="text-xs text-slate-600 mt-1 font-medium">
            مزامنة سحابية مباشرة مع أجهزة الويندوز لغرفة تجارة كربلاء المقدسة
          </p>
        </div>

        {/* أزرار العمليات السريعة */}
        <div className="flex items-center gap-1.5 sm:gap-2 flex-wrap">
          {/* زر تصوير كتاب رسمي بالكاميرا (مخصص للهواتف) */}
          {canUploadFolder(activeBrowsePath) && (
            <>
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
            </>
          )}

          {/* مدخل رفع تحديث المستند بنسخة معدلة */}
          <input 
            type="file" 
            ref={updateFileInputRef} 
            className="hidden" 
            onChange={handleUpdateFile} 
          />

          {/* زر إنشاء مجلد جديد */}
          {canCreateSubFolder(activeBrowsePath) && (
            <button
              onClick={() => setShowNewFolderModal(true)}
              className="flex items-center gap-1.5 bg-slate-100 hover:bg-slate-200 text-slate-700 text-xs font-bold px-3 py-2 rounded-xl transition active:scale-95 shrink-0"
              title="إنشاء مجلد إداري"
            >
              <FolderPlus className="w-4 h-4 text-amber-600" />
              <span className="hidden sm:inline">مجلد جديد</span>
            </button>
          )}

          {/* زر تبديل عرض لوحة الإحصائيات الشاملة */}
          <button
            onClick={() => setShowStats(!showStats)}
            className={`flex items-center gap-1.5 px-3 py-2 rounded-xl text-xs font-bold transition active:scale-95 shrink-0 ${
              showStats 
                ? 'bg-amber-100/90 text-amber-950 border border-amber-300 shadow-2xs' 
                : 'bg-slate-100 hover:bg-slate-200 text-slate-700'
            }`}
            title="عرض إحصائيات المستندات والمساحة حسب النوع"
          >
            <BarChart3 className="w-4 h-4 text-amber-700" />
            <span className="hidden sm:inline">إحصائيات الملفات</span>
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

      {/* 1.5. لوحة إحصائيات الملفات والمساحة التخزينية ولكل نوع */}
      {showStats && (
        <div className="bg-white rounded-2xl border border-slate-200/90 p-4 shadow-xs space-y-3">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-slate-100 pb-2.5">
            <div className="flex items-center gap-2">
              <div className="p-2 bg-[#14372e]/10 text-[#14372e] rounded-xl shrink-0">
                <BarChart3 className="w-4 h-4 text-[#14372e]" />
              </div>
              <div>
                <h3 className="text-xs sm:text-sm font-black text-slate-800 flex items-center gap-1.5">
                  <span>إحصائيات المستندات والأنواع</span>
                  <span className="text-[11px] font-bold text-slate-500">
                    {selectedDept === '__ALL__' ? '• كافة الأقسام والمجلدات' : `• قسم ${selectedDept}`}
                  </span>
                </h3>
                <p className="text-[11px] text-slate-400">
                  اضغط على أي نوع لتصفية وعرض مستنداته فوراً
                </p>
              </div>
            </div>

            <div className="flex items-center gap-2 self-start sm:self-auto flex-wrap">
              <span className="bg-slate-50 text-slate-700 font-bold px-3 py-1 rounded-xl text-xs border border-slate-200 font-mono">
                💾 إجمالي الحجم: <strong className="text-[#14372e]">{formatSize(stats.totalRawSize)}</strong>
              </span>
              <span className="bg-[#14372e]/10 text-[#14372e] font-bold px-3 py-1 rounded-xl text-xs border border-[#14372e]/20 font-mono">
                🗂️ {stats.totalCount} مستنداً
              </span>
            </div>
          </div>

          {/* شبكة بطاقات الإحصائيات لكل نوع */}
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-2.5">
            {/* 1. الإجمالي العام */}
            <div 
              onClick={() => setFilterType('ALL')}
              className={`cursor-pointer p-3 rounded-xl border transition flex flex-col justify-between ${
                filterType === 'ALL'
                  ? 'bg-[#14372e] text-white border-[#14372e] shadow-sm'
                  : 'bg-slate-50 hover:bg-slate-100/80 text-slate-700 border-slate-200'
              }`}
            >
              <div className="flex items-center justify-between">
                <span className="text-xs font-bold">كافة الملفات</span>
                <span className="text-xs">📁</span>
              </div>
              <div className="mt-2.5">
                <div className="text-lg font-black font-mono leading-none">{stats.totalCount}</div>
                <div className={`text-[10px] mt-1 font-mono font-medium ${filterType === 'ALL' ? 'text-emerald-200' : 'text-slate-400'}`}>
                  {formatSize(stats.totalRawSize)}
                </div>
              </div>
            </div>

            {/* 2. مستندات Word */}
            <div 
              onClick={() => setFilterType(filterType === 'WORD' ? 'ALL' : 'WORD')}
              className={`cursor-pointer p-3 rounded-xl border transition flex flex-col justify-between ${
                filterType === 'WORD'
                  ? 'bg-sky-700 text-white border-sky-700 shadow-sm'
                  : 'bg-sky-50/60 hover:bg-sky-50 text-sky-950 border-sky-200'
              }`}
            >
              <div className="flex items-center justify-between">
                <span className="text-xs font-bold">Word</span>
                <FileText className={`w-4 h-4 ${filterType === 'WORD' ? 'text-white' : 'text-sky-600'}`} />
              </div>
              <div className="mt-2.5">
                <div className="text-lg font-black font-mono leading-none">{stats.word.count}</div>
                <div className={`text-[10px] mt-1 font-mono font-medium ${filterType === 'WORD' ? 'text-sky-200' : 'text-sky-700'}`}>
                  {formatSize(stats.word.size)}
                </div>
              </div>
            </div>

            {/* 3. جداول Excel */}
            <div 
              onClick={() => setFilterType(filterType === 'EXCEL' ? 'ALL' : 'EXCEL')}
              className={`cursor-pointer p-3 rounded-xl border transition flex flex-col justify-between ${
                filterType === 'EXCEL'
                  ? 'bg-emerald-700 text-white border-emerald-700 shadow-sm'
                  : 'bg-emerald-50/60 hover:bg-emerald-50 text-emerald-950 border-emerald-200'
              }`}
            >
              <div className="flex items-center justify-between">
                <span className="text-xs font-bold">Excel</span>
                <FileSpreadsheet className={`w-4 h-4 ${filterType === 'EXCEL' ? 'text-white' : 'text-emerald-600'}`} />
              </div>
              <div className="mt-2.5">
                <div className="text-lg font-black font-mono leading-none">{stats.excel.count}</div>
                <div className={`text-[10px] mt-1 font-mono font-medium ${filterType === 'EXCEL' ? 'text-emerald-200' : 'text-emerald-700'}`}>
                  {formatSize(stats.excel.size)}
                </div>
              </div>
            </div>

            {/* 4. قواعد Access */}
            <div 
              onClick={() => setFilterType(filterType === 'ACCESS' ? 'ALL' : 'ACCESS')}
              className={`cursor-pointer p-3 rounded-xl border transition flex flex-col justify-between ${
                filterType === 'ACCESS'
                  ? 'bg-amber-800 text-white border-amber-800 shadow-sm'
                  : 'bg-amber-50/60 hover:bg-amber-50 text-amber-950 border-amber-200'
              }`}
            >
              <div className="flex items-center justify-between">
                <span className="text-xs font-bold">Access</span>
                <Database className={`w-4 h-4 ${filterType === 'ACCESS' ? 'text-white' : 'text-amber-700'}`} />
              </div>
              <div className="mt-2.5">
                <div className="text-lg font-black font-mono leading-none">{stats.access.count}</div>
                <div className={`text-[10px] mt-1 font-mono font-medium ${filterType === 'ACCESS' ? 'text-amber-200' : 'text-amber-800'}`}>
                  {formatSize(stats.access.size)}
                </div>
              </div>
            </div>

            {/* 5. وثائق PDF */}
            <div 
              onClick={() => setFilterType(filterType === 'PDF' ? 'ALL' : 'PDF')}
              className={`cursor-pointer p-3 rounded-xl border transition flex flex-col justify-between ${
                filterType === 'PDF'
                  ? 'bg-rose-700 text-white border-rose-700 shadow-sm'
                  : 'bg-rose-50/60 hover:bg-rose-50 text-rose-950 border-rose-200'
              }`}
            >
              <div className="flex items-center justify-between">
                <span className="text-xs font-bold">PDF</span>
                <FileText className={`w-4 h-4 ${filterType === 'PDF' ? 'text-white' : 'text-rose-600'}`} />
              </div>
              <div className="mt-2.5">
                <div className="text-lg font-black font-mono leading-none">{stats.pdf.count}</div>
                <div className={`text-[10px] mt-1 font-mono font-medium ${filterType === 'PDF' ? 'text-rose-200' : 'text-rose-700'}`}>
                  {formatSize(stats.pdf.size)}
                </div>
              </div>
            </div>

            {/* 6. كتب مصورة / صور */}
            <div 
              onClick={() => setFilterType(filterType === 'IMAGE' ? 'ALL' : 'IMAGE')}
              className={`cursor-pointer p-3 rounded-xl border transition flex flex-col justify-between ${
                filterType === 'IMAGE'
                  ? 'bg-purple-700 text-white border-purple-700 shadow-sm'
                  : 'bg-purple-50/60 hover:bg-purple-50 text-purple-950 border-purple-200'
              }`}
            >
              <div className="flex items-center justify-between">
                <span className="text-xs font-bold">صور / كاميرا</span>
                <Camera className={`w-4 h-4 ${filterType === 'IMAGE' ? 'text-white' : 'text-purple-600'}`} />
              </div>
              <div className="mt-2.5">
                <div className="text-lg font-black font-mono leading-none">{stats.image.count}</div>
                <div className={`text-[10px] mt-1 font-mono font-medium ${filterType === 'IMAGE' ? 'text-purple-200' : 'text-purple-700'}`}>
                  {formatSize(stats.image.size)}
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

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
      <div className="flex items-center gap-2 flex-wrap pb-1.5">
        <button
          onClick={() => handleSelectDepartment('__ALL__', null)}
          className={`px-3.5 py-2 rounded-xl text-xs font-bold transition shrink-0 border ${
            selectedDept === '__ALL__'
              ? 'bg-[#14372e] text-white border-[#14372e] shadow-sm'
              : 'bg-white text-slate-700 border-slate-200 hover:bg-slate-100'
          }`}
        >
          🗂️ كافة الأقسام ({activeFiles.length})
        </button>

        {visibleDepartments.map((dept) => {
          const count = files.filter(
            (f) => !f.isDeleted && (f.department === dept || f.folder === dept || f.folder.startsWith(dept + '/'))
          ).length;
          const isPinLocked = isDeptPinProtected(dept) && !isDeptUnlocked(dept);
          return (
            <button
              key={dept}
              onClick={() => handleSelectDepartment(dept, null)}
              className={`px-3.5 py-2 rounded-xl text-xs font-bold transition shrink-0 border flex items-center gap-1.5 ${
                selectedDept === dept
                  ? 'bg-[#14372e] text-white border-[#14372e] shadow-sm'
                  : 'bg-white text-slate-800 border-slate-200 hover:bg-slate-100'
              }`}
            >
              <span>{isPinLocked ? '🔒' : isDeptPinProtected(dept) ? '🔓' : '🏛️'} {dept}</span>
              <span className={`text-[10px] px-1.5 py-0.5 rounded-full font-mono ${selectedDept === dept ? 'bg-white/20 text-white' : 'bg-slate-100 text-slate-600'}`}>
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

        {/* تصفية سريعة بالصيغة + زر تحديد الكل */}
        <div className="flex items-center gap-1 overflow-x-auto w-full sm:w-auto pb-1 sm:pb-0">
          {(displayedList.length > 0 || visibleSubfolders.length > 0) && (
            <button
              type="button"
              onClick={toggleSelectAllDisplayed}
              className={`px-2.5 py-1 rounded-lg text-[11px] font-bold transition whitespace-nowrap flex items-center gap-1 border ${
                isAllDisplayedSelected
                  ? 'bg-[#0f6cbd] text-white border-[#0f6cbd]'
                  : 'bg-sky-50 text-sky-800 border-sky-200 hover:bg-sky-100'
              }`}
            >
              <Check className="w-3 h-3" />
              <span>{isAllDisplayedSelected ? 'إلغاء تحديد الكل' : 'تحديد الكل'}</span>
            </button>
          )}
          {[
            { tag: 'ALL', label: `الكل (${stats.totalCount})` },
            { tag: 'WORD', label: `Word (${stats.word.count})` },
            { tag: 'EXCEL', label: `Excel (${stats.excel.count})` },
            { tag: 'ACCESS', label: `Access (${stats.access.count})` },
            { tag: 'PDF', label: `PDF (${stats.pdf.count})` },
            { tag: 'IMAGE', label: `صور (${stats.image.count})` },
            { tag: 'OTHER', label: `أخرى (${stats.other.count})` },
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
                const isSubSelected = selectedFolderIds.includes(sub.id);
                return (
                  <div
                    key={sub.id}
                    onClick={() => handleSelectDepartment(sub.department, sub.path)}
                    className={`group cursor-pointer rounded-xl p-3.5 flex items-center justify-between gap-2.5 transition shadow-2xs border ${
                      isSubSelected
                        ? 'bg-sky-50 border-sky-400 ring-2 ring-sky-200'
                        : 'bg-amber-50/50 hover:bg-amber-50 border-amber-200/80 hover:border-amber-400'
                    }`}
                  >
                    <div className="flex items-start gap-2.5 min-w-0 flex-1">
                      <input
                        type="checkbox"
                        checked={isSubSelected}
                        onClick={(e) => e.stopPropagation()}
                        onChange={() => toggleSelectFolder(sub.id)}
                        className="w-4 h-4 mt-1 rounded accent-[#0f6cbd] cursor-pointer shrink-0"
                        title="تحديد المجلد للنقل أو الحذف الجماعي"
                      />
                      <div className="p-2 bg-amber-100/80 text-amber-700 rounded-xl shrink-0">
                        <Folder className="w-5 h-5 fill-amber-400/40" />
                      </div>
                      <div className="min-w-0 flex-1">
                        <h4 className="font-bold text-sm text-slate-900 break-words whitespace-normal leading-snug" title={sub.name}>
                          {sub.name}
                        </h4>
                        <p className="text-[11px] text-slate-600 mt-1 font-medium">
                          {subFilesCount} مستند{childFoldersCount > 0 ? ` • ${childFoldersCount} مجلد فرعي` : ''}
                        </p>
                      </div>
                    </div>

                    <div className="flex items-center gap-1 shrink-0" onClick={(e) => e.stopPropagation()}>
                      {canMoveFolder(sub.path) && (
                        <button
                          onClick={() =>
                            openMoveDialog({
                              folderIds: [sub.id],
                              label: `المجلد: ${sub.name}`,
                              sourceDept: sub.department,
                            })
                          }
                          className="p-1.5 text-slate-500 hover:text-sky-700 hover:bg-white rounded-lg transition"
                          title="نقل المجلد إلى قسم أو مجلد آخر"
                        >
                          <Move className="w-3.5 h-3.5" />
                        </button>
                      )}
                      {canRenameFolder(sub.path) && (
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
                      )}
                      {canDeleteFolder(sub.path) && (
                        <button
                          onClick={() => handleMoveFolderToTrash(sub)}
                          className="p-1.5 text-slate-500 hover:text-rose-600 hover:bg-white rounded-lg transition"
                          title="نقل المجلد للمحذوفات"
                        >
                          <Trash2 className="w-3.5 h-3.5" />
                        </button>
                      )}
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
            {displayedList.map((file) => {
              const isSelected = selectedFileIds.includes(file.id);
              return (
                <div 
                  key={file.id} 
                  className={`bg-white rounded-2xl p-4 border shadow-sm flex flex-col justify-between space-y-3 transition ${
                    isSelected
                      ? 'border-[#0f6cbd] bg-sky-50/30 ring-2 ring-sky-200'
                      : 'border-slate-200/90 hover:border-[#14372e]/50'
                  }`}
                >
                  <div className="flex items-start gap-3">
                    <input
                      type="checkbox"
                      checked={isSelected}
                      onChange={() => toggleSelectFile(file.id)}
                      className="w-4 h-4 mt-1 rounded accent-[#0f6cbd] cursor-pointer shrink-0"
                      title="تحديد الملف"
                    />
                    <div
                      onClick={() => handleOpenFile(file)}
                      className="p-2.5 bg-slate-50 rounded-xl shrink-0 border border-slate-100 cursor-pointer"
                    >
                      {getFileIcon(file.type)}
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="flex items-start gap-1.5 flex-wrap">
                        <h4
                          onClick={() => handleOpenFile(file)}
                          className="font-bold text-sm text-slate-900 break-words whitespace-normal leading-relaxed cursor-pointer hover:text-[#0f6cbd]"
                        >
                          {file.name}
                        </h4>
                        {getFileBadge(file.type)}
                      </div>
                      <p className="text-xs text-slate-600 mt-1.5 font-semibold break-words whitespace-normal">
                        📂 {file.folder}
                      </p>
                      <div className="flex items-center gap-3 text-[11px] text-slate-500 mt-1.5 font-mono">
                        <span>💾 {file.size}</span>
                        <span>📅 {file.lastModifiedAt}</span>
                      </div>
                    </div>
                  </div>

                  {/* أزرار العمليات على بطاقة الجوال */}
                  <div className="flex items-center justify-between border-t border-slate-100 pt-2.5 gap-1.5 flex-wrap">
                    <button
                      onClick={() => handleOpenFile(file)}
                      className="flex-1 min-w-[110px] flex items-center justify-center gap-1.5 bg-[#14372e] text-white text-xs font-bold py-2 px-3 rounded-xl hover:bg-[#1a473b] transition active:scale-95 shadow-sm"
                      title="فتح أو معاينة الملف"
                    >
                      {file.type === 'word' && <FileText className="w-3.5 h-3.5 text-blue-300" />}
                      {file.type === 'excel' && <FileSpreadsheet className="w-3.5 h-3.5 text-emerald-300" />}
                      {file.type === 'access' && <Database className="w-3.5 h-3.5 text-rose-300" />}
                      {['image', 'pdf', 'video', 'audio'].includes(file.type) && <Eye className="w-3.5 h-3.5 text-amber-300" />}
                      {!['word', 'excel', 'access', 'image', 'pdf', 'video', 'audio'].includes(file.type) && (
                        <ExternalLink className="w-3.5 h-3.5 text-amber-300" />
                      )}
                      <span>
                        {file.type === 'word'
                          ? 'فتح Word'
                          : file.type === 'excel'
                          ? 'فتح Excel'
                          : file.type === 'access'
                          ? 'فتح Access'
                          : ['image', 'pdf', 'video', 'audio'].includes(file.type)
                          ? 'معاينة وفتح'
                          : 'فتح المستند'}
                      </span>
                    </button>

                    {activeTab === 'ACTIVE' && canEditFolder(file.folder) && ['word', 'excel', 'file', 'pdf'].includes(file.type) && (
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

                    {['word', 'excel'].includes(file.type) && (
                      <button
                        onClick={() => handleOpenOfficeOnline(file)}
                        className="p-2 text-blue-700 bg-blue-50 hover:bg-blue-100 rounded-xl transition"
                        title="معاينة في المتصفح عبر Office Online"
                      >
                        <Eye className="w-4 h-4" />
                      </button>
                    )}

                    <button
                      onClick={() => handleOpenInMobileApp(file)}
                      className="p-2 text-emerald-800 bg-emerald-50 hover:bg-emerald-100 rounded-xl transition"
                      title="تشغيل في تطبيقات الهاتف أو مشاركة المستند"
                    >
                      <Smartphone className="w-4 h-4" />
                    </button>

                    {canDownloadFolder(file.folder) && (
                      <button
                        onClick={() => handleDownloadFile(file)}
                        className="p-2 text-slate-600 bg-slate-100 hover:bg-slate-200 rounded-xl transition"
                        title="تنزيل نسخة للملف"
                      >
                        <Download className="w-4 h-4" />
                      </button>
                    )}

                    {activeTab === 'ACTIVE' ? (
                      <>
                        {canMoveFolder(file.folder) && (
                          <button
                            onClick={() =>
                              openMoveDialog({
                                fileIds: [file.id],
                                label: file.name,
                                sourceDept: file.department,
                              })
                            }
                            className="p-2 text-sky-700 bg-sky-50 hover:bg-sky-100 rounded-xl transition"
                            title="نقل الملف إلى قسم أو مجلد آخر"
                          >
                            <Move className="w-4 h-4" />
                          </button>
                        )}

                        {canRenameFolder(file.folder) && (
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
                        )}

                        {canDeleteFolder(file.folder) && (
                          <button
                            onClick={() => handleMoveToTrash(file)}
                            className="p-2 text-rose-600 bg-rose-50 hover:bg-rose-100 rounded-xl transition"
                            title="نقل للمحذوفات"
                          >
                            <Trash2 className="w-4 h-4" />
                          </button>
                        )}
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

                        {canPermanentDeleteFolder(file.folder) && (
                          <button
                            onClick={() => handlePermanentDelete(file)}
                            className="p-2 text-rose-700 bg-rose-50 hover:bg-rose-100 rounded-xl transition"
                            title="حذف نهائي"
                          >
                            <Trash2 className="w-4 h-4" />
                          </button>
                        )}
                      </>
                    )}
                  </div>
                </div>
              );
            })}
          </div>

          {/* نمط الجدول للشاشات الكبيرة (Desktop Table View) */}
          <div className="hidden lg:block bg-white rounded-2xl border border-slate-200 shadow-sm overflow-x-auto relative">
            <table className="w-full text-right text-sm min-w-[1020px]">
              <thead className="bg-[#f8fafc] text-slate-700 text-xs font-black border-b border-slate-200">
                <tr>
                  <th className="p-4 w-10 text-center">
                    <input
                      type="checkbox"
                      checked={isAllDisplayedSelected}
                      onChange={toggleSelectAllDisplayed}
                      className="w-4 h-4 rounded accent-[#0f6cbd] cursor-pointer"
                      title="تحديد / إلغاء تحديد الكل"
                    />
                  </th>
                  <th className="p-4 min-w-[300px]">اسم المستند الكامل</th>
                  <th className="p-4 min-w-[160px]">القسم / المجلد</th>
                  <th className="p-4 whitespace-nowrap">النوع</th>
                  <th className="p-4 whitespace-nowrap">الحجم</th>
                  <th className="p-4 whitespace-nowrap">تاريخ الاعتماد</th>
                  <th className="p-4 whitespace-nowrap">المصدر</th>
                  <th className="p-4 text-center sticky left-0 bg-[#f8fafc] z-20 shadow-[-4px_0_8px_-2px_rgba(0,0,0,0.06)] min-w-[295px] whitespace-nowrap">الإجراءات</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {displayedList.map((file) => {
                  const isSelected = selectedFileIds.includes(file.id);
                  return (
                    <tr
                      key={file.id}
                      className={`group transition ${
                        isSelected ? 'bg-sky-50/70 hover:bg-sky-50' : 'hover:bg-slate-50/80'
                      }`}
                    >
                      <td className="p-4 text-center">
                        <input
                          type="checkbox"
                          checked={isSelected}
                          onChange={() => toggleSelectFile(file.id)}
                          className="w-4 h-4 rounded accent-[#0f6cbd] cursor-pointer"
                          title="تحديد هذا الملف"
                        />
                      </td>
                      <td className="p-4 min-w-[300px] max-w-[520px]">
                        <div
                          onClick={() => handleOpenFile(file)}
                          className="flex items-start gap-2.5 cursor-pointer group/title"
                        >
                          <span className="shrink-0 mt-0.5">{getFileIcon(file.type)}</span>
                          <span 
                            className="font-bold text-slate-900 group-hover/title:text-[#0f6cbd] text-sm break-words whitespace-normal leading-relaxed block transition"
                            title={file.name}
                          >
                            {file.name}
                          </span>
                        </div>
                      </td>
                      <td className="p-4 text-xs font-semibold text-slate-700 break-words whitespace-normal max-w-[240px] leading-relaxed">{file.folder}</td>
                      <td className="p-4 whitespace-nowrap">{getFileBadge(file.type)}</td>
                      <td className="p-4 text-xs font-mono font-bold text-slate-700 whitespace-nowrap">{file.size}</td>
                      <td className="p-4 text-xs text-slate-600 font-mono whitespace-nowrap">{file.lastModifiedAt}</td>
                      <td className="p-4 text-xs whitespace-nowrap">
                        <span className="bg-slate-100 text-slate-700 font-bold px-2 py-0.5 rounded text-[10px]">
                          {file.lastModifiedBy}
                        </span>
                      </td>
                      <td className="p-4 text-center sticky left-0 bg-white group-hover:bg-slate-50 transition z-10 shadow-[-4px_0_8px_-2px_rgba(0,0,0,0.06)] min-w-[295px] whitespace-nowrap">
                        <div className="inline-flex items-center gap-1.5 justify-center">
                          <button
                            onClick={() => handleOpenFile(file)}
                            className="flex items-center gap-1.5 bg-[#14372e] hover:bg-[#1a473b] text-white text-xs font-bold py-1.5 px-3 rounded-lg transition active:scale-95 shadow-xs"
                            title="فتح أو معاينة الملف"
                          >
                            {file.type === 'word' && <FileText className="w-3.5 h-3.5 text-blue-300" />}
                            {file.type === 'excel' && <FileSpreadsheet className="w-3.5 h-3.5 text-emerald-300" />}
                            {file.type === 'access' && <Database className="w-3.5 h-3.5 text-rose-300" />}
                            {['image', 'pdf', 'video', 'audio'].includes(file.type) && <Eye className="w-3.5 h-3.5 text-amber-300" />}
                            {!['word', 'excel', 'access', 'image', 'pdf', 'video', 'audio'].includes(file.type) && (
                              <ExternalLink className="w-3.5 h-3.5 text-amber-300" />
                            )}
                            <span>
                              {file.type === 'word'
                                ? 'فتح Word'
                                : file.type === 'excel'
                                ? 'فتح Excel'
                                : file.type === 'access'
                                ? 'فتح Access'
                                : ['image', 'pdf', 'video', 'audio'].includes(file.type)
                                ? 'معاينة'
                                : 'فتح'}
                            </span>
                          </button>

                          {activeTab === 'ACTIVE' && canEditFolder(file.folder) && ['word', 'excel', 'file', 'pdf'].includes(file.type) && (
                            <button
                              onClick={() => triggerUpdateFile(file)}
                              className="flex items-center gap-1 bg-amber-500 hover:bg-amber-600 text-slate-950 text-xs font-bold py-1.5 px-2 rounded-lg transition active:scale-95 shadow-xs"
                              title="رفع نسخة معدلة وتحديث المستند في السحابة ومشاركته فوراً"
                            >
                              <UploadCloud className="w-3.5 h-3.5 text-slate-950" />
                              <span>حفظ التعديلات</span>
                            </button>
                          )}

                          {['word', 'excel'].includes(file.type) && (
                            <button
                              onClick={() => handleOpenOfficeOnline(file)}
                              className="p-1.5 text-slate-500 hover:text-blue-700 hover:bg-blue-50 rounded-lg transition"
                              title="معاينة في المتصفح عبر Office Online"
                            >
                              <Eye className="w-4 h-4" />
                            </button>
                          )}

                          {canDownloadFolder(file.folder) && (
                            <button
                              onClick={() => handleDownloadFile(file)}
                              className="p-1.5 text-slate-500 hover:text-slate-800 hover:bg-slate-100 rounded-lg transition"
                              title="تنزيل نسخة للملف"
                            >
                              <Download className="w-4 h-4" />
                            </button>
                          )}

                          <button
                            onClick={() => handleRevealInExplorer(file)}
                            className="p-1.5 text-slate-500 hover:text-amber-700 hover:bg-amber-50 rounded-lg transition"
                            title="إظهار المستند في مجلد الويندوز المحلي"
                          >
                            <FolderOpen className="w-4 h-4" />
                          </button>

                          <button
                            onClick={() => handleShareFile(file)}
                            className="p-1.5 text-slate-500 hover:text-emerald-700 hover:bg-emerald-50 rounded-lg transition"
                            title="فتح عبر تطبيقات الهاتف أو مشاركة المستند"
                          >
                            <Share2 className="w-4 h-4" />
                          </button>

                          {activeTab === 'ACTIVE' ? (
                            <>
                              {canMoveFolder(file.folder) && (
                                <button
                                  onClick={() =>
                                    openMoveDialog({
                                      fileIds: [file.id],
                                      label: file.name,
                                      sourceDept: file.department,
                                    })
                                  }
                                  className="p-1.5 text-slate-600 hover:text-sky-700 hover:bg-sky-50 rounded-lg transition"
                                  title="نقل الملف إلى قسم أو مجلد آخر"
                                >
                                  <Move className="w-4 h-4" />
                                </button>
                              )}

                              {canRenameFolder(file.folder) && (
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
                              )}

                              {canDeleteFolder(file.folder) && (
                                <button
                                  onClick={() => handleMoveToTrash(file)}
                                  className="p-1.5 text-slate-500 hover:text-rose-600 hover:bg-rose-50 rounded-lg transition"
                                  title="نقل للمحذوفات"
                                >
                                  <Trash2 className="w-4 h-4" />
                                </button>
                              )}
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

                              {canPermanentDeleteFolder(file.folder) && (
                                <button
                                  onClick={() => handlePermanentDelete(file)}
                                  className="p-1.5 text-rose-600 hover:text-rose-800 hover:bg-rose-50 rounded-lg transition"
                                  title="حذف نهائي"
                                >
                                  <Trash2 className="w-4 h-4" />
                                </button>
                              )}
                            </>
                          )}
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </>
      )}

      {/* مؤشر تقدم الرفع والتحميل السحابي الدقيق واللحظي (Detailed Accurate Upload/Download Progress Dialog) */}
      {uploadProgress && uploadProgress.show && !uploadProgress.minimized && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-xs p-4 animate-in fade-in duration-200" dir="rtl">
          <div className="bg-white rounded-3xl shadow-2xl border border-emerald-100 max-w-lg w-full overflow-hidden text-right space-y-4 animate-in zoom-in-95 duration-200">
            {/* رأس النافذة مع هوية غرفة تجارة كربلاء وزر التصغير للعمل بالخلفية */}
            <div className="bg-gradient-to-r from-[#14372e] via-[#1b493d] to-[#14372e] p-4 text-white flex items-center justify-between">
              <div className="flex items-center gap-2.5">
                <div className="w-8 h-8 rounded-xl bg-white/10 flex items-center justify-center text-amber-400">
                  {uploadProgress.mode === 'download' ? (
                    <Download className="w-5 h-5 animate-bounce" />
                  ) : (
                    <UploadCloud className="w-5 h-5 animate-pulse" />
                  )}
                </div>
                <div>
                  <h3 className="text-sm font-black tracking-wide">
                    {uploadProgress.mode === 'download'
                      ? 'مؤشر التنزيل السحابي الحقيقي والمباشر'
                      : 'مؤشر الرفع السحابي الحقيقي والمباشر'}
                  </h3>
                  <p className="text-[11px] text-emerald-200/80 font-medium">غرفة تجارة كربلاء المقدسة • Google Drive</p>
                </div>
              </div>

              <div className="flex items-center gap-1.5">
                <button
                  type="button"
                  onClick={() => setUploadProgress(prev => prev ? { ...prev, minimized: true } : null)}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-white/10 hover:bg-white/20 text-xs text-white font-bold transition-all shadow-xs"
                  title="تصغير ومتابعة العمل بالخلفية"
                >
                  <Minimize2 className="w-3.5 h-3.5" />
                  <span className="hidden sm:inline">تصغير للخلفية</span>
                </button>
              </div>
            </div>

            <div className="p-6 pt-2 space-y-5">
              {/* أيقونة الحالة والعنوان واسم الملف الكامل */}
              <div className="text-center space-y-2.5">
                <div className="flex items-center justify-center w-16 h-16 mx-auto rounded-2xl bg-emerald-50 text-emerald-600 shadow-inner">
                  {uploadProgress.completed ? (
                    <CheckCircle2 className="w-10 h-10 text-emerald-600 animate-bounce" />
                  ) : uploadProgress.mode === 'download' ? (
                    <Download className="w-10 h-10 text-emerald-600 animate-bounce" />
                  ) : (
                    <UploadCloud className="w-10 h-10 text-emerald-600 animate-pulse" />
                  )}
                </div>

                <div className="space-y-1.5">
                  <h4 className="text-base font-black text-slate-900">
                    {uploadProgress.completed
                      ? uploadProgress.mode === 'download'
                        ? '✅ اكتمل تنزيل المستند بنجاح!'
                        : '✅ اكتمل الرفع والمزامنة بنجاح!'
                      : uploadProgress.statusText
                      ? uploadProgress.statusText
                      : uploadProgress.mode === 'download'
                      ? 'جاري تنزيل المستند من السحابة بحجمه وسرعته الحقيقية...'
                      : uploadProgress.total > 1
                      ? `جاري رفع المجلد والملفات (${uploadProgress.current} من ${uploadProgress.total})...`
                      : 'جاري رفع المستند إلى السحابة بحجمه وسرعته الحقيقية...'}
                  </h4>
                  <div className="inline-flex items-center justify-center px-3.5 py-1.5 bg-slate-100 rounded-xl text-xs font-bold text-slate-800 max-w-full break-words whitespace-normal leading-relaxed border border-slate-200/80">
                    <span className="break-words whitespace-normal">{uploadProgress.currentFileName}</span>
                  </div>
                </div>
              </div>

              {/* النسبة المئوية وأشرطة التحميل الدقيقة (إجمالي الدفعة + الملف الفردي النشط) */}
              {uploadProgress.total > 1 ? (
                <div className="space-y-3 bg-slate-50 p-3.5 rounded-2xl border border-slate-200/80">
                  {/* شريط تقدم المجلد أو الدفعة بالكامل */}
                  <div className="space-y-1.5">
                    <div className="flex justify-between items-baseline px-1">
                      <div className="flex items-baseline gap-2">
                        <span className="text-2xl font-black text-[#14372e] tracking-tight font-mono">
                          {uploadProgress.percentage}%
                        </span>
                        <span className="text-[11px] font-black text-emerald-850 bg-emerald-100 px-2 py-0.5 rounded-lg border border-emerald-300">
                          إنجاز المجلد بالكامل
                        </span>
                      </div>
                      <span className="text-xs font-bold text-slate-600 font-mono">
                        مستند {uploadProgress.current} من {uploadProgress.total}
                      </span>
                    </div>

                    <div className="w-full bg-slate-200 rounded-full h-3.5 overflow-hidden p-0.5 border border-slate-300 shadow-inner relative">
                      <div
                        className="bg-gradient-to-r from-emerald-600 via-teal-500 to-amber-500 h-full rounded-full transition-all duration-150 ease-out shadow-sm relative overflow-hidden"
                        style={{ width: `${Math.max(2, uploadProgress.percentage)}%` }}
                      >
                        {!uploadProgress.completed && (
                          <div className="absolute inset-0 bg-white/25 animate-pulse" />
                        )}
                      </div>
                    </div>
                  </div>

                  {/* شريط تقدم الملف الفردي النشط حالياً */}
                  <div className="space-y-1 pt-1 border-t border-slate-200/70">
                    <div className="flex justify-between items-center text-xs px-1">
                      <span className="font-bold text-slate-700 flex items-center gap-1.5">
                        <FileText className="w-3.5 h-3.5 text-emerald-600" />
                        <span>الملف الحالي:</span>
                        <span className="font-black text-emerald-900 font-mono">{uploadProgress.currentFilePercentage}%</span>
                      </span>
                      <span className="text-[11px] text-slate-500 font-mono" dir="ltr">
                        {uploadProgress.megabytesFormatted}
                      </span>
                    </div>

                    <div className="w-full bg-slate-200/70 rounded-full h-2 overflow-hidden">
                      <div
                        className="bg-emerald-600 h-full rounded-full transition-all duration-150"
                        style={{ width: `${Math.max(2, uploadProgress.currentFilePercentage)}%` }}
                      />
                    </div>
                  </div>
                </div>
              ) : (
                /* شريط التحميل الدقيق لملف فردي */
                <div className="space-y-2">
                  <div className="flex justify-between items-baseline px-1">
                    <div className="flex items-baseline gap-2">
                      <span className="text-3xl font-black text-[#14372e] tracking-tight font-mono">
                        {uploadProgress.percentage}%
                      </span>
                      <span className="text-xs font-black text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded-lg border border-emerald-200">
                        نسبة الإنجاز الحقيقية
                      </span>
                    </div>
                    <span className="text-xs font-bold text-slate-600 font-mono" dir="ltr">
                      {uploadProgress.megabytesFormatted}
                    </span>
                  </div>

                  <div className="w-full bg-slate-100 rounded-full h-4 overflow-hidden p-0.5 border border-slate-200/90 shadow-inner relative">
                    <div
                      className="bg-gradient-to-r from-emerald-600 via-teal-500 to-amber-500 h-full rounded-full transition-all duration-150 ease-out shadow-sm relative overflow-hidden"
                      style={{ width: `${Math.max(2, uploadProgress.percentage)}%` }}
                    >
                      {!uploadProgress.completed && (
                        <div className="absolute inset-0 bg-white/25 animate-pulse" />
                      )}
                    </div>
                  </div>
                </div>
              )}

              {/* بطاقات الإحصاءات الحية (Stat Cards): الميغات + سرعة الإنترنت + الوقت المتبقي + الحالة */}
              <div className="grid grid-cols-2 gap-3 pt-1">
                {/* 1. الميغات للملف بدقة (MB) */}
                <div className="p-3.5 rounded-2xl bg-emerald-50/60 border border-emerald-200/80 space-y-1">
                  <div className="flex items-center gap-1.5 text-emerald-900 text-xs font-black">
                    <Database className="w-4 h-4 text-emerald-600" />
                    <span>حجم الملف بالميغابايت (MB)</span>
                  </div>
                  <p className="text-sm font-black text-slate-900 font-mono" dir="ltr">
                    {uploadProgress.megabytesFormatted}
                  </p>
                  <p className="text-[11px] text-slate-600 font-bold" dir="ltr">
                    ({formatBytes(uploadProgress.currentFileUploaded)} / {formatBytes(uploadProgress.currentFileSize)})
                  </p>
                  {uploadProgress.total > 1 && (
                    <p className="text-[11px] text-emerald-800 font-bold break-words whitespace-normal" dir="ltr">
                      إجمالي الدفعة: {uploadProgress.batchMegabytesFormatted}
                    </p>
                  )}
                </div>

                {/* 2. سرعة الإنترنت الحقيقية */}
                <div className="p-3.5 rounded-2xl bg-amber-50/60 border border-amber-200/80 space-y-1">
                  <div className="flex items-center gap-1.5 text-amber-950 text-xs font-black">
                    <Zap className="w-4 h-4 text-amber-600" />
                    <span>سرعة الإنترنت الفورية</span>
                  </div>
                  <p className="text-base font-black text-slate-900 font-mono" dir="ltr">
                    {uploadProgress.speedFormatted}
                  </p>
                  <p className="text-[11px] text-emerald-700 font-bold">
                    {uploadProgress.completed ? 'تم النقل بالكامل 100%' : 'قياس حقيقي مباشر للشبكة'}
                  </p>
                </div>

                {/* 3. الوقت التقديري المتبقي */}
                <div className="p-3 rounded-2xl bg-slate-50 border border-slate-200/80 space-y-1">
                  <div className="flex items-center gap-1.5 text-slate-600 text-xs font-bold">
                    <Clock className="w-3.5 h-3.5 text-teal-600" />
                    <span>الوقت المتبقي</span>
                  </div>
                  <p className="text-xs font-black text-slate-900">
                    {uploadProgress.completed ? 'تم الانتهاء' : uploadProgress.timeRemainingFormatted}
                  </p>
                  <p className="text-[10px] text-slate-500 font-semibold">حساب ديناميكي حسب السرعة</p>
                </div>

                {/* 4. حالة النقل الحقيقي */}
                <div className="p-3 rounded-2xl bg-slate-50 border border-slate-200/80 space-y-1">
                  <div className="flex items-center gap-1.5 text-slate-600 text-xs font-bold">
                    <Activity className="w-3.5 h-3.5 text-blue-600" />
                    <span>حالة النقل السحابي</span>
                  </div>
                  <p className="text-xs font-black text-slate-900 break-words whitespace-normal">
                    {uploadProgress.chunkText || (uploadProgress.total > 1 ? `الملف ${uploadProgress.current} من ${uploadProgress.total}` : 'نقل مباشر مؤكد')}
                  </p>
                  <p className="text-[10px] text-slate-500 font-semibold">تأكيد بايت تلو الآخر من السحابة</p>
                </div>
              </div>

              {/* أزرار المتابعة بالخلفية أو الإلغاء أو إشعار الإتمام */}
              {uploadProgress.completed ? (
                <div className="text-xs text-emerald-800 font-bold bg-emerald-50 py-3 px-4 rounded-2xl border border-emerald-200 text-center animate-in fade-in">
                  {uploadProgress.mode === 'download'
                    ? '🎉 اكتمل تنزيل المستند بنجاح إلى جهازك!'
                    : '🎉 تمت المزامنة وتأكيد وصول الملفات 100% لجميع الأجهزة وتطبيق الحاسوب!'}
                </div>
              ) : (
                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    onClick={() => setUploadProgress(prev => prev ? { ...prev, minimized: true } : null)}
                    className="flex-1 py-2.5 px-4 rounded-2xl bg-slate-100 hover:bg-slate-200 text-slate-800 text-xs font-bold transition-all text-center flex items-center justify-center gap-2"
                  >
                    <Minimize2 className="w-4 h-4 text-slate-600" />
                    <span>تصفح المستندات والمتابعة بالخلفية</span>
                  </button>

                  <button
                    type="button"
                    onClick={handleAbortActiveTransfer}
                    className="py-2.5 px-4 rounded-2xl bg-rose-50 hover:bg-rose-100 text-rose-700 border border-rose-200 text-xs font-bold transition-all flex items-center justify-center gap-1.5 shrink-0"
                    title="إلغاء عملية النقل الحالية"
                  >
                    <X className="w-4 h-4" />
                    <span>إلغاء</span>
                  </button>
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* المؤشر العائم المصغر بالزاوية لمتابعة الرفع أو التنزيل بالخلفية (Floating Minimized Progress Pill) */}
      {uploadProgress && uploadProgress.show && uploadProgress.minimized && (
        <div
          className="fixed bottom-6 left-6 z-50 bg-slate-900/95 text-white backdrop-blur-md rounded-2xl shadow-2xl border border-emerald-500/40 p-4 max-w-sm w-84 animate-in slide-in-from-bottom-5 duration-200"
          dir="rtl"
        >
          <div className="flex items-center justify-between pb-2 border-b border-slate-800">
            <div className="flex items-center gap-2">
              <span className={`w-2.5 h-2.5 rounded-full ${uploadProgress.completed ? 'bg-emerald-400' : 'bg-amber-400 animate-ping'}`} />
              <span className="text-xs font-black">
                {uploadProgress.completed
                  ? uploadProgress.mode === 'download' ? 'اكتمل التنزيل!' : 'اكتمل الرفع!'
                  : uploadProgress.mode === 'download' ? 'جاري التنزيل بالخلفية' : 'جاري الرفع بالخلفية'}
              </span>
            </div>

            <div className="flex items-center gap-2">
              <span className="text-xs font-black text-amber-400 font-mono" dir="ltr">
                {uploadProgress.speedFormatted}
              </span>
              <button
                type="button"
                onClick={() => setUploadProgress(prev => prev ? { ...prev, minimized: false } : null)}
                className="p-1 rounded-lg hover:bg-white/10 text-slate-300 hover:text-white transition-colors"
                title="توسيع نافذة المؤشر التفصيلي"
              >
                <Maximize2 className="w-4 h-4" />
              </button>
            </div>
          </div>

          <div className="pt-2.5 space-y-2">
            <p className="text-xs text-slate-200 font-bold break-words whitespace-normal leading-snug">
              {uploadProgress.currentFileName}
            </p>

            <div className="w-full bg-slate-800 rounded-full h-2.5 overflow-hidden">
              <div
                className="bg-gradient-to-r from-emerald-500 to-amber-500 h-full rounded-full transition-all duration-150"
                style={{ width: `${Math.max(3, uploadProgress.percentage)}%` }}
              />
            </div>

            <div className="flex justify-between items-center text-[11px] font-bold text-slate-300 pt-0.5 font-mono">
              <span className="text-emerald-400 text-xs font-black">
                {uploadProgress.percentage}% {uploadProgress.total > 1 ? `(${uploadProgress.current}/${uploadProgress.total})` : ''}
              </span>
              <span dir="ltr">{uploadProgress.total > 1 ? uploadProgress.batchMegabytesFormatted : uploadProgress.megabytesFormatted}</span>
              <span>{uploadProgress.completed ? 'اكتمل' : uploadProgress.timeRemainingFormatted}</span>
            </div>
          </div>
        </div>
      )}

      {/* نافذة التحقق من الرمز السري للقسم المحمي (Department PIN Prompt Modal) */}
      {pinPromptDept && (
        <div className="fixed inset-0 bg-black/60 backdrop-blur-xs z-50 flex items-center justify-center p-4" dir="rtl">
          <div className="bg-white rounded-3xl p-6 max-w-md w-full space-y-4 shadow-2xl border border-amber-300">
            <div className="flex items-center justify-between border-b pb-3">
              <h3 className="font-black text-base text-[#14372e] flex items-center gap-2">
                <Lock className="w-5 h-5 text-amber-600" />
                <span>قسم محمي برمز سري (PIN)</span>
              </h3>
              <button
                onClick={() => {
                  setPinPromptDept(null);
                  setPinPromptTargetFolder(null);
                  setPinPromptInput('');
                  setPinPromptError('');
                }}
                className="text-slate-400 hover:text-slate-600"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <p className="text-xs text-slate-600 leading-relaxed font-medium">
              القسم <strong className="text-[#14372e]">({pinPromptDept})</strong> محمي برمز سري من قِبل الإدارة. يرجى إدخال الرمز السري لفتح القسم واستعراض مستنداته:
            </p>

            <form onSubmit={handleVerifyDeptPin} className="space-y-3">
              <input
                type="password"
                value={pinPromptInput}
                onChange={(e) => {
                  setPinPromptInput(e.target.value);
                  setPinPromptError('');
                }}
                placeholder="أدخل الرمز السري للقسم..."
                className="w-full px-4 py-3 text-sm bg-slate-50 border border-slate-300 rounded-xl focus:outline-none focus:ring-2 focus:ring-[#14372e] text-center font-mono font-bold tracking-widest"
                autoFocus
              />

              {pinPromptError && (
                <p className="text-xs text-rose-600 font-bold text-center">
                  {pinPromptError}
                </p>
              )}

              <div className="flex items-center justify-end gap-2 pt-2 border-t">
                <button
                  type="button"
                  onClick={() => {
                    setPinPromptDept(null);
                    setPinPromptTargetFolder(null);
                    setPinPromptInput('');
                    setPinPromptError('');
                  }}
                  className="px-4 py-2 text-xs font-bold text-slate-600 hover:bg-slate-100 rounded-xl transition"
                >
                  إلغاء
                </button>
                <button
                  type="submit"
                  className="px-5 py-2.5 text-xs font-black bg-[#14372e] text-white rounded-xl hover:bg-[#1a473b] transition shadow-sm"
                >
                  🔓 فتح القسم
                </button>
              </div>
            </form>
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
            <div className="flex items-start justify-between border-b pb-3 gap-2">
              <div className="flex items-start gap-2.5 min-w-0 flex-1">
                <div className="mt-0.5 shrink-0">{getFileIcon(selectedMobileFile.type)}</div>
                <div className="min-w-0 flex-1">
                  <h3 className="font-bold text-sm text-[#14372e] break-words whitespace-normal leading-snug">
                    {selectedMobileFile.name}
                  </h3>
                  <div className="flex items-center gap-2 text-[11px] text-slate-500 mt-1 flex-wrap">
                    <span className="break-words whitespace-normal">📂 {selectedMobileFile.folder}</span>
                    <span>•</span>
                    <span className="font-bold text-emerald-700 bg-emerald-50 px-1.5 py-0.2 rounded border border-emerald-200">
                      الإصدار V{selectedMobileFile.version}
                    </span>
                  </div>
                </div>
              </div>
              <button 
                onClick={() => setSelectedMobileFile(null)} 
                className="text-slate-400 hover:text-slate-600 p-1.5 rounded-full hover:bg-slate-100 shrink-0"
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

      {/* شريط الإجراءات الجماعية العائم عند تحديد ملفات أو مجلدات (Floating Bulk Action Bar) */}
      {(selectedFileIds.length > 0 || selectedFolderIds.length > 0) && (
        <div
          className="fixed bottom-5 left-1/2 -translate-x-1/2 z-40 bg-slate-900/95 text-white backdrop-blur-md px-4 py-3 rounded-2xl shadow-2xl border border-slate-700 flex items-center gap-3 flex-wrap justify-center max-w-[95vw]"
          dir="rtl"
        >
          <div className="flex items-center gap-2 pl-2 border-l border-slate-700">
            <span className="w-6 h-6 rounded-full bg-[#0f6cbd] text-white text-xs font-black flex items-center justify-center">
              {selectedFileIds.length + selectedFolderIds.length}
            </span>
            <span className="text-xs font-bold">عنصر محدد</span>
          </div>

          {activeTab === 'ACTIVE' && (
            <button
              type="button"
              onClick={() =>
                openMoveDialog({
                  fileIds: selectedFileIds,
                  folderIds: selectedFolderIds,
                  label: `${selectedFileIds.length + selectedFolderIds.length} عنصر محدد`,
                  sourceDept: selectedDept !== '__ALL__' ? selectedDept : undefined,
                })
              }
              disabled={actionLoading}
              className="px-3.5 py-1.5 rounded-xl bg-sky-600 hover:bg-sky-500 text-white text-xs font-bold transition flex items-center gap-1.5 shadow-sm"
            >
              <Move className="w-3.5 h-3.5" />
              <span>نقل المحدد إلى...</span>
            </button>
          )}

          {activeTab === 'TRASH' && (
            <button
              type="button"
              onClick={async () => {
                if (selectedFileIds.length === 0) return;
                try {
                  setActionLoading(true);
                  const res = await fetch('/api/drive/files', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ action: 'BATCH_RESTORE', ids: selectedFileIds }),
                  });
                  const data = await res.json();
                  if (!data.success) throw new Error(data.error);
                  clearSelection();
                  notifyLocalDesktopSync();
                  await loadData();
                  setToastMessage({
                    text: `♻️ تم استرجاع (${selectedFileIds.length}) ملف بنجاح!`,
                    type: 'success',
                  });
                } catch (err: any) {
                  alert(`تعذر استرجاع المحدد: ${err.message || err}`);
                } finally {
                  setActionLoading(false);
                }
              }}
              disabled={actionLoading}
              className="px-3.5 py-1.5 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-bold transition flex items-center gap-1.5 shadow-sm"
            >
              <RotateCcw className="w-3.5 h-3.5" />
              <span>استرجاع المحدد</span>
            </button>
          )}

          <button
            type="button"
            onClick={handleBulkDeleteSelected}
            disabled={actionLoading}
            className="px-3.5 py-1.5 rounded-xl bg-rose-600 hover:bg-rose-500 text-white text-xs font-bold transition flex items-center gap-1.5 shadow-sm"
          >
            <Trash2 className="w-3.5 h-3.5" />
            <span>{activeTab === 'TRASH' ? 'حذف نهائي للمحدد' : 'حذف المحدد للسلة'}</span>
          </button>

          <button
            type="button"
            onClick={clearSelection}
            className="px-2.5 py-1.5 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-bold transition"
          >
            إلغاء التحديد
          </button>
        </div>
      )}

      {/* نافذة نقل الملفات والمجلدات بين الأقسام والمجلدات الفرعية (Move Modal) */}
      {showMoveModal && itemsToMove && (
        <div className="fixed inset-0 bg-black/60 backdrop-blur-xs z-50 flex items-center justify-center p-4" dir="rtl">
          <div className="bg-white rounded-3xl p-6 max-w-md w-full space-y-4 shadow-2xl border border-slate-200">
            <div className="flex items-center justify-between border-b pb-3">
              <h3 className="font-bold text-base text-[#14372e] flex items-center gap-2">
                <Move className="w-5 h-5 text-sky-600" />
                <span>نقل إلى قسم أو مجلد آخر</span>
              </h3>
              <button
                onClick={() => {
                  setShowMoveModal(false);
                  setItemsToMove(null);
                }}
                className="text-slate-400 hover:text-slate-600"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="p-3 rounded-xl bg-sky-50 border border-sky-200 text-xs text-sky-900 font-bold">
              📦 العناصر المراد نقلها: <span className="text-[#0f6cbd]">{itemsToMove.label}</span>
            </div>

            <div className="space-y-3">
              <div>
                <label className="block text-xs font-bold text-slate-700 mb-1">
                  1. اختر القسم الهدف:
                </label>
                <select
                  value={moveTargetDept}
                  onChange={(e) => {
                    setMoveTargetDept(e.target.value);
                    setMoveTargetSubfolder('');
                  }}
                  className="w-full px-3.5 py-2.5 text-xs bg-slate-50 border border-slate-200 rounded-xl font-bold focus:outline-none focus:ring-2 focus:ring-[#14372e]"
                >
                  {departments.map((d) => (
                    <option key={d} value={d}>
                      🏛️ {d}
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-xs font-bold text-slate-700 mb-1">
                  2. اختر مجلداً فرعياً داخل القسم (اختياري):
                </label>
                <select
                  value={moveTargetSubfolder}
                  onChange={(e) => setMoveTargetSubfolder(e.target.value)}
                  className="w-full px-3.5 py-2.5 text-xs bg-slate-50 border border-slate-200 rounded-xl font-bold focus:outline-none focus:ring-2 focus:ring-[#14372e]"
                >
                  <option value="">📂 المجلد الرئيسي للقسم ({moveTargetDept})</option>
                  {allFolders
                    .filter((f) => f.department === moveTargetDept && f.parentPath)
                    .map((sub) => (
                      <option key={sub.id} value={sub.path}>
                        📁 {sub.path}
                      </option>
                    ))}
                </select>
              </div>

              <div>
                <label className="block text-xs font-bold text-slate-700 mb-1">
                  أو اكتب اسم مجلد فرعي جديد ليتم إنشاؤه ونقل الملفات إليه:
                </label>
                <input
                  type="text"
                  value={moveCustomSubfolder}
                  onChange={(e) => setMoveCustomSubfolder(e.target.value)}
                  placeholder="اتركه فارغاً للنقل للمجلد المختار أعلاه..."
                  className="w-full px-3.5 py-2 text-xs bg-slate-50 border border-slate-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-[#14372e]"
                />
              </div>
            </div>

            <p className="text-[11px] text-slate-500">
              سيتم تنفيذ النقل في سحابة Google Drive فوراً ومزامنة الموقع الجديد مع تطبيق سطح المكتب وكافة المنصات.
            </p>

            <div className="flex items-center justify-end gap-2 pt-2 border-t">
              <button
                type="button"
                onClick={() => {
                  setShowMoveModal(false);
                  setItemsToMove(null);
                }}
                className="px-4 py-2 text-xs font-bold text-slate-600 hover:bg-slate-100 rounded-xl transition"
              >
                إلغاء
              </button>
              <button
                type="button"
                onClick={handleExecuteMove}
                disabled={actionLoading || !moveTargetDept}
                className="px-5 py-2 text-xs font-bold bg-[#14372e] text-white rounded-xl hover:bg-[#1a473b] transition shadow-sm flex items-center gap-1.5"
              >
                <Move className="w-3.5 h-3.5" />
                <span>تأكيد النقل ومزامنة السحابة</span>
              </button>
            </div>
          </div>
        </div>
      )}

      {/* نافذة شريط تقدم تفريغ السلة والعمليات الجماعية السريعة (Trash & Batch Progress Modal) */}
      {trashProgress && trashProgress.show && (
        <div className="fixed inset-0 bg-black/60 backdrop-blur-xs z-50 flex items-center justify-center p-4" dir="rtl">
          <div className="bg-white rounded-3xl p-6 max-w-md w-full space-y-4 shadow-2xl border border-slate-200 text-right">
            <div className="flex items-center gap-3">
              <div className="w-11 h-11 rounded-2xl bg-rose-50 text-rose-600 flex items-center justify-center shrink-0">
                <RefreshCw className="w-5 h-5 animate-spin" />
              </div>
              <div className="min-w-0 flex-1">
                <h3 className="font-black text-sm text-slate-900">{trashProgress.title}</h3>
                <p className="text-xs text-slate-600 break-words whitespace-normal mt-0.5">{trashProgress.currentName}</p>
              </div>
            </div>

            <div className="space-y-2">
              <div className="flex items-center justify-between text-xs font-bold">
                <span className="text-2xl font-black text-[#14372e]">{trashProgress.percentage}%</span>
                <span className="text-slate-600">
                  تم إنجاز {trashProgress.current} من {trashProgress.total}
                </span>
              </div>
              <div className="w-full bg-slate-100 rounded-full h-3.5 overflow-hidden p-0.5 border border-slate-200">
                <div
                  className="bg-gradient-to-r from-[#14372e] via-emerald-600 to-amber-500 h-full rounded-full transition-all duration-200"
                  style={{ width: `${Math.max(4, trashProgress.percentage)}%` }}
                />
              </div>
            </div>

            <p className="text-[11px] text-slate-400 text-center">
              تتم معالجة الدفعات بالتوازي مع سحابة Google Drive لضمان أقصى سرعة وعدم توقف المنصة...
            </p>
          </div>
        </div>
      )}

      {/* عارض الصور والوسائط وملفات PDF المدمج (Built-in Lightbox Preview Modal) */}
      {previewFile && (
        <div
          className="fixed inset-0 bg-black/85 backdrop-blur-md z-50 flex flex-col justify-between p-3 sm:p-6 animate-in fade-in duration-150"
          dir="rtl"
        >
          {/* شريط علوي للعارض */}
          <div className="flex items-center justify-between gap-3 bg-slate-900/90 text-white px-4 py-3 rounded-2xl border border-slate-700/80">
            <div className="flex items-center gap-2.5 min-w-0 flex-1">
              <div className="shrink-0">{getFileIcon(previewFile.type)}</div>
              <div className="min-w-0 flex-1">
                <h3 className="font-bold text-xs sm:text-sm break-words whitespace-normal leading-snug">{previewFile.name}</h3>
                <p className="text-[11px] text-slate-400 break-words whitespace-normal mt-0.5">
                  📂 {previewFile.folder} • {previewFile.size}
                </p>
              </div>
            </div>

            <div className="flex items-center gap-2 shrink-0">
              <button
                type="button"
                onClick={() => handleDownloadFile(previewFile)}
                className="px-3 py-1.5 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-bold transition flex items-center gap-1.5"
              >
                <Download className="w-3.5 h-3.5" />
                <span>تنزيل الملف</span>
              </button>
              <button
                type="button"
                onClick={() => setPreviewFile(null)}
                className="p-2 rounded-xl bg-slate-800 hover:bg-rose-600 text-white transition"
                title="إغلاق المعاينة"
              >
                <X className="w-5 h-5" />
              </button>
            </div>
          </div>

          {/* محتوى المعاينة الوسطي */}
          <div
            className="flex-1 flex items-center justify-center overflow-auto my-3 rounded-2xl bg-slate-950/60 border border-slate-800 p-2 sm:p-4"
            onClick={(e) => {
              if (e.target === e.currentTarget) setPreviewFile(null);
            }}
          >
            {previewFile.type === 'image' && (
              <img
                src={`/api/drive/stream?id=${encodeURIComponent(previewFile.id)}`}
                alt={previewFile.name}
                className="max-h-[78vh] max-w-full object-contain rounded-xl shadow-2xl"
              />
            )}

            {previewFile.type === 'pdf' && (
              <iframe
                src={`/api/drive/stream?id=${encodeURIComponent(previewFile.id)}`}
                title={previewFile.name}
                className="w-full h-[78vh] rounded-xl bg-white border-0"
              />
            )}

            {previewFile.type === 'video' && (
              <video
                src={`/api/drive/stream?id=${encodeURIComponent(previewFile.id)}`}
                controls
                autoPlay
                className="max-h-[78vh] max-w-full rounded-xl shadow-2xl bg-black"
              />
            )}

            {previewFile.type === 'audio' && (
              <div className="bg-slate-900 p-8 rounded-3xl border border-slate-700 text-center space-y-4 max-w-md w-full">
                <div className="w-16 h-16 rounded-2xl bg-pink-500/20 text-pink-400 flex items-center justify-center mx-auto">
                  <Music className="w-8 h-8" />
                </div>
                <h4 className="text-white font-bold text-sm">{previewFile.name}</h4>
                <audio
                  src={`/api/drive/stream?id=${encodeURIComponent(previewFile.id)}`}
                  controls
                  autoPlay
                  className="w-full"
                />
              </div>
            )}
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
