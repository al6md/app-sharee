import fs from 'fs';
import path from 'path';
import crypto from 'crypto';
import { Readable } from 'stream';
import { spawn } from 'child_process';

export const STORAGE_ROOT =
  process.env.SHARE_STORAGE_DIR ||
  (process.env.NODE_ENV === 'production' ? '/app/storage' : path.join(process.cwd(), 'storage'));

export const FILES_DIR = path.join(STORAGE_ROOT, 'files');
export const TRASH_DIR = path.join(STORAGE_ROOT, 'trash');
export const TRASH_INDEX_PATH = path.join(STORAGE_ROOT, 'trash-index.json');
export const UPLOADS_DIR = path.join(STORAGE_ROOT, 'uploads');
export const PERMISSIONS_PATH = path.join(STORAGE_ROOT, 'permissions.json');
export const SEED_PERMISSIONS_PATH = path.join(process.cwd(), 'data', 'access-hub', 'permissions.seed.json');
export const GDRIVE_ID_MAP_PATH = path.join(STORAGE_ROOT, 'gdrive-id-map.json');

export const ROOT_FOLDER_ID = 'root';
export const DEFAULT_DEPARTMENT_NAME = 'سجل التجاري';
const LEGACY_ROOT_FOLDER_ID = '1BF6mDMuwuaS5c4Ekq9KPcEXaAOxGOmfB';

const FOLDER_MIME = 'application/vnd.google-apps.folder';
const IGNORED_EXACT = new Set(['desktop.ini', 'thumbs.db', '.ds_store']);
const IGNORED_SUFFIXES = ['.tmp', '.part', '.laccdb', '.ldb', '.crdownload', '.partial', '~'];

const EXT_MIME_MAP: Record<string, string> = {
  accdb: 'application/msaccess',
  mdb: 'application/msaccess',
  docx: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
  doc: 'application/msword',
  dotx: 'application/vnd.openxmlformats-officedocument.wordprocessingml.template',
  xlsx: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  xls: 'application/vnd.ms-excel',
  xltx: 'application/vnd.openxmlformats-officedocument.spreadsheetml.template',
  pptx: 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
  ppt: 'application/vnd.ms-powerpoint',
  pdf: 'application/pdf',
  jpg: 'image/jpeg',
  jpeg: 'image/jpeg',
  png: 'image/png',
  gif: 'image/gif',
  webp: 'image/webp',
  svg: 'image/svg+xml',
  bmp: 'image/bmp',
  ico: 'image/x-icon',
  tif: 'image/tiff',
  tiff: 'image/tiff',
  mp4: 'video/mp4',
  webm: 'video/webm',
  mov: 'video/quicktime',
  avi: 'video/x-msvideo',
  mkv: 'video/x-matroska',
  mp3: 'audio/mpeg',
  wav: 'audio/wav',
  ogg: 'audio/ogg',
  m4a: 'audio/mp4',
  txt: 'text/plain; charset=utf-8',
  log: 'text/plain; charset=utf-8',
  md: 'text/markdown; charset=utf-8',
  csv: 'text/csv; charset=utf-8',
  json: 'application/json; charset=utf-8',
  xml: 'application/xml; charset=utf-8',
  html: 'text/html; charset=utf-8',
  htm: 'text/html; charset=utf-8',
  rtf: 'application/rtf',
  odt: 'application/vnd.oasis.opendocument.text',
  ods: 'application/vnd.oasis.opendocument.spreadsheet',
  zip: 'application/zip',
  rar: 'application/x-rar-compressed',
  '7z': 'application/x-7z-compressed',
};

export function inferMimeType(fileName: string): string {
  const ext = fileName.includes('.') ? fileName.split('.').pop()?.toLowerCase() || '' : '';
  return (ext && EXT_MIME_MAP[ext]) || 'application/octet-stream';
}

function isIgnoredName(name?: string | null): boolean {
  if (!name) return true;
  const low = name.toLowerCase();
  if (IGNORED_EXACT.has(low)) return true;
  if (name.startsWith('~$') || name.startsWith('.') || name.startsWith('~WRL')) return true;
  if (/^[0-9a-f]{8}$/i.test(name)) return true;
  return IGNORED_SUFFIXES.some((s) => low.endsWith(s));
}

function ensureStorageDirs() {
  fs.mkdirSync(FILES_DIR, { recursive: true });
  fs.mkdirSync(TRASH_DIR, { recursive: true });
  fs.mkdirSync(UPLOADS_DIR, { recursive: true });
}

function sleepSync(ms: number) {
  const end = Date.now() + ms;
  while (Date.now() < end) {
    // brief synchronous backoff for Windows transient rename lock
  }
}

export function renameWithRetrySync(srcPath: string, destPath: string, maxAttempts: number = 6) {
  let lastErr: any;
  for (let attempt = 0; attempt < maxAttempts; attempt++) {
    try {
      fs.renameSync(srcPath, destPath);
      return;
    } catch (err: any) {
      lastErr = err;
      if (err?.code === 'EPERM' || err?.code === 'EACCES' || err?.code === 'EBUSY') {
        sleepSync(20 * (attempt + 1));
        continue;
      }
      throw err;
    }
  }
  throw lastErr;
}

export function atomicWriteFileSync(targetPath: string, data: string | Buffer) {
  fs.mkdirSync(path.dirname(targetPath), { recursive: true });
  const tmpPath = `${targetPath}.${process.pid}.${Date.now()}.${crypto.randomBytes(4).toString('hex')}.tmp`;
  try {
    if (typeof data === 'string') {
      fs.writeFileSync(tmpPath, data, 'utf-8');
    } else {
      fs.writeFileSync(tmpPath, data);
    }
    renameWithRetrySync(tmpPath, targetPath);
  } catch (err) {
    try {
      if (fs.existsSync(tmpPath)) fs.unlinkSync(tmpPath);
    } catch {
      // ignore cleanup error
    }
    throw err;
  }
}

function movePathSafeSync(srcPath: string, destPath: string) {
  fs.mkdirSync(path.dirname(destPath), { recursive: true });
  try {
    renameWithRetrySync(srcPath, destPath);
  } catch (err: any) {
    if (err?.code === 'EXDEV') {
      fs.cpSync(srcPath, destPath, { recursive: true });
      fs.rmSync(srcPath, { recursive: true, force: true });
      return;
    }
    throw err;
  }
}

function sanitizeSingleName(rawName: string): string {
  const clean = String(rawName || '')
    .replace(/[\0\r\n]/g, '')
    .trim();
  if (!clean || clean === '.' || clean === '..' || clean.includes('/') || clean.includes('\\')) {
    throw new Error('اسم الملف أو المجلد غير صالح');
  }
  return clean;
}

function normalizeRelPath(rawRel: string): string {
  const raw = String(rawRel || '').replace(/\0/g, '');
  if (raw.includes('\0')) {
    throw new Error('مسار غير صالح');
  }
  // Reject Windows drive-letter prefixes like C:\ or D:/
  if (/^[a-zA-Z]:/.test(raw.trim())) {
    throw new Error('مسار غير صالح (محاولة خروج عن نطاق التخزين)');
  }
  const parts = raw
    .replace(/\\/g, '/')
    .split('/')
    .map((p) => p.trim())
    .filter((p) => p.length > 0 && p !== '.');
  for (const part of parts) {
    if (part === '..') {
      throw new Error('مسار غير صالح (محاولة تخطي الدليل)');
    }
  }
  return parts.join('/');
}

function safeResolveInDir(baseDir: string, relPath: string): string {
  const cleanRel = normalizeRelPath(relPath);
  const baseResolved = path.resolve(baseDir);
  const targetResolved = cleanRel ? path.resolve(baseResolved, ...cleanRel.split('/')) : baseResolved;
  if (targetResolved !== baseResolved && !targetResolved.startsWith(baseResolved + path.sep)) {
    throw new Error('تم رفض المسار: محاولة وصول خارج مجلد التخزين');
  }
  return targetResolved;
}

export function encodeLocalId(relPath: string): string {
  const norm = normalizeRelPath(relPath);
  if (!norm) return ROOT_FOLDER_ID;
  return 'loc_' + Buffer.from(norm, 'utf8').toString('base64url');
}

function decodeLocalId(id: string): string {
  const encoded = id.slice(4);
  if (!encoded) throw new Error('معرف الملف غير صالح');
  const decoded = Buffer.from(encoded, 'base64url').toString('utf8');
  if (!decoded || decoded.includes('\0')) {
    throw new Error('معرف الملف تالف أو غير صالح');
  }
  return normalizeRelPath(decoded);
}

function buildStreamLink(id: string, name: string): string {
  return `/api/drive/stream?id=${encodeURIComponent(id)}&name=${encodeURIComponent(name)}`;
}

// ============================================================================
// Legacy Drive ID map & Trash Index
// ============================================================================

let _idMapCache: { mtimeMs: number; map: Record<string, string> } | null = null;

function readGdriveIdMap(): Record<string, string> {
  try {
    if (!fs.existsSync(GDRIVE_ID_MAP_PATH)) return {};
    const stat = fs.statSync(GDRIVE_ID_MAP_PATH);
    if (_idMapCache && _idMapCache.mtimeMs === stat.mtimeMs) {
      return _idMapCache.map;
    }
    const raw = fs.readFileSync(GDRIVE_ID_MAP_PATH, 'utf-8');
    const parsed = JSON.parse(raw.replace(/^\uFEFF/, '').trim() || '{}');
    const map = parsed && typeof parsed === 'object' && !Array.isArray(parsed) ? parsed : {};
    _idMapCache = { mtimeMs: stat.mtimeMs, map };
    return map;
  } catch {
    return {};
  }
}

function updateGdriveIdMapPrefix(oldRel: string, newRel: string) {
  try {
    if (!fs.existsSync(GDRIVE_ID_MAP_PATH)) return;
    const map = { ...readGdriveIdMap() };
    let changed = false;
    const normOld = normalizeRelPath(oldRel);
    const normNew = normalizeRelPath(newRel);
    for (const [legacyId, rel] of Object.entries(map)) {
      const normVal = normalizeRelPath(String(rel || ''));
      if (normVal === normOld) {
        map[legacyId] = normNew;
        changed = true;
      } else if (normVal.startsWith(normOld + '/')) {
        map[legacyId] = normNew + normVal.slice(normOld.length);
        changed = true;
      }
    }
    if (changed) {
      atomicWriteFileSync(GDRIVE_ID_MAP_PATH, JSON.stringify(map, null, 2));
      _idMapCache = null;
    }
  } catch {
    // non-fatal
  }
}

export interface TrashIndexItem {
  trashId: string;
  storedName: string;
  name: string;
  originalRelPath: string;
  isFolder: boolean;
  size: number;
  mimeType: string;
  modifiedTime: string;
  deletedAt: string;
}

let _trashIndexQueue: Promise<any> = Promise.resolve();

function readTrashIndexSync(): TrashIndexItem[] {
  ensureStorageDirs();
  if (!fs.existsSync(TRASH_INDEX_PATH)) return [];
  try {
    const raw = fs.readFileSync(TRASH_INDEX_PATH, 'utf-8');
    const parsed = JSON.parse(raw.replace(/^\uFEFF/, '').trim() || '[]');
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function writeTrashIndexSync(items: TrashIndexItem[]) {
  ensureStorageDirs();
  atomicWriteFileSync(TRASH_INDEX_PATH, JSON.stringify(items, null, 2));
}

function withTrashIndexLock<T>(fn: () => Promise<T> | T): Promise<T> {
  const run = () => Promise.resolve().then(fn);
  const next = _trashIndexQueue.then(run, run);
  _trashIndexQueue = next.catch(() => {});
  return next;
}

export interface ResolvedLocalItem {
  kind: 'root' | 'active' | 'trash';
  id: string;
  relPath: string;
  fullPath: string;
  name: string;
  isFolder: boolean;
  exists: boolean;
  trashEntry?: TrashIndexItem;
}

function isRootAlias(id?: string | null): boolean {
  if (!id) return true;
  const trimmed = String(id).trim();
  if (!trimmed || trimmed === ROOT_FOLDER_ID || trimmed === LEGACY_ROOT_FOLDER_ID) return true;
  if (process.env.GDRIVE_FOLDER_ID && trimmed === process.env.GDRIVE_FOLDER_ID) return true;
  return false;
}

export function resolveItemById(rawId: string): ResolvedLocalItem {
  ensureStorageDirs();
  const id = String(rawId || '').trim();

  if (isRootAlias(id)) {
    return {
      kind: 'root',
      id: ROOT_FOLDER_ID,
      relPath: '',
      fullPath: path.resolve(FILES_DIR),
      name: ROOT_FOLDER_ID,
      isFolder: true,
      exists: fs.existsSync(FILES_DIR),
    };
  }

  if (id.startsWith('trash_')) {
    const trashId = id.slice(6);
    if (!trashId || trashId.includes('/') || trashId.includes('\\') || trashId.includes('..') || trashId.includes('\0')) {
      throw new Error('معرف سلة المحذوفات غير صالح');
    }
    const items = readTrashIndexSync();
    const entry = items.find((t) => t.trashId === trashId);
    if (!entry) {
      return {
        kind: 'trash',
        id,
        relPath: '',
        fullPath: safeResolveInDir(TRASH_DIR, trashId),
        name: '',
        isFolder: false,
        exists: false,
      };
    }
    const trashFullPath = safeResolveInDir(TRASH_DIR, entry.storedName);
    return {
      kind: 'trash',
      id: `trash_${entry.trashId}`,
      relPath: normalizeRelPath(entry.originalRelPath),
      fullPath: trashFullPath,
      name: entry.name,
      isFolder: Boolean(entry.isFolder),
      exists: fs.existsSync(trashFullPath),
      trashEntry: entry,
    };
  }

  if (id.startsWith('loc_')) {
    const relPath = decodeLocalId(id);
    if (!relPath) {
      return {
        kind: 'root',
        id: ROOT_FOLDER_ID,
        relPath: '',
        fullPath: path.resolve(FILES_DIR),
        name: ROOT_FOLDER_ID,
        isFolder: true,
        exists: true,
      };
    }
    const fullPath = safeResolveInDir(FILES_DIR, relPath);
    const exists = fs.existsSync(fullPath);
    const isFolder = exists ? fs.statSync(fullPath).isDirectory() : false;
    return {
      kind: 'active',
      id: encodeLocalId(relPath),
      relPath,
      fullPath,
      name: path.posix.basename(relPath),
      isFolder,
      exists,
    };
  }

  // Legacy Google Drive ID lookup via gdrive-id-map.json
  const idMap = readGdriveIdMap();
  if (Object.prototype.hasOwnProperty.call(idMap, id)) {
    const mappedRel = normalizeRelPath(String(idMap[id] || ''));
    if (!mappedRel) {
      return {
        kind: 'root',
        id: ROOT_FOLDER_ID,
        relPath: '',
        fullPath: path.resolve(FILES_DIR),
        name: ROOT_FOLDER_ID,
        isFolder: true,
        exists: true,
      };
    }
    const fullPath = safeResolveInDir(FILES_DIR, mappedRel);
    const exists = fs.existsSync(fullPath);
    const isFolder = exists ? fs.statSync(fullPath).isDirectory() : false;
    return {
      kind: 'active',
      id: encodeLocalId(mappedRel),
      relPath: mappedRel,
      fullPath,
      name: path.posix.basename(mappedRel),
      isFolder,
      exists,
    };
  }

  // Direct relative path fallback (strictly guarded inside FILES_DIR)
  const relPath = normalizeRelPath(id);
  if (!relPath) {
    return {
      kind: 'root',
      id: ROOT_FOLDER_ID,
      relPath: '',
      fullPath: path.resolve(FILES_DIR),
      name: ROOT_FOLDER_ID,
      isFolder: true,
      exists: true,
    };
  }
  const fullPath = safeResolveInDir(FILES_DIR, relPath);
  const exists = fs.existsSync(fullPath);
  const isFolder = exists ? fs.statSync(fullPath).isDirectory() : false;
  return {
    kind: 'active',
    id: encodeLocalId(relPath),
    relPath,
    fullPath,
    name: path.posix.basename(relPath),
    isFolder,
    exists,
  };
}

// ============================================================================
// File Metadata Cache
// ============================================================================

const FILE_META_TTL_MS = 15_000;
const fileMetaCache = new Map<string, { at: number; data: any }>();

export async function getCachedDriveFileMeta(fileId: string) {
  const now = Date.now();
  const hit = fileMetaCache.get(fileId);
  if (hit && now - hit.at < FILE_META_TTL_MS) {
    return hit.data;
  }

  const resolved = resolveItemById(fileId);
  if (!resolved.exists) {
    fileMetaCache.delete(fileId);
    throw new Error(`الملف غير موجود: ${fileId}`);
  }

  const stat = await fs.promises.stat(resolved.fullPath);
  const isDir = resolved.kind === 'trash' ? Boolean(resolved.trashEntry?.isFolder) : stat.isDirectory();
  const mimeType = isDir
    ? FOLDER_MIME
    : resolved.trashEntry?.mimeType || inferMimeType(resolved.name);
  const size = resolved.kind === 'trash' && resolved.trashEntry ? resolved.trashEntry.size : stat.size;

  const data = {
    id: resolved.id,
    name: resolved.name,
    mimeType,
    size: String(size),
    modifiedTime: stat.mtime.toISOString(),
  };

  fileMetaCache.set(fileId, { at: now, data });
  if (resolved.id !== fileId) {
    fileMetaCache.set(resolved.id, { at: now, data });
  }
  return data;
}

export function invalidateDriveFileMeta(fileId?: string) {
  if (fileId) fileMetaCache.delete(fileId);
  else fileMetaCache.clear();
}

// ============================================================================
// Types & Permissions / Auth Helpers (identical signatures & behavior)
// ============================================================================

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
    hasCreds: Boolean(
      store.accessHubSecurity?.username ||
        store.accessHubSecurity?.password ||
        store.accessHubSecurity?.pinCode
    ),
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
    canUpload: raw.canUpload !== undefined ? Boolean(raw.canUpload) : legacyWrite ?? def.canUpload,
    canCreateFolder:
      raw.canCreateFolder !== undefined ? Boolean(raw.canCreateFolder) : legacyWrite ?? def.canCreateFolder,
    canEdit: raw.canEdit !== undefined ? Boolean(raw.canEdit) : legacyWrite ?? def.canEdit,
    canRename: raw.canRename !== undefined ? Boolean(raw.canRename) : legacyWrite ?? def.canRename,
    canMove: raw.canMove !== undefined ? Boolean(raw.canMove) : legacyWrite ?? def.canMove,
    canDelete: raw.canDelete !== undefined ? Boolean(raw.canDelete) : def.canDelete,
    canPermanentDelete:
      raw.canPermanentDelete !== undefined
        ? Boolean(raw.canPermanentDelete)
        : legacyDelete ?? def.canPermanentDelete,
    pinCode: typeof raw.pinCode === 'string' ? raw.pinCode : '',
    deptUsername:
      typeof raw.deptUsername === 'string'
        ? raw.deptUsername.trim()
        : typeof raw.username === 'string'
          ? raw.username.trim()
          : '',
    deptPassword:
      typeof raw.deptPassword === 'string'
        ? raw.deptPassword.trim()
        : typeof raw.password === 'string'
          ? raw.password.trim()
          : '',
    authorizedDevices: Array.isArray(raw.authorizedDevices) ? raw.authorizedDevices.filter(Boolean) : [],
    updatedAt: raw.updatedAt || new Date().toISOString(),
  };
}

// ============================================================================
// Caches & Local Disk Permissions Store
// ============================================================================

let _adminStoreCache: { store: CloudAdminStore; ts: number; mtimeMs: number } | null = null;
const PERMISSIONS_CACHE_TTL_MS = 20_000;
let _saveQueuePromise: Promise<any> = Promise.resolve();

let _cloudFilesCache: { data: any; ts: number } | null = null;
const CLOUD_FILES_CACHE_TTL_MS = 4000;

export function invalidateCloudFilesCache() {
  _cloudFilesCache = null;
}

function parseRawAdminStore(rawText: string): CloudAdminStore {
  let rawData: any = {};
  if (rawText && rawText.trim()) {
    try {
      rawData = JSON.parse(rawText.replace(/^\uFEFF/, '').trim());
    } catch (parseErr) {
      console.error('JSON parse error on permissions.json:', parseErr);
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
        deptName === 'accessHubSecurity' ||
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

  const rawAccessSec = rawData.accessHubSecurity || rawData.departments?.['مركز بيانات Access'];
  const hubUser = String(rawAccessSec?.username || rawAccessSec?.deptUsername || '').trim();
  const hubPass = String(rawAccessSec?.password || rawAccessSec?.deptPassword || '').trim();
  const hubPin = String(rawAccessSec?.pinCode || '').trim();
  const hasHubCreds = Boolean(hubUser || hubPass || hubPin);
  const accessHubSecurity: AccessHubSecurityConfig = {
    enabled: rawAccessSec?.enabled !== undefined ? Boolean(rawAccessSec.enabled) || hasHubCreds : hasHubCreds,
    username: hubUser,
    password: hubPass,
    pinCode: hubPin,
    authorizedDevices: Array.isArray(rawAccessSec?.authorizedDevices)
      ? rawAccessSec.authorizedDevices.filter(Boolean)
      : [],
    roles: rawAccessSec?.roles && typeof rawAccessSec.roles === 'object' ? rawAccessSec.roles : {},
    allowedSections:
      rawAccessSec?.allowedSections && typeof rawAccessSec.allowedSections === 'object'
        ? rawAccessSec.allowedSections
        : {},
    securityEpoch: Number(rawAccessSec?.securityEpoch || 0),
    updatedAt: rawAccessSec?.updatedAt || new Date().toISOString(),
  };

  const rawDevices = rawData.devices !== undefined ? rawData.devices : rawData.__authorized_devices__;
  const devices: AuthorizedDeviceConfig[] = Array.isArray(rawDevices)
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
          : dev.department
            ? [String(dev.department)]
            : [],
        registeredAt: dev.registeredAt ? String(dev.registeredAt) : undefined,
        accessRole: dev.accessRole || accessHubSecurity.roles?.[dev.machineGuid] || 'data_entry',
        allowedAccessSections: Array.isArray(dev.allowedAccessSections)
          ? dev.allowedAccessSections
          : accessHubSecurity.allowedSections?.[dev.machineGuid],
        departmentPermissions:
          dev.departmentPermissions && typeof dev.departmentPermissions === 'object'
            ? dev.departmentPermissions
            : undefined,
      }))
    : [];

  return {
    version: 3,
    updatedAt: rawData.updatedAt || new Date().toISOString(),
    adminCredentials,
    devices,
    departments: normalizedDepts,
    accessHubSecurity,
  };
}

function ensurePermissionsSeeded(): void {
  fs.mkdirSync(STORAGE_ROOT, { recursive: true });
  if (!fs.existsSync(PERMISSIONS_PATH) && fs.existsSync(SEED_PERMISSIONS_PATH)) {
    try {
      const seedRaw = fs.readFileSync(SEED_PERMISSIONS_PATH, 'utf-8');
      if (seedRaw && seedRaw.trim()) {
        atomicWriteFileSync(PERMISSIONS_PATH, seedRaw);
      }
    } catch (err) {
      console.error('Error auto-seeding permissions.json:', err);
    }
  }
}

export async function getCloudAdminStore(forceRefresh: boolean = false): Promise<CloudAdminStore> {
  try {
    ensurePermissionsSeeded();

    if (!fs.existsSync(PERMISSIONS_PATH)) {
      const emptyStore: CloudAdminStore = {
        version: 3,
        updatedAt: new Date().toISOString(),
        adminCredentials: { ...DEFAULT_ADMIN_CREDENTIALS },
        devices: [],
        departments: {},
        accessHubSecurity: { ...DEFAULT_ACCESS_HUB_SECURITY },
      };
      _adminStoreCache = { store: emptyStore, ts: Date.now(), mtimeMs: 0 };
      return emptyStore;
    }

    const stat = fs.statSync(PERMISSIONS_PATH);
    if (
      !forceRefresh &&
      _adminStoreCache &&
      _adminStoreCache.mtimeMs === stat.mtimeMs &&
      Date.now() - _adminStoreCache.ts < PERMISSIONS_CACHE_TTL_MS
    ) {
      return _adminStoreCache.store;
    }

    const rawText = fs.readFileSync(PERMISSIONS_PATH, 'utf-8');
    const store = parseRawAdminStore(rawText);
    _adminStoreCache = { store, ts: Date.now(), mtimeMs: stat.mtimeMs };
    return store;
  } catch (e) {
    console.error('Error reading local admin store:', e);
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

export async function persistCloudAdminStore(
  mutator: (current: CloudAdminStore) => CloudAdminStore
): Promise<CloudAdminStore> {
  const runSave = async (): Promise<CloudAdminStore> => {
    const baseStore = await getCloudAdminStore(true);
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

    const payload = JSON.stringify(updatedStore, null, 2);
    atomicWriteFileSync(PERMISSIONS_PATH, payload);
    const mtimeMs = fs.existsSync(PERMISSIONS_PATH) ? fs.statSync(PERMISSIONS_PATH).mtimeMs : Date.now();

    _adminStoreCache = {
      store: updatedStore,
      ts: Date.now(),
      mtimeMs,
    };

    if (_cloudFilesCache && _cloudFilesCache.data) {
      _cloudFilesCache.data.permissions = updatedStore.departments;
      _cloudFilesCache.data.devices = updatedStore.devices;
      _cloudFilesCache.data.accessHubSecurity = updatedStore.accessHubSecurity;
    }
    invalidateCloudFilesCache();
    return updatedStore;
  };

  const next = _saveQueuePromise.then(runSave, runSave);
  _saveQueuePromise = next.catch(() => {});
  return next;
}

export async function getCloudPermissions(
  forceRefresh: boolean = false
): Promise<Record<string, DepartmentPermissionConfig>> {
  const store = await getCloudAdminStore(forceRefresh);
  return store.departments;
}

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

export async function saveCloudDevices(
  devicesInput: AuthorizedDeviceConfig[]
): Promise<AuthorizedDeviceConfig[]> {
  const updated = await persistCloudAdminStore((current) => ({
    ...current,
    devices: Array.isArray(devicesInput) ? devicesInput : current.devices,
  }));
  return updated.devices;
}

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

export async function revokeOrDeleteDevice(
  identifier: string
): Promise<{
  success: boolean;
  devices: AuthorizedDeviceConfig[];
  departments: Record<string, DepartmentPermissionConfig>;
  accessHubSecurity?: AccessHubSecurityConfig;
}> {
  const cleanId = String(identifier || '').trim();
  if (!cleanId) throw new Error('معرف الجهاز مطلوب');

  const updated = await persistCloudAdminStore((current) => {
    const targetDev = current.devices.find((d) => d.id === cleanId || d.machineGuid === cleanId);
    const targetGuid = targetDev?.machineGuid || cleanId;

    const devices = (current.devices || []).filter((d) => d.id !== cleanId && d.machineGuid !== cleanId);

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

  return {
    success: true,
    devices: updated.devices,
    departments: updated.departments,
    accessHubSecurity: updated.accessHubSecurity,
  };
}

export async function saveAccessHubSecurity(
  secInput: Partial<AccessHubSecurityConfig> & { resetAuthorizedDevices?: boolean }
): Promise<AccessHubSecurityConfig> {
  const updated = await persistCloudAdminStore((current) => {
    const curSec = current.accessHubSecurity || { ...DEFAULT_ACCESS_HUB_SECURITY };
    const username = secInput.username !== undefined ? String(secInput.username).trim() : curSec.username;
    const password = secInput.password !== undefined ? String(secInput.password).trim() : curSec.password;
    const pinCode = secInput.pinCode !== undefined ? String(secInput.pinCode).trim() : curSec.pinCode;
    const hasCredentials = Boolean(username || password || pinCode);
    const enabled =
      secInput.enabled !== undefined
        ? Boolean(secInput.enabled) || hasCredentials
        : curSec.enabled || hasCredentials;

    const credsChanged =
      username !== curSec.username || password !== curSec.password || pinCode !== curSec.pinCode;
    let authDevs = Array.isArray(secInput.authorizedDevices)
      ? secInput.authorizedDevices
      : curSec.authorizedDevices || [];
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

  return {
    success: true,
    device: matchingDev,
    accessHubSecurity: updated.accessHubSecurity || DEFAULT_ACCESS_HUB_SECURITY,
  };
}

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
      allowedAccessSections:
        updates.allowedAccessSections !== undefined ? updates.allowedAccessSections : cur.allowedAccessSections,
      departmentPermissions:
        updates.departmentPermissions !== undefined ? updates.departmentPermissions : cur.departmentPermissions,
    };
    devices[devIdx] = updatedDev;

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

    let accessHubSecurity = current.accessHubSecurity
      ? { ...current.accessHubSecurity }
      : { ...DEFAULT_ACCESS_HUB_SECURITY };
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

// ============================================================================
// Directory Traversal, Change Detection, Folder Operations
// ============================================================================

let _lastCloudStateSig: string | null = null;

async function walkActiveStorage(): Promise<{
  folders: { relPath: string; name: string; parentPath: string; modifiedTime: string; mtimeMs: number }[];
  files: { relPath: string; relFolder: string; name: string; size: number; modifiedTime: string; mtimeMs: number }[];
}> {
  ensureStorageDirs();
  const folders: { relPath: string; name: string; parentPath: string; modifiedTime: string; mtimeMs: number }[] = [];
  const files: { relPath: string; relFolder: string; name: string; size: number; modifiedTime: string; mtimeMs: number }[] = [];

  async function walk(absDir: string, relDir: string) {
    let entries: fs.Dirent[];
    try {
      entries = await fs.promises.readdir(absDir, { withFileTypes: true });
    } catch {
      return;
    }
    for (const entry of entries) {
      if (isIgnoredName(entry.name)) continue;
      const absPath = path.join(absDir, entry.name);
      const relPath = relDir ? `${relDir}/${entry.name}` : entry.name;
      try {
        const stat = await fs.promises.stat(absPath);
        if (entry.isDirectory()) {
          folders.push({
            relPath,
            name: entry.name,
            parentPath: relDir,
            modifiedTime: stat.mtime.toISOString(),
            mtimeMs: stat.mtimeMs,
          });
          await walk(absPath, relPath);
        } else if (entry.isFile()) {
          files.push({
            relPath,
            relFolder: relDir,
            name: entry.name,
            size: stat.size,
            modifiedTime: stat.mtime.toISOString(),
            mtimeMs: stat.mtimeMs,
          });
        }
      } catch {
        // skip unreadable or vanished temp file
      }
    }
  }

  await walk(FILES_DIR, '');
  return { folders, files };
}

export async function checkCloudChanges(clientSig?: string | null): Promise<{ changed: boolean; sig: string }> {
  try {
    ensureStorageDirs();
    const { folders, files } = await walkActiveStorage();
    const trashMtime = fs.existsSync(TRASH_INDEX_PATH) ? fs.statSync(TRASH_INDEX_PATH).mtimeMs : 0;
    const permMtime = fs.existsSync(PERMISSIONS_PATH) ? fs.statSync(PERMISSIONS_PATH).mtimeMs : 0;

    const sortedTopFiles = [...files]
      .sort((a, b) => b.mtimeMs - a.mtimeMs)
      .slice(0, 6)
      .map((f) => `${f.relPath}:${Math.round(f.mtimeMs)}:${f.size}`)
      .join('|');

    const rawSig = `F:${folders.length}|N:${files.length}|T:${Math.round(trashMtime)}|P:${Math.round(permMtime)}|${sortedTopFiles}`;
    const currentSig = crypto.createHash('sha1').update(rawSig).digest('hex').slice(0, 16);

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

export async function getCloudFolders() {
  ensureStorageDirs();
  const defaultDir = path.join(FILES_DIR, DEFAULT_DEPARTMENT_NAME);
  if (!fs.existsSync(defaultDir)) {
    fs.mkdirSync(defaultDir, { recursive: true });
  }

  const entries = await fs.promises.readdir(FILES_DIR, { withFileTypes: true });
  const results: { id: string; name: string; modifiedTime: string }[] = [];
  for (const entry of entries) {
    if (!entry.isDirectory() || isIgnoredName(entry.name)) continue;
    const stat = await fs.promises.stat(path.join(FILES_DIR, entry.name));
    results.push({
      id: encodeLocalId(entry.name),
      name: entry.name,
      modifiedTime: stat.mtime.toISOString(),
    });
  }
  results.sort((a, b) => a.name.localeCompare(b.name, 'ar'));
  return results;
}

export async function createCloudFolder(name: string, parentId: string = ROOT_FOLDER_ID) {
  ensureStorageDirs();
  const cleanName = sanitizeSingleName(name);
  const parent = resolveItemById(parentId || ROOT_FOLDER_ID);
  if (parent.kind === 'trash') {
    throw new Error('لا يمكن إنشاء مجلد داخل سلة المحذوفات');
  }
  if (!parent.exists) {
    fs.mkdirSync(parent.fullPath, { recursive: true });
  }
  const targetRelPath = parent.relPath ? `${parent.relPath}/${cleanName}` : cleanName;
  const targetFullPath = safeResolveInDir(FILES_DIR, targetRelPath);

  if (!fs.existsSync(targetFullPath)) {
    fs.mkdirSync(targetFullPath, { recursive: true });
    invalidateCloudFilesCache();
  }

  return {
    id: encodeLocalId(targetRelPath),
    name: cleanName,
    mimeType: FOLDER_MIME,
  };
}

export async function ensureCloudFolderPath(
  folderPath: string,
  baseParentId: string = ROOT_FOLDER_ID
): Promise<string> {
  ensureStorageDirs();
  if (!folderPath) return baseParentId || ROOT_FOLDER_ID;
  const parts = folderPath
    .replace(/\\/g, '/')
    .split('/')
    .map((p) => p.trim())
    .filter((p) => p && p !== '.' && p !== '__ALL__');
  for (const part of parts) {
    if (part === '..') {
      throw new Error('مسار المجلد غير صالح');
    }
  }
  if (parts.length === 0) return baseParentId || ROOT_FOLDER_ID;

  // Handle callers (like files/page.tsx CREATE_FOLDER) passing both fullPath from root and parentId
  let currentParent = baseParentId || ROOT_FOLDER_ID;
  if (!isRootAlias(currentParent)) {
    try {
      const parentItem = resolveItemById(currentParent);
      const joined = parts.join('/');
      if (
        parentItem.relPath &&
        (joined === parentItem.relPath || joined.startsWith(parentItem.relPath + '/'))
      ) {
        currentParent = ROOT_FOLDER_ID;
      }
    } catch {
      currentParent = ROOT_FOLDER_ID;
    }
  }

  for (const part of parts) {
    const folder = await createCloudFolder(part, currentParent);
    if (folder?.id) {
      currentParent = folder.id;
    }
  }
  return currentParent;
}

export async function ensureCloudFolderPathsBatch(
  folderPaths: string[],
  baseParentId: string = ROOT_FOLDER_ID
): Promise<Record<string, string>> {
  const resultMap: Record<string, string> = {};
  const cache = new Map<string, string>();
  const uniquePaths = Array.from(new Set(folderPaths.map((p) => String(p || '').trim()).filter(Boolean)));

  for (const rawPath of uniquePaths) {
    const parts = rawPath
      .replace(/\\/g, '/')
      .split('/')
      .map((p) => p.trim())
      .filter((p) => p && p !== '.' && p !== '__ALL__');
    for (const part of parts) {
      if (part === '..') throw new Error('مسار المجلد غير صالح');
    }
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

const BOOTSTRAP_MARKER_FILENAME = '.gdrive_migrated_v1.json';
const BOOTSTRAP_LOCK_FILENAME = 'bootstrap.lock';
const BOOTSTRAP_LOCK_TTL_MS = 10 * 60 * 1000;
let _bootstrapTriggered = false;
let _lastBootstrapAttemptAt = 0;

function isBootstrapLockActive(lockPath: string, now: number = Date.now()): boolean {
  try {
    if (!fs.existsSync(lockPath)) return false;
    const stat = fs.statSync(lockPath);
    let newestTs = stat.mtimeMs;
    try {
      const raw = fs.readFileSync(lockPath, 'utf8');
      const parsed = JSON.parse(raw);
      if (parsed && parsed.updatedAt !== undefined && parsed.updatedAt !== null) {
        const parsedTs =
          typeof parsed.updatedAt === 'number'
            ? parsed.updatedAt
            : Date.parse(String(parsed.updatedAt));
        if (Number.isFinite(parsedTs)) {
          newestTs = Math.max(newestTs, parsedTs);
        }
      }
    } catch {
      // Fall back to stat.mtimeMs if lock JSON is partially written or unreadable.
    }
    return now - newestTs < BOOTSTRAP_LOCK_TTL_MS;
  } catch {
    return false;
  }
}

/**
 * Lazily spawns the resumable background Google Drive -> local disk bootstrapper
 * once per cooldown window when storage has not finished migrating yet.
 */
function maybeTriggerBackgroundBootstrap(): void {
  try {
    if (process.env.NEXT_PHASE === 'phase-production-build') return;

    const now = Date.now();
    if (_bootstrapTriggered && now - _lastBootstrapAttemptAt < BOOTSTRAP_LOCK_TTL_MS) {
      return;
    }

    const markerPath = path.join(STORAGE_ROOT, BOOTSTRAP_MARKER_FILENAME);
    if (fs.existsSync(markerPath)) return;

    const lockPath = path.join(STORAGE_ROOT, BOOTSTRAP_LOCK_FILENAME);
    if (isBootstrapLockActive(lockPath, now)) return;

    const scriptPath = path.join(process.cwd(), 'scripts', 'bootstrap-storage.mjs');
    if (!fs.existsSync(scriptPath)) return;

    _bootstrapTriggered = true;
    _lastBootstrapAttemptAt = now;

    const child = spawn(process.execPath, [scriptPath, '--background'], {
      cwd: process.cwd(),
      detached: true,
      stdio: 'ignore',
      windowsHide: true,
      env: process.env,
    });
    child.on('error', () => {
      // Never propagate background spawn errors into request handling.
    });
    child.unref();
  } catch {
    // Bootstrap check must never break getAllCloudFiles().
  }
}

export async function getAllCloudFiles(forceRefresh: boolean = false) {
  maybeTriggerBackgroundBootstrap();

  if (!forceRefresh && _cloudFilesCache && Date.now() - _cloudFilesCache.ts < CLOUD_FILES_CACHE_TTL_MS) {
    return _cloudFilesCache.data;
  }

  ensureStorageDirs();
  const { folders: rawFolders, files: rawFiles } = await walkActiveStorage();

  // Ensure default department folder exists on fresh/empty storage unless it was explicitly trashed
  if (rawFolders.length === 0) {
    const trashed = readTrashIndexSync();
    const defaultInTrash = trashed.some(
      (t) => t.isFolder && normalizeRelPath(t.originalRelPath) === DEFAULT_DEPARTMENT_NAME
    );
    if (!defaultInTrash) {
      const defaultPath = path.join(FILES_DIR, DEFAULT_DEPARTMENT_NAME);
      fs.mkdirSync(defaultPath, { recursive: true });
      const stat = fs.statSync(defaultPath);
      rawFolders.push({
        relPath: DEFAULT_DEPARTMENT_NAME,
        name: DEFAULT_DEPARTMENT_NAME,
        parentPath: '',
        modifiedTime: stat.mtime.toISOString(),
        mtimeMs: stat.mtimeMs,
      });
    }
  }

  const allFolders: CloudFolderItem[] = rawFolders
    .map((f) => ({
      id: encodeLocalId(f.relPath),
      name: f.name,
      path: f.relPath,
      parentPath: f.parentPath,
      department: f.relPath.split('/')[0],
      modifiedTime: f.modifiedTime,
    }))
    .sort((a, b) => a.path.localeCompare(b.path, 'ar'));

  const departments = allFolders
    .filter((f) => !f.parentPath)
    .map((f) => ({ id: f.id, name: f.name, modifiedTime: f.modifiedTime }));

  const activeFiles = rawFiles
    .sort((a, b) => String(b.modifiedTime).localeCompare(String(a.modifiedTime)))
    .map((f) => {
      const id = encodeLocalId(f.relPath);
      const deptName = f.relFolder ? f.relFolder.split('/')[0] : 'القسم العام';
      const subFolder = f.relFolder.includes('/') ? f.relFolder.split('/').slice(1).join('/') : '';
      const streamUrl = buildStreamLink(id, f.name);
      return {
        id,
        name: f.name,
        size: Number(f.size || 0),
        mimeType: inferMimeType(f.name),
        modifiedTime: f.modifiedTime,
        folder: f.relFolder || 'القسم العام',
        department: deptName,
        subFolder,
        folderId: f.relFolder ? encodeLocalId(f.relFolder) : ROOT_FOLDER_ID,
        previewUrl: streamUrl,
        downloadUrl: streamUrl,
        webViewLink: streamUrl,
        webContentLink: streamUrl,
        isDeleted: false,
      };
    });

  let trashFiles: any[] = [];
  try {
    const trashItems = readTrashIndexSync();
    trashFiles = trashItems
      .filter((entry) => {
        if (!entry || entry.isFolder || isIgnoredName(entry.name)) return false;
        try {
          const p = safeResolveInDir(TRASH_DIR, entry.storedName);
          return fs.existsSync(p);
        } catch {
          return false;
        }
      })
      .sort((a, b) => String(b.deletedAt || b.modifiedTime).localeCompare(String(a.deletedAt || a.modifiedTime)))
      .map((entry) => {
        const id = `trash_${entry.trashId}`;
        const origRel = normalizeRelPath(entry.originalRelPath || '');
        const lastSlash = origRel.lastIndexOf('/');
        const relFolder = lastSlash > 0 ? origRel.slice(0, lastSlash) : 'القسم العام';
        const deptName = relFolder.split('/')[0] || 'القسم العام';
        const subFolder = relFolder.includes('/') ? relFolder.split('/').slice(1).join('/') : '';
        const streamUrl = buildStreamLink(id, entry.name);
        return {
          id,
          name: entry.name,
          size: Number(entry.size || 0),
          mimeType: entry.mimeType || inferMimeType(entry.name),
          modifiedTime: entry.modifiedTime || entry.deletedAt,
          folder: relFolder,
          department: deptName,
          subFolder,
          folderId: relFolder !== 'القسم العام' ? encodeLocalId(relFolder) : ROOT_FOLDER_ID,
          previewUrl: streamUrl,
          downloadUrl: streamUrl,
          webViewLink: streamUrl,
          webContentLink: streamUrl,
          isDeleted: true,
        };
      });
  } catch (e) {
    console.error('Error reading trash index:', e);
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

// ============================================================================
// Upload, WebDAV Content Update, and Chunked Resumable Uploads
// ============================================================================

async function resolveTargetFolder(folderId?: string, folderPath?: string): Promise<ResolvedLocalItem> {
  if (folderId && !isRootAlias(folderId)) {
    try {
      const resolved = resolveItemById(folderId);
      if (resolved.kind !== 'trash' && resolved.exists && resolved.isFolder) {
        return resolved;
      }
    } catch {
      // fall through to folderPath if provided
    }
  }
  if (folderPath) {
    const ensuredId = await ensureCloudFolderPath(folderPath, ROOT_FOLDER_ID);
    return resolveItemById(ensuredId);
  }
  return resolveItemById(ROOT_FOLDER_ID);
}

export async function uploadFileToDrive(
  buffer: Buffer,
  fileName: string,
  mimeType: string,
  folderId: string = ROOT_FOLDER_ID,
  folderPath?: string
) {
  ensureStorageDirs();
  const cleanName = sanitizeSingleName(fileName);
  const targetFolder = await resolveTargetFolder(folderId, folderPath);
  const targetRelPath = targetFolder.relPath ? `${targetFolder.relPath}/${cleanName}` : cleanName;
  const targetFullPath = safeResolveInDir(FILES_DIR, targetRelPath);

  const isUpdate = fs.existsSync(targetFullPath);
  atomicWriteFileSync(targetFullPath, buffer);
  const stat = fs.statSync(targetFullPath);
  const id = encodeLocalId(targetRelPath);
  const streamUrl = buildStreamLink(id, cleanName);

  invalidateCloudFilesCache();
  invalidateDriveFileMeta(id);

  return {
    id,
    name: cleanName,
    size: String(stat.size),
    mimeType: mimeType || inferMimeType(cleanName),
    modifiedTime: stat.mtime.toISOString(),
    webViewLink: streamUrl,
    webContentLink: streamUrl,
    isUpdate,
    folderId: targetFolder.id,
  };
}

export async function updateDriveFileContent(fileId: string, buffer: Buffer, mimeType?: string) {
  ensureStorageDirs();
  const resolved = resolveItemById(fileId);
  if (resolved.kind !== 'active' || !resolved.exists || resolved.isFolder) {
    throw new Error(`الملف غير موجود أو لا يمكن تعديله: ${fileId}`);
  }

  atomicWriteFileSync(resolved.fullPath, buffer);
  const stat = fs.statSync(resolved.fullPath);
  const streamUrl = buildStreamLink(resolved.id, resolved.name);

  invalidateCloudFilesCache();
  invalidateDriveFileMeta(fileId);
  invalidateDriveFileMeta(resolved.id);

  return {
    id: resolved.id,
    name: resolved.name,
    size: String(stat.size),
    mimeType: mimeType || inferMimeType(resolved.name),
    modifiedTime: stat.mtime.toISOString(),
    webViewLink: streamUrl,
    webContentLink: streamUrl,
  };
}

interface UploadSessionMeta {
  sessionId: string;
  fileName: string;
  mimeType: string;
  fileSize: number | null;
  folderId: string;
  folderPath: string;
  targetRelPath: string;
  createdAt: string;
  completedFile?: any;
}

function parseSessionId(sessionUri: string): string {
  const raw = String(sessionUri || '').trim();
  if (!raw.startsWith('local-upload://')) {
    throw new Error('معرف جلسة الرفع غير صالح');
  }
  const sessionId = raw.slice('local-upload://'.length);
  if (!sessionId || !/^[a-zA-Z0-9_-]+$/.test(sessionId)) {
    throw new Error('معرف جلسة الرفع تالف');
  }
  return sessionId;
}

export async function initResumableUpload(params: {
  fileName: string;
  mimeType?: string;
  fileSize?: number;
  folderId?: string;
  folderPath?: string;
  origin?: string;
}) {
  ensureStorageDirs();
  const { fileName, mimeType = 'application/octet-stream', fileSize, folderId, folderPath } = params;
  const cleanName = sanitizeSingleName(fileName);
  const targetFolder = await resolveTargetFolder(folderId, folderPath);
  const targetRelPath = targetFolder.relPath ? `${targetFolder.relPath}/${cleanName}` : cleanName;
  const targetFullPath = safeResolveInDir(FILES_DIR, targetRelPath);

  const exists = fs.existsSync(targetFullPath);
  const existingId = exists ? encodeLocalId(targetRelPath) : null;
  const sessionId = crypto.randomUUID();

  const partPath = path.join(UPLOADS_DIR, `${sessionId}.part`);
  const metaPath = path.join(UPLOADS_DIR, `${sessionId}.meta.json`);

  const meta: UploadSessionMeta = {
    sessionId,
    fileName: cleanName,
    mimeType: mimeType || inferMimeType(cleanName),
    fileSize: typeof fileSize === 'number' ? fileSize : null,
    folderId: targetFolder.id,
    folderPath: targetFolder.relPath,
    targetRelPath,
    createdAt: new Date().toISOString(),
  };

  fs.writeFileSync(partPath, Buffer.alloc(0));
  atomicWriteFileSync(metaPath, JSON.stringify(meta, null, 2));

  return {
    sessionUri: `local-upload://${sessionId}`,
    fileName: cleanName,
    folderPath: targetFolder.relPath,
    folderId: targetFolder.id,
    existingId,
    isUpdate: Boolean(existingId),
  };
}

export async function uploadResumableChunk(params: {
  sessionUri: string;
  chunkBuffer: Buffer;
  start: number;
  end: number;
  total: number;
}) {
  ensureStorageDirs();
  const { sessionUri, chunkBuffer, start, end, total } = params;
  const sessionId = parseSessionId(sessionUri);
  const partPath = path.join(UPLOADS_DIR, `${sessionId}.part`);
  const metaPath = path.join(UPLOADS_DIR, `${sessionId}.meta.json`);

  if (!fs.existsSync(metaPath)) {
    throw new Error('جلسة الرفع غير موجودة أو انتهت صلاحيتها');
  }
  const meta: UploadSessionMeta = JSON.parse(fs.readFileSync(metaPath, 'utf-8'));

  if (meta.completedFile) {
    return {
      done: true,
      status: 200,
      file: meta.completedFile,
    };
  }

  if (start < 0 || !Number.isFinite(start)) {
    throw new Error('إزاحة البداية للجزء غير صالحة');
  }

  const mode = fs.existsSync(partPath) ? 'r+' : 'w+';
  const fh = await fs.promises.open(partPath, mode);
  try {
    await fh.write(chunkBuffer, 0, chunkBuffer.length, start);
  } finally {
    await fh.close();
  }

  const isComplete = total > 0 ? end + 1 >= total : chunkBuffer.length === 0;
  if (!isComplete) {
    return {
      done: false,
      status: 308,
      range: `bytes=0-${end}`,
    };
  }

  const targetFullPath = safeResolveInDir(FILES_DIR, meta.targetRelPath);
  movePathSafeSync(partPath, targetFullPath);
  const stat = fs.statSync(targetFullPath);
  const fileId = encodeLocalId(meta.targetRelPath);
  const streamUrl = buildStreamLink(fileId, meta.fileName);

  const fileResult = {
    id: fileId,
    name: meta.fileName,
    size: String(stat.size),
    mimeType: meta.mimeType || inferMimeType(meta.fileName),
    modifiedTime: stat.mtime.toISOString(),
    webViewLink: streamUrl,
    webContentLink: streamUrl,
  };

  meta.completedFile = fileResult;
  try {
    fs.unlinkSync(metaPath);
  } catch {
    // non-fatal
  }

  invalidateCloudFilesCache();
  invalidateDriveFileMeta(fileId);

  return {
    done: true,
    status: 200,
    file: fileResult,
  };
}

export async function getResumableUploadStatus(sessionUri: string, totalSize: number) {
  ensureStorageDirs();
  const sessionId = parseSessionId(sessionUri);
  const partPath = path.join(UPLOADS_DIR, `${sessionId}.part`);
  const metaPath = path.join(UPLOADS_DIR, `${sessionId}.meta.json`);

  if (!fs.existsSync(metaPath)) {
    throw new Error('جلسة الرفع غير موجودة');
  }
  const meta: UploadSessionMeta = JSON.parse(fs.readFileSync(metaPath, 'utf-8'));

  if (meta.completedFile) {
    invalidateCloudFilesCache();
    return {
      done: true,
      status: 200,
      nextOffset: totalSize,
      file: meta.completedFile,
    };
  }

  const currentSize = fs.existsSync(partPath) ? fs.statSync(partPath).size : 0;
  const nextOffset = Math.min(currentSize, Math.max(0, totalSize));
  return {
    done: false,
    status: 308,
    nextOffset,
    range: nextOffset > 0 ? `bytes=0-${nextOffset - 1}` : null,
  };
}

// ============================================================================
// Trash / Restore / Rename / Move / Permanent Delete
// ============================================================================

export async function deleteDriveItem(fileId: string) {
  return withTrashIndexLock(async () => {
    const resolved = resolveItemById(fileId);
    if (resolved.kind === 'root') {
      throw new Error('لا يمكن حذف المجلد الجذري');
    }
    if (resolved.kind === 'trash') {
      return { data: { id: resolved.id, trashed: true } };
    }
    if (!resolved.exists) {
      throw new Error(`العنصر غير موجود: ${fileId}`);
    }

    const stat = fs.statSync(resolved.fullPath);
    const isFolder = stat.isDirectory();
    const trashId = `${Date.now()}_${crypto.randomBytes(4).toString('hex')}`;
    const storedName = isFolder ? trashId : `${trashId}${path.extname(resolved.name)}`;
    const trashFullPath = safeResolveInDir(TRASH_DIR, storedName);

    movePathSafeSync(resolved.fullPath, trashFullPath);

    const items = readTrashIndexSync();
    const entry: TrashIndexItem = {
      trashId,
      storedName,
      name: resolved.name,
      originalRelPath: resolved.relPath,
      isFolder,
      size: isFolder ? 0 : stat.size,
      mimeType: isFolder ? FOLDER_MIME : inferMimeType(resolved.name),
      modifiedTime: stat.mtime.toISOString(),
      deletedAt: new Date().toISOString(),
    };
    items.unshift(entry);
    writeTrashIndexSync(items);

    invalidateCloudFilesCache();
    invalidateDriveFileMeta(fileId);
    invalidateDriveFileMeta(resolved.id);

    return { data: { id: `trash_${trashId}`, trashed: true } };
  });
}

export async function restoreDriveItem(fileId: string) {
  return withTrashIndexLock(async () => {
    ensureStorageDirs();
    const items = readTrashIndexSync();
    const cleanId = String(fileId || '').trim();

    let idx = -1;
    if (cleanId.startsWith('trash_')) {
      const tId = cleanId.slice(6);
      idx = items.findIndex((t) => t.trashId === tId);
    } else if (cleanId.startsWith('loc_')) {
      const rel = decodeLocalId(cleanId);
      idx = items.findIndex((t) => normalizeRelPath(t.originalRelPath) === rel);
    } else {
      idx = items.findIndex((t) => t.trashId === cleanId);
    }

    if (idx < 0) {
      throw new Error(`العنصر غير موجود في سلة المحذوفات: ${fileId}`);
    }

    const entry = items[idx];
    const trashFullPath = safeResolveInDir(TRASH_DIR, entry.storedName);
    if (!fs.existsSync(trashFullPath)) {
      items.splice(idx, 1);
      writeTrashIndexSync(items);
      throw new Error('ملف السلة غير موجود على القرص');
    }

    let targetRelPath = normalizeRelPath(entry.originalRelPath || entry.name);
    let targetFullPath = safeResolveInDir(FILES_DIR, targetRelPath);

    if (fs.existsSync(targetFullPath)) {
      const ext = entry.isFolder ? '' : path.posix.extname(targetRelPath);
      const base = ext ? targetRelPath.slice(0, -ext.length) : targetRelPath;
      targetRelPath = `${base} (restored ${Date.now()})${ext}`;
      targetFullPath = safeResolveInDir(FILES_DIR, targetRelPath);
    }

    movePathSafeSync(trashFullPath, targetFullPath);
    items.splice(idx, 1);
    writeTrashIndexSync(items);

    const restoredId = encodeLocalId(targetRelPath);
    invalidateCloudFilesCache();
    invalidateDriveFileMeta(fileId);
    invalidateDriveFileMeta(restoredId);

    return { data: { id: restoredId, trashed: false } };
  });
}

export async function permanentDeleteDriveItem(fileId: string) {
  return withTrashIndexLock(async () => {
    const resolved = resolveItemById(fileId);
    if (resolved.kind === 'root') {
      throw new Error('لا يمكن حذف المجلد الجذري');
    }

    if (resolved.kind === 'trash') {
      const items = readTrashIndexSync();
      const trashId = resolved.id.slice(6);
      const entry = items.find((t) => t.trashId === trashId);
      if (entry) {
        const trashFullPath = safeResolveInDir(TRASH_DIR, entry.storedName);
        if (fs.existsSync(trashFullPath)) {
          fs.rmSync(trashFullPath, { recursive: true, force: true });
        }
        writeTrashIndexSync(items.filter((t) => t.trashId !== trashId));
      }
    } else if (resolved.exists) {
      fs.rmSync(resolved.fullPath, { recursive: true, force: true });
    }

    invalidateCloudFilesCache();
    invalidateDriveFileMeta(fileId);
    invalidateDriveFileMeta(resolved.id);
    return { data: {} };
  });
}

export async function renameDriveItem(fileId: string, newName: string) {
  const resolved = resolveItemById(fileId);
  if (resolved.kind !== 'active' || !resolved.exists) {
    throw new Error(`العنصر غير موجود: ${fileId}`);
  }

  const cleanNewName = sanitizeSingleName(newName);
  const parentRel = resolved.relPath.includes('/')
    ? resolved.relPath.slice(0, resolved.relPath.lastIndexOf('/'))
    : '';
  const newRelPath = parentRel ? `${parentRel}/${cleanNewName}` : cleanNewName;
  const newFullPath = safeResolveInDir(FILES_DIR, newRelPath);

  if (newRelPath === resolved.relPath) {
    return { id: resolved.id, name: resolved.name };
  }

  if (fs.existsSync(newFullPath)) {
    const oldStat = fs.statSync(resolved.fullPath);
    const newStat = fs.statSync(newFullPath);
    const sameFile = oldStat.ino && newStat.ino && oldStat.ino === newStat.ino && oldStat.dev === newStat.dev;
    if (!sameFile) {
      throw new Error(`يوجد عنصر آخر بالاسم "${cleanNewName}" مسبقاً`);
    }
  }

  renameWithRetrySync(resolved.fullPath, newFullPath);
  updateGdriveIdMapPrefix(resolved.relPath, newRelPath);

  const newId = encodeLocalId(newRelPath);
  invalidateCloudFilesCache();
  invalidateDriveFileMeta(fileId);
  invalidateDriveFileMeta(resolved.id);
  invalidateDriveFileMeta(newId);

  return { id: newId, name: cleanNewName };
}

export async function moveDriveItem(
  fileId: string,
  targetFolderId: string = ROOT_FOLDER_ID,
  targetFolderPath?: string
) {
  let finalTargetId = targetFolderId || ROOT_FOLDER_ID;
  if (targetFolderPath && isRootAlias(targetFolderId)) {
    finalTargetId = await ensureCloudFolderPath(targetFolderPath, ROOT_FOLDER_ID);
  }

  const resolved = resolveItemById(fileId);
  if (resolved.kind !== 'active' || !resolved.exists) {
    throw new Error(`العنصر المطلوب نقله غير موجود: ${fileId}`);
  }

  const targetFolder = await resolveTargetFolder(finalTargetId, targetFolderPath);
  finalTargetId = targetFolder.id;

  if (resolved.id === finalTargetId || targetFolder.relPath === resolved.relPath) {
    throw new Error('لا يمكن نقل المجلد داخل نفسه');
  }
  if (resolved.isFolder && targetFolder.relPath.startsWith(resolved.relPath + '/')) {
    throw new Error('لا يمكن نقل المجلد داخل أحد مجلداته الفرعية');
  }

  const destRelPath = targetFolder.relPath ? `${targetFolder.relPath}/${resolved.name}` : resolved.name;
  if (destRelPath === resolved.relPath) {
    return {
      id: resolved.id,
      name: resolved.name,
      parents: [finalTargetId],
      mimeType: resolved.isFolder ? FOLDER_MIME : inferMimeType(resolved.name),
      targetFolderId: finalTargetId,
    };
  }

  const destFullPath = safeResolveInDir(FILES_DIR, destRelPath);
  if (fs.existsSync(destFullPath)) {
    throw new Error(`يوجد عنصر بالاسم "${resolved.name}" بالفعل في المجلد الهدف`);
  }

  movePathSafeSync(resolved.fullPath, destFullPath);
  updateGdriveIdMapPrefix(resolved.relPath, destRelPath);
  const stat = fs.statSync(destFullPath);
  const newId = encodeLocalId(destRelPath);

  invalidateCloudFilesCache();
  invalidateDriveFileMeta(fileId);
  invalidateDriveFileMeta(resolved.id);
  invalidateDriveFileMeta(newId);

  return {
    id: newId,
    name: resolved.name,
    parents: [finalTargetId],
    mimeType: resolved.isFolder ? FOLDER_MIME : inferMimeType(resolved.name),
    modifiedTime: stat.mtime.toISOString(),
    targetFolderId: finalTargetId,
  };
}

export async function batchMoveDriveItems(
  fileIds: string[],
  targetFolderId: string = ROOT_FOLDER_ID,
  targetFolderPath?: string
) {
  let finalTargetId = targetFolderId || ROOT_FOLDER_ID;
  if (targetFolderPath && isRootAlias(targetFolderId)) {
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

// ============================================================================
// Streaming with HTTP Range (206 / 200)
// ============================================================================

export async function getDriveFileStreamResponse(fileId: string, rangeHeader?: string | null) {
  const resolved = resolveItemById(fileId);
  if (!resolved.exists || resolved.isFolder) {
    throw new Error(`الملف غير موجود: ${fileId}`);
  }

  const stat = await fs.promises.stat(resolved.fullPath);
  const totalSize = stat.size;
  const contentType = resolved.trashEntry?.mimeType || inferMimeType(resolved.name);
  const meta = {
    id: resolved.id,
    name: resolved.name,
    mimeType: contentType,
    size: String(totalSize),
    modifiedTime: stat.mtime.toISOString(),
  };

  if (rangeHeader && totalSize > 0) {
    const match = /^bytes=(\d*)-(\d*)$/i.exec(rangeHeader.trim());
    if (match) {
      const startStr = match[1];
      const endStr = match[2];
      let start = 0;
      let end = totalSize - 1;

      if (startStr === '' && endStr !== '') {
        const suffixLen = parseInt(endStr, 10);
        start = Math.max(0, totalSize - suffixLen);
      } else {
        start = parseInt(startStr, 10);
        end = endStr !== '' ? Math.min(totalSize - 1, parseInt(endStr, 10)) : totalSize - 1;
      }

      if (Number.isNaN(start) || Number.isNaN(end) || start < 0 || start >= totalSize || start > end) {
        const errHeaders = new Headers();
        errHeaders.set('Content-Range', `bytes */${totalSize}`);
        errHeaders.set('Accept-Ranges', 'bytes');
        return {
          meta,
          upstreamRes: new Response(null, { status: 416, headers: errHeaders }),
        };
      }

      const chunkSize = end - start + 1;
      const nodeStream = fs.createReadStream(resolved.fullPath, { start, end });
      const webStream = Readable.toWeb(nodeStream) as unknown as ReadableStream<Uint8Array>;

      const headers = new Headers();
      headers.set('Content-Type', contentType);
      headers.set('Content-Length', String(chunkSize));
      headers.set('Content-Range', `bytes ${start}-${end}/${totalSize}`);
      headers.set('Accept-Ranges', 'bytes');

      return {
        meta,
        upstreamRes: new Response(webStream, { status: 206, headers }),
      };
    }
  }

  const headers = new Headers();
  headers.set('Content-Type', contentType);
  headers.set('Content-Length', String(totalSize));
  headers.set('Accept-Ranges', 'bytes');

  if (totalSize === 0) {
    return {
      meta,
      upstreamRes: new Response(Buffer.alloc(0), { status: 200, headers }),
    };
  }

  const nodeStream = fs.createReadStream(resolved.fullPath);
  const webStream = Readable.toWeb(nodeStream) as unknown as ReadableStream<Uint8Array>;

  return {
    meta,
    upstreamRes: new Response(webStream, { status: 200, headers }),
  };
}
