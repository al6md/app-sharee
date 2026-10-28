import { google } from 'googleapis';
import { Readable } from 'stream';

const CLIENT_ID = process.env.GDRIVE_CLIENT_ID;
const CLIENT_SECRET = process.env.GDRIVE_CLIENT_SECRET;
const REFRESH_TOKEN = process.env.GDRIVE_REFRESH_TOKEN;
export const ROOT_FOLDER_ID = process.env.GDRIVE_FOLDER_ID || '1BF6mDMuwuaS5c4Ekq9KPcEXaAOxGOmfB';

const FOLDER_MIME = 'application/vnd.google-apps.folder';
const IGNORED_EXACT = new Set(['desktop.ini', 'thumbs.db', '.ds_store']);
const IGNORED_SUFFIXES = ['.tmp', '.laccdb', '.ldb', '.crdownload', '.partial', '~'];

function isIgnoredName(name?: string | null): boolean {
  if (!name) return true;
  const low = name.toLowerCase();
  if (IGNORED_EXACT.has(low)) return true;
  if (name.startsWith('~$') || name.startsWith('.') || name.startsWith('~WRL')) return true;
  return IGNORED_SUFFIXES.some((s) => low.endsWith(s));
}

function qEscape(val: string): string {
  return val.replace(/\\/g, '\\\\').replace(/'/g, "\\'");
}

const oauth2Client = new google.auth.OAuth2(CLIENT_ID, CLIENT_SECRET);
oauth2Client.setCredentials({ refresh_token: REFRESH_TOKEN });

export const drive = google.drive({ version: 'v3', auth: oauth2Client });

export interface CloudFolderItem {
  id: string;
  name: string;
  path: string;
  parentPath: string;
  department: string;
  modifiedTime?: string | null;
}

export interface DepartmentPermissionConfig {
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
  updatedAt?: string;
}

export interface AdminCredentialsConfig {
  username: string;
  password: string;
  updatedAt: string;
}

export interface AuthorizedDeviceConfig {
  id: string;
  name: string;
  user: string;
  os: string;
  machineGuid: string;
  isAuthorized: boolean;
  lastSeen: string;
  status?: string;
}

export interface CloudAdminStore {
  version: number;
  updatedAt: string;
  adminCredentials: AdminCredentialsConfig;
  devices: AuthorizedDeviceConfig[];
  departments: Record<string, DepartmentPermissionConfig>;
}

export const PERMISSIONS_CONFIG_FILENAME = '.sharecoc_permissions.json';

export const DEFAULT_ADMIN_CREDENTIALS: AdminCredentialsConfig = {
  username: 'admin',
  password: 'admin1234',
  updatedAt: new Date(0).toISOString(),
};

export const DEFAULT_AUTHORIZED_DEVICES: AuthorizedDeviceConfig[] = [
  {
    id: 'dev-1',
    name: 'COC-SECRETARY-PC',
    user: 'أمانة السر والإدارة العامة',
    os: 'Windows 11 Pro',
    machineGuid: 'COC-KARBALA-SEC-001',
    isAuthorized: true,
    lastSeen: 'متصل ومفعّل',
    status: 'متصل الآن',
  },
  {
    id: 'dev-2',
    name: 'COC-REGISTRY-01',
    user: 'قسم السجل التجاري',
    os: 'Windows 10 Enterprise',
    machineGuid: 'COC-KARBALA-REG-002',
    isAuthorized: true,
    lastSeen: 'متصل ومفعّل',
    status: 'متصل الآن',
  },
  {
    id: 'dev-3',
    name: 'COC-SUBSCRIPTION-01',
    user: 'قسم الاشتراكات والهويات',
    os: 'Windows 11 Pro',
    machineGuid: 'COC-KARBALA-SUB-003',
    isAuthorized: true,
    lastSeen: 'متصل ومفعّل',
    status: 'متصل الآن',
  },
  {
    id: 'dev-4',
    name: 'COC-GENERAL-LAPTOP',
    user: 'القسم العام والمتابعة',
    os: 'Windows 11 Home',
    machineGuid: 'COC-KARBALA-GEN-004',
    isAuthorized: true,
    lastSeen: 'متصل ومفعّل',
    status: 'متصل الآن',
  },
];

export function getDefaultDepartmentPermission(departmentName: string): DepartmentPermissionConfig {
  return {
    departmentName,
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
  };
}

export function normalizeDepartmentPermission(
  departmentName: string,
  raw?: Partial<DepartmentPermissionConfig> | any
): DepartmentPermissionConfig {
  const def = getDefaultDepartmentPermission(departmentName);
  if (!raw || typeof raw !== 'object') return def;
  const legacyWrite = raw.canWrite !== undefined ? Boolean(raw.canWrite) : undefined;
  const legacyDelete = raw.canDelete !== undefined ? Boolean(raw.canDelete) : undefined;
  return {
    departmentName,
    canView: raw.canView !== undefined ? Boolean(raw.canView) : def.canView,
    canDownload: raw.canDownload !== undefined ? Boolean(raw.canDownload) : def.canDownload,
    canUpload: raw.canUpload !== undefined ? Boolean(raw.canUpload) : (legacyWrite ?? def.canUpload),
    canCreateFolder: raw.canCreateFolder !== undefined ? Boolean(raw.canCreateFolder) : (legacyWrite ?? def.canCreateFolder),
    canEdit: raw.canEdit !== undefined ? Boolean(raw.canEdit) : (legacyWrite ?? def.canEdit),
    canRename: raw.canRename !== undefined ? Boolean(raw.canRename) : (legacyWrite ?? def.canRename),
    canMove: raw.canMove !== undefined ? Boolean(raw.canMove) : (legacyWrite ?? def.canMove),
    canDelete: raw.canDelete !== undefined ? Boolean(raw.canDelete) : def.canDelete,
    canPermanentDelete:
      raw.canPermanentDelete !== undefined ? Boolean(raw.canPermanentDelete) : (legacyDelete ?? def.canPermanentDelete),
    pinCode: typeof raw.pinCode === 'string' ? raw.pinCode : '',
    updatedAt: raw.updatedAt || new Date().toISOString(),
  };
}

let _adminStoreCache: { store: CloudAdminStore; ts: number; fileId?: string } | null = null;
const PERMISSIONS_CACHE_TTL_MS = 20000;
let _saveQueuePromise: Promise<any> = Promise.resolve();

// ذاكرة تخزين مؤقتة لشجرة الملفات والأقسام لتسريع التنقل وجعله فورياً (Sub-second navigation)
let _cloudFilesCache: { data: any; ts: number } | null = null;
const CLOUD_FILES_CACHE_TTL_MS = 12000; // 12 ثانية كاش خفيف يمنع ازدحام طلبات Google Drive

export function invalidateCloudFilesCache() {
  _cloudFilesCache = null;
}

async function runWithConcurrency<T, R>(
  items: T[],
  concurrency: number,
  worker: (item: T, index: number) => Promise<R>
): Promise<PromiseSettledResult<R>[]> {
  const results: PromiseSettledResult<R>[] = new Array(items.length);
  let cursor = 0;
  const runners = Array.from({ length: Math.min(concurrency, items.length) }, async () => {
    while (cursor < items.length) {
      const idx = cursor++;
      try {
        const value = await worker(items[idx], idx);
        results[idx] = { status: 'fulfilled', value };
      } catch (reason) {
        results[idx] = { status: 'rejected', reason };
      }
    }
  });
  await Promise.all(runners);
  return results;
}

async function listChildrenBatch(parentIds: string[]) {
  const qParents = parentIds.map((id) => `'${id}' in parents`).join(' or ');
  const query = `(${qParents}) and trashed = false`;
  const all: any[] = [];
  let pageToken: string | undefined = undefined;
  do {
    const res: any = await drive.files.list({
      q: query,
      fields: 'nextPageToken, files(id, name, size, mimeType, modifiedTime, webViewLink, webContentLink, parents)',
      pageSize: 1000,
      pageToken,
    });
    if (res.data.files) {
      all.push(...res.data.files);
    }
    pageToken = res.data.nextPageToken || undefined;
  } while (pageToken);
  return all;
}

/**
 * جلب أقسام المستوى الأول من سحابة Google Drive مباشرة
 */
export async function getCloudFolders() {
  const res = await drive.files.list({
    q: `'${ROOT_FOLDER_ID}' in parents and mimeType = '${FOLDER_MIME}' and trashed = false`,
    fields: 'files(id, name, modifiedTime)',
    orderBy: 'name',
    pageSize: 500,
  });
  return (res.data.files || []).filter((f) => !isIgnoredName(f.name));
}

/**
 * إنشاء مجلد / قسم جديد (مع إعادة استخدام المجلد إن كان موجوداً بنفس الاسم داخل نفس الأب لمنع التكرار)
 */
export async function createCloudFolder(name: string, parentId: string = ROOT_FOLDER_ID) {
  const cleanName = name.trim();
  const check = await drive.files.list({
    q: `'${parentId}' in parents and name = '${qEscape(cleanName)}' and mimeType = '${FOLDER_MIME}' and trashed = false`,
    fields: 'files(id, name, mimeType)',
    pageSize: 5,
  });
  if (check.data.files && check.data.files.length > 0) {
    return check.data.files[0];
  }
  const res = await drive.files.create({
    requestBody: {
      name: cleanName,
      mimeType: FOLDER_MIME,
      parents: [parentId],
    },
    fields: 'id, name, mimeType',
  });
  invalidateCloudFilesCache();
  return res.data;
}

/**
 * ضمان وجود مسار مجلدات متداخل بالكامل في السحابة (مثال: "السجل التجاري/كتب رسمية/2026") وإرجاع معرف آخر مجلد
 */
export async function ensureCloudFolderPath(folderPath: string, baseParentId: string = ROOT_FOLDER_ID): Promise<string> {
  if (!folderPath) return baseParentId || ROOT_FOLDER_ID;
  const parts = folderPath
    .replace(/\\/g, '/')
    .split('/')
    .map((p) => p.trim())
    .filter((p) => p && p !== '.' && p !== '__ALL__');
  let currentParent = baseParentId || ROOT_FOLDER_ID;
  for (const part of parts) {
    const folder = await createCloudFolder(part, currentParent);
    if (folder?.id) {
      currentParent = folder.id;
    }
  }
  return currentParent;
}

/**
 * إنشاء/تأكيد مجموعة مسارات مجلدات دفعة واحدة مع تخزين مؤقت للمجلدات المشتركة لتسريع رفع المجلدات الكاملة
 */
export async function ensureCloudFolderPathsBatch(
  folderPaths: string[],
  baseParentId: string = ROOT_FOLDER_ID
): Promise<Record<string, string>> {
  const resultMap: Record<string, string> = {};
  const cache = new Map<string, string>(); // key: `${parentId}:::${name}` -> folderId
  const uniquePaths = Array.from(new Set(folderPaths.map((p) => String(p || '').trim()).filter(Boolean)));

  for (const rawPath of uniquePaths) {
    const parts = rawPath
      .replace(/\\/g, '/')
      .split('/')
      .map((p) => p.trim())
      .filter((p) => p && p !== '.' && p !== '__ALL__');
    let currentParent = baseParentId || ROOT_FOLDER_ID;
    for (const part of parts) {
      const cacheKey = `${currentParent}:::${part.toLowerCase()}`;
      let folderId = cache.get(cacheKey);
      if (!folderId) {
        const folder = await createCloudFolder(part, currentParent);
        folderId = folder?.id || currentParent;
        cache.set(cacheKey, folderId);
      }
      currentParent = folderId;
    }
    resultMap[rawPath] = currentParent;
  }
  return resultMap;
}

/**
 * قراءة ملف الإعدادات الإدارية والصلاحيات الكامل (.sharecoc_permissions.json) من Google Drive بشكل موثوق 100%
 */
export async function getCloudAdminStore(forceRefresh: boolean = false): Promise<CloudAdminStore> {
  if (!forceRefresh && _adminStoreCache && Date.now() - _adminStoreCache.ts < PERMISSIONS_CACHE_TTL_MS) {
    return _adminStoreCache.store;
  }
  try {
    const check = await drive.files.list({
      q: `'${ROOT_FOLDER_ID}' in parents and name = '${PERMISSIONS_CONFIG_FILENAME}' and trashed = false`,
      fields: 'files(id, name, modifiedTime)',
      orderBy: 'modifiedTime desc',
      pageSize: 10,
    });
    const filesList = check.data.files || [];
    const configFile = filesList[0];

    // تنظيف أي ملفات إعدادات مكررة قديمة في الخلفية إن وجدت
    if (filesList.length > 1) {
      for (let i = 1; i < filesList.length; i++) {
        const dupId = filesList[i]?.id;
        if (dupId) {
          drive.files.delete({ fileId: dupId }).catch(() => {});
        }
      }
    }

    if (!configFile?.id) {
      const emptyStore: CloudAdminStore = {
        version: 3,
        updatedAt: new Date().toISOString(),
        adminCredentials: { ...DEFAULT_ADMIN_CREDENTIALS },
        devices: [...DEFAULT_AUTHORIZED_DEVICES],
        departments: {},
      };
      _adminStoreCache = { store: emptyStore, ts: Date.now() };
      return emptyStore;
    }

    const contentRes = await drive.files.get(
      { fileId: configFile.id, alt: 'media' },
      { responseType: 'arraybuffer' }
    );

    let rawText = '';
    const d: any = contentRes.data;
    if (typeof d === 'string') {
      rawText = d;
    } else if (Buffer.isBuffer(d)) {
      rawText = d.toString('utf-8');
    } else if (d instanceof ArrayBuffer) {
      rawText = Buffer.from(d).toString('utf-8');
    } else if (ArrayBuffer.isView(d)) {
      rawText = Buffer.from(d.buffer, d.byteOffset, d.byteLength).toString('utf-8');
    } else if (d && typeof d === 'object') {
      rawText = JSON.stringify(d);
    }

    let rawData: any = {};
    if (rawText && rawText.trim()) {
      try {
        rawData = JSON.parse(rawText.replace(/^\uFEFF/, '').trim());
      } catch (parseErr) {
        console.error('JSON parse error on .sharecoc_permissions.json:', parseErr);
        rawData = {};
      }
    }

    const departmentsObj = rawData.departments || rawData;
    const normalizedDepts: Record<string, DepartmentPermissionConfig> = {};
    if (departmentsObj && typeof departmentsObj === 'object') {
      for (const [deptName, cfg] of Object.entries(departmentsObj)) {
        if (
          deptName === 'version' ||
          deptName === 'updatedAt' ||
          deptName === 'adminCredentials' ||
          deptName === 'devices' ||
          deptName.startsWith('__')
        ) {
          continue;
        }
        if (cfg && typeof cfg === 'object') {
          normalizedDepts[deptName] = normalizeDepartmentPermission(deptName, cfg);
        }
      }
    }

    const rawCreds = rawData.adminCredentials || rawData.__admin_credentials__;
    const adminCredentials: AdminCredentialsConfig = {
      username:
        rawCreds && typeof rawCreds.username === 'string' && rawCreds.username.trim()
          ? rawCreds.username.trim()
          : DEFAULT_ADMIN_CREDENTIALS.username,
      password:
        rawCreds && typeof rawCreds.password === 'string' && rawCreds.password.length > 0
          ? rawCreds.password
          : DEFAULT_ADMIN_CREDENTIALS.password,
      updatedAt: (rawCreds && rawCreds.updatedAt) || rawData.updatedAt || DEFAULT_ADMIN_CREDENTIALS.updatedAt,
    };

    const rawDevices = rawData.devices || rawData.__authorized_devices__;
    const devices: AuthorizedDeviceConfig[] =
      Array.isArray(rawDevices) && rawDevices.length > 0
        ? rawDevices.map((dev: any, idx: number) => ({
            id: String(dev.id || `dev-${idx + 1}`),
            name: String(dev.name || `COC-DEVICE-${idx + 1}`),
            user: String(dev.user || 'موظف الغرفة'),
            os: String(dev.os || 'Windows 10/11'),
            machineGuid: String(dev.machineGuid || `COC-GUID-${idx + 1}`),
            isAuthorized: dev.isAuthorized !== undefined ? Boolean(dev.isAuthorized) : true,
            lastSeen: String(dev.lastSeen || 'نشط'),
            status: dev.isAuthorized === false ? 'موقوف' : String(dev.status || 'متصل الآن'),
          }))
        : [...DEFAULT_AUTHORIZED_DEVICES];

    const store: CloudAdminStore = {
      version: 3,
      updatedAt: rawData.updatedAt || new Date().toISOString(),
      adminCredentials,
      devices,
      departments: normalizedDepts,
    };

    _adminStoreCache = { store, ts: Date.now(), fileId: configFile.id };
    return store;
  } catch (e) {
    console.error('Error reading cloud admin store:', e);
    if (_adminStoreCache) return _adminStoreCache.store;
    return {
      version: 3,
      updatedAt: new Date().toISOString(),
      adminCredentials: { ...DEFAULT_ADMIN_CREDENTIALS },
      devices: [...DEFAULT_AUTHORIZED_DEVICES],
      departments: {},
    };
  }
}

/**
 * حفظ ملف الإعدادات الإدارية والصلاحيات الكامل في Google Drive بشكل متسلسل ذري (Atomic Queue)
 */
async function persistCloudAdminStore(
  mutator: (current: CloudAdminStore) => CloudAdminStore
): Promise<CloudAdminStore> {
  const runSave = async (): Promise<CloudAdminStore> => {
    const baseStore = _adminStoreCache ? _adminStoreCache.store : await getCloudAdminStore(true);
    const updatedStore = mutator({
      version: 3,
      updatedAt: new Date().toISOString(),
      adminCredentials: { ...baseStore.adminCredentials },
      devices: [...baseStore.devices],
      departments: { ...baseStore.departments },
    });
    updatedStore.version = 3;
    updatedStore.updatedAt = new Date().toISOString();

    // تحديث الذاكرة المؤقتة فوراً قبل انتهاء الكتابة السحابية لضمان استجابة لحظية 100%
    _adminStoreCache = {
      store: updatedStore,
      ts: Date.now(),
      fileId: _adminStoreCache?.fileId,
    };

    const payload = JSON.stringify(updatedStore, null, 2);
    const buffer = Buffer.from(payload, 'utf-8');
    const stream = new Readable();
    stream.push(buffer);
    stream.push(null);

    let existingFileId = _adminStoreCache?.fileId;
    if (!existingFileId) {
      const check = await drive.files.list({
        q: `'${ROOT_FOLDER_ID}' in parents and name = '${PERMISSIONS_CONFIG_FILENAME}' and trashed = false`,
        fields: 'files(id, modifiedTime)',
        orderBy: 'modifiedTime desc',
        pageSize: 5,
      });
      existingFileId = check.data.files?.[0]?.id || undefined;
    }

    let savedFileId = existingFileId;
    if (existingFileId) {
      try {
        await drive.files.update({
          fileId: existingFileId,
          media: {
            mimeType: 'application/json',
            body: stream,
          },
          fields: 'id',
        });
      } catch {
        // إذا حُذف الملف القديم لسبب ما نعيد إنشاءه
        const streamRetry = new Readable();
        streamRetry.push(buffer);
        streamRetry.push(null);
        const created = await drive.files.create({
          requestBody: {
            name: PERMISSIONS_CONFIG_FILENAME,
            parents: [ROOT_FOLDER_ID],
            mimeType: 'application/json',
          },
          media: {
            mimeType: 'application/json',
            body: streamRetry,
          },
          fields: 'id',
        });
        savedFileId = created.data.id || undefined;
      }
    } else {
      const created = await drive.files.create({
        requestBody: {
          name: PERMISSIONS_CONFIG_FILENAME,
          parents: [ROOT_FOLDER_ID],
          mimeType: 'application/json',
        },
        media: {
          mimeType: 'application/json',
          body: stream,
        },
        fields: 'id',
      });
      savedFileId = created.data.id || undefined;
    }

    _adminStoreCache = {
      store: updatedStore,
      ts: Date.now(),
      fileId: savedFileId,
    };
    return updatedStore;
  };

  _saveQueuePromise = _saveQueuePromise.then(runSave, runSave);
  return _saveQueuePromise;
}

/**
 * قراءة صلاحيات الأقسام المخزنة سحابياً في ملف .sharecoc_permissions.json داخل المجلد الجذري
 */
export async function getCloudPermissions(
  forceRefresh: boolean = false
): Promise<Record<string, DepartmentPermissionConfig>> {
  const store = await getCloudAdminStore(forceRefresh);
  return store.departments;
}

/**
 * حفظ صلاحيات الأقسام سحابياً في ملف .sharecoc_permissions.json داخل المجلد الجذري
 */
export async function saveCloudPermissions(
  permissionsInput: Record<string, Partial<DepartmentPermissionConfig>>,
  replaceAll: boolean = false
): Promise<Record<string, DepartmentPermissionConfig>> {
  const updated = await persistCloudAdminStore((current) => {
    const merged: Record<string, DepartmentPermissionConfig> = replaceAll ? {} : { ...current.departments };
    for (const [deptName, cfg] of Object.entries(permissionsInput || {})) {
      if (!deptName) continue;
      merged[deptName] = normalizeDepartmentPermission(deptName, {
        ...(merged[deptName] || {}),
        ...cfg,
        departmentName: deptName,
        updatedAt: new Date().toISOString(),
      });
    }
    return {
      ...current,
      departments: merged,
    };
  });
  return updated.departments;
}

/**
 * تحديث وحفظ بيانات دخول الأدمن (اسم المستخدم وكلمة المرور) سحابياً
 */
export async function saveCloudAdminCredentials(
  username: string,
  password: string
): Promise<AdminCredentialsConfig> {
  const cleanUser = username.trim() || DEFAULT_ADMIN_CREDENTIALS.username;
  const cleanPass = password || DEFAULT_ADMIN_CREDENTIALS.password;
  const updated = await persistCloudAdminStore((current) => ({
    ...current,
    adminCredentials: {
      username: cleanUser,
      password: cleanPass,
      updatedAt: new Date().toISOString(),
    },
  }));
  return updated.adminCredentials;
}

/**
 * تحديث وحفظ قائمة الأجهزة المعتمدة سحابياً
 */
export async function saveCloudDevices(
  devicesInput: AuthorizedDeviceConfig[]
): Promise<AuthorizedDeviceConfig[]> {
  const updated = await persistCloudAdminStore((current) => ({
    ...current,
    devices: Array.isArray(devicesInput) ? devicesInput : current.devices,
  }));
  return updated.devices;
}

/**
 * جلب الشجرة الكاملة لكافة الأقسام والمجلدات الفرعية والمستندات (بأي عمق وبترقيم صفحات كامل)
 * مع دعم التخزين المؤقت في الذاكرة لتسريع التصفح والانتقال بين المجلدات فورياً
 */
export async function getAllCloudFiles(forceRefresh: boolean = false) {
  if (!forceRefresh && _cloudFilesCache && Date.now() - _cloudFilesCache.ts < CLOUD_FILES_CACHE_TTL_MS) {
    return _cloudFilesCache.data;
  }

  const idToPath = new Map<string, string>([[ROOT_FOLDER_ID, '']]);
  const allFolders: CloudFolderItem[] = [];
  const rawActiveFiles: { file: any; relFolder: string }[] = [];

  let currentLevel = [ROOT_FOLDER_ID];
  const visited = new Set<string>([ROOT_FOLDER_ID]);

  while (currentLevel.length > 0) {
    const nextLevel: string[] = [];
    for (let i = 0; i < currentLevel.length; i += 25) {
      const chunk = currentLevel.slice(i, i + 25);
      const children = await listChildrenBatch(chunk);
      for (const item of children) {
        const parentId = item.parents?.[0];
        if (!parentId || !idToPath.has(parentId)) continue;
        const parentPath = idToPath.get(parentId) || '';
        const name = item.name || '';
        if (isIgnoredName(name)) continue;

        const relPath = parentPath ? `${parentPath}/${name}` : name;

        if (item.mimeType === FOLDER_MIME) {
          if (visited.has(item.id!)) continue;
          visited.add(item.id!);
          idToPath.set(item.id!, relPath);
          const dept = relPath.split('/')[0];
          allFolders.push({
            id: item.id!,
            name,
            path: relPath,
            parentPath,
            department: dept,
            modifiedTime: item.modifiedTime,
          });
          nextLevel.push(item.id!);
        } else {
          if (String(item.mimeType || '').startsWith('application/vnd.google-apps.')) continue;
          rawActiveFiles.push({ file: item, relFolder: parentPath });
        }
      }
    }
    currentLevel = nextLevel;
  }

  allFolders.sort((a, b) => a.path.localeCompare(b.path, 'ar'));

  const departments = allFolders
    .filter((f) => !f.parentPath)
    .map((f) => ({ id: f.id, name: f.name, modifiedTime: f.modifiedTime }));

  const activeFiles = rawActiveFiles
    .sort((a, b) => String(b.file.modifiedTime || '').localeCompare(String(a.file.modifiedTime || '')))
    .map(({ file, relFolder }) => {
      const deptName = relFolder ? relFolder.split('/')[0] : 'القسم العام';
      const subFolder = relFolder.includes('/') ? relFolder.split('/').slice(1).join('/') : '';
      return {
        id: file.id!,
        name: file.name!,
        size: Number(file.size || 0),
        mimeType: file.mimeType || 'application/octet-stream',
        modifiedTime: file.modifiedTime!,
        folder: relFolder || 'القسم العام',
        department: deptName,
        subFolder,
        folderId: file.parents?.[0],
        previewUrl: file.webViewLink,
        downloadUrl: file.webContentLink,
        isDeleted: false,
      };
    });

  // جلب ملفات سلة المحذوفات (بصفحات تصل إلى 500 ملف)
  let trashFiles: any[] = [];
  try {
    const rawTrash: any[] = [];
    let trashToken: string | undefined = undefined;
    do {
      const trashRes: any = await drive.files.list({
        q: `trashed = true and mimeType != '${FOLDER_MIME}'`,
        fields: 'nextPageToken, files(id, name, size, mimeType, modifiedTime, webViewLink, webContentLink, parents)',
        orderBy: 'modifiedTime desc',
        pageSize: 250,
        pageToken: trashToken,
      });
      if (trashRes.data.files) {
        rawTrash.push(...trashRes.data.files);
      }
      trashToken = trashRes.data.nextPageToken || undefined;
    } while (trashToken && rawTrash.length < 500);

    trashFiles = rawTrash
      .filter((file) => !isIgnoredName(file.name))
      .map((file) => {
        const parentId = file.parents?.[0];
        const relFolder = (parentId && idToPath.get(parentId)) || 'القسم العام';
        const deptName = relFolder.split('/')[0] || 'القسم العام';
        const subFolder = relFolder.includes('/') ? relFolder.split('/').slice(1).join('/') : '';
        return {
          id: file.id!,
          name: file.name!,
          size: Number(file.size || 0),
          mimeType: file.mimeType || 'application/octet-stream',
          modifiedTime: file.modifiedTime!,
          folder: relFolder,
          department: deptName,
          subFolder,
          folderId: parentId,
          previewUrl: file.webViewLink,
          downloadUrl: file.webContentLink,
          isDeleted: true,
        };
      });
  } catch (e) {
    console.error('Error fetching trash files:', e);
  }

  const adminStore = await getCloudAdminStore();

  const result = {
    folders: departments,
    allFolders,
    files: [...activeFiles, ...trashFiles],
    permissions: adminStore.departments,
    adminCredentials: adminStore.adminCredentials,
    devices: adminStore.devices,
  };

  _cloudFilesCache = { data: result, ts: Date.now() };
  return result;
}

/**
 * رفع ملف لسحابة Google Drive داخل مجلد محدد أو مسار نسبي
 */
export async function uploadFileToDrive(
  buffer: Buffer,
  fileName: string,
  mimeType: string,
  folderId: string = ROOT_FOLDER_ID,
  folderPath?: string
) {
  let targetFolderId = folderId || ROOT_FOLDER_ID;
  if (folderPath && (!folderId || folderId === ROOT_FOLDER_ID)) {
    targetFolderId = await ensureCloudFolderPath(folderPath, ROOT_FOLDER_ID);
  }

  const stream = new Readable();
  stream.push(buffer);
  stream.push(null);

  const check = await drive.files.list({
    q: `'${targetFolderId}' in parents and name = '${qEscape(fileName)}' and mimeType != '${FOLDER_MIME}' and trashed = false`,
    fields: 'files(id)',
    pageSize: 5,
  });

  invalidateCloudFilesCache();
  if (check.data.files && check.data.files.length > 0) {
    const existingId = check.data.files[0].id!;
    const res = await drive.files.update({
      fileId: existingId,
      media: {
        mimeType,
        body: stream,
      },
      fields: 'id, name, size, modifiedTime, webViewLink, webContentLink',
    });
    return { ...res.data, isUpdate: true, folderId: targetFolderId };
  } else {
    const res = await drive.files.create({
      requestBody: {
        name: fileName,
        parents: [targetFolderId],
      },
      media: {
        mimeType,
        body: stream,
      },
      fields: 'id, name, size, modifiedTime, webViewLink, webContentLink',
    });
    return { ...res.data, isUpdate: false, folderId: targetFolderId };
  }
}

/**
 * بدء جلسة رفع مجزأ قابلة للاستئناف (Resumable Upload Session) لدعم الملفات الكبيرة والمجلدات دون قيود حجم الطلب
 */
export async function initResumableUpload(params: {
  fileName: string;
  mimeType?: string;
  fileSize?: number;
  folderId?: string;
  folderPath?: string;
  origin?: string;
}) {
  const { fileName, mimeType = 'application/octet-stream', fileSize, folderId, folderPath, origin } = params;
  let targetFolderId = folderId || ROOT_FOLDER_ID;
  if (folderPath && (!folderId || folderId === ROOT_FOLDER_ID)) {
    targetFolderId = await ensureCloudFolderPath(folderPath, ROOT_FOLDER_ID);
  }

  const check = await drive.files.list({
    q: `'${targetFolderId}' in parents and name = '${qEscape(fileName)}' and mimeType != '${FOLDER_MIME}' and trashed = false`,
    fields: 'files(id)',
    pageSize: 5,
  });
  const existingId = check.data.files?.[0]?.id || null;

  const tokenRes = await oauth2Client.getAccessToken();
  const accessToken = typeof tokenRes === 'string' ? tokenRes : tokenRes?.token;
  if (!accessToken) {
    throw new Error('تعذر توليد رمز المصادقة السحابية (OAuth2 Access Token)');
  }

  const initUrl = existingId
    ? `https://www.googleapis.com/upload/drive/v3/files/${existingId}?uploadType=resumable&fields=id,name,size,modifiedTime,webViewLink,webContentLink`
    : `https://www.googleapis.com/upload/drive/v3/files?uploadType=resumable&fields=id,name,size,modifiedTime,webViewLink,webContentLink`;

  const method = existingId ? 'PATCH' : 'POST';
  const metadata = existingId ? { name: fileName } : { name: fileName, parents: [targetFolderId] };

  const headers: Record<string, string> = {
    Authorization: `Bearer ${accessToken}`,
    'Content-Type': 'application/json; charset=UTF-8',
    'X-Upload-Content-Type': mimeType || 'application/octet-stream',
  };
  if (typeof fileSize === 'number' && fileSize >= 0) {
    headers['X-Upload-Content-Length'] = String(fileSize);
  }
  if (origin) {
    headers['Origin'] = origin;
  }

  const res = await fetch(initUrl, {
    method,
    headers,
    body: JSON.stringify(metadata),
  });

  if (!res.ok) {
    const errText = await res.text();
    throw new Error(`فشل تهيئة الرفع السحابي (${res.status}): ${errText}`);
  }

  const sessionUri = res.headers.get('location');
  if (!sessionUri) {
    throw new Error('لم يُرجع Google Drive رابط جلسة الرفع (Location header missing)');
  }

  return {
    sessionUri,
    folderId: targetFolderId,
    existingId,
    isUpdate: Boolean(existingId),
  };
}

/**
 * رفع جزء (Chunk) من الملف ضمن جلسة الرفع القابلة للاستئناف (Resumable Upload)
 */
export async function uploadResumableChunk(params: {
  sessionUri: string;
  chunkBuffer: Buffer;
  start: number;
  end: number;
  total: number;
}) {
  const { sessionUri, chunkBuffer, start, end, total } = params;
  const headers: Record<string, string> = {
    'Content-Length': String(chunkBuffer.length),
    'Content-Range': `bytes ${start}-${end}/${total}`,
  };

  const res = await fetch(sessionUri, {
    method: 'PUT',
    headers,
    body: new Uint8Array(chunkBuffer),
  });

  if (res.status === 308) {
    return {
      done: false,
      status: 308,
      range: res.headers.get('range') || null,
    };
  }

  if (res.status === 200 || res.status === 201) {
    invalidateCloudFilesCache();
    let data: any = null;
    try {
      data = await res.json();
    } catch {
      data = null;
    }
    return {
      done: true,
      status: res.status,
      file: data,
    };
  }

  const errText = await res.text();
  throw new Error(`فشل رفع جزء الملف (${res.status}): ${errText}`);
}

/**
 * استعلام حالة واستئناف جلسة رفع مجزأ للملفات الكبيرة من Google Drive (Resume Status Query)
 */
export async function getResumableUploadStatus(sessionUri: string, totalSize: number) {
  const res = await fetch(sessionUri, {
    method: 'PUT',
    headers: {
      'Content-Length': '0',
      'Content-Range': `bytes */${totalSize}`,
    },
  });

  if (res.status === 308) {
    const range = res.headers.get('range'); // e.g. "bytes=0-4194303"
    let nextOffset = 0;
    if (range) {
      const match = range.match(/bytes=0-(\d+)/);
      if (match) {
        nextOffset = parseInt(match[1], 10) + 1;
      }
    }
    return {
      done: false,
      status: 308,
      nextOffset,
      range,
    };
  }

  if (res.status === 200 || res.status === 201) {
    invalidateCloudFilesCache();
    let data: any = null;
    try {
      data = await res.json();
    } catch {
      data = null;
    }
    return {
      done: true,
      status: res.status,
      nextOffset: totalSize,
      file: data,
    };
  }

  const errText = await res.text();
  throw new Error(`تعذر استعلام حالة جلسة الرفع (${res.status}): ${errText}`);
}

/**
 * نقل ملف أو مجلد إلى سلة المحذوفات
 */
export async function deleteDriveItem(fileId: string) {
  invalidateCloudFilesCache();
  return await drive.files.update({
    fileId,
    requestBody: {
      trashed: true,
    },
  });
}

/**
 * استرجاع ملف من سلة المحذوفات
 */
export async function restoreDriveItem(fileId: string) {
  invalidateCloudFilesCache();
  return await drive.files.update({
    fileId,
    requestBody: {
      trashed: false,
    },
  });
}

/**
 * حذف نهائي لملف
 */
export async function permanentDeleteDriveItem(fileId: string) {
  invalidateCloudFilesCache();
  return await drive.files.delete({
    fileId,
  });
}

/**
 * إعادة تسمية ملف أو مجلد
 */
export async function renameDriveItem(fileId: string, newName: string) {
  invalidateCloudFilesCache();
  const res = await drive.files.update({
    fileId,
    requestBody: {
      name: newName,
    },
    fields: 'id, name',
  });
  return res.data;
}

/**
 * نقل ملف أو مجلد إلى مجلد هدف جديد في Google Drive
 */
export async function moveDriveItem(
  fileId: string,
  targetFolderId: string = ROOT_FOLDER_ID,
  targetFolderPath?: string
) {
  let finalTargetId = targetFolderId || ROOT_FOLDER_ID;
  if (targetFolderPath && (!targetFolderId || targetFolderId === ROOT_FOLDER_ID)) {
    finalTargetId = await ensureCloudFolderPath(targetFolderPath, ROOT_FOLDER_ID);
  }
  if (fileId === finalTargetId) {
    throw new Error('لا يمكن نقل المجلد داخل نفسه');
  }
  const currentMeta = await drive.files.get({
    fileId,
    fields: 'id, name, parents, mimeType',
  });
  const previousParents = (currentMeta.data.parents || []).join(',');
  if (currentMeta.data.parents?.includes(finalTargetId)) {
    return { ...currentMeta.data, targetFolderId: finalTargetId };
  }
  const res = await drive.files.update({
    fileId,
    addParents: finalTargetId,
    removeParents: previousParents || undefined,
    fields: 'id, name, parents, mimeType, modifiedTime',
  });
  return { ...res.data, targetFolderId: finalTargetId };
}

/**
 * نقل مجموعة ملفات/مجلدات دفعة واحدة بالتوازي إلى مجلد هدف في Google Drive
 */
export async function batchMoveDriveItems(
  fileIds: string[],
  targetFolderId: string = ROOT_FOLDER_ID,
  targetFolderPath?: string
) {
  let finalTargetId = targetFolderId || ROOT_FOLDER_ID;
  if (targetFolderPath && (!targetFolderId || targetFolderId === ROOT_FOLDER_ID)) {
    finalTargetId = await ensureCloudFolderPath(targetFolderPath, ROOT_FOLDER_ID);
  }
  const validIds = Array.from(new Set((fileIds || []).filter((id) => id && id !== finalTargetId)));
  const results = await runWithConcurrency(validIds, 6, async (id) => {
    return await moveDriveItem(id, finalTargetId);
  });

  const movedIds: string[] = [];
  const errors: { id: string; error: string }[] = [];
  results.forEach((r, idx) => {
    if (r.status === 'fulfilled') {
      movedIds.push(validIds[idx]);
    } else {
      errors.push({ id: validIds[idx], error: String((r.reason as any)?.message || r.reason) });
    }
  });
  return { movedIds, errors, targetFolderId: finalTargetId };
}

/**
 * نقل مجموعة عناصر إلى سلة المهملات بالتوازي
 */
export async function batchTrashDriveItems(fileIds: string[]) {
  const validIds = Array.from(new Set((fileIds || []).filter(Boolean)));
  const results = await runWithConcurrency(validIds, 8, async (id) => {
    await deleteDriveItem(id);
    return id;
  });
  const deletedIds: string[] = [];
  const errors: { id: string; error: string }[] = [];
  results.forEach((r, idx) => {
    if (r.status === 'fulfilled') {
      deletedIds.push(validIds[idx]);
    } else {
      errors.push({ id: validIds[idx], error: String((r.reason as any)?.message || r.reason) });
    }
  });
  return { deletedIds, errors };
}

/**
 * استرجاع مجموعة عناصر من سلة المهملات بالتوازي
 */
export async function batchRestoreDriveItems(fileIds: string[]) {
  const validIds = Array.from(new Set((fileIds || []).filter(Boolean)));
  const results = await runWithConcurrency(validIds, 8, async (id) => {
    await restoreDriveItem(id);
    return id;
  });
  const restoredIds: string[] = [];
  const errors: { id: string; error: string }[] = [];
  results.forEach((r, idx) => {
    if (r.status === 'fulfilled') {
      restoredIds.push(validIds[idx]);
    } else {
      errors.push({ id: validIds[idx], error: String((r.reason as any)?.message || r.reason) });
    }
  });
  return { restoredIds, errors };
}

/**
 * حذف نهائي لمجموعة عناصر من سلة المهملات بالتوازي (سريع جداً لتفريغ السلة)
 */
export async function batchPermanentDeleteDriveItems(fileIds: string[]) {
  const validIds = Array.from(new Set((fileIds || []).filter(Boolean)));
  const results = await runWithConcurrency(validIds, 8, async (id) => {
    await permanentDeleteDriveItem(id);
    return id;
  });
  const purgedIds: string[] = [];
  const errors: { id: string; error: string }[] = [];
  results.forEach((r, idx) => {
    if (r.status === 'fulfilled') {
      purgedIds.push(validIds[idx]);
    } else {
      errors.push({ id: validIds[idx], error: String((r.reason as any)?.message || r.reason) });
    }
  });
  return { purgedIds, errors };
}

/**
 * جلب استجابة بث مباشر (Stream) لملف من Google Drive لدعم عارض الصور والوسائط وملفات PDF والتنزيل المباشر
 */
export async function getDriveFileStreamResponse(fileId: string, rangeHeader?: string | null) {
  const metaRes = await drive.files.get({
    fileId,
    fields: 'id, name, mimeType, size',
  });
  const meta = metaRes.data;

  const tokenRes = await oauth2Client.getAccessToken();
  const accessToken = typeof tokenRes === 'string' ? tokenRes : tokenRes?.token;
  if (!accessToken) {
    throw new Error('تعذر الحصول على رمز الوصول السحابي');
  }

  const headers: Record<string, string> = {
    Authorization: `Bearer ${accessToken}`,
  };
  if (rangeHeader) {
    headers['Range'] = rangeHeader;
  }

  const mediaUrl = `https://www.googleapis.com/drive/v3/files/${encodeURIComponent(fileId)}?alt=media`;
  const upstreamRes = await fetch(mediaUrl, { headers });
  if (!upstreamRes.ok && upstreamRes.status !== 206) {
    throw new Error(`فشل جلب محتوى الملف من السحابة (${upstreamRes.status})`);
  }

  return {
    meta,
    upstreamRes,
  };
}
