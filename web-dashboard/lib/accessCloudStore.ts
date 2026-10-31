import { drive, ROOT_FOLDER_ID } from './googleDrive';
import fs from 'fs';
import path from 'path';
import os from 'os';
import { Readable } from 'stream';

export const ACCESS_MUTATIONS_FILENAME = '.sharecoc_access_mutations.json';

export interface AccessRecord {
  _adh_id: string;
  _adh_file: string;
  _adh_table: string;
  _adh_created_at: string;
  _adh_updated_at?: string;
  [key: string]: any;
}

export interface AccessMutations {
  adds: AccessRecord[];
  updates: Record<string, Record<string, any>>;
  deletes: string[];
  last_sync: string;
}

const DEFAULT_MUTATIONS: AccessMutations = {
  adds: [],
  updates: {},
  deletes: [],
  last_sync: new Date().toISOString(),
};

// مسار التخزين المؤقت المحلي /tmp المضمون للكتابة حتى على خوادم Vercel Serverless
const TMP_MUTATIONS_PATH = path.join(os.tmpdir(), '.sharecoc_access_mutations.json');
const LOCAL_DATA_DIR = path.join(process.cwd(), 'data', 'access-hub');
const LOCAL_MUTATIONS_PATH = path.join(LOCAL_DATA_DIR, 'mutations.json');

// ذاكرة تخزين مؤقتة سريعة (In-memory Cache) لمنع استنزاف طلبات Google Drive
let _memoryCache: { data: AccessMutations; ts: number; fileId?: string } | null = null;
const CACHE_TTL_MS = 6000; // 6 ثوانٍ كاش لتسريع التصفح والـ Pagination

/**
 * جلب سجل التعديلات السحابية (Deltas & Mutations) من السحابة أو الكاش
 */
export async function getAccessHubMutations(forceRefresh: boolean = false): Promise<{ mutations: AccessMutations; fileId?: string }> {
  const now = Date.now();

  // 1. فحص الكاش في الذاكرة أولاً
  if (!forceRefresh && _memoryCache && (now - _memoryCache.ts < CACHE_TTL_MS)) {
    return { mutations: _memoryCache.data, fileId: _memoryCache.fileId };
  }

  // 2. فحص ملف /tmp المحلي كنسخة احتياطية فائقة السرعة
  if (!forceRefresh && !_memoryCache && fs.existsSync(TMP_MUTATIONS_PATH)) {
    try {
      const raw = fs.readFileSync(TMP_MUTATIONS_PATH, 'utf-8');
      const parsed = JSON.parse(raw);
      if (parsed && Array.isArray(parsed.adds)) {
        _memoryCache = { data: parsed, ts: now };
      }
    } catch {
      // تجاهل أخطاء القراءة ومتابعة السحابة
    }
  }

  // 3. الجلب المباشر من Google Drive
  try {
    const listRes: any = await drive.files.list({
      q: `'${ROOT_FOLDER_ID}' in parents and name = '${ACCESS_MUTATIONS_FILENAME}' and trashed = false`,
      fields: 'files(id, modifiedTime)',
      orderBy: 'modifiedTime desc',
      pageSize: 2,
    });

    const file = listRes.data.files?.[0];
    if (file && file.id) {
      const getRes: any = await drive.files.get(
        { fileId: file.id, alt: 'media' },
        { responseType: 'text' }
      );

      let parsed: AccessMutations = DEFAULT_MUTATIONS;
      if (typeof getRes.data === 'string') {
        parsed = JSON.parse(getRes.data);
      } else if (typeof getRes.data === 'object') {
        parsed = getRes.data;
      }

      // تنظيف وضمان سلامة البيانات
      parsed.adds = Array.isArray(parsed.adds) ? parsed.adds : [];
      parsed.updates = parsed.updates && typeof parsed.updates === 'object' ? parsed.updates : {};
      parsed.deletes = Array.isArray(parsed.deletes) ? parsed.deletes : [];
      parsed.last_sync = parsed.last_sync || new Date().toISOString();

      _memoryCache = { data: parsed, ts: now, fileId: file.id };

      // حفظ نسخة في /tmp
      try {
        fs.writeFileSync(TMP_MUTATIONS_PATH, JSON.stringify(parsed), 'utf-8');
      } catch {
        // تجاهل
      }

      return { mutations: parsed, fileId: file.id };
    }
  } catch (err) {
    console.warn('[AccessCloudStore] Google Drive fetch warning, using local/fallback:', err);
  }

  // 4. إذا لم يوجد في السحابة وكان موجوداً في القرص المحلي
  if (fs.existsSync(LOCAL_MUTATIONS_PATH)) {
    try {
      const raw = fs.readFileSync(LOCAL_MUTATIONS_PATH, 'utf-8');
      const parsed = JSON.parse(raw);
      _memoryCache = { data: parsed, ts: now };
      return { mutations: parsed };
    } catch {
      // تجاهل
    }
  }

  const fallback = _memoryCache?.data || DEFAULT_MUTATIONS;
  _memoryCache = { data: fallback, ts: now };
  return { mutations: fallback };
}

/**
 * حفظ التعديلات السحابية في Google Drive و /tmp بطريقة متزامنة وآمنة 100%
 */
export async function saveAccessHubMutations(mutations: AccessMutations): Promise<void> {
  mutations.last_sync = new Date().toISOString();
  const jsonStr = JSON.stringify(mutations);

  // 1. تحديث الذاكرة فوراً لتجاوب التطبيق بدون أي انتظار
  const fileId = _memoryCache?.fileId;
  _memoryCache = { data: mutations, ts: Date.now(), fileId };

  // 2. الحفظ في مسار /tmp المضمون للكتابة على Vercel وجميع البيئات
  try {
    fs.writeFileSync(TMP_MUTATIONS_PATH, jsonStr, 'utf-8');
  } catch (err) {
    console.warn('[AccessCloudStore] /tmp write warning:', err);
  }

  // 3. محاولة الحفظ في القرص المحلي إذا كان متاحاً للكتابة (بدون رمي استثناء EROFS)
  try {
    if (fs.existsSync(LOCAL_DATA_DIR)) {
      fs.writeFileSync(LOCAL_MUTATIONS_PATH, jsonStr, 'utf-8');
    }
  } catch {
    // بيئة قراءة فقط مثل Vercel، نتجاهل الخطأ تماماً
  }

  // 4. الحفظ السحابي في Google Drive لتعميم التعديل فوراً على جميع الموظفين
  try {
    const buffer = Buffer.from(jsonStr, 'utf-8');
    const stream = new Readable();
    stream.push(buffer);
    stream.push(null);

    let targetFileId = fileId;
    if (!targetFileId) {
      const check: any = await drive.files.list({
        q: `'${ROOT_FOLDER_ID}' in parents and name = '${ACCESS_MUTATIONS_FILENAME}' and trashed = false`,
        fields: 'files(id)',
        pageSize: 1,
      });
      targetFileId = check.data.files?.[0]?.id;
    }

    if (targetFileId) {
      await drive.files.update({
        fileId: targetFileId,
        media: {
          mimeType: 'application/json',
          body: stream,
        },
      });
      if (_memoryCache) _memoryCache.fileId = targetFileId;
    } else {
      const created: any = await drive.files.create({
        requestBody: {
          name: ACCESS_MUTATIONS_FILENAME,
          parents: [ROOT_FOLDER_ID],
          mimeType: 'application/json',
        },
        media: {
          mimeType: 'application/json',
          body: stream,
        },
        fields: 'id',
      });
      if (_memoryCache) _memoryCache.fileId = created.data.id;
    }
  } catch (err) {
    console.error('[AccessCloudStore] Failed to sync mutations to Google Drive:', err);
    // عدم رمي الخطأ حتى لا تتعطل تجربة المستخدم إذا كان هناك انقطاع مؤقت
  }
}

/**
 * إضافة قيد جديد وتخزينه سحابياً
 */
export async function addAccessRecord(file: string, table: string, record: any): Promise<AccessRecord> {
  const { mutations } = await getAccessHubMutations(true);

  const newId = `${file}_${table}_${Date.now()}_${Math.random().toString(36).substring(2, 7)}`;
  const newRecord: AccessRecord = {
    ...record,
    _adh_id: newId,
    _adh_file: file,
    _adh_table: table,
    _adh_created_at: new Date().toISOString(),
  };

  mutations.adds.unshift(newRecord);
  await saveAccessHubMutations(mutations);
  return newRecord;
}

/**
 * تعديل قيد وحفظ التعديلات سحابياً
 */
export async function updateAccessRecord(id: string, updates: Record<string, any>): Promise<Record<string, any>> {
  const { mutations } = await getAccessHubMutations(true);

  // إذا كان السجل من السجلات المضافة حديثاً في adds
  const addedIndex = mutations.adds.findIndex((r) => r._adh_id === id);
  if (addedIndex !== -1) {
    mutations.adds[addedIndex] = {
      ...mutations.adds[addedIndex],
      ...updates,
      _adh_updated_at: new Date().toISOString(),
    };
  } else {
    // وإلا يتم تسجيل التعديل في جدول الـ updates السحابي
    const prev = mutations.updates[id] || {};
    mutations.updates[id] = {
      ...prev,
      ...updates,
      _adh_updated_at: new Date().toISOString(),
    };
  }

  await saveAccessHubMutations(mutations);
  return { id, ...updates };
}

/**
 * حذف قيد وتعميمه سحابياً على جميع الموظفين
 */
export async function deleteAccessRecord(id: string): Promise<boolean> {
  const { mutations } = await getAccessHubMutations(true);

  // إذا كان في adds نزيله مباشرة
  mutations.adds = mutations.adds.filter((r) => r._adh_id !== id);

  // نضيفه إلى قائمة المحذوفات deletes
  if (!mutations.deletes.includes(id)) {
    mutations.deletes.push(id);
  }

  // إزالة أي تحديثات تخصه
  if (mutations.updates[id]) {
    delete mutations.updates[id];
  }

  await saveAccessHubMutations(mutations);
  return true;
}

/**
 * دمج التعديلات السحابية مع السجلات الأصلية بدقة 100%
 */
export function applyMutations(
  fileName: string,
  tableName: string,
  baseRows: any[],
  mutations: AccessMutations
): any[] {
  const deletesSet = new Set(mutations.deletes || []);
  const updatesMap = mutations.updates || {};

  // 1. تصفية وتحديث السجلات الأساسية
  const processedBase: any[] = [];
  for (let i = 0; i < baseRows.length; i++) {
    const row = baseRows[i];
    const id = row._adh_id || `${fileName}_${tableName}_${i}`;
    if (deletesSet.has(id)) {
      continue;
    }
    if (updatesMap[id]) {
      processedBase.push({ ...row, ...updatesMap[id], _adh_id: id });
    } else {
      processedBase.push(row._adh_id ? row : { ...row, _adh_id: id });
    }
  }

  // 2. استخراج السجلات المضافة حديثاً الخاصة بهذا الملف والجدول
  const relevantAdds: any[] = [];
  for (const added of mutations.adds || []) {
    if (deletesSet.has(added._adh_id)) {
      continue;
    }

    const matchesFile = fileName === 'all' || added._adh_file === fileName;
    const matchesTable = !tableName || added._adh_table === tableName;

    if (matchesFile && matchesTable) {
      let finalAdded = added;
      if (updatesMap[added._adh_id]) {
        finalAdded = { ...added, ...updatesMap[added._adh_id] };
      }
      relevantAdds.push(finalAdded);
    }
  }

  // السجلات المضافة تكون دائماً في الأعلى (أحدث السجلات أولاً)
  return [...relevantAdds, ...processedBase];
}
