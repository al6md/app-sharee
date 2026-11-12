import { google } from 'googleapis';
import { Readable } from 'stream';
import crypto from 'crypto';

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
  if (/^[0-9a-f]{8}$/i.test(name)) return true;
  return IGNORED_SUFFIXES.some((s) => low.endsWith(s));
}

function qEscape(val: string): string {
  return val.replace(/\\/g, '\\\\').replace(/'/g, "\\'");
}

const oauth2Client = new google.auth.OAuth2(CLIENT_ID, CLIENT_SECRET);
oauth2Client.setCredentials({ refresh_token: REFRESH_TOKEN });

export const drive = google.drive({ version: 'v3', auth: oauth2Client });

// كاش قصير لبيانات الملف (الاسم/النوع/الحجم): Office يرسل عدة طلبات (HEAD/GET/Range) لكل فتح،
// وكل طلب كان يستدعي files.get من جديد مما يبطئ فتح الملف.
const FILE_META_TTL_MS = 30_000;
const fileMetaCache = new Map<string, { at: number; data: any; pending?: Promise<any> }>();

export async function getCachedDriveFileMeta(fileId: string) {
  const now = Date.now();
  const hit = fileMetaCache.get(fileId);
  if (hit && !hit.pending && now - hit.at < FILE_META_TTL_MS) return hit.data;
  if (hit?.pending) return hit.pending;

  const pending = drive.files
    .get({ fileId, fields: 'id, name, mimeType, size' })
    .then((res) => {
      fileMetaCache.set(fileId, { at: Date.now(), data: res.data });
      return res.data;
    })
    .catch((err) => {
      fileMetaCache.delete(fileId);
      throw err;
    });
  fileMetaCache.set(fileId, { at: now, data: hit?.data, pending });
  return pending;
}

export function invalidateDriveFileMeta(fileId?: string) {
  if (fileId) fileMetaCache.delete(fileId);
  else fileMetaCache.clear();
}

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
  deptUsername?: string;
  deptPassword?: string;
  authorizedDevices?: string[];
  updatedAt?: string;
}

export interface AdminCredentialsConfig {
  username: string;
  password: string;
  updatedAt: string;
}

export interface DeviceDeptPermissionConfig {
  canView?: boolean;
  canDownload?: boolean;
  canUpload?: boolean;
  canCreateFolder?: boolean;
  canEdit?: boolean;
  canRename?: boolean;
  canMove?: boolean;
  canDelete?: boolean;
  canPermanentDelete?: boolean;
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
  department?: string;
  authorizedDepts?: string[];
  registeredAt?: string;
  accessRole?: 'admin' | 'supervisor' | 'data_entry' | 'viewer';
  allowedAccessSections?: string[];
  departmentPermissions?: Record<string, DeviceDeptPermissionConfig>;
}

export interface AccessHubSecurityConfig {
  enabled: boolean;
  username?: string;
  password?: string;
  pinCode?: string;
  authorizedDevices?: string[];
  roles?: Record<string, 'admin' | 'supervisor' | 'data_entry' | 'viewer'>;
  allowedSections?: Record<string, string[]>;
  securityEpoch?: number;
  updatedAt?: string;
}

const ADMIN_TOKEN_SECRET = process.env.ADMIN_JWT_SECRET || 'sharecoc-admin-secure-token-secret-2026';

export function createAdminSessionToken(username: string): string {
  const ts = Date.now();
  const raw = `${username}:${ts}:${ADMIN_TOKEN_SECRET}`;
  const sig = crypto.createHash('sha256').update(raw).digest('hex').substring(0, 32);
  const payload = Buffer.from(JSON.stringify({ u: username, ts, sig })).toString('base64url');
  return payload;
}

export function isValidAdminToken(tokenOrHeader?: string | null): boolean {
  if (!tokenOrHeader) return false;
  const token = String(tokenOrHeader).replace(/^Bearer\s+/i, '').trim();
  if (!token) return false;
  try {
    const jsonStr = Buffer.from(token, 'base64url').toString('utf-8');
    const obj = JSON.parse(jsonStr);
    if (!obj || !obj.u || !obj.ts || !obj.sig) return false;
    // انتهاء الصلاحية بعد 48 ساعة
    if (Date.now() - Number(obj.ts) > 48 * 60 * 60 * 1000) return false;
    const expectedRaw = `${obj.u}:${obj.ts}:${ADMIN_TOKEN_SECRET}`;
    const expectedSig = crypto.createHash('sha256').update(expectedRaw).digest('hex').substring(0, 32);
    return obj.sig === expectedSig;
  } catch {
    return false;
  }
}

export function getDeviceEffectiveDeptPerms(
  device: AuthorizedDeviceConfig | undefined,
  departmentName: string,
  baseDeptConfig?: DepartmentPermissionConfig
): DeviceDeptPermissionConfig {
  const base: DeviceDeptPermissionConfig = {
    canView: baseDeptConfig?.canView ?? true,
    canDownload: baseDeptConfig?.canDownload ?? true,
    canUpload: baseDeptConfig?.canUpload ?? true,
    canCreateFolder: baseDeptConfig?.canCreateFolder ?? true,
    canEdit: baseDeptConfig?.canEdit ?? true,
    canRename: baseDeptConfig?.canRename ?? true,
    canMove: baseDeptConfig?.canMove ?? true,
    canDelete: baseDeptConfig?.canDelete ?? true,
    canPermanentDelete: baseDeptConfig?.canPermanentDelete ?? true,
  };

  if (!device || !device.departmentPermissions) {
    return base;
  }

  const custom = device.departmentPermissions[departmentName];
  if (!custom) return base;

  return {
    canView: custom.canView ?? base.canView,
    canDownload: custom.canDownload ?? base.canDownload,
    canUpload: custom.canUpload ?? base.canUpload,
    canCreateFolder: custom.canCreateFolder ?? base.canCreateFolder,
    canEdit: custom.canEdit ?? base.canEdit,
    canRename: custom.canRename ?? base.canRename,
    canMove: custom.canMove ?? base.canMove,
    canDelete: custom.canDelete ?? base.canDelete,
    canPermanentDelete: custom.canPermanentDelete ?? base.canPermanentDelete,
  };
}

export function isDeviceAllowedAccessSection(
  device: AuthorizedDeviceConfig | undefined,
  sectionName: string
): boolean {
  if (!device || !device.isAuthorized) return false;
  if (device.accessRole === 'admin') return true;
  if (!Array.isArray(device.allowedAccessSections) || device.allowedAccessSections.length === 0) {
    return true;
  }
  return device.allowedAccessSections.includes(sectionName);
}

export function sanitizeAdminStoreForPublic(store: CloudAdminStore) {
  const sanitizedAdminCreds = {
    username: store.adminCredentials?.username || 'admin',
    updatedAt: store.adminCredentials?.updatedAt || '',
  };

  const isHubProtected = Boolean(
    store.accessHubSecurity?.enabled ||
    store.accessHubSecurity?.username ||
    store.accessHubSecurity?.password ||
    store.accessHubSecurity?.pinCode
  );

  const sanitizedHubSec = {
    enabled: isHubProtected,
    authorizedDevices: store.accessHubSecurity?.authorizedDevices || [],
    roles: store.accessHubSecurity?.roles || {},
    allowedSections: store.accessHubSecurity?.allowedSections || {},
    securityEpoch: store.accessHubSecurity?.securityEpoch || 0,
    updatedAt: store.accessHubSecurity?.updatedAt || '',
    isProtected: isHubProtected,
    hasCreds: Boolean(store.accessHubSecurity?.username || store.accessHubSecurity?.password || store.accessHubSecurity?.pinCode),
  };

  const sanitizedDepts: Record<string, any> = {};
  for (const [dName, dCfg] of Object.entries(store.departments || {})) {
    sanitizedDepts[dName] = {
      departmentName: dCfg.departmentName || dName,
      canView: dCfg.canView,
      canDownload: dCfg.canDownload,
      canUpload: dCfg.canUpload,
      canCreateFolder: dCfg.canCreateFolder,
      canEdit: dCfg.canEdit,
      canRename: dCfg.canRename,
      canMove: dCfg.canMove,
      canDelete: dCfg.canDelete,
      canPermanentDelete: dCfg.canPermanentDelete,
      authorizedDevices: dCfg.authorizedDevices || [],
      updatedAt: dCfg.updatedAt,
      isProtected: Boolean(dCfg.pinCode || dCfg.deptUsername || dCfg.deptPassword),
      hasUserPass: Boolean(dCfg.deptUsername || dCfg.deptPassword),
      hasPin: Boolean(dCfg.pinCode),
    };
  }

  if (sanitizedDepts['مركز بيانات Access']) {
    sanitizedDepts['مركز بيانات Access'].isProtected = isHubProtected;
    sanitizedDepts['مركز بيانات Access'].enabled = isHubProtected;
    sanitizedDepts['مركز بيانات Access'].securityEpoch = store.accessHubSecurity?.securityEpoch || 0;
    sanitizedDepts['مركز بيانات Access'].authorizedDevices = store.accessHubSecurity?.authorizedDevices || [];
  }

  return {
    departments: sanitizedDepts,
    devices: store.devices || [],
    accessHubSecurity: sanitizedHubSec,
    adminCredentials: sanitizedAdminCreds,
  };
}

export interface CloudAdminStore {
  version: number;
  updatedAt: string;
  adminCredentials: AdminCredentialsConfig;
  devices: AuthorizedDeviceConfig[];
  departments: Record<string, DepartmentPermissionConfig>;
  accessHubSecurity?: AccessHubSecurityConfig;
}

export const PERMISSIONS_CONFIG_FILENAME = '.sharecoc_permissions.json';

export const DEFAULT_ACCESS_HUB_SECURITY: AccessHubSecurityConfig = {
  enabled: false,
  username: '',
  password: '',
  pinCode: '',
  authorizedDevices: [],
  securityEpoch: 0,
  updatedAt: new Date(0).toISOString(),
};

export const DEFAULT_ADMIN_CREDENTIALS: AdminCredentialsConfig = {
  username: 'admin',
  password: 'admin1234',
  updatedAt: new Date(0).toISOString(),
};

export const DEFAULT_AUTHORIZED_DEVICES: AuthorizedDeviceConfig[] = [];

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
    deptUsername: typeof raw.deptUsername === 'string' ? raw.deptUsername.trim() : (typeof raw.username === 'string' ? raw.username.trim() : ''),
    deptPassword: typeof raw.deptPassword === 'string' ? raw.deptPassword.trim() : (typeof raw.password === 'string' ? raw.password.trim() : ''),
    authorizedDevices: Array.isArray(raw.authorizedDevices) ? raw.authorizedDevices.filter(Boolean) : [],
    updatedAt: raw.updatedAt || new Date().toISOString(),
  };
}

let _adminStoreCache: { store: CloudAdminStore; ts: number; fileId?: string } | null = null;
const PERMISSIONS_CACHE_TTL_MS = 20000;
let _saveQueuePromise: Promise<any> = Promise.resolve();

// ذاكرة تخزين مؤقتة لشجرة الملفات والأقسام لتسريع التنقل وجعله فورياً (Sub-second navigation)
let _cloudFilesCache: { data: any; ts: number } | null = null;
const CLOUD_FILES_CACHE_TTL_MS = 8000; // 8 ثوانٍ كاش خفيف يمنع ازدحام طلبات Google Drive

export function invalidateCloudFilesCache() {
  _cloudFilesCache = null;
}

let _lastCloudStateSig: string | null = null;

/**
 * فحص سريع وخفيف للتغييرات السحابية بدقة 100% عبر مقارنة بصمات أحدث العناصر المعدلة.
 * يعمل بمرونة تامة سواء محلياً أو على خوادم Serverless (Vercel) بدون فقدان الجلسة.
 */
export async function checkCloudChanges(clientSig?: string | null): Promise<{ changed: boolean; sig: string }> {
  try {
    const res: any = await drive.files.list({
      q: "mimeType != 'application/vnd.google-apps.folder'",
      orderBy: 'modifiedTime desc',
      pageSize: 4,
      fields: 'files(id, name, modifiedTime, md5Checksum, trashed)',
    });
    const items = res.data.files || [];
    const currentSig = items
      .map((f: any) => `${f.id}:${f.modifiedTime || ''}:${f.md5Checksum || ''}:${f.trashed ? 1 : 0}`)
      .join('|');

    const compareSig = clientSig || _lastCloudStateSig;
    const changed = Boolean(compareSig && currentSig && compareSig !== currentSig);

    if (changed || !clientSig) {
      invalidateCloudFilesCache();
    }
    _lastCloudStateSig = currentSig;

    return { changed, sig: currentSig };
  } catch {
    return { changed: false, sig: clientSig || '' };
  }
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
  // إذا تم التحديث محلياً في الذاكرة خلال آخر 8 ثوانٍ، نعتمد دائماً على النسخة الأحدث لمنع سباق التزامن مع Google Drive
  if (_adminStoreCache && Date.now() - _adminStoreCache.ts < 8000) {
    return _adminStoreCache.store;
  }
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
        devices: [],
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

    const rawDevices = rawData.devices !== undefined ? rawData.devices : rawData.__authorized_devices__;
    const devices: AuthorizedDeviceConfig[] =
      Array.isArray(rawDevices)
        ? rawDevices.map((dev: any, idx: number) => ({
            id: String(dev.id || `dev-${idx + 1}`),
            name: String(dev.name || `COC-DEVICE-${idx + 1}`),
            user: String(dev.user || 'موظف الغرفة'),
            os: String(dev.os || 'Windows 10/11'),
            machineGuid: String(dev.machineGuid || `COC-GUID-${idx + 1}`),
            isAuthorized: dev.isAuthorized !== undefined ? Boolean(dev.isAuthorized) : true,
            lastSeen: String(dev.lastSeen || 'نشط'),
            status: dev.isAuthorized === false ? 'موقوف' : String(dev.status || 'متصل الآن'),
            department: dev.department ? String(dev.department) : undefined,
            authorizedDepts: Array.isArray(dev.authorizedDepts)
              ? dev.authorizedDepts
              : (dev.department ? [String(dev.department)] : []),
            registeredAt: dev.registeredAt ? String(dev.registeredAt) : undefined,
            accessRole: dev.accessRole || rawAccessSec?.roles?.[dev.machineGuid] || 'data_entry',
          }))
        : [];

    const rawAccessSec = rawData.accessHubSecurity || rawData.departments?.['مركز بيانات Access'];
    const hubUser = String(rawAccessSec?.username || rawAccessSec?.deptUsername || '').trim();
    const hubPass = String(rawAccessSec?.password || rawAccessSec?.deptPassword || '').trim();
    const hubPin = String(rawAccessSec?.pinCode || '').trim();
    const hasHubCreds = Boolean(hubUser || hubPass || hubPin);
    const accessHubSecurity: AccessHubSecurityConfig = {
      enabled: rawAccessSec?.enabled !== undefined ? (Boolean(rawAccessSec.enabled) || hasHubCreds) : hasHubCreds,
      username: hubUser,
      password: hubPass,
      pinCode: hubPin,
      authorizedDevices: Array.isArray(rawAccessSec?.authorizedDevices)
        ? rawAccessSec.authorizedDevices.filter(Boolean)
        : [],
      roles: rawAccessSec?.roles && typeof rawAccessSec.roles === 'object' ? rawAccessSec.roles : {},
      updatedAt: rawAccessSec?.updatedAt || new Date().toISOString(),
    };

    const store: CloudAdminStore = {
      version: 3,
      updatedAt: rawData.updatedAt || new Date().toISOString(),
      adminCredentials,
      devices,
      departments: normalizedDepts,
      accessHubSecurity,
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
      devices: [],
      departments: {},
      accessHubSecurity: { ...DEFAULT_ACCESS_HUB_SECURITY },
    };
  }
}

/**
 * حفظ ملف الإعدادات الإدارية والصلاحيات الكامل في Google Drive بشكل متسلسل ذري (Atomic Queue)
 */
export async function persistCloudAdminStore(
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
      accessHubSecurity: baseStore.accessHubSecurity
        ? { ...baseStore.accessHubSecurity }
        : { ...DEFAULT_ACCESS_HUB_SECURITY },
    });
    updatedStore.version = 3;
    updatedStore.updatedAt = new Date().toISOString();

    // تحديث الذاكرة المؤقتة فوراً قبل انتهاء الكتابة السحابية لضمان استجابة لحظية 100%
    _adminStoreCache = {
      store: updatedStore,
      ts: Date.now(),
      fileId: _adminStoreCache?.fileId,
    };

    if (_cloudFilesCache && _cloudFilesCache.data) {
      _cloudFilesCache.data.permissions = updatedStore.departments;
      _cloudFilesCache.data.devices = updatedStore.devices;
      _cloudFilesCache.data.accessHubSecurity = updatedStore.accessHubSecurity;
    }
    invalidateCloudFilesCache();

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
 * اعتماد وتسجيل جهاز لقسم معين سحابياً (يخزن اسم الجهاز ونظامه في لوحة الأدمن)
 */
export async function authorizeDeviceForDepartment(deviceInfo: {
  machineGuid: string;
  name: string;
  os?: string;
  user?: string;
  departmentName: string;
}): Promise<{ success: boolean; device: AuthorizedDeviceConfig; departments: Record<string, DepartmentPermissionConfig> }> {
  const cleanGuid = String(deviceInfo.machineGuid || '').trim();
  const cleanName = String(deviceInfo.name || '').trim() || 'جهاز غير مسمى';
  const cleanDept = String(deviceInfo.departmentName || '').trim();
  const cleanOs = String(deviceInfo.os || 'متصفح ويب');
  const cleanUser = String(deviceInfo.user || 'موظف الغرفة');

  if (!cleanGuid) throw new Error('معرف الجهاز GUID مطلوب');
  if (!cleanDept) throw new Error('اسم القسم مطلوب');

  const updated = await persistCloudAdminStore((current) => {
    const devices = [...(current.devices || [])];
    const devIndex = devices.findIndex((d) => d.machineGuid === cleanGuid);

    let devRecord: AuthorizedDeviceConfig;
    if (devIndex >= 0) {
      const existing = devices[devIndex];
      const depts = new Set<string>(Array.isArray(existing.authorizedDepts) ? existing.authorizedDepts : []);
      depts.add(cleanDept);
      devRecord = {
        ...existing,
        name: cleanName || existing.name,
        os: cleanOs || existing.os,
        user: cleanUser || existing.user,
        department: cleanDept,
        authorizedDepts: Array.from(depts),
        isAuthorized: true,
        lastSeen: 'متصل الآن',
        status: 'متصل الآن',
      };
      devices[devIndex] = devRecord;
    } else {
      devRecord = {
        id: `dev-${Date.now()}-${Math.random().toString(36).substring(2, 7)}`,
        name: cleanName,
        user: cleanUser,
        os: cleanOs,
        machineGuid: cleanGuid,
        isAuthorized: true,
        lastSeen: 'متصل الآن',
        status: 'متصل الآن',
        department: cleanDept,
        authorizedDepts: [cleanDept],
        registeredAt: new Date().toISOString(),
      };
      devices.push(devRecord);
    }

    // تحديث القسم لإضافة معرف الجهاز إلى قائمته
    const departments = { ...(current.departments || {}) };
    if (!departments[cleanDept]) {
      departments[cleanDept] = getDefaultDepartmentPermission(cleanDept);
    }
    const currentAuthed = new Set<string>(departments[cleanDept].authorizedDevices || []);
    currentAuthed.add(cleanGuid);
    departments[cleanDept] = {
      ...departments[cleanDept],
      authorizedDevices: Array.from(currentAuthed),
      updatedAt: new Date().toISOString(),
    };

    return {
      ...current,
      devices,
      departments,
    };
  });

  const matchingDev = updated.devices.find((d) => d.machineGuid === cleanGuid) || {
    id: cleanGuid,
    name: cleanName,
    user: cleanUser,
    os: cleanOs,
    machineGuid: cleanGuid,
    isAuthorized: true,
    lastSeen: 'متصل الآن',
    department: cleanDept,
  };

  return { success: true, device: matchingDev, departments: updated.departments };
}

/**
 * حذف جهاز وسحب اعتماده نهائياً من كافة الأقسام (حصرياً من لوحة تحكم الأدمن)
 */
export async function revokeOrDeleteDevice(
  identifier: string // id or machineGuid
): Promise<{ success: boolean; devices: AuthorizedDeviceConfig[]; departments: Record<string, DepartmentPermissionConfig>; accessHubSecurity?: AccessHubSecurityConfig }> {
  const cleanId = String(identifier || '').trim();
  if (!cleanId) throw new Error('معرف الجهاز مطلوب');

  const updated = await persistCloudAdminStore((current) => {
    const targetDev = current.devices.find((d) => d.id === cleanId || d.machineGuid === cleanId);
    const targetGuid = targetDev?.machineGuid || cleanId;

    // 1. حذف الجهاز من قائمة الأجهزة
    const devices = (current.devices || []).filter((d) => d.id !== cleanId && d.machineGuid !== cleanId);

    // 2. إزالة بصمة الجهاز من جميع الأقسام المعتمدة
    const departments = { ...(current.departments || {}) };
    for (const [dName, dCfg] of Object.entries(departments)) {
      if (Array.isArray(dCfg.authorizedDevices) && dCfg.authorizedDevices.includes(targetGuid)) {
        departments[dName] = {
          ...dCfg,
          authorizedDevices: dCfg.authorizedDevices.filter((g) => g !== targetGuid),
          updatedAt: new Date().toISOString(),
        };
      }
    }

    // 3. إزالة بصمة الجهاز من أمان مركز بيانات Access وصلاحياته
    let accessHubSecurity = current.accessHubSecurity ? { ...current.accessHubSecurity } : undefined;
    if (accessHubSecurity) {
      const curRoles = { ...(accessHubSecurity.roles || {}) };
      delete curRoles[targetGuid];
      const curAuths = Array.isArray(accessHubSecurity.authorizedDevices)
        ? accessHubSecurity.authorizedDevices.filter((g) => g !== targetGuid)
        : [];
      accessHubSecurity = {
        ...accessHubSecurity,
        authorizedDevices: curAuths,
        roles: curRoles,
        updatedAt: new Date().toISOString(),
      };
    }

    return {
      ...current,
      devices,
      departments,
      accessHubSecurity,
    };
  });

  return { success: true, devices: updated.devices, departments: updated.departments, accessHubSecurity: updated.accessHubSecurity };
}

/**
 * حفظ إعدادات أمان مركز بيانات Access وتحديث كلمة المرور واسم المستخدم وقائمة الأجهزة
 */
export async function saveAccessHubSecurity(
  secInput: Partial<AccessHubSecurityConfig> & { resetAuthorizedDevices?: boolean }
): Promise<AccessHubSecurityConfig> {
  const updated = await persistCloudAdminStore((current) => {
    const curSec = current.accessHubSecurity || { ...DEFAULT_ACCESS_HUB_SECURITY };
    const username = secInput.username !== undefined ? String(secInput.username).trim() : curSec.username;
    const password = secInput.password !== undefined ? String(secInput.password).trim() : curSec.password;
    const pinCode = secInput.pinCode !== undefined ? String(secInput.pinCode).trim() : curSec.pinCode;
    const hasCredentials = Boolean(username || password || pinCode);
    const enabled = secInput.enabled !== undefined ? (Boolean(secInput.enabled) || hasCredentials) : (curSec.enabled || hasCredentials);

    // إذا تغيرت كلمة المرور أو اسم المستخدم أو طلب الأدمن صراحة إعادة ضبط الاعتماد
    const credsChanged = (username !== curSec.username) || (password !== curSec.password) || (pinCode !== curSec.pinCode);
    let authDevs = Array.isArray(secInput.authorizedDevices) ? secInput.authorizedDevices : curSec.authorizedDevices || [];
    if (secInput.resetAuthorizedDevices || (credsChanged && hasCredentials)) {
      authDevs = [];
    }

    const roles = secInput.roles !== undefined ? secInput.roles : curSec.roles || {};

    const newSec: AccessHubSecurityConfig = {
      enabled,
      username,
      password,
      pinCode,
      authorizedDevices: authDevs,
      roles,
      allowedSections: secInput.allowedSections || curSec.allowedSections || {},
      securityEpoch: Date.now(),
      updatedAt: new Date().toISOString(),
    };

    const departments = { ...(current.departments || {}) };
    departments['مركز بيانات Access'] = {
      departmentName: 'مركز بيانات Access',
      canView: true,
      canDownload: true,
      canUpload: true,
      canCreateFolder: true,
      canEdit: true,
      canRename: true,
      canMove: true,
      canDelete: true,
      canPermanentDelete: true,
      deptUsername: username,
      deptPassword: password,
      pinCode,
      authorizedDevices: authDevs,
      updatedAt: new Date().toISOString(),
    };

    return {
      ...current,
      departments,
      accessHubSecurity: newSec,
    };
  });

  return updated.accessHubSecurity || DEFAULT_ACCESS_HUB_SECURITY;
}

/**
 * تسجيل واعتماد جهاز جديد لمركز بيانات Access لمرة واحدة فقط
 */
export async function authorizeDeviceForAccessHub(deviceInfo: {
  machineGuid: string;
  name: string;
  os?: string;
  user?: string;
}): Promise<{ success: boolean; device: AuthorizedDeviceConfig; accessHubSecurity: AccessHubSecurityConfig }> {
  const cleanGuid = String(deviceInfo.machineGuid || '').trim();
  const cleanName = String(deviceInfo.name || '').trim() || 'جهاز موظف';
  const cleanOs = String(deviceInfo.os || 'متصفح ويب');
  const cleanUser = String(deviceInfo.user || 'موظف الغرفة');

  if (!cleanGuid) throw new Error('معرف الجهاز مطلوب');

  const updated = await persistCloudAdminStore((current) => {
    const devices = [...(current.devices || [])];
    const devIndex = devices.findIndex((d) => d.machineGuid === cleanGuid);

    let devRecord: AuthorizedDeviceConfig;
    if (devIndex >= 0) {
      const existing = devices[devIndex];
      const depts = new Set<string>(Array.isArray(existing.authorizedDepts) ? existing.authorizedDepts : []);
      depts.add('مركز بيانات Access');
      devRecord = {
        ...existing,
        name: cleanName || existing.name,
        os: cleanOs || existing.os,
        user: cleanUser || existing.user,
        department: existing.department || 'مركز بيانات Access',
        authorizedDepts: Array.from(depts),
        isAuthorized: true,
        lastSeen: 'متصل الآن',
        status: 'متصل الآن',
        accessRole: existing.accessRole || 'data_entry',
      };
      devices[devIndex] = devRecord;
    } else {
      devRecord = {
        id: `dev-${Date.now()}-${Math.random().toString(36).substring(2, 7)}`,
        name: cleanName,
        user: cleanUser,
        os: cleanOs,
        machineGuid: cleanGuid,
        isAuthorized: true,
        lastSeen: 'متصل الآن',
        status: 'متصل الآن',
        department: 'مركز بيانات Access',
        authorizedDepts: ['مركز بيانات Access'],
        accessRole: 'data_entry',
        registeredAt: new Date().toISOString(),
      };
      devices.push(devRecord);
    }

    const curSec = current.accessHubSecurity || { ...DEFAULT_ACCESS_HUB_SECURITY };
    const curAuthed = new Set<string>(curSec.authorizedDevices || []);
    curAuthed.add(cleanGuid);
    const curRoles = { ...(curSec.roles || {}) };
    if (!curRoles[cleanGuid]) {
      curRoles[cleanGuid] = 'data_entry';
    }

    const newSec: AccessHubSecurityConfig = {
      ...curSec,
      authorizedDevices: Array.from(curAuthed),
      roles: curRoles,
      updatedAt: new Date().toISOString(),
    };

    const departments = { ...(current.departments || {}) };
    if (!departments['مركز بيانات Access']) {
      departments['مركز بيانات Access'] = getDefaultDepartmentPermission('مركز بيانات Access');
    }
    departments['مركز بيانات Access'] = {
      ...departments['مركز بيانات Access'],
      deptUsername: newSec.username,
      deptPassword: newSec.password,
      pinCode: newSec.pinCode,
      authorizedDevices: Array.from(curAuthed),
      updatedAt: new Date().toISOString(),
    };

    return {
      ...current,
      devices,
      departments,
      accessHubSecurity: newSec,
    };
  });

  const matchingDev = updated.devices.find((d) => d.machineGuid === cleanGuid) || {
    id: cleanGuid,
    name: cleanName,
    user: cleanUser,
    os: cleanOs,
    machineGuid: cleanGuid,
    isAuthorized: true,
    lastSeen: 'متصل الآن',
    department: 'مركز بيانات Access',
  };

  return { success: true, device: matchingDev, accessHubSecurity: updated.accessHubSecurity || DEFAULT_ACCESS_HUB_SECURITY };
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
        if (relPath.split('/').some(p => p.startsWith('.'))) continue;

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
  const sanitized = sanitizeAdminStoreForPublic(adminStore);

  const result = {
    folders: departments,
    allFolders,
    files: [...activeFiles, ...trashFiles],
    permissions: sanitized.departments,
    adminCredentials: sanitized.adminCredentials,
    devices: sanitized.devices,
    accessHubSecurity: sanitized.accessHubSecurity,
  };

  _cloudFilesCache = { data: result, ts: Date.now() };
  return result;
}

/**
 * تحديث الصلاحيات المخصصة لجهاز معين في نظام المستندات وقواعد بيانات Access
 */
export async function updateDeviceCustomPermissions(
  machineGuid: string,
  updates: {
    name?: string;
    user?: string;
    department?: string;
    authorizedDepts?: string[];
    accessRole?: 'admin' | 'supervisor' | 'data_entry' | 'viewer';
    allowedAccessSections?: string[];
    departmentPermissions?: Record<string, DeviceDeptPermissionConfig>;
    isAuthorized?: boolean;
  }
): Promise<{ success: boolean; device: AuthorizedDeviceConfig; devices: AuthorizedDeviceConfig[] }> {
  const cleanGuid = String(machineGuid || '').trim();
  if (!cleanGuid) throw new Error('معرف الجهاز مطلوب');

  const updated = await persistCloudAdminStore((current) => {
    const devices = [...(current.devices || [])];
    const devIdx = devices.findIndex((d) => d.machineGuid === cleanGuid || d.id === cleanGuid);
    if (devIdx < 0) {
      throw new Error(`الجهاز ذو المعرف "${cleanGuid}" غير موجود في قائمة الأجهزة`);
    }

    const cur = devices[devIdx];
    const updatedDev: AuthorizedDeviceConfig = {
      ...cur,
      name: updates.name !== undefined ? updates.name : cur.name,
      user: updates.user !== undefined ? updates.user : cur.user,
      department: updates.department !== undefined ? updates.department : cur.department,
      isAuthorized: updates.isAuthorized !== undefined ? updates.isAuthorized : cur.isAuthorized,
      authorizedDepts: updates.authorizedDepts !== undefined ? updates.authorizedDepts : cur.authorizedDepts,
      accessRole: updates.accessRole !== undefined ? updates.accessRole : cur.accessRole,
      allowedAccessSections: updates.allowedAccessSections !== undefined ? updates.allowedAccessSections : cur.allowedAccessSections,
      departmentPermissions: updates.departmentPermissions !== undefined ? updates.departmentPermissions : cur.departmentPermissions,
    };
    devices[devIdx] = updatedDev;

    // مزامنة أقسام المستندات في departments
    const departments = { ...(current.departments || {}) };
    const allowedDepts = new Set(updatedDev.authorizedDepts || []);
    for (const [dName, dCfg] of Object.entries(departments)) {
      const curAuthed = new Set(dCfg.authorizedDevices || []);
      if (allowedDepts.has(dName)) {
        curAuthed.add(cleanGuid);
      } else {
        curAuthed.delete(cleanGuid);
      }
      departments[dName] = {
        ...dCfg,
        authorizedDevices: Array.from(curAuthed),
        updatedAt: new Date().toISOString(),
      };
    }

    // مزامنة أمان Access Hub
    let accessHubSecurity = current.accessHubSecurity ? { ...current.accessHubSecurity } : { ...DEFAULT_ACCESS_HUB_SECURITY };
    const curRoles = { ...(accessHubSecurity.roles || {}) };
    if (updatedDev.accessRole) {
      curRoles[cleanGuid] = updatedDev.accessRole;
    }
    const curAllowedSections = { ...(accessHubSecurity.allowedSections || {}) };
    if (updatedDev.allowedAccessSections) {
      curAllowedSections[cleanGuid] = updatedDev.allowedAccessSections;
    }
    accessHubSecurity = {
      ...accessHubSecurity,
      roles: curRoles,
      allowedSections: curAllowedSections,
      updatedAt: new Date().toISOString(),
    };

    return {
      ...current,
      devices,
      departments,
      accessHubSecurity,
    };
  });

  const matching = updated.devices.find((d) => d.machineGuid === cleanGuid || d.id === cleanGuid)!;
  return { success: true, device: matching, devices: updated.devices };
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
 * تحديث محتوى ملف موجود مباشرة في Google Drive (لحفظ تعديلات WebDAV و Ctrl+S المباشرة من Office)
 */
export async function updateDriveFileContent(
  fileId: string,
  buffer: Buffer,
  mimeType?: string
) {
  const stream = new Readable();
  stream.push(buffer);
  stream.push(null);

  invalidateCloudFilesCache();
  invalidateDriveFileMeta(fileId);
  const res = await drive.files.update({
    fileId,
    media: {
      mimeType: mimeType || 'application/octet-stream',
      body: stream,
    },
    fields: 'id, name, size, modifiedTime, webViewLink, webContentLink',
  });
  return res.data;
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
  const meta = await getCachedDriveFileMeta(fileId);

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
