import fs from 'fs';
import path from 'path';
import { Readable } from 'stream';
import { pipeline } from 'stream/promises';
import { spawn } from 'child_process';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const APP_ROOT = path.resolve(__dirname, '..');

const DEFAULT_GDRIVE_FOLDER_ID = '1BF6mDMuwuaS5c4Ekq9KPcEXaAOxGOmfB';

const FOLDER_MIME = 'application/vnd.google-apps.folder';
export const LARGE_FILE_BYTES = 50 * 1024 * 1024; // 50 MB
export const RANGE_CHUNK_BYTES = 32 * 1024 * 1024; // 32 MB
const LOCK_TTL_MS = 10 * 60 * 1000; // 10 minutes
const CHUNK_MAX_ATTEMPTS = 5;
const CHUNK_TIMEOUT_MS = 10 * 60 * 1000; // 10 minutes per 32 MB chunk

let _tmpSeq = 0;

const SKIP_EXACT = new Set([
  '.sharecoc_permissions.json',
  '.sharecoc_access_mutations.json',
  '.sync_shadow',
  'thumbs.db',
  '.ds_store',
  'desktop.ini',
]);
const SKIP_SUFFIXES = ['.tmp', '.lcdb', '.laccdb'];

function shouldSkipName(name) {
  if (!name || typeof name !== 'string') return true;
  const low = name.toLowerCase();
  if (SKIP_EXACT.has(low)) return true;
  if (name.startsWith('~$')) return true;
  return SKIP_SUFFIXES.some((suffix) => low.endsWith(suffix));
}

function resolveStorageDir() {
  return (
    process.env.SHARE_STORAGE_DIR ||
    (process.env.NODE_ENV === 'production' ? '/app/storage' : path.join(process.cwd(), 'storage'))
  );
}

function atomicWriteFileSync(targetPath, content) {
  fs.mkdirSync(path.dirname(targetPath), { recursive: true });
  const tmpPath = `${targetPath}.${process.pid}.${Date.now()}.${++_tmpSeq}.tmp`;
  fs.writeFileSync(tmpPath, content, 'utf-8');
  if (fs.existsSync(targetPath)) {
    try {
      fs.renameSync(tmpPath, targetPath);
      return;
    } catch {
      fs.rmSync(targetPath, { force: true });
    }
  }
  fs.renameSync(tmpPath, targetPath);
}

function isPidAlive(pid) {
  if (!Number.isInteger(pid) || pid <= 0) return false;
  try {
    process.kill(pid, 0);
    return true;
  } catch (err) {
    return Boolean(err && err.code === 'EPERM');
  }
}

export function readActiveLock(lockPath, now = Date.now()) {
  if (!fs.existsSync(lockPath)) return null;
  try {
    const stat = fs.statSync(lockPath);
    const raw = fs.readFileSync(lockPath, 'utf-8').trim();
    const parsed = raw ? JSON.parse(raw) : {};
    const updatedAt =
      typeof parsed?.updatedAt === 'number' && Number.isFinite(parsed.updatedAt)
        ? parsed.updatedAt
        : stat.mtimeMs;
    if (now - updatedAt >= LOCK_TTL_MS) return null;
    if (parsed?.pid !== undefined) {
      const pid = Number(parsed.pid);
      if (pid !== process.pid && !isPidAlive(pid)) return null;
      return { pid, updatedAt };
    }
    return { pid: null, updatedAt };
  } catch {
    return null;
  }
}

export function touchMigrationLock(lockPath, pid = process.pid) {
  atomicWriteFileSync(lockPath, JSON.stringify({ pid, updatedAt: Date.now() }) + '\n');
}

export function acquireMigrationLock(lockPath) {
  const active = readActiveLock(lockPath);
  if (active && active.pid !== process.pid) {
    return { acquired: false, active };
  }
  touchMigrationLock(lockPath, process.pid);
  return { acquired: true, active: null };
}

export function releaseMigrationLock(lockPath) {
  if (!fs.existsSync(lockPath)) return;
  try {
    const raw = fs.readFileSync(lockPath, 'utf-8').trim();
    const parsed = raw ? JSON.parse(raw) : {};
    if (parsed?.pid !== undefined) {
      const pid = Number(parsed.pid);
      if (pid !== process.pid && isPidAlive(pid)) {
        return;
      }
    }
  } catch {
    // if unreadable, still remove lock owned/left behind
  }
  try {
    fs.rmSync(lockPath, { force: true });
  } catch {
    // ignore cleanup error
  }
}

function parseEnvFile(filePath) {
  if (!fs.existsSync(filePath)) return {};
  const out = {};
  const raw = fs.readFileSync(filePath, 'utf-8');
  for (const line of raw.split(/\r?\n/)) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith('#')) continue;
    const eqIdx = trimmed.indexOf('=');
    if (eqIdx === -1) continue;
    const key = trimmed.slice(0, eqIdx).trim();
    let val = trimmed.slice(eqIdx + 1).trim();
    if (
      (val.startsWith('"') && val.endsWith('"')) ||
      (val.startsWith("'") && val.endsWith("'"))
    ) {
      val = val.slice(1, -1);
    }
    out[key] = val;
  }
  return out;
}

function resolveGDriveCredentials() {
  const candidates = [
    path.join(process.cwd(), '.env.local'),
    path.join(APP_ROOT, '.env.local'),
  ];
  let fileEnv = {};
  for (const p of candidates) {
    if (fs.existsSync(p)) {
      fileEnv = parseEnvFile(p);
      break;
    }
  }
  return {
    clientId: process.env.GDRIVE_CLIENT_ID || fileEnv.GDRIVE_CLIENT_ID || '',
    clientSecret: process.env.GDRIVE_CLIENT_SECRET || fileEnv.GDRIVE_CLIENT_SECRET || '',
    refreshToken: process.env.GDRIVE_REFRESH_TOKEN || fileEnv.GDRIVE_REFRESH_TOKEN || '',
    folderId:
      process.env.GDRIVE_FOLDER_ID ||
      fileEnv.GDRIVE_FOLDER_ID ||
      DEFAULT_GDRIVE_FOLDER_ID,
  };
}

function countMutations(obj) {
  if (!obj || typeof obj !== 'object') return -1;
  const addsLen = Array.isArray(obj.adds) ? obj.adds.length : 0;
  const updatesLen = Array.isArray(obj.updates)
    ? obj.updates.length
    : obj.updates && typeof obj.updates === 'object'
      ? Object.keys(obj.updates).length
      : 0;
  return addsLen + updatesLen;
}

function seedJsonFiles(storageDir) {
  const dataAccessDir = fs.existsSync(path.join(process.cwd(), 'data', 'access-hub'))
    ? path.join(process.cwd(), 'data', 'access-hub')
    : path.join(APP_ROOT, 'data', 'access-hub');

  // 1. Seed mutations.json
  const seedMutationsPath = path.join(dataAccessDir, 'mutations.json');
  const targetMutationsPath = path.join(storageDir, 'access-hub', 'mutations.json');

  if (fs.existsSync(seedMutationsPath)) {
    const seedRaw = fs.readFileSync(seedMutationsPath, 'utf-8');
    let seedCount = 0;
    try {
      seedCount = countMutations(JSON.parse(seedRaw.replace(/^\uFEFF/, '')));
    } catch {
      seedCount = -1;
    }

    let shouldCopy = !fs.existsSync(targetMutationsPath);
    if (!shouldCopy) {
      try {
        const existingRaw = fs.readFileSync(targetMutationsPath, 'utf-8');
        const existingCount = countMutations(JSON.parse(existingRaw.replace(/^\uFEFF/, '')));
        if (seedCount > existingCount) {
          shouldCopy = true;
        }
      } catch {
        shouldCopy = true;
      }
    }

    if (shouldCopy) {
      atomicWriteFileSync(targetMutationsPath, seedRaw);
      console.log(`[bootstrap] Seeded mutations.json (count=${seedCount}) -> ${targetMutationsPath}`);
    } else {
      console.log(`[bootstrap] Kept existing mutations.json at ${targetMutationsPath}`);
    }
  } else {
    console.warn(`[bootstrap] Seed mutations.json not found at ${seedMutationsPath}`);
  }

  // 2. Seed permissions.json
  const seedPermissionsPath = path.join(dataAccessDir, 'permissions.seed.json');
  const targetPermissionsPath = path.join(storageDir, 'permissions.json');

  if (fs.existsSync(seedPermissionsPath)) {
    let shouldCopyPerm = !fs.existsSync(targetPermissionsPath);
    if (!shouldCopyPerm) {
      try {
        const raw = fs.readFileSync(targetPermissionsPath, 'utf-8').trim();
        if (!raw) shouldCopyPerm = true;
        else JSON.parse(raw.replace(/^\uFEFF/, ''));
      } catch {
        shouldCopyPerm = true;
      }
    }
    if (shouldCopyPerm) {
      const seedPermRaw = fs.readFileSync(seedPermissionsPath, 'utf-8');
      atomicWriteFileSync(targetPermissionsPath, seedPermRaw);
      console.log(`[bootstrap] Seeded permissions.json -> ${targetPermissionsPath}`);
    } else {
      console.log(`[bootstrap] Kept existing permissions.json at ${targetPermissionsPath}`);
    }
  } else {
    console.warn(`[bootstrap] Seed permissions.seed.json not found at ${seedPermissionsPath}`);
  }
}

function ensureStorageDirs(storageDir) {
  for (const sub of ['files', 'trash', 'uploads', 'access-hub']) {
    fs.mkdirSync(path.join(storageDir, sub), { recursive: true });
  }
}

class OAuthTokenManager {
  constructor(creds) {
    this.creds = creds;
    this.accessToken = null;
    this.expiresAt = 0;
    this.pending = null;
  }

  async getToken(forceRefresh = false) {
    if (!forceRefresh && this.accessToken && Date.now() < this.expiresAt - 60_000) {
      return this.accessToken;
    }
    if (this.pending) return this.pending;
    this.pending = (async () => {
      const res = await fetch('https://oauth2.googleapis.com/token', {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body: new URLSearchParams({
          client_id: this.creds.clientId,
          client_secret: this.creds.clientSecret,
          refresh_token: this.creds.refreshToken,
          grant_type: 'refresh_token',
        }),
      });
      if (!res.ok) {
        const text = await res.text();
        throw new Error(`OAuth token error ${res.status}: ${text}`);
      }
      const data = await res.json();
      if (!data.access_token) {
        throw new Error('OAuth response missing access_token');
      }
      this.accessToken = data.access_token;
      this.expiresAt = Date.now() + Number(data.expires_in || 3600) * 1000;
      return this.accessToken;
    })();
    try {
      return await this.pending;
    } finally {
      this.pending = null;
    }
  }
}

async function fetchWithAuth(url, tokenMgr, attempts = 3) {
  let lastErr;
  for (let i = 0; i < attempts; i++) {
    const token = await tokenMgr.getToken(i > 0);
    try {
      const res = await fetch(url, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.status === 401 && i < attempts - 1) {
        await tokenMgr.getToken(true);
        continue;
      }
      if (res.status >= 500 && i < attempts - 1) {
        await new Promise((r) => setTimeout(r, 1000 * (i + 1)));
        continue;
      }
      if (!res.ok) {
        const body = await res.text();
        throw new Error(`HTTP ${res.status} for ${url}: ${body.slice(0, 300)}`);
      }
      return res;
    } catch (err) {
      lastErr = err;
      if (i < attempts - 1) {
        await new Promise((r) => setTimeout(r, 1000 * (i + 1)));
      }
    }
  }
  throw lastErr;
}

async function listDriveChildren(parentId, tokenMgr) {
  const children = [];
  let pageToken = undefined;
  const q = encodeURIComponent(`'${parentId}' in parents and trashed = false`);
  do {
    const url =
      `https://www.googleapis.com/drive/v3/files?q=${q}` +
      `&fields=nextPageToken,files(id,name,mimeType,size,modifiedTime)` +
      `&pageSize=1000` +
      (pageToken ? `&pageToken=${encodeURIComponent(pageToken)}` : '');
    const res = await fetchWithAuth(url, tokenMgr);
    const data = await res.json();
    if (Array.isArray(data.files)) {
      children.push(...data.files);
    }
    pageToken = data.nextPageToken || undefined;
  } while (pageToken);
  return children;
}

function sanitizeSegment(name) {
  return String(name).replace(/[\\/]/g, '_').trim();
}

async function traverseDriveTree(rootFolderId, tokenMgr) {
  const folders = [];
  const files = [];

  async function walk(parentId, relPrefix) {
    const children = await listDriveChildren(parentId, tokenMgr);
    for (const item of children) {
      if (shouldSkipName(item.name)) continue;
      const safeName = sanitizeSegment(item.name);
      if (!safeName || safeName === '.' || safeName === '..') continue;
      const relPath = relPrefix ? `${relPrefix}/${safeName}` : safeName;

      if (item.mimeType === FOLDER_MIME) {
        folders.push({
          id: item.id,
          name: safeName,
          relativePath: relPath,
          modifiedTime: item.modifiedTime || null,
        });
        await walk(item.id, relPath);
      } else if (!String(item.mimeType || '').startsWith('application/vnd.google-apps.')) {
        files.push({
          id: item.id,
          name: safeName,
          relativePath: relPath,
          size: item.size !== undefined && item.size !== null ? Number(item.size) : null,
          modifiedTime: item.modifiedTime || null,
        });
      }
    }
  }

  await walk(rootFolderId, '');
  return { folders, files };
}

async function runWithConcurrency(items, concurrency, worker) {
  let cursor = 0;
  const count = Math.min(concurrency, items.length);
  const runners = Array.from({ length: count }, async () => {
    while (cursor < items.length) {
      const idx = cursor++;
      await worker(items[idx], idx);
    }
  });
  await Promise.all(runners);
}

function preserveModifiedTime(targetPath, modifiedTime) {
  if (!modifiedTime) return;
  const dt = new Date(modifiedTime);
  if (Number.isNaN(dt.getTime())) return;
  try {
    fs.utimesSync(targetPath, dt, dt);
  } catch {
    // ignore mtime errors on restricted filesystems
  }
}

function replaceFileSync(srcPath, destPath) {
  if (fs.existsSync(destPath)) {
    try {
      fs.renameSync(srcPath, destPath);
      return;
    } catch {
      fs.rmSync(destPath, { force: true });
    }
  }
  fs.renameSync(srcPath, destPath);
}

async function downloadLargeFileResumable(file, destPath, tokenMgr, touchLock) {
  const partPath = `${destPath}.part`;
  const url = `https://www.googleapis.com/drive/v3/files/${encodeURIComponent(file.id)}?alt=media`;

  let offset = fs.existsSync(partPath) ? fs.statSync(partPath).size : 0;
  if (offset > file.size) {
    fs.rmSync(partPath, { force: true });
    offset = 0;
  }

  if (offset === file.size) {
    replaceFileSync(partPath, destPath);
    preserveModifiedTime(destPath, file.modifiedTime);
    return { status: 'downloaded', bytes: file.size };
  }

  while (offset < file.size) {
    const end = Math.min(offset + RANGE_CHUNK_BYTES - 1, file.size - 1);
    const expectedChunkLen = end - offset + 1;
    const rangeHeader = `bytes=${offset}-${end}`;

    let chunkDone = false;
    let lastChunkErr;

    for (let attempt = 0; attempt < CHUNK_MAX_ATTEMPTS && !chunkDone; attempt++) {
      let wroteFromZero = false;
      try {
        const token = await tokenMgr.getToken(attempt > 0);
        const res = await fetch(url, {
          headers: {
            Authorization: `Bearer ${token}`,
            Range: rangeHeader,
          },
          signal: AbortSignal.timeout(CHUNK_TIMEOUT_MS),
        });

        if (res.status === 401) {
          try {
            await res.body?.cancel();
          } catch {
            // ignore
          }
          await tokenMgr.getToken(true);
          throw new Error(`HTTP 401 unauthorized on ${rangeHeader}`);
        }

        if (res.status >= 500 || res.status === 429) {
          const body = await res.text().catch(() => '');
          throw new Error(`HTTP ${res.status} for ${rangeHeader}: ${body.slice(0, 200)}`);
        }

        if (res.status !== 206 && res.status !== 200) {
          const body = await res.text().catch(() => '');
          throw new Error(`HTTP ${res.status} for ${rangeHeader}: ${body.slice(0, 300)}`);
        }

        if (!res.body) {
          throw new Error(`Empty response body for ${file.relativePath} (${rangeHeader})`);
        }

        if (res.status === 200) {
          wroteFromZero = true;
          await pipeline(Readable.fromWeb(res.body), fs.createWriteStream(partPath, { flags: 'w' }));
          const totalWritten = fs.statSync(partPath).size;
          if (totalWritten !== file.size) {
            throw new Error(
              `Full-stream size mismatch for ${file.relativePath}: expected ${file.size}, got ${totalWritten}`
            );
          }
          offset = totalWritten;
          chunkDone = true;
        } else {
          // 206 Partial Content
          const contentRange = res.headers.get('content-range');
          if (contentRange) {
            const m = /^bytes\s+(\d+)-(\d+)\/(\d+|\*)$/i.exec(contentRange.trim());
            if (m && Number(m[1]) !== offset) {
              try {
                await res.body.cancel();
              } catch {
                // ignore
              }
              throw new Error(
                `Content-Range start mismatch for ${file.relativePath}: expected ${offset}, got ${m[1]}`
              );
            }
          }

          const preSize = fs.existsSync(partPath) ? fs.statSync(partPath).size : 0;
          if (preSize !== offset) {
            throw new Error(
              `Part file offset mismatch before append for ${file.relativePath}: expected ${offset}, got ${preSize}`
            );
          }

          await pipeline(Readable.fromWeb(res.body), fs.createWriteStream(partPath, { flags: 'a' }));

          const postSize = fs.statSync(partPath).size;
          const written = postSize - offset;
          if (written !== expectedChunkLen) {
            throw new Error(
              `Chunk byte count mismatch for ${file.relativePath} (${rangeHeader}): expected ${expectedChunkLen}, wrote ${written}`
            );
          }

          offset = postSize;
          chunkDone = true;
        }
      } catch (err) {
        lastChunkErr = err;
        if (wroteFromZero) {
          offset = 0;
        }
        if (fs.existsSync(partPath)) {
          const curSize = fs.statSync(partPath).size;
          if (curSize > offset) {
            try {
              fs.truncateSync(partPath, offset);
            } catch {
              // ignore
            }
          }
        }
        if (attempt < CHUNK_MAX_ATTEMPTS - 1) {
          await new Promise((r) => setTimeout(r, Math.min(30_000, 1000 * 2 ** attempt)));
        }
      }
    }

    if (!chunkDone) {
      throw lastChunkErr || new Error(`Failed chunk ${rangeHeader} for ${file.relativePath}`);
    }

    if (typeof touchLock === 'function') {
      touchLock();
    }
    const pct = Math.round((offset / file.size) * 100);
    console.log(
      `[bootstrap] Chunk ${file.relativePath}: ${offset}/${file.size} bytes (${pct}%)`
    );
  }

  const finalSize = fs.statSync(partPath).size;
  if (finalSize !== file.size) {
    throw new Error(
      `Final size mismatch for ${file.relativePath}: expected ${file.size}, got ${finalSize}`
    );
  }

  replaceFileSync(partPath, destPath);
  preserveModifiedTime(destPath, file.modifiedTime);
  return { status: 'downloaded', bytes: finalSize };
}

export async function downloadFileIfNeeded(file, filesDir, tokenMgr, touchLock = null) {
  const destPath = path.join(filesDir, ...file.relativePath.split('/'));
  fs.mkdirSync(path.dirname(destPath), { recursive: true });

  if (fs.existsSync(destPath)) {
    const stat = fs.statSync(destPath);
    if (file.size === null || stat.size === file.size) {
      if (file.modifiedTime) {
        const dt = new Date(file.modifiedTime);
        if (!Number.isNaN(dt.getTime()) && Math.abs(stat.mtimeMs - dt.getTime()) > 2000) {
          preserveModifiedTime(destPath, file.modifiedTime);
        }
      }
      return { status: 'skipped-existing', bytes: stat.size };
    }
  }

  if (file.size !== null && file.size > LARGE_FILE_BYTES) {
    return downloadLargeFileResumable(file, destPath, tokenMgr, touchLock);
  }

  const tmpPath = `${destPath}.download.${process.pid}.${Date.now()}.${++_tmpSeq}.tmp`;
  const url = `https://www.googleapis.com/drive/v3/files/${encodeURIComponent(file.id)}?alt=media`;
  try {
    const res = await fetchWithAuth(url, tokenMgr, 3);
    if (!res.body) {
      throw new Error(`Empty response body for ${file.relativePath}`);
    }
    await pipeline(Readable.fromWeb(res.body), fs.createWriteStream(tmpPath));

    const tmpStat = fs.statSync(tmpPath);
    if (file.size !== null && tmpStat.size !== file.size) {
      throw new Error(
        `Size mismatch for ${file.relativePath}: expected ${file.size}, got ${tmpStat.size}`
      );
    }

    replaceFileSync(tmpPath, destPath);
    preserveModifiedTime(destPath, file.modifiedTime);

    return { status: 'downloaded', bytes: tmpStat.size };
  } catch (err) {
    try {
      if (fs.existsSync(tmpPath)) fs.rmSync(tmpPath, { force: true });
    } catch {
      // ignore cleanup error
    }
    throw err;
  }
}

async function migrateFromGoogleDrive(storageDir, { skipLarge, touchLock = null }) {
  const markerPath = path.join(storageDir, '.gdrive_migrated_v1.json');
  if (fs.existsSync(markerPath)) {
    console.log(`[bootstrap] Migration marker already exists at ${markerPath}; skipping Drive sync.`);
    return;
  }

  const creds = resolveGDriveCredentials();
  if (!creds.clientId || !creds.clientSecret || !creds.refreshToken) {
    console.warn(
      '[bootstrap] Skipping Drive file download: GDRIVE_* credentials not configured; local seeds are ready.'
    );
    return;
  }

  const tokenMgr = new OAuthTokenManager(creds);
  console.log(`[bootstrap] Traversing Google Drive folder ${creds.folderId}...`);
  const { folders, files } = await traverseDriveTree(creds.folderId, tokenMgr);
  console.log(`[bootstrap] Found ${folders.length} folders and ${files.length} active user files.`);
  if (typeof touchLock === 'function') touchLock();

  const filesDir = path.join(storageDir, 'files');
  const idMapPath = path.join(storageDir, 'gdrive-id-map.json');
  let idMap = {};
  if (fs.existsSync(idMapPath)) {
    try {
      idMap = JSON.parse(fs.readFileSync(idMapPath, 'utf-8'));
    } catch {
      idMap = {};
    }
  }

  for (const folder of folders) {
    const folderDiskPath = path.join(filesDir, ...folder.relativePath.split('/'));
    fs.mkdirSync(folderDiskPath, { recursive: true });
    idMap[folder.id] = folder.relativePath;
  }

  const nonAccdb = [];
  const accdb = [];
  let skippedLargeCount = 0;
  let skippedLargeBytes = 0;

  for (const file of files) {
    const isAccdb = file.name.toLowerCase().endsWith('.accdb');
    const isOver50Mb = file.size !== null && file.size > LARGE_FILE_BYTES;
    if (skipLarge && (isAccdb || isOver50Mb)) {
      skippedLargeCount++;
      skippedLargeBytes += file.size || 0;
      console.log(
        `[bootstrap] [--skip-large] Skipping ${file.relativePath} (${file.size ?? '?'} bytes)`
      );
      continue;
    }
    if (isAccdb) accdb.push(file);
    else nonAccdb.push(file);
  }

  let downloadedCount = 0;
  let downloadedBytes = 0;
  let skippedExistingCount = 0;
  let skippedExistingBytes = 0;
  const failures = [];

  const handleFile = async (file) => {
    try {
      const res = await downloadFileIfNeeded(file, filesDir, tokenMgr, touchLock);
      idMap[file.id] = file.relativePath;
      if (typeof touchLock === 'function') touchLock();
      if (res.status === 'downloaded') {
        downloadedCount++;
        downloadedBytes += res.bytes;
        console.log(`[bootstrap] Downloaded ${file.relativePath} (${res.bytes} bytes)`);
      } else {
        skippedExistingCount++;
        skippedExistingBytes += res.bytes;
      }
    } catch (err) {
      failures.push({ path: file.relativePath, id: file.id, error: err.message });
      console.error(`[bootstrap] Failed ${file.relativePath}: ${err.message}`);
    }
  };

  // Download non-.accdb files first, then .accdb files
  await runWithConcurrency(nonAccdb, 4, handleFile);
  atomicWriteFileSync(idMapPath, JSON.stringify(idMap, null, 2) + '\n');

  await runWithConcurrency(accdb, 1, handleFile);
  atomicWriteFileSync(idMapPath, JSON.stringify(idMap, null, 2) + '\n');

  // Preserve folder timestamps where feasible
  for (const folder of folders) {
    if (!folder.modifiedTime) continue;
    const dt = new Date(folder.modifiedTime);
    if (Number.isNaN(dt.getTime())) continue;
    try {
      fs.utimesSync(path.join(filesDir, ...folder.relativePath.split('/')), dt, dt);
    } catch {
      // ignore
    }
  }

  console.log(
    `[bootstrap] Summary: folders=${folders.length}, downloaded=${downloadedCount} (${downloadedBytes} bytes), ` +
      `existing=${skippedExistingCount} (${skippedExistingBytes} bytes), ` +
      `skippedLarge=${skippedLargeCount} (${skippedLargeBytes} bytes), failures=${failures.length}, ` +
      `idMapEntries=${Object.keys(idMap).length}`
  );

  if (failures.length > 0) {
    throw new Error(`${failures.length} file(s) failed to download; marker not written.`);
  }

  if (skippedLargeCount === 0) {
    const marker = {
      version: 1,
      completedAt: new Date().toISOString(),
      folderId: creds.folderId,
      foldersCount: folders.length,
      filesCount: downloadedCount + skippedExistingCount,
      downloadedCount,
      skippedExistingCount,
      totalBytes: downloadedBytes + skippedExistingBytes,
    };
    atomicWriteFileSync(markerPath, JSON.stringify(marker, null, 2) + '\n');
    console.log(`[bootstrap] Wrote completion marker -> ${markerPath}`);
  } else {
    console.log(
      `[bootstrap] Completion marker NOT written because --skip-large skipped ${skippedLargeCount} file(s).`
    );
  }
}

async function main() {
  const args = process.argv.slice(2);
  const isBackground = args.includes('--background');
  const skipLarge = args.includes('--skip-large');

  const storageDir = resolveStorageDir();
  console.log(`[bootstrap] Storage root: ${storageDir}`);

  // Synchronous phase: ensure directories & seed mutations.json + permissions.json
  ensureStorageDirs(storageDir);
  seedJsonFiles(storageDir);

  const markerPath = path.join(storageDir, '.gdrive_migrated_v1.json');
  if (fs.existsSync(markerPath)) {
    console.log(`[bootstrap] Already migrated (${markerPath} exists). Done.`);
    return;
  }

  const lockPath = path.join(storageDir, 'bootstrap.lock');

  if (isBackground) {
    const active = readActiveLock(lockPath);
    if (active) {
      console.log(
        `[bootstrap] Active migration lock exists (pid=${active.pid ?? 'unknown'}); skipping duplicate background spawn.`
      );
      return;
    }

    const childArgs = [__filename, ...args.filter((a) => a !== '--background')];
    const logPath = path.join(storageDir, 'bootstrap.log');
    const logFd = fs.openSync(logPath, 'a');
    const child = spawn(process.execPath, childArgs, {
      cwd: process.cwd(),
      detached: true,
      windowsHide: true,
      stdio: ['ignore', logFd, logFd],
      env: process.env,
    });
    if (child.pid && child.exitCode === null) {
      touchMigrationLock(lockPath, child.pid);
    }
    child.unref();
    fs.closeSync(logFd);
    console.log(
      `[bootstrap] Spawned detached migration worker (pid=${child.pid}) logging to ${logPath}`
    );
    return;
  }

  const lockResult = acquireMigrationLock(lockPath);
  if (!lockResult.acquired) {
    console.log(
      `[bootstrap] Another migration process is active (pid=${lockResult.active?.pid ?? 'unknown'}); exiting.`
    );
    return;
  }

  const onSignal = (sig) => {
    releaseMigrationLock(lockPath);
    process.exit(128 + (sig === 'SIGINT' ? 2 : 15));
  };
  process.once('SIGINT', onSignal);
  process.once('SIGTERM', onSignal);

  try {
    await migrateFromGoogleDrive(storageDir, {
      skipLarge,
      touchLock: () => touchMigrationLock(lockPath),
    });
  } finally {
    process.off('SIGINT', onSignal);
    process.off('SIGTERM', onSignal);
    releaseMigrationLock(lockPath);
  }
}

const isMain = (() => {
  if (!process.argv[1]) return false;
  try {
    return fs.realpathSync(process.argv[1]) === fs.realpathSync(__filename);
  } catch {
    return path.resolve(process.argv[1]) === path.resolve(__filename);
  }
})();

if (isMain) {
  main().catch((err) => {
    console.error('[bootstrap] Error:', err);
    process.exit(1);
  });
}
