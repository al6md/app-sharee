'use client';

import { useState, useEffect, useRef, useMemo } from 'react';
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
  Move,
  LayoutGrid,
  List,
  Unlock
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
  const [showStats, setShowStats] = useState(false);
  const [viewMode, setViewMode] = useState<'LIST' | 'GRID'>('LIST');

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

  const loadData = async (isSilent: boolean | any = false, forceRefresh: boolean = false) => {
    const silent = typeof isSilent === 'boolean' ? isSilent : false;
    try {
      if (!silent) {
        setLoading(true);
      }

      const refreshParam = forceRefresh ? '&refresh=1' : '';
      const res = await fetch(`/api/drive/files?t=${Date.now()}${refreshParam}`, {
        cache: 'no-store',
        headers: {
          'Pragma': 'no-cache',
          'Cache-Control': 'no-cache'
        }
      });
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
      if (!silent) {
        setLoading(false);
      }
    }
  };

  useEffect(() => {
    loadData(false);

    // 1. مزامنة فائقة السرعة مع جسر تطبيق الحاسوب المحلي (فقط عند العمل على بروتوكول HTTP لتفادي Mixed Content)
    const isHttps = typeof window !== 'undefined' && window.location.protocol === 'https:';
    let lastKnownBridgeSync = 0;
    let bridgeInterval: any = null;

    if (!isHttps) {
      bridgeInterval = setInterval(async () => {
        try {
          const bridgeRes = await fetch('http://127.0.0.1:18290/status', {
            method: 'GET',
            mode: 'cors',
            cache: 'no-store',
            signal: AbortSignal.timeout(1000),
          });
          if (bridgeRes.ok) {
            const info = await bridgeRes.json();
            const bridgeTs = Number(info.last_sync_time || 0);
            if (bridgeTs > 0 && bridgeTs > lastKnownBridgeSync) {
              if (lastKnownBridgeSync !== 0) {
                // تم حفظ ورفع تعديلات من تطبيق الحاسوب فورياً!
                loadData(true);
              }
              lastKnownBridgeSync = bridgeTs;
            }
          }
        } catch {
          // الجسر المحلي غير متاح
        }
      }, 2500);
    }

    // 2. فحص سحابي دوري هادئ لمزامنة تعديلات المستخدمين الآخرين (كل 10 ثوانٍ لمنع أي ثقل في التصفح)
    const cloudInterval = setInterval(() => {
      if (typeof document !== 'undefined' && document.visibilityState === 'visible') {
        loadData(true);
      }
    }, 10000);

    // 3. تحديث فوري لحظة الرجوع إلى المتصفح مع كبح التكرار
    let lastFocusRefresh = 0;
    const onFocus = () => {
      const now = Date.now();
      if (now - lastFocusRefresh > 5000) {
        lastFocusRefresh = now;
        loadData(true);
      }
    };
    const onVisibilityChange = () => {
      if (typeof document !== 'undefined' && document.visibilityState === 'visible') {
        const now = Date.now();
        if (now - lastFocusRefresh > 5000) {
          lastFocusRefresh = now;
          loadData(true);
        }
      }
    };

    window.addEventListener('focus', onFocus);
    document.addEventListener('visibilitychange', onVisibilityChange);

    return () => {
      if (bridgeInterval) clearInterval(bridgeInterval);
      clearInterval(cloudInterval);
      window.removeEventListener('focus', onFocus);
      document.removeEventListener('visibilitychange', onVisibilityChange);
    };
  }, []);

  // إشعار تطبيق سطح المكتب المحلي بالمزامنة الفورية بعد أي عملية رفع أو تعديل عبر الويب
  const notifyLocalDesktopSync = () => {
    try {
      const isHttps = typeof window !== 'undefined' && window.location.protocol === 'https:';
      if (!isHttps) {
        fetch('http://127.0.0.1:18290/sync', { method: 'GET', mode: 'cors' }).catch(() => {});
      }
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

  // رابط بث مباشر مطلق ينتهي باسم الملف الحقيقي (تشترطه برامج Office لتحديد نوع المستند)
  const getFileDirectUrl = async (file: FileItem): Promise<string> => {
    const origin = typeof window !== 'undefined' ? window.location.origin : '';
    return `${origin}/api/drive/file/${encodeURIComponent(file.id)}/${encodeURIComponent(file.name)}`;
  };

  // 1. فتح المستند في البرنامج الأصلي أو عرض وسائط المعاينة (صور وفيديو وصوت)
  const handleOpenFile = async (file: FileItem) => {
    if (!canDownloadFolder(file.folder)) {
      alert(`⛔ عذراً، صلاحية فتح وتنزيل الملفات معطلة لقسم "${file.department}" من قِبل الإدارة.`);
      return;
    }

    // للوسائط فقط (صور، فيديو، صوت)، فتح عارض الوسائط المدمج
    if (['image', 'video', 'audio'].includes(file.type)) {
      setPreviewFile(file);
      return;
    }

    // لكافة المستندات والملفات الأخرى (Word, Excel, Access, PowerPoint, PDF... إلخ):
    // تشغيل فوري في البرنامج الأصلي على جهاز المستخدم بدون فتح أي نوافذ أو خانات زائدة
    await openNativeFile(file);
  };

  // تنزيل ملف عبر رابط مخفي (يتحول لملف في مجلد التنزيلات)
  const triggerBrowserDownload = (url: string, name: string) => {
    const link = document.createElement('a');
    link.href = url;
    link.download = name;
    link.style.display = 'none';
    document.body.appendChild(link);
    link.click();
    setTimeout(() => {
      try { document.body.removeChild(link); } catch {}
    }, 1500);
  };

  // إطلاق بروتوكول برنامج خارجي (ms-word ...) مع كشف عدم الاستجابة: إذا لم تفقد الصفحة التركيز خلال 3 ثوانٍ
  // فهذا يعني أن البرنامج لم يُفتح فعلياً، فنُبلغ المستخدم بدل رسالة نجاح كاذبة.
  const launchExternalProtocol = (uri: string, onNoResponse: () => void) => {
    let handled = false;
    const markHandled = () => { handled = true; };
    const onVisibility = () => { if (document.hidden) markHandled(); };
    window.addEventListener('blur', markHandled, { once: true });
    document.addEventListener('visibilitychange', onVisibility);

    const link = document.createElement('a');
    link.href = uri;
    link.style.display = 'none';
    document.body.appendChild(link);
    link.click();
    setTimeout(() => {
      try { document.body.removeChild(link); } catch {}
    }, 500);

    setTimeout(() => {
      window.removeEventListener('blur', markHandled);
      document.removeEventListener('visibilitychange', onVisibility);
      if (!handled) onNoResponse();
    }, 3000);
  };

  // فتح الملف في برنامجه الأصلي على جهاز المستخدم (بدون أي تطبيق مساعد)
  const openNativeFile = async (file: FileItem) => {
    const fileUrl = await getFileDirectUrl(file);
    const downloadUrl = `${fileUrl}?download=1`;
    const ext = file.name.split('.').pop()?.toLowerCase() || '';

    // الهواتف المحمولة
    const isMobile = typeof navigator !== 'undefined' && /Android|iPhone|iPad|iPod/i.test(navigator.userAgent);
    if (isMobile) {
      if (['word', 'excel'].includes(file.type)) {
        setSelectedMobileFile(file);
        handleOpenInMobileApp(file);
      } else {
        window.open(fileUrl, '_blank');
      }
      return;
    }

    // بروتوكولات Microsoft Office الرسمية المثبتة مع Office في ويندوز
    const OFFICE_PROTOCOLS: Record<string, [string, string]> = {
      docx: ['ms-word', 'Word'], doc: ['ms-word', 'Word'], docm: ['ms-word', 'Word'], dotx: ['ms-word', 'Word'], rtf: ['ms-word', 'Word'],
      xlsx: ['ms-excel', 'Excel'], xls: ['ms-excel', 'Excel'], xlsm: ['ms-excel', 'Excel'], xltx: ['ms-excel', 'Excel'], csv: ['ms-excel', 'Excel'],
      pptx: ['ms-powerpoint', 'PowerPoint'], ppt: ['ms-powerpoint', 'PowerPoint'], pptm: ['ms-powerpoint', 'PowerPoint'],
      accdb: ['ms-access', 'Access'], mdb: ['ms-access', 'Access'],
    };
    const entry = OFFICE_PROTOCOLS[ext];

    if (entry) {
      const [scheme, appName] = entry;
      setToastMessage({ text: `⏳ جاري فتح "${file.name}" في ${appName}...`, type: 'info' });
      launchExternalProtocol(`${scheme}:ofe|u|${fileUrl}`, () => {
        setToastMessage({
          text: `⚠️ لم يستجب ${appName}. تم تنزيل نسخة من الملف بدلاً من ذلك، افتحها من مجلد التنزيلات.`,
          type: 'error'
        });
        triggerBrowserDownload(downloadUrl, file.name);
      });
      return;
    }

    // باقي الأنواع (PDF وغيرها): تنزيل مباشر ليفتحه المتصفح/النظام بالبرنامج الافتراضي
    setToastMessage({
      text: `📥 جاري تنزيل "${file.name}" لفتحه في البرنامج الافتراضي...`,
      type: 'info'
    });
    triggerBrowserDownload(downloadUrl, file.name);
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

    const downloadUrl = `/api/drive/stream?id=${encodeURIComponent(file.id)}&download=1`;

    // للملفات الكبيرة (أكبر من 30 ميجابايت وخاصة قواعد بيانات Access):
    // استخدام التنزيل المباشر للمتصفح لمنع حشو ذاكرة الرام وضمان أقصى سرعة ممكنة
    if ((file.rawSize || 0) > 30 * 1024 * 1024) {
      setToastMessage({
        text: `📥 جاري تنزيل "${file.name}" مباشرة عبر المتصفح...`,
        type: 'info'
      });
      const a = document.createElement('a');
      a.href = downloadUrl;
      a.download = file.name;
      document.body.appendChild(a);
      a.click();
      a.remove();
      return;
    }

    transferAbortedRef.current = false;
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
      // في حال فشل XHR لأي سبب، استخدام التنزيل المباشر كبديل فوري موثوق 100%
      const a = document.createElement('a');
      a.href = downloadUrl;
      a.download = file.name;
      document.body.appendChild(a);
      a.click();
      a.remove();
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

  // تصفية وحسابات الذاكرة السريعة (Memoized) لتسريع التنقل وجعله فورياً دون أي بطء أو تجميد
  const visibleDepartments = useMemo(() => {
    return departments.filter((d) => canViewFolder(d));
  }, [departments, permissionsMap]);

  const activeFiles = useMemo(() => {
    return files.filter(
      (f) => !f.isDeleted && canViewFolder(f.department) && isDeptUnlocked(f.department)
    );
  }, [files, permissionsMap, unlockedDepts]);

  const trashFiles = useMemo(() => {
    return files.filter(
      (f) => f.isDeleted && canViewFolder(f.department) && isDeptUnlocked(f.department)
    );
  }, [files, permissionsMap, unlockedDepts]);

  const deptCountsMap = useMemo(() => {
    const map = new Map<string, number>();
    for (const f of files) {
      if (f.isDeleted) continue;
      const dept = f.department || (f.folder ? String(f.folder).split('/')[0] : '');
      if (dept) map.set(dept, (map.get(dept) || 0) + 1);
    }
    return map;
  }, [files]);

  const activeBrowsePath = currentFolder || (selectedDept !== '__ALL__' ? selectedDept : '');

  const visibleSubfolders = useMemo(() => {
    if (activeTab !== 'ACTIVE' || searchTerm.trim()) return [];
    return allFolders.filter(
      (folder) =>
        folder.parentPath === activeBrowsePath &&
        canViewFolder(folder.department) &&
        isDeptUnlocked(folder.department)
    );
  }, [activeTab, searchTerm, allFolders, activeBrowsePath, permissionsMap, unlockedDepts]);

  // خريطة سريعة لعدد الملفات والمجلدات الفرعية لكل مجلد بحساب O(N) مرة واحدة فقط بدلاً من إعادة التكرار في كل بطاقة
  const { folderFilesCountMap, folderChildsCountMap } = useMemo(() => {
    const fileCounts = new Map<string, number>();
    const childCounts = new Map<string, number>();

    for (const f of activeFiles) {
      const parts = (f.folder || '').split('/');
      let curr = '';
      for (let i = 0; i < parts.length; i++) {
        curr = curr ? `${curr}/${parts[i]}` : parts[i];
        fileCounts.set(curr, (fileCounts.get(curr) || 0) + 1);
      }
    }

    for (const cf of allFolders) {
      if (cf.parentPath) {
        childCounts.set(cf.parentPath, (childCounts.get(cf.parentPath) || 0) + 1);
      }
    }

    return { folderFilesCountMap: fileCounts, folderChildsCountMap: childCounts };
  }, [activeFiles, allFolders]);

  const displayedList = useMemo(() => {
    const targetFiles = activeTab === 'ACTIVE' ? activeFiles : trashFiles;
    const cleanSearch = searchTerm.trim().toLowerCase();

    return targetFiles.filter((f) => {
      const matchSearch =
        !cleanSearch ||
        f.name.toLowerCase().includes(cleanSearch) ||
        f.folder.toLowerCase().includes(cleanSearch);

      const matchType =
        filterType === 'ALL' ||
        f.type.toUpperCase() === filterType ||
        (filterType === 'OTHER' && ['file', 'video', 'audio', 'archive'].includes(f.type));

      if (cleanSearch) {
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
  }, [activeTab, activeFiles, trashFiles, searchTerm, filterType, selectedDept, currentFolder, visibleSubfolders.length]);

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

  // إحصائيات المستندات والمساحة التخزينية الإجمالية ولكل نوع مع useMemo
  const scopeFiles = useMemo(() => {
    if (activeTab === 'TRASH') return trashFiles;
    if (currentFolder) {
      return activeFiles.filter((f) => f.folder === currentFolder || f.folder.startsWith(currentFolder + '/'));
    }
    if (selectedDept === '__ALL__') return activeFiles;
    return activeFiles.filter(
      (f) => f.department === selectedDept || f.folder === selectedDept || f.folder.startsWith(selectedDept + '/')
    );
  }, [activeTab, trashFiles, currentFolder, selectedDept, activeFiles]);

  const stats = useMemo(() => {
    let totalRawSize = 0;
    let wordCount = 0, wordSize = 0;
    let excelCount = 0, excelSize = 0;
    let accessCount = 0, accessSize = 0;
    let pdfCount = 0, pdfSize = 0;
    let imageCount = 0, imageSize = 0;
    let otherCount = 0, otherSize = 0;

    for (const f of scopeFiles) {
      const sz = f.rawSize || 0;
      totalRawSize += sz;
      if (f.type === 'word') { wordCount++; wordSize += sz; }
      else if (f.type === 'excel') { excelCount++; excelSize += sz; }
      else if (f.type === 'access') { accessCount++; accessSize += sz; }
      else if (f.type === 'pdf') { pdfCount++; pdfSize += sz; }
      else if (f.type === 'image') { imageCount++; imageSize += sz; }
      else { otherCount++; otherSize += sz; }
    }

    const foldersCount =
      selectedDept === '__ALL__'
        ? allFolders.length
        : allFolders.filter((f) => f.department === selectedDept || f.path.startsWith(selectedDept + '/')).length;

    return {
      totalCount: scopeFiles.length,
      totalRawSize,
      word: { count: wordCount, size: wordSize },
      excel: { count: excelCount, size: excelSize },
      access: { count: accessCount, size: accessSize },
      pdf: { count: pdfCount, size: pdfSize },
      image: { count: imageCount, size: imageSize },
      other: { count: otherCount, size: otherSize },
      foldersCount,
    };
  }, [scopeFiles, selectedDept, allFolders]);

  const getFileBadge = (type: string) => {
    switch (type) {
      case 'word':
        return <span className="bg-[#2B579A]/10 text-[#2B579A] border border-[#2B579A]/25 text-[11px] font-semibold px-2 py-0.5 rounded-md">Word</span>;
      case 'excel':
        return <span className="bg-[#217346]/10 text-[#217346] border border-[#217346]/25 text-[11px] font-semibold px-2 py-0.5 rounded-md">Excel</span>;
      case 'access':
        return <span className="bg-[#A4373A]/10 text-[#A4373A] border border-[#A4373A]/25 text-[11px] font-semibold px-2 py-0.5 rounded-md">Access</span>;
      case 'pdf':
        return <span className="bg-[#E5252A]/10 text-[#E5252A] border border-[#E5252A]/25 text-[11px] font-semibold px-2 py-0.5 rounded-md">PDF</span>;
      case 'image':
        return <span className="bg-purple-50 text-purple-700 border border-purple-200 text-[11px] font-semibold px-2 py-0.5 rounded-md">صورة</span>;
      case 'video':
        return <span className="bg-indigo-50 text-indigo-700 border border-indigo-200 text-[11px] font-semibold px-2 py-0.5 rounded-md">فيديو</span>;
      case 'audio':
        return <span className="bg-pink-50 text-pink-700 border border-pink-200 text-[11px] font-semibold px-2 py-0.5 rounded-md">صوت</span>;
      case 'archive':
        return <span className="bg-amber-50 text-amber-800 border border-amber-200 text-[11px] font-semibold px-2 py-0.5 rounded-md">أرشيف</span>;
      default:
        return <span className="bg-slate-100 text-[#667085] border border-[#E4E7EC] text-[11px] font-semibold px-2 py-0.5 rounded-md">ملف</span>;
    }
  };

  const getFileIcon = (type: string, size: 'sm' | 'md' | 'lg' = 'md') => {
    const boxClass =
      size === 'lg'
        ? 'w-11 h-11 rounded-xl text-xs'
        : size === 'sm'
        ? 'w-8 h-8 rounded-lg text-[10px]'
        : 'w-10 h-10 rounded-xl text-[11px]';
    const iconSize = size === 'lg' ? 'w-5 h-5' : 'w-4 h-4';

    switch (type) {
      case 'word':
        return (
          <div className={`${boxClass} bg-[#2B579A] text-white font-bold flex flex-col items-center justify-center shrink-0 select-none`} title="Microsoft Word">
            <span className="leading-none font-black tracking-tighter">W</span>
          </div>
        );
      case 'excel':
        return (
          <div className={`${boxClass} bg-[#217346] text-white font-bold flex flex-col items-center justify-center shrink-0 select-none`} title="Microsoft Excel">
            <span className="leading-none font-black tracking-tighter">X</span>
          </div>
        );
      case 'access':
        return (
          <div className={`${boxClass} bg-[#A4373A] text-white font-bold flex flex-col items-center justify-center shrink-0 select-none`} title="Microsoft Access">
            <span className="leading-none font-black tracking-tighter">A</span>
          </div>
        );
      case 'pdf':
        return (
          <div className={`${boxClass} bg-[#E5252A] text-white font-bold flex flex-col items-center justify-center shrink-0 select-none`} title="وثيقة PDF">
            <span className="leading-none font-black tracking-tighter text-[10px]">PDF</span>
          </div>
        );
      case 'image':
        return (
          <div className={`${boxClass} bg-purple-600 text-white flex items-center justify-center shrink-0`} title="صورة">
            <Camera className={iconSize} />
          </div>
        );
      case 'video':
        return (
          <div className={`${boxClass} bg-indigo-600 text-white flex items-center justify-center shrink-0`} title="فيديو">
            <Film className={iconSize} />
          </div>
        );
      case 'audio':
        return (
          <div className={`${boxClass} bg-pink-600 text-white flex items-center justify-center shrink-0`} title="ملف صوتي">
            <Music className={iconSize} />
          </div>
        );
      case 'archive':
        return (
          <div className={`${boxClass} bg-amber-600 text-white flex items-center justify-center shrink-0`} title="أرشيف مضغوط">
            <Archive className={iconSize} />
          </div>
        );
      default:
        return (
          <div className={`${boxClass} bg-slate-600 text-white flex items-center justify-center shrink-0`} title="ملف عام">
            <FileCode className={iconSize} />
          </div>
        );
    }
  };

  return (
    <div
      className="p-4 sm:p-6 md:p-8 space-y-4 max-w-[1400px] mx-auto w-full relative"
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
      {/* شاشة السحب والإفلات التفاعلية */}
      {isDraggingOver && (
        <div className="fixed inset-0 z-50 bg-[#14372e]/90 flex flex-col items-center justify-center p-6 text-white border-2 border-dashed border-[#c59b27] m-4 rounded-2xl pointer-events-none" dir="rtl">
          <div className="bg-white/10 p-5 rounded-2xl mb-4 border border-white/20">
            <UploadCloud className="w-12 h-12 text-[#ecd58a]" />
          </div>
          <h3 className="text-xl font-bold mb-1 text-white">
            أفلت الملفات أو المجلدات هنا للرفع المباشر
          </h3>
          <p className="text-slate-200 text-sm max-w-md text-center">
            سيتم رفعها إلى القسم النشط ومزامنتها مع كافة أجهزة الغرفة.
          </p>
        </div>
      )}

      {/* 1. الترويسة الرئيسية النظيفة */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 bg-white p-5 rounded-xl border border-[#E4E7EC]">
        <div className="min-w-0">
          <div className="flex items-center gap-2.5 flex-wrap">
            <h2 className="text-xl sm:text-2xl font-bold text-[#1B1F24] break-words whitespace-normal">
              {selectedDept === '__ALL__' ? 'كافة المستندات والأقسام' : selectedDept}
            </h2>
            <span className="text-xs bg-[#F7F8FA] text-[#667085] font-semibold px-2.5 py-1 rounded-md border border-[#E4E7EC] shrink-0">
              {displayedList.length} ملف
            </span>
          </div>
          <p className="text-[13px] text-[#667085] mt-1">
            {currentFolder ? `المسار الحالي: ${currentFolder}` : 'مزامنة سحابية مباشرة مع أجهزة الحاسوب في الغرفة'}
          </p>
        </div>

        {/* أزرار الإجراءات الرئيسية */}
        <div className="flex items-center gap-2 flex-wrap">
          {canUploadFolder(activeBrowsePath) && (
            <>
              <button
                onClick={() => fileInputRef.current?.click()}
                disabled={actionLoading}
                className="flex items-center gap-2 bg-[#14372e] hover:bg-[#1b473b] text-white text-xs font-semibold h-10 px-4 rounded-lg transition shrink-0"
                title="رفع ملفات متعددة"
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

              <button
                onClick={() => folderInputRef.current?.click()}
                disabled={actionLoading}
                className="flex items-center gap-1.5 bg-white hover:bg-[#F7F8FA] text-[#1B1F24] text-xs font-semibold h-10 px-3.5 rounded-lg transition border border-[#E4E7EC] shrink-0"
                title="رفع مجلد كامل بمحتوياته"
              >
                <FolderOpen className="w-4 h-4 text-[#14372e]" />
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

              <button
                onClick={() => cameraInputRef.current?.click()}
                disabled={actionLoading}
                className="flex items-center gap-1.5 bg-white hover:bg-[#F7F8FA] text-[#1B1F24] text-xs font-semibold h-10 px-3.5 rounded-lg transition border border-[#E4E7EC] shrink-0"
                title="تصوير كتاب رسمي بالكاميرا"
              >
                <Camera className="w-4 h-4 text-[#c59b27]" />
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
            </>
          )}

          <input 
            type="file" 
            ref={updateFileInputRef} 
            className="hidden" 
            onChange={handleUpdateFile} 
          />

          {canCreateSubFolder(activeBrowsePath) && (
            <button
              onClick={() => setShowNewFolderModal(true)}
              className="flex items-center gap-1.5 bg-white hover:bg-[#F7F8FA] text-[#1B1F24] text-xs font-semibold h-10 px-3.5 rounded-lg transition border border-[#E4E7EC] shrink-0"
              title="إنشاء مجلد فرعي جديد"
            >
              <FolderPlus className="w-4 h-4 text-[#14372e]" />
              <span>مجلد جديد</span>
            </button>
          )}

          <button
            onClick={() => setShowStats(!showStats)}
            className={`flex items-center gap-1.5 h-10 px-3 rounded-lg text-xs font-semibold transition border shrink-0 ${
              showStats 
                ? 'bg-[#14372e] text-white border-[#14372e]' 
                : 'bg-white hover:bg-[#F7F8FA] text-[#667085] border-[#E4E7EC]'
            }`}
            title="إظهار أو إخفاء ملخص الإحصائيات"
          >
            <BarChart3 className="w-4 h-4" />
            <span className="hidden sm:inline">الإحصائيات</span>
          </button>

          <button
            onClick={() => loadData()}
            disabled={loading}
            className="h-10 w-10 flex items-center justify-center bg-white hover:bg-[#F7F8FA] text-[#667085] hover:text-[#1B1F24] rounded-lg border border-[#E4E7EC] transition"
            title="تحديث الملفات"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin text-[#14372e]' : ''}`} />
          </button>
        </div>
      </div>

      {/* 1.5. ملخص الإحصائيات (يظهر عند الطلب فقط لمنع الازدحام) */}
      {showStats && (
        <div className="bg-white rounded-xl border border-[#E4E7EC] p-4 space-y-3">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-[#E4E7EC] pb-3">
            <div className="flex items-center gap-2">
              <BarChart3 className="w-4 h-4 text-[#14372e]" />
              <h3 className="text-sm font-bold text-[#1B1F24]">
                ملخص أنواع المستندات والمساحة التخزينية
              </h3>
            </div>
            <div className="flex items-center gap-2 text-xs text-[#667085]">
              <span>إجمالي الحجم: <strong className="text-[#1B1F24] font-mono">{formatSize(stats.totalRawSize)}</strong></span>
              <span>•</span>
              <span>العدد: <strong className="text-[#1B1F24] font-mono">{stats.totalCount}</strong></span>
            </div>
          </div>

          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-2.5">
            {[
              { key: 'ALL', label: 'الكل', count: stats.totalCount, size: stats.totalRawSize, color: '#14372e' },
              { key: 'WORD', label: 'Word', count: stats.word.count, size: stats.word.size, color: '#2B579A' },
              { key: 'EXCEL', label: 'Excel', count: stats.excel.count, size: stats.excel.size, color: '#217346' },
              { key: 'ACCESS', label: 'Access', count: stats.access.count, size: stats.access.size, color: '#A4373A' },
              { key: 'PDF', label: 'PDF', count: stats.pdf.count, size: stats.pdf.size, color: '#E5252A' },
              { key: 'IMAGE', label: 'صور', count: stats.image.count, size: stats.image.size, color: '#7C3AED' },
            ].map((item) => (
              <button
                key={item.key}
                type="button"
                onClick={() => setFilterType(filterType === item.key ? 'ALL' : item.key)}
                className={`p-3 rounded-lg border text-right transition flex flex-col justify-between ${
                  filterType === item.key
                    ? 'bg-[#14372e] text-white border-[#14372e]'
                    : 'bg-[#F7F8FA] hover:bg-white text-[#1B1F24] border-[#E4E7EC]'
                }`}
              >
                <div className="flex items-center justify-between w-full">
                  <span className="text-xs font-semibold">{item.label}</span>
                  <span
                    className="w-2 h-2 rounded-full"
                    style={{ backgroundColor: filterType === item.key ? '#ffffff' : item.color }}
                  />
                </div>
                <div className="mt-2">
                  <div className="text-lg font-bold font-mono leading-none">{item.count}</div>
                  <div className={`text-[11px] mt-1 font-mono ${filterType === item.key ? 'text-slate-200' : 'text-[#667085]'}`}>
                    {formatSize(item.size)}
                  </div>
                </div>
              </button>
            ))}
          </div>
        </div>
      )}

      {/* 2. شريط الأقسام الأفقية + التبديل بين المستندات النشطة وسلة المحذوفات */}
      <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-3 border-b border-[#E4E7EC] pb-3">
        {/* شرائح الأقسام */}
        <div className="flex items-center gap-1.5 flex-wrap">
          <button
            onClick={() => {
              setActiveTab('ACTIVE');
              handleSelectDepartment('__ALL__', null);
            }}
            className={`px-3.5 py-2 rounded-lg text-xs font-semibold transition border ${
              activeTab === 'ACTIVE' && selectedDept === '__ALL__'
                ? 'bg-[#14372e] text-white border-[#14372e]'
                : 'bg-white text-[#1B1F24] border-[#E4E7EC] hover:bg-[#F7F8FA]'
            }`}
          >
            كافة الأقسام ({activeFiles.length})
          </button>

          {visibleDepartments.map((dept) => {
            const count = deptCountsMap.get(dept) || 0;
            const isPinLocked = isDeptPinProtected(dept) && !isDeptUnlocked(dept);
            const isSelected = activeTab === 'ACTIVE' && selectedDept === dept;
            return (
              <button
                key={dept}
                onClick={() => {
                  setActiveTab('ACTIVE');
                  handleSelectDepartment(dept, null);
                }}
                className={`px-3.5 py-2 rounded-lg text-xs font-semibold transition border flex items-center gap-1.5 ${
                  isSelected
                    ? 'bg-[#14372e] text-white border-[#14372e]'
                    : 'bg-white text-[#1B1F24] border-[#E4E7EC] hover:bg-[#F7F8FA]'
                }`}
              >
                {isPinLocked ? (
                  <Lock className="w-3.5 h-3.5 text-amber-600" />
                ) : isDeptPinProtected(dept) ? (
                  <Unlock className="w-3.5 h-3.5 text-emerald-600" />
                ) : (
                  <Folder className={`w-3.5 h-3.5 ${isSelected ? 'text-[#ecd58a]' : 'text-[#14372e]'}`} />
                )}
                <span>{dept}</span>
                <span className={`text-[11px] px-1.5 py-0.2 rounded font-mono ${isSelected ? 'bg-white/20 text-white' : 'bg-[#F7F8FA] text-[#667085]'}`}>
                  {count}
                </span>
              </button>
            );
          })}
        </div>

        {/* زر سلة المحذوفات وأزرار إدارتها */}
        <div className="flex items-center gap-2 shrink-0">
          {activeTab === 'TRASH' && trashFiles.length > 0 && (
            <>
              <button
                onClick={handleRestoreAll}
                className="flex items-center gap-1.5 px-3 py-2 bg-emerald-600 hover:bg-emerald-700 text-white rounded-lg text-xs font-semibold transition"
              >
                <RotateCcw className="w-3.5 h-3.5" />
                <span>استرجاع الكل</span>
              </button>
              <button
                onClick={handleEmptyTrash}
                className="flex items-center gap-1.5 px-3 py-2 bg-rose-50 hover:bg-rose-100 text-rose-700 border border-rose-200 rounded-lg text-xs font-semibold transition"
              >
                <Trash2 className="w-3.5 h-3.5" />
                <span>إفراغ السلة</span>
              </button>
            </>
          )}

          <button
            onClick={() => setActiveTab(activeTab === 'TRASH' ? 'ACTIVE' : 'TRASH')}
            className={`flex items-center gap-1.5 px-3.5 py-2 text-xs font-semibold rounded-lg border transition ${
              activeTab === 'TRASH'
                ? 'bg-[#F04438] text-white border-[#F04438]'
                : 'bg-white text-[#667085] hover:text-[#1B1F24] border-[#E4E7EC]'
            }`}
          >
            <Trash2 className="w-3.5 h-3.5" />
            <span>المحذوفات ({trashFiles.length})</span>
          </button>
        </div>
      </div>

      {/* 3. شريط البحث، التصفية بالنوع، ومفتاح تبديل طريقة العرض (قائمة / شبكة) */}
      <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-3 bg-white p-3 rounded-xl border border-[#E4E7EC]">
        <div className="flex items-center gap-2 flex-1 min-w-0">
          <div className="relative flex-1 max-w-md">
            <Search className="w-4 h-4 text-[#667085] absolute right-3.5 top-3" />
            <input
              type="text"
              placeholder="ابحث بالاسم الكامل للملف أو القسم..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="w-full pl-8 pr-10 h-10 text-[13px] bg-[#F7F8FA] border border-[#E4E7EC] rounded-lg focus:outline-none focus:border-[#14372e] focus:bg-white text-[#1B1F24]"
            />
            {searchTerm && (
              <button
                type="button"
                onClick={() => setSearchTerm('')}
                className="absolute left-2.5 top-2.5 text-[#667085] hover:text-[#1B1F24]"
              >
                <X className="w-4 h-4" />
              </button>
            )}
          </div>

          {(displayedList.length > 0 || visibleSubfolders.length > 0) && (
            <button
              type="button"
              onClick={toggleSelectAllDisplayed}
              className={`h-10 px-3 rounded-lg text-xs font-semibold transition whitespace-nowrap flex items-center gap-1.5 border shrink-0 ${
                isAllDisplayedSelected
                  ? 'bg-[#14372e] text-white border-[#14372e]'
                  : 'bg-white text-[#1B1F24] border-[#E4E7EC] hover:bg-[#F7F8FA]'
              }`}
            >
              <Check className="w-3.5 h-3.5" />
              <span>{isAllDisplayedSelected ? 'إلغاء التحديد' : 'تحديد الكل'}</span>
            </button>
          )}
        </div>

        <div className="flex items-center justify-between lg:justify-end gap-2 flex-wrap">
          {/* فلاتر الأنواع */}
          <div className="flex items-center gap-1 overflow-x-auto">
            {[
              { tag: 'ALL', label: `الكل (${stats.totalCount})` },
              { tag: 'WORD', label: `Word (${stats.word.count})` },
              { tag: 'EXCEL', label: `Excel (${stats.excel.count})` },
              { tag: 'ACCESS', label: `Access (${stats.access.count})` },
              { tag: 'PDF', label: `PDF (${stats.pdf.count})` },
              { tag: 'IMAGE', label: `صور (${stats.image.count})` },
              { tag: 'OTHER', label: `أخرى (${stats.other.count})` },
            ].map((t) => (
              <button
                key={t.tag}
                onClick={() => setFilterType(t.tag)}
                className={`px-2.5 py-1.5 rounded-lg text-xs font-semibold transition whitespace-nowrap ${
                  filterType === t.tag
                    ? 'bg-[#14372e] text-white'
                    : 'bg-[#F7F8FA] text-[#667085] hover:text-[#1B1F24]'
                }`}
              >
                {t.label}
              </button>
            ))}
          </div>

          {/* زر تبديل طريقة العرض: قائمة تفصيلية أو شبكة بطاقات */}
          <div className="flex items-center bg-[#F7F8FA] p-1 rounded-lg border border-[#E4E7EC] shrink-0">
            <button
              type="button"
              onClick={() => setViewMode('LIST')}
              className={`flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-semibold transition ${
                viewMode === 'LIST'
                  ? 'bg-white text-[#14372e] shadow-2xs border border-[#E4E7EC]'
                  : 'text-[#667085] hover:text-[#1B1F24]'
              }`}
              title="عرض على شكل قائمة تفصيلية"
            >
              <List className="w-3.5 h-3.5" />
              <span>قائمة</span>
            </button>
            <button
              type="button"
              onClick={() => setViewMode('GRID')}
              className={`flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-semibold transition ${
                viewMode === 'GRID'
                  ? 'bg-white text-[#14372e] shadow-2xs border border-[#E4E7EC]'
                  : 'text-[#667085] hover:text-[#1B1F24]'
              }`}
              title="عرض على شكل شبكة بطاقات"
            >
              <LayoutGrid className="w-3.5 h-3.5" />
              <span>شبكة</span>
            </button>
          </div>
        </div>
      </div>

      {/* 4. شريط مسار المجلدات (Breadcrumb) والمجلدات الفرعية */}
      {activeTab === 'ACTIVE' && (currentFolder || visibleSubfolders.length > 0) && (
        <div className="bg-white rounded-xl border border-[#E4E7EC] p-4 space-y-3">
          <div className="flex items-center justify-between flex-wrap gap-2">
            <div className="flex items-center gap-1 flex-wrap text-xs font-semibold">
              <button
                onClick={() => {
                  setSelectedDept('__ALL__');
                  setCurrentFolder(null);
                }}
                className="text-[#667085] hover:text-[#14372e] px-2 py-1 rounded-md hover:bg-[#F7F8FA] transition"
              >
                كافة الأقسام
              </button>
              {activeBrowsePath &&
                activeBrowsePath.split('/').map((part, idx, arr) => {
                  const targetPath = arr.slice(0, idx + 1).join('/');
                  const isLast = idx === arr.length - 1;
                  return (
                    <div key={targetPath} className="flex items-center gap-1">
                      <ChevronLeft className="w-3.5 h-3.5 text-[#667085]" />
                      <button
                        onClick={() => {
                          setSelectedDept(arr[0]);
                          setCurrentFolder(idx === 0 ? null : targetPath);
                        }}
                        className={`px-2.5 py-1 rounded-md transition ${
                          isLast
                            ? 'bg-[#14372e] text-white'
                            : 'text-[#1B1F24] hover:bg-[#F7F8FA]'
                        }`}
                      >
                        {part}
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
                className="flex items-center gap-1.5 px-3 py-1.5 bg-[#F7F8FA] hover:bg-slate-200/70 text-[#1B1F24] rounded-lg border border-[#E4E7EC] text-xs font-semibold transition"
              >
                <ArrowRight className="w-3.5 h-3.5" />
                <span>رجوع للمجلد الأعلى</span>
              </button>
            )}
          </div>

          {/* شبكة المجلدات الفرعية بتصميم متناسق وعريض يمنع تكسير الكلمات نهائياً */}
          {visibleSubfolders.length > 0 && (
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3 pt-1">
              {visibleSubfolders.map((sub) => {
                const subFilesCount = folderFilesCountMap.get(sub.path) || 0;
                const childFoldersCount = folderChildsCountMap.get(sub.path) || 0;
                const isSubSelected = selectedFolderIds.includes(sub.id);
                return (
                  <div
                    key={sub.id}
                    onClick={() => handleSelectDepartment(sub.department, sub.path)}
                    className={`group cursor-pointer rounded-xl p-3 flex items-center justify-between gap-3 transition-all duration-150 border shadow-2xs hover:shadow-sm ${
                      isSubSelected
                        ? 'bg-[#14372e]/5 border-[#14372e] ring-1 ring-[#14372e]'
                        : 'bg-white hover:bg-[#FDFEFE] border-[#E4E7EC] hover:border-[#14372e]/60'
                    }`}
                  >
                    {/* قسم الأيقونة والتفاصيل على اليمين بتنسيق أفقي كامل */}
                    <div className="flex items-center gap-2.5 min-w-0 flex-1">
                      <input
                        type="checkbox"
                        checked={isSubSelected}
                        onClick={(e) => e.stopPropagation()}
                        onChange={() => toggleSelectFolder(sub.id)}
                        className="w-4 h-4 rounded accent-[#14372e] cursor-pointer shrink-0"
                        title="تحديد المجلد"
                      />
                      <div className="w-10 h-10 bg-emerald-50 text-[#14372e] rounded-xl flex items-center justify-center shrink-0 border border-emerald-100 group-hover:bg-[#14372e] group-hover:text-white transition-colors duration-150">
                        <Folder className="w-5 h-5 fill-current/20" />
                      </div>
                      <div className="min-w-0 flex-1">
                        <h4
                          className="font-bold text-[14px] text-[#1B1F24] group-hover:text-[#14372e] truncate transition-colors leading-tight"
                          title={sub.name}
                          dir="auto"
                        >
                          {sub.name}
                        </h4>
                        <div className="flex items-center gap-1.5 text-[11px] text-[#667085] mt-1 font-medium">
                          <span>{subFilesCount} ملف</span>
                          {childFoldersCount > 0 && (
                            <>
                              <span>•</span>
                              <span className="text-[#14372e]">{childFoldersCount} فرعي</span>
                            </>
                          )}
                        </div>
                      </div>
                    </div>

                    {/* أدوات الإجراءات السريعة على اليسار */}
                    <div className="flex items-center gap-0.5 shrink-0 opacity-80 group-hover:opacity-100 transition-opacity" onClick={(e) => e.stopPropagation()}>
                      {canMoveFolder(sub.path) && (
                        <button
                          onClick={() =>
                            openMoveDialog({
                              folderIds: [sub.id],
                              label: `المجلد: ${sub.name}`,
                              sourceDept: sub.department,
                            })
                          }
                          className="p-1.5 text-[#667085] hover:text-[#1B1F24] hover:bg-[#F2F4F7] rounded-md transition"
                          title="نقل المجلد"
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
                          className="p-1.5 text-[#667085] hover:text-[#14372e] hover:bg-emerald-50 rounded-md transition"
                          title="إعادة تسمية المجلد"
                        >
                          <Edit3 className="w-3.5 h-3.5" />
                        </button>
                      )}
                      {canDeleteFolder(sub.path) && (
                        <button
                          onClick={() => handleMoveFolderToTrash(sub)}
                          className="p-1.5 text-[#667085] hover:text-[#F04438] hover:bg-rose-50 rounded-md transition"
                          title="نقل للمحذوفات"
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

      {/* 5. عرض الملفات (الاسم الكامل دائماً + الأيقونات الواضحة + وضع القائمة أو الشبكة) */}
      {displayedList.length === 0 ? (
        visibleSubfolders.length === 0 ? (
          <div className="bg-white rounded-xl border border-[#E4E7EC] p-12 text-center flex flex-col items-center justify-center space-y-3">
            <div className="w-14 h-14 bg-[#F7F8FA] rounded-full text-[#667085] flex items-center justify-center border border-[#E4E7EC]">
              <Inbox className="w-7 h-7" />
            </div>
            <h4 className="text-[15px] font-semibold text-[#1B1F24]">لا توجد ملفات في هذا العرض</h4>
            <p className="text-[13px] text-[#667085] max-w-sm leading-relaxed">
              {activeTab === 'TRASH'
                ? 'سلة المحذوفات فارغة حالياً.'
                : 'يمكنك رفع ملفات جديدة أو إنشاء مجلد فرعي باستخدام الأزرار في الأعلى.'}
            </p>
          </div>
        ) : null
      ) : viewMode === 'GRID' ? (
        /* =========================================================
           ب) وضع الشبكة (Grid View) - بطاقات نظيفة بأيقونة بارزة واسم كامل
           ========================================================= */
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3.5">
          {displayedList.map((file) => {
            const isSelected = selectedFileIds.includes(file.id);
            return (
              <div
                key={file.id}
                className={`bg-white rounded-xl p-4 border flex flex-col justify-between gap-3 transition ${
                  isSelected
                    ? 'border-[#14372e] bg-[#14372e]/[0.02] ring-1 ring-[#14372e]'
                    : 'border-[#E4E7EC] hover:border-[#14372e]/60'
                }`}
              >
                {/* أعلى البطاقة: التحديد + الأيقونة الكبيرة + النوع */}
                <div className="space-y-3">
                  <div className="flex items-start justify-between gap-2">
                    <div className="flex items-center gap-2.5">
                      <input
                        type="checkbox"
                        checked={isSelected}
                        onChange={() => toggleSelectFile(file.id)}
                        className="w-4 h-4 rounded accent-[#14372e] cursor-pointer shrink-0"
                        title="تحديد الملف"
                      />
                      <div onClick={() => handleOpenFile(file)} className="cursor-pointer">
                        {getFileIcon(file.type, 'lg')}
                      </div>
                    </div>
                    <div className="flex items-center gap-1.5">
                      {getFileBadge(file.type)}
                    </div>
                  </div>

                  {/* الاسم الكامل للملف مع الامتداد دون أي اقتطاع */}
                  <div>
                    <h4
                      onClick={() => handleOpenFile(file)}
                      className="text-[15px] font-medium text-[#1B1F24] hover:text-[#14372e] break-words whitespace-normal leading-relaxed cursor-pointer transition"
                      title={file.name}
                    >
                      {file.name}
                    </h4>
                    <p className="text-[13px] text-[#667085] mt-1 break-words whitespace-normal">
                      {file.folder}
                    </p>
                  </div>
                </div>

                {/* أسفل البطاقة: الحجم والتاريخ + أزرار الإجراءات */}
                <div className="space-y-2.5 pt-2.5 border-t border-[#E4E7EC]">
                  <div className="flex items-center justify-between text-[13px] text-[#667085] font-mono">
                    <span>{file.size}</span>
                    <span>{file.lastModifiedAt}</span>
                  </div>

                  <div className="flex items-center justify-between gap-1.5">
                    <button
                      onClick={() => handleOpenFile(file)}
                      className="flex-1 h-9 flex items-center justify-center gap-1.5 bg-[#14372e] hover:bg-[#1b473b] text-white text-xs font-semibold px-3 rounded-lg transition"
                    >
                      <span>
                        {file.type === 'word'
                          ? 'فتح Word'
                          : file.type === 'excel'
                          ? 'فتح Excel'
                          : file.type === 'access'
                          ? 'فتح Access'
                          : file.type === 'pdf'
                          ? 'فتح PDF'
                          : ['image', 'video', 'audio'].includes(file.type)
                          ? 'معاينة'
                          : 'فتح'}
                      </span>
                    </button>

                    {activeTab === 'ACTIVE' && canEditFolder(file.folder) && ['word', 'excel', 'file', 'pdf'].includes(file.type) && (
                      <button
                        onClick={() => triggerUpdateFile(file)}
                        disabled={actionLoading}
                        className="h-9 px-2.5 bg-amber-50 hover:bg-amber-100 text-amber-900 border border-amber-200 text-xs font-semibold rounded-lg transition flex items-center gap-1 shrink-0"
                        title="رفع نسخة معدلة وحفظ التعديلات"
                      >
                        <UploadCloud className="w-3.5 h-3.5" />
                        <span>تحديث</span>
                      </button>
                    )}

                    {canDownloadFolder(file.folder) && (
                      <button
                        onClick={() => handleDownloadFile(file)}
                        className="h-9 w-9 flex items-center justify-center text-[#667085] hover:text-[#1B1F24] bg-[#F7F8FA] hover:bg-slate-200/60 rounded-lg border border-[#E4E7EC] transition shrink-0"
                        title="تنزيل الملف"
                      >
                        <Download className="w-4 h-4" />
                      </button>
                    )}

                    {activeTab === 'ACTIVE' ? (
                      <>
                        {canRenameFolder(file.folder) && (
                          <button
                            onClick={() => {
                              setItemToRename({ id: file.id, name: file.name });
                              setNewRenameValue(file.name);
                              setShowRenameModal(true);
                            }}
                            className="h-9 w-9 flex items-center justify-center text-[#667085] hover:text-[#14372e] bg-[#F7F8FA] hover:bg-slate-200/60 rounded-lg border border-[#E4E7EC] transition shrink-0"
                            title="تعديل الاسم"
                          >
                            <Edit3 className="w-4 h-4" />
                          </button>
                        )}
                        {canMoveFolder(file.folder) && (
                          <button
                            onClick={() =>
                              openMoveDialog({
                                fileIds: [file.id],
                                label: file.name,
                                sourceDept: file.department,
                              })
                            }
                            className="h-9 w-9 flex items-center justify-center text-[#667085] hover:text-[#1B1F24] bg-[#F7F8FA] hover:bg-slate-200/60 rounded-lg border border-[#E4E7EC] transition shrink-0"
                            title="نقل الملف"
                          >
                            <Move className="w-4 h-4" />
                          </button>
                        )}
                        {canDeleteFolder(file.folder) && (
                          <button
                            onClick={() => handleMoveToTrash(file)}
                            className="h-9 w-9 flex items-center justify-center text-[#667085] hover:text-[#F04438] bg-[#F7F8FA] hover:bg-rose-50 rounded-lg border border-[#E4E7EC] transition shrink-0"
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
                          className="h-9 px-2.5 text-emerald-700 bg-emerald-50 hover:bg-emerald-100 border border-emerald-200 rounded-lg transition font-semibold text-xs flex items-center gap-1"
                          title="استرجاع المستند"
                        >
                          <RotateCcw className="w-3.5 h-3.5" />
                          <span>استرجاع</span>
                        </button>
                        {canPermanentDeleteFolder(file.folder) && (
                          <button
                            onClick={() => handlePermanentDelete(file)}
                            className="h-9 w-9 flex items-center justify-center text-[#F04438] bg-rose-50 hover:bg-rose-100 border border-rose-200 rounded-lg transition shrink-0"
                            title="حذف نهائي"
                          >
                            <Trash2 className="w-4 h-4" />
                          </button>
                        )}
                      </>
                    )}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      ) : (
        /* =========================================================
           أ) وضع القائمة التفصيلية (List View - الافتراضي)
           ========================================================= */
        <>
          {/* عرض الجوال والشاشات الصغيرة */}
          <div className="grid grid-cols-1 gap-2.5 lg:hidden">
            {displayedList.map((file) => {
              const isSelected = selectedFileIds.includes(file.id);
              return (
                <div
                  key={file.id}
                  className={`bg-white rounded-xl p-4 border space-y-3 transition ${
                    isSelected
                      ? 'border-[#14372e] bg-[#14372e]/[0.02]'
                      : 'border-[#E4E7EC]'
                  }`}
                >
                  <div className="flex items-start gap-3">
                    <input
                      type="checkbox"
                      checked={isSelected}
                      onChange={() => toggleSelectFile(file.id)}
                      className="w-4 h-4 mt-2.5 rounded accent-[#14372e] cursor-pointer shrink-0"
                    />
                    <div onClick={() => handleOpenFile(file)} className="cursor-pointer shrink-0">
                      {getFileIcon(file.type, 'md')}
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="flex items-start justify-between gap-2">
                        <h4
                          onClick={() => handleOpenFile(file)}
                          className="text-[15px] font-medium text-[#1B1F24] break-words whitespace-normal leading-relaxed cursor-pointer hover:text-[#14372e]"
                        >
                          {file.name}
                        </h4>
                        <div className="shrink-0">{getFileBadge(file.type)}</div>
                      </div>
                      <div className="flex items-center gap-3 text-[13px] text-[#667085] mt-1 flex-wrap">
                        <span>{file.folder}</span>
                        <span>•</span>
                        <span className="font-mono">{file.size}</span>
                        <span>•</span>
                        <span className="font-mono">{file.lastModifiedAt}</span>
                      </div>
                    </div>
                  </div>

                  <div className="flex items-center justify-between border-t border-[#E4E7EC] pt-2.5 gap-1.5 flex-wrap">
                    <button
                      onClick={() => handleOpenFile(file)}
                      className="flex-1 min-w-[100px] h-9 flex items-center justify-center gap-1.5 bg-[#14372e] text-white text-xs font-semibold px-3 rounded-lg hover:bg-[#1a473b] transition"
                    >
                      <span>
                        {file.type === 'word'
                          ? 'فتح Word'
                          : file.type === 'excel'
                          ? 'فتح Excel'
                          : file.type === 'access'
                          ? 'فتح Access'
                          : ['image', 'pdf', 'video', 'audio'].includes(file.type)
                          ? 'معاينة'
                          : 'فتح المستند'}
                      </span>
                    </button>

                    {activeTab === 'ACTIVE' && canEditFolder(file.folder) && ['word', 'excel', 'file', 'pdf'].includes(file.type) && (
                      <button
                        onClick={() => triggerUpdateFile(file)}
                        disabled={actionLoading}
                        className="h-9 flex items-center justify-center gap-1 bg-amber-50 hover:bg-amber-100 text-amber-900 border border-amber-200 text-xs font-semibold px-3 rounded-lg transition shrink-0"
                      >
                        <UploadCloud className="w-3.5 h-3.5" />
                        <span>حفظ التعديلات</span>
                      </button>
                    )}

                    <button
                      onClick={() => handleOpenInMobileApp(file)}
                      className="h-9 w-9 flex items-center justify-center text-[#14372e] bg-[#F7F8FA] hover:bg-slate-200/60 border border-[#E4E7EC] rounded-lg transition"
                      title="فتح في تطبيقات الهاتف أو مشاركة"
                    >
                      <Smartphone className="w-4 h-4" />
                    </button>

                    {canDownloadFolder(file.folder) && (
                      <button
                        onClick={() => handleDownloadFile(file)}
                        className="h-9 w-9 flex items-center justify-center text-[#667085] hover:text-[#1B1F24] bg-[#F7F8FA] border border-[#E4E7EC] rounded-lg transition"
                        title="تنزيل"
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
                            className="h-9 w-9 flex items-center justify-center text-[#667085] bg-[#F7F8FA] border border-[#E4E7EC] rounded-lg transition"
                            title="نقل"
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
                            className="h-9 w-9 flex items-center justify-center text-[#667085] bg-[#F7F8FA] border border-[#E4E7EC] rounded-lg transition"
                            title="إعادة تسمية"
                          >
                            <Edit3 className="w-4 h-4" />
                          </button>
                        )}
                        {canDeleteFolder(file.folder) && (
                          <button
                            onClick={() => handleMoveToTrash(file)}
                            className="h-9 w-9 flex items-center justify-center text-[#F04438] bg-rose-50 border border-rose-200 rounded-lg transition"
                            title="حذف للسلة"
                          >
                            <Trash2 className="w-4 h-4" />
                          </button>
                        )}
                      </>
                    ) : (
                      <>
                        <button
                          onClick={() => handleRestoreFile(file)}
                          className="h-9 px-3 text-emerald-700 bg-emerald-50 border border-emerald-200 rounded-lg transition font-semibold text-xs flex items-center gap-1"
                        >
                          <RotateCcw className="w-3.5 h-3.5" />
                          <span>استرجاع</span>
                        </button>
                        {canPermanentDeleteFolder(file.folder) && (
                          <button
                            onClick={() => handlePermanentDelete(file)}
                            className="h-9 w-9 flex items-center justify-center text-[#F04438] bg-rose-50 border border-rose-200 rounded-lg transition"
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

          {/* جدول الشاشات الكبيرة النظيف (الاسم الكامل يأخذ أكبر مساحة + أيقونة واضحة) */}
          <div className="hidden lg:block bg-white rounded-xl border border-[#E4E7EC] overflow-x-auto">
            <table className="w-full text-right text-sm">
              <thead className="bg-[#F7F8FA] text-[#667085] text-xs font-semibold border-b border-[#E4E7EC]">
                <tr>
                  <th className="py-3.5 px-4 w-10 text-center">
                    <input
                      type="checkbox"
                      checked={isAllDisplayedSelected}
                      onChange={toggleSelectAllDisplayed}
                      className="w-4 h-4 rounded accent-[#14372e] cursor-pointer"
                      title="تحديد الكل"
                    />
                  </th>
                  <th className="py-3.5 px-4 min-w-[360px]">اسم الملف الكامل</th>
                  <th className="py-3.5 px-4 min-w-[150px]">القسم / المجلد</th>
                  <th className="py-3.5 px-4 whitespace-nowrap">الحجم</th>
                  <th className="py-3.5 px-4 whitespace-nowrap">آخر تعديل</th>
                  <th className="py-3.5 px-4 whitespace-nowrap">الحالة</th>
                  <th className="py-3.5 px-4 text-left whitespace-nowrap min-w-[260px]">الإجراءات</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[#E4E7EC]">
                {displayedList.map((file) => {
                  const isSelected = selectedFileIds.includes(file.id);
                  return (
                    <tr
                      key={file.id}
                      className={`group transition min-h-[56px] ${
                        isSelected ? 'bg-[#14372e]/[0.04]' : 'hover:bg-[#F7F8FA]/80'
                      }`}
                    >
                      <td className="py-3.5 px-4 text-center">
                        <input
                          type="checkbox"
                          checked={isSelected}
                          onChange={() => toggleSelectFile(file.id)}
                          className="w-4 h-4 rounded accent-[#14372e] cursor-pointer"
                        />
                      </td>

                      {/* الأيقونة المميزة + الاسم الكامل مع الامتداد دون أي اقتطاع */}
                      <td className="py-3.5 px-4 min-w-[360px] max-w-[600px]">
                        <div
                          onClick={() => handleOpenFile(file)}
                          className="flex items-center gap-3 cursor-pointer group/title"
                        >
                          {getFileIcon(file.type, 'md')}
                          <div className="min-w-0 flex-1">
                            <span
                              className="text-[15px] font-medium text-[#1B1F24] group-hover/title:text-[#14372e] break-words whitespace-normal leading-relaxed block transition"
                              title={file.name}
                            >
                              {file.name}
                            </span>
                          </div>
                        </div>
                      </td>

                      <td className="py-3.5 px-4 text-[13px] text-[#667085] break-words whitespace-normal max-w-[220px]">
                        {file.folder}
                      </td>

                      <td className="py-3.5 px-4 text-[13px] font-mono text-[#667085] whitespace-nowrap">
                        {file.size}
                      </td>

                      <td className="py-3.5 px-4 text-[13px] font-mono text-[#667085] whitespace-nowrap">
                        {file.lastModifiedAt}
                      </td>

                      <td className="py-3.5 px-4 whitespace-nowrap">
                        <span className="inline-flex items-center gap-1.5 text-xs font-medium text-[#12B76A] bg-emerald-50 px-2.5 py-0.5 rounded-full border border-emerald-200">
                          <span className="w-1.5 h-1.5 rounded-full bg-[#12B76A]" />
                          متزامن
                        </span>
                      </td>

                      <td className="py-3.5 px-4 text-left whitespace-nowrap">
                        <div className="inline-flex items-center gap-1.5 justify-end">
                          <button
                            onClick={() => handleOpenFile(file)}
                            className="h-8 flex items-center gap-1.5 bg-[#14372e] hover:bg-[#1b473b] text-white text-xs font-semibold px-3 rounded-lg transition"
                            title="فتح أو معاينة الملف"
                          >
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
                              className="h-8 flex items-center gap-1 bg-amber-50 hover:bg-amber-100 text-amber-900 border border-amber-200 text-xs font-semibold px-2.5 rounded-lg transition"
                              title="رفع نسخة معدلة وحفظ التعديلات في السحابة"
                            >
                              <UploadCloud className="w-3.5 h-3.5" />
                              <span>حفظ التعديلات</span>
                            </button>
                          )}

                          {['word', 'excel'].includes(file.type) && (
                            <button
                              onClick={() => handleOpenOfficeOnline(file)}
                              className="h-8 w-8 flex items-center justify-center text-[#667085] hover:text-[#2B579A] hover:bg-[#F7F8FA] rounded-lg border border-transparent hover:border-[#E4E7EC] transition"
                              title="معاينة عبر Office Online"
                            >
                              <Eye className="w-4 h-4" />
                            </button>
                          )}

                          {canDownloadFolder(file.folder) && (
                            <button
                              onClick={() => handleDownloadFile(file)}
                              className="h-8 w-8 flex items-center justify-center text-[#667085] hover:text-[#1B1F24] hover:bg-[#F7F8FA] rounded-lg border border-transparent hover:border-[#E4E7EC] transition"
                              title="تنزيل نسخة للملف"
                            >
                              <Download className="w-4 h-4" />
                            </button>
                          )}

                          <button
                            onClick={() => handleRevealInExplorer(file)}
                            className="h-8 w-8 flex items-center justify-center text-[#667085] hover:text-[#1B1F24] hover:bg-[#F7F8FA] rounded-lg border border-transparent hover:border-[#E4E7EC] transition"
                            title="إظهار في مجلد الويندوز المحلي"
                          >
                            <FolderOpen className="w-4 h-4" />
                          </button>

                          <button
                            onClick={() => handleShareFile(file)}
                            className="h-8 w-8 flex items-center justify-center text-[#667085] hover:text-[#14372e] hover:bg-[#F7F8FA] rounded-lg border border-transparent hover:border-[#E4E7EC] transition"
                            title="مشاركة المستند"
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
                                  className="h-8 w-8 flex items-center justify-center text-[#667085] hover:text-[#1B1F24] hover:bg-[#F7F8FA] rounded-lg border border-transparent hover:border-[#E4E7EC] transition"
                                  title="نقل الملف"
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
                                  className="h-8 w-8 flex items-center justify-center text-[#667085] hover:text-[#14372e] hover:bg-[#F7F8FA] rounded-lg border border-transparent hover:border-[#E4E7EC] transition"
                                  title="إعادة تسمية"
                                >
                                  <Edit3 className="w-4 h-4" />
                                </button>
                              )}

                              {canDeleteFolder(file.folder) && (
                                <button
                                  onClick={() => handleMoveToTrash(file)}
                                  className="h-8 w-8 flex items-center justify-center text-[#667085] hover:text-[#F04438] hover:bg-rose-50 rounded-lg transition"
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
                                className="h-8 px-2.5 text-emerald-700 bg-emerald-50 hover:bg-emerald-100 rounded-lg transition font-semibold text-xs flex items-center gap-1"
                                title="استرجاع المستند"
                              >
                                <RotateCcw className="w-3.5 h-3.5" />
                                <span>استرجاع</span>
                              </button>

                              {canPermanentDeleteFolder(file.folder) && (
                                <button
                                  onClick={() => handlePermanentDelete(file)}
                                  className="h-8 w-8 flex items-center justify-center text-[#F04438] hover:bg-rose-50 rounded-lg transition"
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
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4" dir="rtl">
          <div className="bg-white rounded-2xl shadow-xl border border-[#E4E7EC] max-w-lg w-full overflow-hidden text-right">
            {/* رأس النافذة */}
            <div className="bg-[#14372e] px-5 py-3.5 text-white flex items-center justify-between">
              <div className="flex items-center gap-2.5">
                <div className="w-8 h-8 rounded-lg bg-white/10 flex items-center justify-center text-[#c59b27]">
                  {uploadProgress.mode === 'download' ? (
                    <Download className="w-4 h-4" />
                  ) : (
                    <UploadCloud className="w-4 h-4" />
                  )}
                </div>
                <div>
                  <h3 className="text-[14px] font-bold">
                    {uploadProgress.mode === 'download'
                      ? 'تنزيل المستند من السحابة'
                      : 'رفع المستندات إلى السحابة'}
                  </h3>
                  <p className="text-[11px] text-white/70">غرفة تجارة كربلاء المقدسة • Google Drive</p>
                </div>
              </div>

              <button
                type="button"
                onClick={() => setUploadProgress(prev => prev ? { ...prev, minimized: true } : null)}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-white/10 hover:bg-white/20 text-[12px] text-white font-semibold transition"
                title="تصغير ومتابعة العمل بالخلفية"
              >
                <Minimize2 className="w-3.5 h-3.5" />
                <span className="hidden sm:inline">تصغير للخلفية</span>
              </button>
            </div>

            <div className="p-5 space-y-4">
              {/* أيقونة الحالة والعنوان واسم الملف الكامل */}
              <div className="text-center space-y-2">
                <div className="flex items-center justify-center w-12 h-12 mx-auto rounded-xl bg-[#EDF5F2] text-[#14372e]">
                  {uploadProgress.completed ? (
                    <CheckCircle2 className="w-6 h-6 text-[#12B76A]" />
                  ) : uploadProgress.mode === 'download' ? (
                    <Download className="w-6 h-6 text-[#14372e]" />
                  ) : (
                    <UploadCloud className="w-6 h-6 text-[#14372e]" />
                  )}
                </div>

                <div className="space-y-1.5">
                  <h4 className="text-[15px] font-bold text-[#1B1F24]">
                    {uploadProgress.completed
                      ? uploadProgress.mode === 'download'
                        ? 'اكتمل تنزيل المستند بنجاح'
                        : 'اكتمل الرفع والمزامنة بنجاح'
                      : uploadProgress.statusText
                      ? uploadProgress.statusText
                      : uploadProgress.mode === 'download'
                      ? 'جاري تنزيل المستند من السحابة...'
                      : uploadProgress.total > 1
                      ? `جاري رفع المجلد والملفات (${uploadProgress.current} من ${uploadProgress.total})...`
                      : 'جاري رفع المستند إلى السحابة...'}
                  </h4>
                  <div className="inline-flex items-center justify-center px-3 py-1.5 bg-[#F7F8FA] rounded-lg text-[13px] font-medium text-[#1B1F24] max-w-full break-words whitespace-normal leading-relaxed border border-[#E4E7EC]">
                    <span className="break-words whitespace-normal">{uploadProgress.currentFileName}</span>
                  </div>
                </div>
              </div>

              {/* النسبة المئوية وأشرطة التحميل الدقيقة */}
              {uploadProgress.total > 1 ? (
                <div className="space-y-3 bg-[#F7F8FA] p-3.5 rounded-xl border border-[#E4E7EC]">
                  <div className="space-y-1.5">
                    <div className="flex justify-between items-baseline">
                      <div className="flex items-baseline gap-2">
                        <span className="text-xl font-bold text-[#14372e] font-mono">
                          {uploadProgress.percentage}%
                        </span>
                        <span className="text-[11px] font-semibold text-[#14372e] bg-[#EDF5F2] px-2 py-0.5 rounded-md">
                          إنجاز الدفعة
                        </span>
                      </div>
                      <span className="text-[12px] font-semibold text-[#667085] font-mono">
                        مستند {uploadProgress.current} من {uploadProgress.total}
                      </span>
                    </div>

                    <div className="w-full bg-[#E4E7EC] rounded-full h-2.5 overflow-hidden">
                      <div
                        className="bg-[#14372e] h-full rounded-full transition-all duration-150"
                        style={{ width: `${Math.max(2, uploadProgress.percentage)}%` }}
                      />
                    </div>
                  </div>

                  <div className="space-y-1 pt-2 border-t border-[#E4E7EC]">
                    <div className="flex justify-between items-center text-[12px]">
                      <span className="font-semibold text-[#1B1F24] flex items-center gap-1.5">
                        <FileText className="w-3.5 h-3.5 text-[#14372e]" />
                        <span>الملف الحالي:</span>
                        <span className="font-bold text-[#14372e] font-mono">{uploadProgress.currentFilePercentage}%</span>
                      </span>
                      <span className="text-[11px] text-[#667085] font-mono" dir="ltr">
                        {uploadProgress.megabytesFormatted}
                      </span>
                    </div>

                    <div className="w-full bg-[#E4E7EC] rounded-full h-1.5 overflow-hidden">
                      <div
                        className="bg-[#12B76A] h-full rounded-full transition-all duration-150"
                        style={{ width: `${Math.max(2, uploadProgress.currentFilePercentage)}%` }}
                      />
                    </div>
                  </div>
                </div>
              ) : (
                <div className="space-y-1.5">
                  <div className="flex justify-between items-baseline">
                    <span className="text-2xl font-bold text-[#14372e] font-mono">
                      {uploadProgress.percentage}%
                    </span>
                    <span className="text-[12px] font-semibold text-[#667085] font-mono" dir="ltr">
                      {uploadProgress.megabytesFormatted}
                    </span>
                  </div>

                  <div className="w-full bg-[#E4E7EC] rounded-full h-2.5 overflow-hidden">
                    <div
                      className="bg-[#14372e] h-full rounded-full transition-all duration-150"
                      style={{ width: `${Math.max(2, uploadProgress.percentage)}%` }}
                    />
                  </div>
                </div>
              )}

              {/* بطاقات الإحصاءات الحية */}
              <div className="grid grid-cols-2 gap-2.5">
                <div className="p-3 rounded-xl bg-[#F7F8FA] border border-[#E4E7EC] space-y-0.5">
                  <div className="flex items-center gap-1.5 text-[#667085] text-[11px] font-semibold">
                    <Database className="w-3.5 h-3.5 text-[#14372e]" />
                    <span>الحجم المنقول</span>
                  </div>
                  <p className="text-[13px] font-bold text-[#1B1F24] font-mono" dir="ltr">
                    {uploadProgress.megabytesFormatted}
                  </p>
                  {uploadProgress.total > 1 && (
                    <p className="text-[11px] text-[#667085] break-words whitespace-normal" dir="ltr">
                      الإجمالي: {uploadProgress.batchMegabytesFormatted}
                    </p>
                  )}
                </div>

                <div className="p-3 rounded-xl bg-[#F7F8FA] border border-[#E4E7EC] space-y-0.5">
                  <div className="flex items-center gap-1.5 text-[#667085] text-[11px] font-semibold">
                    <Zap className="w-3.5 h-3.5 text-[#c59b27]" />
                    <span>السرعة الفورية</span>
                  </div>
                  <p className="text-[13px] font-bold text-[#1B1F24] font-mono" dir="ltr">
                    {uploadProgress.speedFormatted}
                  </p>
                </div>

                <div className="p-3 rounded-xl bg-[#F7F8FA] border border-[#E4E7EC] space-y-0.5">
                  <div className="flex items-center gap-1.5 text-[#667085] text-[11px] font-semibold">
                    <Clock className="w-3.5 h-3.5 text-[#14372e]" />
                    <span>الوقت المتبقي</span>
                  </div>
                  <p className="text-[12px] font-bold text-[#1B1F24]">
                    {uploadProgress.completed ? 'تم الانتهاء' : uploadProgress.timeRemainingFormatted}
                  </p>
                </div>

                <div className="p-3 rounded-xl bg-[#F7F8FA] border border-[#E4E7EC] space-y-0.5">
                  <div className="flex items-center gap-1.5 text-[#667085] text-[11px] font-semibold">
                    <Activity className="w-3.5 h-3.5 text-[#14372e]" />
                    <span>الحالة</span>
                  </div>
                  <p className="text-[12px] font-bold text-[#1B1F24] break-words whitespace-normal">
                    {uploadProgress.chunkText || (uploadProgress.total > 1 ? `الملف ${uploadProgress.current} من ${uploadProgress.total}` : 'نقل مباشر')}
                  </p>
                </div>
              </div>

              {/* أزرار المتابعة بالخلفية أو الإلغاء */}
              {uploadProgress.completed ? (
                <div className="text-[13px] text-[#14372e] font-semibold bg-[#EDF5F2] py-2.5 px-4 rounded-xl border border-[#14372e]/20 text-center">
                  {uploadProgress.mode === 'download'
                    ? 'اكتمل تنزيل المستند بنجاح إلى جهازك'
                    : 'تمت المزامنة وتأكيد وصول الملفات لجميع الأجهزة'}
                </div>
              ) : (
                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    onClick={() => setUploadProgress(prev => prev ? { ...prev, minimized: true } : null)}
                    className="flex-1 py-2.5 px-4 rounded-lg bg-[#F7F8FA] hover:bg-[#EDF0F5] text-[#1B1F24] border border-[#E4E7EC] text-[12px] font-semibold transition text-center flex items-center justify-center gap-2"
                  >
                    <Minimize2 className="w-3.5 h-3.5 text-[#667085]" />
                    <span>المتابعة بالخلفية</span>
                  </button>

                  <button
                    type="button"
                    onClick={handleAbortActiveTransfer}
                    className="py-2.5 px-4 rounded-lg bg-rose-50 hover:bg-rose-100 text-[#F04438] border border-rose-200 text-[12px] font-semibold transition flex items-center justify-center gap-1.5 shrink-0"
                  >
                    <X className="w-3.5 h-3.5" />
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
          className="fixed bottom-6 left-6 z-50 bg-white text-[#1B1F24] rounded-xl shadow-lg border border-[#E4E7EC] p-4 max-w-sm w-80"
          dir="rtl"
        >
          <div className="flex items-center justify-between pb-2 border-b border-[#E4E7EC]">
            <div className="flex items-center gap-2">
              <span className={`w-2 h-2 rounded-full ${uploadProgress.completed ? 'bg-[#12B76A]' : 'bg-[#c59b27]'}`} />
              <span className="text-[12px] font-bold">
                {uploadProgress.completed
                  ? uploadProgress.mode === 'download' ? 'اكتمل التنزيل' : 'اكتمل الرفع'
                  : uploadProgress.mode === 'download' ? 'جاري التنزيل بالخلفية' : 'جاري الرفع بالخلفية'}
              </span>
            </div>

            <div className="flex items-center gap-2">
              <span className="text-[11px] font-bold text-[#14372e] font-mono" dir="ltr">
                {uploadProgress.speedFormatted}
              </span>
              <button
                type="button"
                onClick={() => setUploadProgress(prev => prev ? { ...prev, minimized: false } : null)}
                className="p-1 rounded-md hover:bg-[#F7F8FA] text-[#667085] hover:text-[#1B1F24] transition-colors"
                title="توسيع نافذة المؤشر التفصيلي"
              >
                <Maximize2 className="w-3.5 h-3.5" />
              </button>
            </div>
          </div>

          <div className="pt-2.5 space-y-2">
            <p className="text-[12px] text-[#1B1F24] font-medium break-words whitespace-normal leading-snug">
              {uploadProgress.currentFileName}
            </p>

            <div className="w-full bg-[#E4E7EC] rounded-full h-2 overflow-hidden">
              <div
                className="bg-[#14372e] h-full rounded-full transition-all duration-150"
                style={{ width: `${Math.max(3, uploadProgress.percentage)}%` }}
              />
            </div>

            <div className="flex justify-between items-center text-[11px] font-semibold text-[#667085] font-mono">
              <span className="text-[#14372e] font-bold">
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
        <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4" dir="rtl">
          <div className="bg-white rounded-2xl p-6 max-w-md w-full space-y-4 shadow-xl border border-[#E4E7EC]">
            <div className="flex items-center justify-between border-b border-[#E4E7EC] pb-3">
              <h3 className="font-bold text-[16px] text-[#1B1F24] flex items-center gap-2">
                <Lock className="w-4 h-4 text-[#c59b27]" />
                <span>قسم محمي برمز سري (PIN)</span>
              </h3>
              <button
                onClick={() => {
                  setPinPromptDept(null);
                  setPinPromptTargetFolder(null);
                  setPinPromptInput('');
                  setPinPromptError('');
                }}
                className="text-[#667085] hover:text-[#1B1F24]"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <p className="text-[13px] text-[#667085] leading-relaxed">
              القسم <strong className="text-[#1B1F24]">({pinPromptDept})</strong> محمي برمز سري من قِبل الإدارة. يرجى إدخال الرمز السري لفتح القسم واستعراض مستنداته:
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
                className="w-full px-4 py-2.5 text-[14px] bg-[#F7F8FA] border border-[#E4E7EC] rounded-lg focus:outline-none focus:border-[#14372e] text-center font-mono font-bold tracking-widest"
                autoFocus
              />

              {pinPromptError && (
                <p className="text-[12px] text-[#F04438] font-semibold text-center">
                  {pinPromptError}
                </p>
              )}

              <div className="flex items-center justify-end gap-2 pt-3 border-t border-[#E4E7EC]">
                <button
                  type="button"
                  onClick={() => {
                    setPinPromptDept(null);
                    setPinPromptTargetFolder(null);
                    setPinPromptInput('');
                    setPinPromptError('');
                  }}
                  className="px-4 py-2 text-[13px] font-semibold text-[#667085] hover:bg-[#F7F8FA] rounded-lg transition"
                >
                  إلغاء
                </button>
                <button
                  type="submit"
                  className="px-5 py-2 text-[13px] font-semibold bg-[#14372e] text-white rounded-lg hover:bg-[#1b493d] transition"
                >
                  فتح القسم
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* 6. نافذة إنشاء مجلد جديد (New Folder Modal) */}
      {showNewFolderModal && (
        <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl p-6 max-w-md w-full space-y-4 shadow-xl border border-[#E4E7EC]">
            <div className="flex items-center justify-between border-b border-[#E4E7EC] pb-3">
              <h3 className="font-bold text-[16px] text-[#1B1F24] flex items-center gap-2">
                <FolderPlus className="w-5 h-5 text-[#14372e]" />
                <span>إنشاء مجلد إداري جديد</span>
              </h3>
              <button onClick={() => setShowNewFolderModal(false)} className="text-[#667085] hover:text-[#1B1F24]">
                <X className="w-5 h-5" />
              </button>
            </div>

            <p className="text-[13px] text-[#667085]">
              أدخل اسم المجلد لتنظيم الكتب الرسمية والمستندات في السحابة:
            </p>

            <input
              type="text"
              placeholder="مثال: الكتب الصادرة 2026..."
              value={newFolderName}
              onChange={(e) => setNewFolderName(e.target.value)}
              className="w-full px-4 py-2.5 text-[14px] bg-[#F7F8FA] border border-[#E4E7EC] rounded-lg focus:outline-none focus:border-[#14372e]"
              autoFocus
            />

            <div className="space-y-1.5">
              <span className="text-[12px] text-[#667085]">اقتراحات سريعة:</span>
              <div className="flex items-center gap-1.5 flex-wrap">
                {['الكتب الصادرة', 'الكتب الواردة', 'أضابير الكفالات', 'التقارير المالية'].map(sug => (
                  <button
                    key={sug}
                    onClick={() => setNewFolderName(sug)}
                    className="text-[12px] bg-[#F7F8FA] hover:bg-[#EDF5F2] text-[#1B1F24] border border-[#E4E7EC] font-medium px-2.5 py-1 rounded-md transition"
                  >
                    {sug}
                  </button>
                ))}
              </div>
            </div>

            <div className="flex items-center justify-end gap-2 pt-3 border-t border-[#E4E7EC]">
              <button
                onClick={() => setShowNewFolderModal(false)}
                className="px-4 py-2 text-[13px] font-semibold text-[#667085] hover:bg-[#F7F8FA] rounded-lg transition"
              >
                إلغاء
              </button>
              <button
                onClick={handleCreateFolder}
                className="px-5 py-2 text-[13px] font-semibold bg-[#14372e] text-white rounded-lg hover:bg-[#1b493d] transition"
              >
                إنشاء المجلد
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 7. نافذة تعديل الاسم (Rename Modal) */}
      {showRenameModal && itemToRename && (
        <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl p-6 max-w-md w-full space-y-4 shadow-xl border border-[#E4E7EC]">
            <div className="flex items-center justify-between border-b border-[#E4E7EC] pb-3">
              <h3 className="font-bold text-[16px] text-[#1B1F24] flex items-center gap-2">
                <Edit3 className="w-5 h-5 text-[#14372e]" />
                <span>تعديل اسم المستند</span>
              </h3>
              <button onClick={() => setShowRenameModal(false)} className="text-[#667085] hover:text-[#1B1F24]">
                <X className="w-5 h-5" />
              </button>
            </div>

            <p className="text-[13px] text-[#667085] break-words whitespace-normal">
              الاسم الحالي: <strong className="text-[#1B1F24]">{itemToRename.name}</strong>
            </p>

            <input
              type="text"
              value={newRenameValue}
              onChange={(e) => setNewRenameValue(e.target.value)}
              className="w-full px-4 py-2.5 text-[14px] bg-[#F7F8FA] border border-[#E4E7EC] rounded-lg focus:outline-none focus:border-[#14372e]"
              autoFocus
            />

            <p className="text-[12px] text-[#667085]">
              سيتم الحفاظ على صيغة المستند تلقائياً، وتحديث الاسم فوراً على السحابة وتطبيق الكمبيوتر.
            </p>

            <div className="flex items-center justify-end gap-2 pt-3 border-t border-[#E4E7EC]">
              <button
                onClick={() => setShowRenameModal(false)}
                className="px-4 py-2 text-[13px] font-semibold text-[#667085] hover:bg-[#F7F8FA] rounded-lg transition"
              >
                إلغاء
              </button>
              <button
                onClick={handleSaveRename}
                className="px-5 py-2 text-[13px] font-semibold bg-[#14372e] text-white rounded-lg hover:bg-[#1b493d] transition"
              >
                حفظ التعديل
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 8. نافذة إرشاد وتشغيل وحفظ المستند في تطبيقات الهاتف الأصلية (Mobile Sheet) */}
      {selectedMobileFile && (
        <div className="fixed inset-0 bg-black/50 z-50 flex items-end sm:items-center justify-center p-0 sm:p-4">
          <div className="bg-white rounded-t-2xl sm:rounded-2xl p-5 sm:p-6 max-w-lg w-full space-y-4 shadow-xl border border-[#E4E7EC] max-h-[92vh] overflow-y-auto">
            {/* الترويسة */}
            <div className="flex items-start justify-between border-b border-[#E4E7EC] pb-3 gap-3">
              <div className="flex items-start gap-3 min-w-0 flex-1">
                {getFileIcon(selectedMobileFile.type, 'md')}
                <div className="min-w-0 flex-1">
                  <h3 className="font-medium text-[15px] text-[#1B1F24] break-words whitespace-normal leading-relaxed">
                    {selectedMobileFile.name}
                  </h3>
                  <div className="flex items-center gap-2 text-[12px] text-[#667085] mt-1 flex-wrap">
                    <span className="break-words whitespace-normal">{selectedMobileFile.folder}</span>
                    <span>•</span>
                    <span className="font-semibold text-[#14372e] bg-[#EDF5F2] px-1.5 py-0.5 rounded">
                      V{selectedMobileFile.version}
                    </span>
                  </div>
                </div>
              </div>
              <button 
                onClick={() => setSelectedMobileFile(null)} 
                className="text-[#667085] hover:text-[#1B1F24] p-1.5 rounded-lg hover:bg-[#F7F8FA] shrink-0"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* 1. الخطوة الأولى: تشغيل وتعديل المستند في تطبيقات الهاتف */}
            <div className="bg-[#F7F8FA] border border-[#E4E7EC] rounded-xl p-4 space-y-3">
              <div className="flex items-center justify-between">
                <span className="text-[13px] font-bold text-[#1B1F24] flex items-center gap-2">
                  <span className="w-5 h-5 rounded-full bg-[#14372e] text-white flex items-center justify-center text-[11px]">1</span>
                  <span>الخطوة الأولى: فتح وتعديل المستند</span>
                </span>
              </div>

              <button
                onClick={() => handleOpenInMobileApp(selectedMobileFile)}
                disabled={preparingMobileOpen}
                className="w-full flex items-center justify-center gap-2 p-3 bg-[#14372e] hover:bg-[#1b493d] text-white rounded-lg font-semibold text-[13px] transition"
              >
                <Smartphone className="w-4 h-4" />
                <span>
                  {preparingMobileOpen ? 'جاري تحضير التطبيق...' : `تشغيل وتعديل في تطبيق ${selectedMobileFile.type === 'word' ? 'Word' : 'Excel'} بهاتفك`}
                </span>
              </button>

              <div className="grid grid-cols-2 gap-2">
                <button
                  onClick={() => handleLaunchOfficeProtocol(selectedMobileFile)}
                  className="flex items-center justify-center gap-1.5 p-2 bg-white hover:bg-[#EDF0F5] text-[#1B1F24] rounded-lg font-semibold text-[12px] border border-[#E4E7EC] transition"
                >
                  <Sparkles className="w-3.5 h-3.5 text-[#14372e]" />
                  <span>بروتوكول Office</span>
                </button>

                <button
                  onClick={() => {
                    const f = selectedMobileFile;
                    setSelectedMobileFile(null);
                    handleOpenOfficeOnline(f);
                  }}
                  className="flex items-center justify-center gap-1.5 p-2 bg-white hover:bg-[#EDF0F5] text-[#1B1F24] rounded-lg font-semibold text-[12px] border border-[#E4E7EC] transition"
                >
                  <Eye className="w-3.5 h-3.5 text-[#14372e]" />
                  <span>معاينة بالمتصفح</span>
                </button>
              </div>

              <button
                onClick={() => handleDownloadFile(selectedMobileFile)}
                className="w-full flex items-center justify-center gap-1.5 py-1.5 text-[#667085] hover:text-[#1B1F24] text-[12px] font-medium transition"
              >
                <Download className="w-3.5 h-3.5" />
                <span>تنزيل نسخة عادية إلى الهاتف</span>
              </button>
            </div>

            {/* 2. الخطوة الثانية: حفظ التعديلات ومشاركتها في النظام */}
            <div className="bg-[#EDF5F2] border border-[#14372e]/20 rounded-xl p-4 space-y-3">
              <div className="flex items-center gap-2">
                <span className="w-5 h-5 rounded-full bg-[#c59b27] text-white flex items-center justify-center text-[11px] font-bold">2</span>
                <span className="text-[13px] font-bold text-[#1B1F24]">الخطوة الثانية: حفظ ومشاركة التعديلات</span>
              </div>

              <p className="text-[12px] text-[#667085] leading-relaxed">
                بعد إجراء التعديلات وحفظها بهاتفك، اضغط الزر أدناه لاختيار الملف المعدل ليتم تحديثه ومشاركته مع جميع أجهزة الغرفة.
              </p>

              <button
                onClick={() => triggerUpdateFile(selectedMobileFile)}
                disabled={actionLoading}
                className="w-full flex items-center justify-center gap-2 py-2.5 px-4 bg-[#c59b27] hover:bg-[#b08920] text-white rounded-lg font-bold text-[13px] transition"
              >
                <UploadCloud className="w-4 h-4" />
                <span>اختيار الملف المعدل وحفظ التعديلات</span>
              </button>
            </div>

            <div className="pt-2 border-t border-[#E4E7EC]">
              <button
                onClick={() => setSelectedMobileFile(null)}
                className="w-full py-2 text-[13px] font-semibold text-[#667085] hover:text-[#1B1F24] rounded-lg transition"
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
          className="fixed bottom-5 left-1/2 -translate-x-1/2 z-40 bg-[#1B1F24] text-white px-4 py-2.5 rounded-xl shadow-xl border border-white/10 flex items-center gap-3 flex-wrap justify-center max-w-[95vw]"
          dir="rtl"
        >
          <div className="flex items-center gap-2 pl-2 border-l border-white/15">
            <span className="w-6 h-6 rounded-full bg-[#14372e] text-white text-[12px] font-bold flex items-center justify-center">
              {selectedFileIds.length + selectedFolderIds.length}
            </span>
            <span className="text-[12px] font-semibold">عنصر محدد</span>
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
              className="px-3 py-1.5 rounded-lg bg-[#14372e] hover:bg-[#1b493d] text-white text-[12px] font-semibold transition flex items-center gap-1.5"
            >
              <Move className="w-3.5 h-3.5" />
              <span>نقل المحدد</span>
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
                    text: `تم استرجاع (${selectedFileIds.length}) ملف بنجاح`,
                    type: 'success',
                  });
                } catch (err: any) {
                  alert(`تعذر استرجاع المحدد: ${err.message || err}`);
                } finally {
                  setActionLoading(false);
                }
              }}
              disabled={actionLoading}
              className="px-3 py-1.5 rounded-lg bg-[#12B76A] hover:bg-[#0e9f5a] text-white text-[12px] font-semibold transition flex items-center gap-1.5"
            >
              <RotateCcw className="w-3.5 h-3.5" />
              <span>استرجاع المحدد</span>
            </button>
          )}

          <button
            type="button"
            onClick={handleBulkDeleteSelected}
            disabled={actionLoading}
            className="px-3 py-1.5 rounded-lg bg-[#F04438] hover:bg-rose-600 text-white text-[12px] font-semibold transition flex items-center gap-1.5"
          >
            <Trash2 className="w-3.5 h-3.5" />
            <span>{activeTab === 'TRASH' ? 'حذف نهائي للمحدد' : 'حذف المحدد للسلة'}</span>
          </button>

          <button
            type="button"
            onClick={clearSelection}
            className="px-2.5 py-1.5 rounded-lg bg-white/10 hover:bg-white/20 text-white/80 text-[12px] font-semibold transition"
          >
            إلغاء التحديد
          </button>
        </div>
      )}

      {/* نافذة نقل الملفات والمجلدات بين الأقسام والمجلدات الفرعية (Move Modal) */}
      {showMoveModal && itemsToMove && (
        <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4" dir="rtl">
          <div className="bg-white rounded-2xl p-6 max-w-md w-full space-y-4 shadow-xl border border-[#E4E7EC]">
            <div className="flex items-center justify-between border-b border-[#E4E7EC] pb-3">
              <h3 className="font-bold text-[16px] text-[#1B1F24] flex items-center gap-2">
                <Move className="w-5 h-5 text-[#14372e]" />
                <span>نقل إلى قسم أو مجلد آخر</span>
              </h3>
              <button
                onClick={() => {
                  setShowMoveModal(false);
                  setItemsToMove(null);
                }}
                className="text-[#667085] hover:text-[#1B1F24]"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="p-3 rounded-lg bg-[#F7F8FA] border border-[#E4E7EC] text-[13px] text-[#1B1F24] font-medium break-words whitespace-normal">
              العناصر المراد نقلها: <strong className="text-[#14372e]">{itemsToMove.label}</strong>
            </div>

            <div className="space-y-3">
              <div>
                <label className="block text-[13px] font-semibold text-[#1B1F24] mb-1">
                  1. اختر القسم الهدف:
                </label>
                <select
                  value={moveTargetDept}
                  onChange={(e) => {
                    setMoveTargetDept(e.target.value);
                    setMoveTargetSubfolder('');
                  }}
                  className="w-full px-3.5 py-2.5 text-[13px] bg-[#F7F8FA] border border-[#E4E7EC] rounded-lg font-medium focus:outline-none focus:border-[#14372e]"
                >
                  {departments.map((d) => (
                    <option key={d} value={d}>
                      {d}
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-[13px] font-semibold text-[#1B1F24] mb-1">
                  2. اختر مجلداً فرعياً داخل القسم (اختياري):
                </label>
                <select
                  value={moveTargetSubfolder}
                  onChange={(e) => setMoveTargetSubfolder(e.target.value)}
                  className="w-full px-3.5 py-2.5 text-[13px] bg-[#F7F8FA] border border-[#E4E7EC] rounded-lg font-medium focus:outline-none focus:border-[#14372e]"
                >
                  <option value="">المجلد الرئيسي للقسم ({moveTargetDept})</option>
                  {allFolders
                    .filter((f) => f.department === moveTargetDept && f.parentPath)
                    .map((sub) => (
                      <option key={sub.id} value={sub.path}>
                        {sub.path}
                      </option>
                    ))}
                </select>
              </div>

              <div>
                <label className="block text-[13px] font-semibold text-[#1B1F24] mb-1">
                  أو اكتب اسم مجلد فرعي جديد:
                </label>
                <input
                  type="text"
                  value={moveCustomSubfolder}
                  onChange={(e) => setMoveCustomSubfolder(e.target.value)}
                  placeholder="اتركه فارغاً للنقل للمجلد المختار أعلاه..."
                  className="w-full px-3.5 py-2 text-[13px] bg-[#F7F8FA] border border-[#E4E7EC] rounded-lg focus:outline-none focus:border-[#14372e]"
                />
              </div>
            </div>

            <div className="flex items-center justify-end gap-2 pt-3 border-t border-[#E4E7EC]">
              <button
                type="button"
                onClick={() => {
                  setShowMoveModal(false);
                  setItemsToMove(null);
                }}
                className="px-4 py-2 text-[13px] font-semibold text-[#667085] hover:bg-[#F7F8FA] rounded-lg transition"
              >
                إلغاء
              </button>
              <button
                type="button"
                onClick={handleExecuteMove}
                disabled={actionLoading || !moveTargetDept}
                className="px-5 py-2 text-[13px] font-semibold bg-[#14372e] text-white rounded-lg hover:bg-[#1b493d] transition flex items-center gap-1.5"
              >
                <Move className="w-3.5 h-3.5" />
                <span>تأكيد النقل</span>
              </button>
            </div>
          </div>
        </div>
      )}

      {/* نافذة شريط تقدم تفريغ السلة والعمليات الجماعية السريعة (Trash & Batch Progress Modal) */}
      {trashProgress && trashProgress.show && (
        <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4" dir="rtl">
          <div className="bg-white rounded-2xl p-6 max-w-md w-full space-y-4 shadow-xl border border-[#E4E7EC] text-right">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-xl bg-[#EDF5F2] text-[#14372e] flex items-center justify-center shrink-0">
                <RefreshCw className="w-5 h-5 animate-spin" />
              </div>
              <div className="min-w-0 flex-1">
                <h3 className="font-bold text-[14px] text-[#1B1F24]">{trashProgress.title}</h3>
                <p className="text-[12px] text-[#667085] break-words whitespace-normal mt-0.5">{trashProgress.currentName}</p>
              </div>
            </div>

            <div className="space-y-2">
              <div className="flex items-center justify-between text-[12px] font-semibold">
                <span className="text-xl font-bold text-[#14372e] font-mono">{trashProgress.percentage}%</span>
                <span className="text-[#667085]">
                  تم إنجاز {trashProgress.current} من {trashProgress.total}
                </span>
              </div>
              <div className="w-full bg-[#E4E7EC] rounded-full h-2.5 overflow-hidden">
                <div
                  className="bg-[#14372e] h-full rounded-full transition-all duration-200"
                  style={{ width: `${Math.max(4, trashProgress.percentage)}%` }}
                />
              </div>
            </div>
          </div>
        </div>
      )}

      {/* عارض الصور والوسائط وملفات PDF المدمج (Built-in Lightbox Preview Modal) */}
      {previewFile && (
        <div
          className="fixed inset-0 bg-black/85 z-50 flex flex-col justify-between p-3 sm:p-6"
          dir="rtl"
        >
          {/* شريط علوي للعارض */}
          <div className="flex items-center justify-between gap-3 bg-[#1B1F24] text-white px-4 py-3 rounded-xl border border-white/10">
            <div className="flex items-center gap-3 min-w-0 flex-1">
              {getFileIcon(previewFile.type, 'sm')}
              <div className="min-w-0 flex-1">
                <h3 className="font-medium text-[14px] break-words whitespace-normal leading-snug">{previewFile.name}</h3>
                <p className="text-[11px] text-white/60 break-words whitespace-normal mt-0.5">
                  {previewFile.folder} • {previewFile.size}
                </p>
              </div>
            </div>

            <div className="flex items-center gap-2 shrink-0">
                            <button
                type="button"
                onClick={() => handleDownloadFile(previewFile)}
                className="px-3 py-1.5 rounded-lg bg-[#14372e] hover:bg-[#1b493d] text-white text-[12px] font-semibold transition flex items-center gap-1.5"
              >
                <Download className="w-3.5 h-3.5" />
                <span>تنزيل الملف</span>
              </button>
              <button
                type="button"
                onClick={() => setPreviewFile(null)}
                className="p-2 rounded-lg bg-white/10 hover:bg-[#F04438] text-white transition"
                title="إغلاق المعاينة"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
          </div>

          {/* محتوى المعاينة الوسطي */}
          <div
            className="flex-1 flex items-center justify-center overflow-auto my-3 rounded-xl bg-black/40 border border-white/10 p-2 sm:p-4"
            onClick={(e) => {
              if (e.target === e.currentTarget) setPreviewFile(null);
            }}
          >
            {previewFile.type === 'image' && (
              <img
                src={`/api/drive/stream?id=${encodeURIComponent(previewFile.id)}`}
                alt={previewFile.name}
                className="max-h-[78vh] max-w-full object-contain rounded-lg"
              />
            )}

            

            {previewFile.type === 'video' && (
              <video
                src={`/api/drive/stream?id=${encodeURIComponent(previewFile.id)}`}
                controls
                autoPlay
                className="max-h-[78vh] max-w-full rounded-lg bg-black"
              />
            )}

            {previewFile.type === 'audio' && (
              <div className="bg-[#1B1F24] p-8 rounded-2xl border border-white/10 text-center space-y-4 max-w-md w-full">
                <div className="flex justify-center">
                  {getFileIcon('audio', 'lg')}
                </div>
                <h4 className="text-white font-medium text-[15px] break-words whitespace-normal">{previewFile.name}</h4>
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

      {/* 9. إشعار عائم هادئ (Toast Notification) */}
      {toastMessage && (
        <div className="fixed bottom-6 left-1/2 -translate-x-1/2 z-50 shadow-lg pointer-events-none">
          <div className={`flex items-center gap-2.5 px-4 py-2.5 rounded-xl text-[13px] font-semibold border ${
            toastMessage.type === 'success' 
              ? 'bg-[#14372e] text-white border-[#1b493d]' 
              : toastMessage.type === 'error'
              ? 'bg-[#F04438] text-white border-rose-600'
              : 'bg-[#1B1F24] text-white border-white/15'
          }`}>
            <span>{toastMessage.text}</span>
          </div>
        </div>
      )}
    </div>
  );
}
