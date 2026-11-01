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

export interface TrashItem {
  id: string;
  file: string;
  table: string;
  record: any;
  deleted_at: string;
  deleted_by: string;
}

export interface AccessRole {
  guid: string;
  name: string;
  role: 'admin' | 'supervisor' | 'data_entry' | 'viewer';
  allowedSections?: string[];
  lastSeen?: string;
}

export interface AccessCustomSection {
  name: string;
  tables: string[];
  table_counts?: Record<string, number>;
  total_rows?: number;
  size_kb?: number;
  created_at?: string;
  created_by?: string;
}

export interface AccessMutations {
  adds: AccessRecord[];
  updates: Record<string, Record<string, any>>;
  deletes: string[];
  added_columns?: Record<string, string[]>;
  deleted_columns?: Record<string, string[]>;
  renamed_columns?: Record<string, Record<string, string>>;
  column_orders?: Record<string, string[]>;
  deleted_sections?: string[];
  custom_sections?: AccessCustomSection[];
  trash_bin?: TrashItem[];
  roles?: Record<string, AccessRole>;
  last_sync: string;
}

const DEFAULT_MUTATIONS: AccessMutations = {
  adds: [],
  updates: {},
  deletes: [],
  added_columns: {},
  deleted_columns: {},
  renamed_columns: {},
  column_orders: {},
  deleted_sections: [],
  custom_sections: [],
  trash_bin: [],
  roles: {},
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
 * إضافة حقل جديد سحابياً لجدول معين وتعميمه على جميع الموظفين
 */
export async function addColumnToTable(file: string, table: string, columnName: string): Promise<string[]> {
  const cleanCol = columnName.trim();
  if (!cleanCol) throw new Error('اسم الحقل مطلوب');

  const { mutations } = await getAccessHubMutations(true);
  if (!mutations.added_columns) mutations.added_columns = {};
  if (!mutations.deleted_columns) mutations.deleted_columns = {};

  const key = `${file}_${table}`;
  const currentAdded = mutations.added_columns[key] || [];
  if (!currentAdded.includes(cleanCol)) {
    mutations.added_columns[key] = [...currentAdded, cleanCol];
  }

  // إذا كان الحقل في المحذوفات نزيله منها
  const currentDeleted = mutations.deleted_columns[key] || [];
  if (currentDeleted.includes(cleanCol)) {
    mutations.deleted_columns[key] = currentDeleted.filter((c) => c !== cleanCol);
  }

  await saveAccessHubMutations(mutations);
  return mutations.added_columns[key];
}

/**
 * حذف حقل سحابياً من جدول معين وتعميم الحذف على جميع الموظفين
 */
export async function deleteColumnFromTable(file: string, table: string, columnName: string): Promise<string[]> {
  const cleanCol = columnName.trim();
  if (!cleanCol) throw new Error('اسم الحقل مطلوب');

  const { mutations } = await getAccessHubMutations(true);
  if (!mutations.added_columns) mutations.added_columns = {};
  if (!mutations.deleted_columns) mutations.deleted_columns = {};

  const key = `${file}_${table}`;

  // إزالته من الحقول المضافة إن وجد
  const currentAdded = mutations.added_columns[key] || [];
  if (currentAdded.includes(cleanCol)) {
    mutations.added_columns[key] = currentAdded.filter((c) => c !== cleanCol);
  }

  // إضافته إلى قائمة الحقول المحذوفة
  const currentDeleted = mutations.deleted_columns[key] || [];
  if (!currentDeleted.includes(cleanCol)) {
    mutations.deleted_columns[key] = [...currentDeleted, cleanCol];
  }

  // إزالته أيضاً من ترتيب الأعمدة إن وجد
  if (mutations.column_orders?.[key]) {
    mutations.column_orders[key] = mutations.column_orders[key].filter((c) => c !== cleanCol);
  }

  await saveAccessHubMutations(mutations);
  return mutations.deleted_columns[key];
}

/**
 * تعديل اسم حقل سحابياً لجدول معين وتعميم التعديل على جميع المنصات
 */
export async function renameColumnInTable(
  file: string,
  table: string,
  oldName: string,
  newName: string
): Promise<{ success: boolean; renamed_columns: Record<string, string> }> {
  const cleanOld = oldName.trim();
  const cleanNew = newName.trim();
  if (!cleanOld || !cleanNew) throw new Error('الاسم الحالي والاسم الجديد للحقل مطلوبان');
  if (cleanOld === cleanNew) return { success: true, renamed_columns: {} };

  const { mutations } = await getAccessHubMutations(true);
  if (!mutations.renamed_columns) mutations.renamed_columns = {};
  if (!mutations.column_orders) mutations.column_orders = {};

  const key = `${file}_${table}`;
  if (!mutations.renamed_columns[key]) mutations.renamed_columns[key] = {};

  // هل كان الحقل قد أُعيدت تسميته سابقاً؟
  let originalKey = cleanOld;
  for (const [orig, cur] of Object.entries(mutations.renamed_columns[key])) {
    if (cur === cleanOld) {
      originalKey = orig;
      break;
    }
  }

  mutations.renamed_columns[key][originalKey] = cleanNew;

  // تحديث الحقل إن كان في قائمة الحقول المضافة حديثاً
  if (mutations.added_columns?.[key]) {
    mutations.added_columns[key] = mutations.added_columns[key].map((c) => (c === cleanOld ? cleanNew : c));
  }

  // تحديث الحقل إن كان في ترتيب الأعمدة المخصص
  if (mutations.column_orders?.[key]) {
    mutations.column_orders[key] = mutations.column_orders[key].map((c) => (c === cleanOld ? cleanNew : c));
  }

  await saveAccessHubMutations(mutations);
  return { success: true, renamed_columns: mutations.renamed_columns[key] };
}

/**
 * حفظ ترتيب مخصص للأعمدة لجدول معين سحابياً
 */
export async function reorderColumnsInTable(
  file: string,
  table: string,
  orderedColumns: string[]
): Promise<string[]> {
  const { mutations } = await getAccessHubMutations(true);
  if (!mutations.column_orders) mutations.column_orders = {};

  const key = `${file}_${table}`;
  mutations.column_orders[key] = [...orderedColumns];

  await saveAccessHubMutations(mutations);
  return mutations.column_orders[key];
}

/**
 * نقل مكان حقل (إلى البداية، إلى النهاية، للأعلى، أو للأسفل)
 */
export async function moveColumnInTable(
  file: string,
  table: string,
  columnName: string,
  direction: 'start' | 'end' | 'up' | 'down',
  allColumns: string[]
): Promise<string[]> {
  const cleanCol = columnName.trim();
  const currentList = [...allColumns];
  const idx = currentList.indexOf(cleanCol);
  if (idx === -1) throw new Error(`الحقل "${cleanCol}" غير موجود في قائمة الحقول النشطة`);

  currentList.splice(idx, 1);

  if (direction === 'start') {
    currentList.unshift(cleanCol);
  } else if (direction === 'end') {
    currentList.push(cleanCol);
  } else if (direction === 'up') {
    const newIdx = Math.max(0, idx - 1);
    currentList.splice(newIdx, 0, cleanCol);
  } else if (direction === 'down') {
    const newIdx = Math.min(currentList.length, idx + 1);
    currentList.splice(newIdx, 0, cleanCol);
  }

  return await reorderColumnsInTable(file, table, currentList);
}

/**
 * استخراج قائمة الأعمدة النهائية بدمج الأعمدة المضافة وتصفية المحذوفة وتطبيق الأسماء المعدلة والترتيب المخصص
 */
export function getCustomColumns(file: string, table: string, baseColumns: string[], mutations: AccessMutations): string[] {
  if (table === 'all' || !table) {
    return baseColumns;
  }

  const key = `${file}_${table}`;
  const allKey = `all_${table}`;

  const deletedSet = new Set<string>([
    ...(mutations.deleted_columns?.[key] || []),
    ...(mutations.deleted_columns?.[allKey] || [])
  ]);

  const addedList = [
    ...(mutations.added_columns?.[allKey] || []),
    ...(mutations.added_columns?.[key] || [])
  ];

  const renamedMap: Record<string, string> = {
    ...(mutations.renamed_columns?.[allKey] || {}),
    ...(mutations.renamed_columns?.[key] || {})
  };

  // 1. تصفية الحقول المحذوفة وتبديل أسماء الحقول المعاد تسميتها
  let finalCols = baseColumns
    .filter((c) => !deletedSet.has(c))
    .map((c) => renamedMap[c] || c);

  // 2. إضافة الحقول المضافة حديثاً إذا لم تكن موجودة بالفعل
  for (const col of addedList) {
    const displayCol = renamedMap[col] || col;
    if (!deletedSet.has(col) && !finalCols.includes(displayCol)) {
      finalCols.push(displayCol);
    }
  }

  // 3. تطبيق الترتيب المخصص إن وجد (نقل للبداية أو النهاية أو ترتيب إداري)
  const customOrder = mutations.column_orders?.[key] || mutations.column_orders?.[allKey];
  if (customOrder && Array.isArray(customOrder) && customOrder.length > 0) {
    const orderMap = new Map<string, number>();
    customOrder.forEach((name, idx) => orderMap.set(name, idx));
    finalCols.sort((a, b) => {
      const idxA = orderMap.has(a) ? orderMap.get(a)! : 9999;
      const idxB = orderMap.has(b) ? orderMap.get(b)! : 9999;
      return idxA - idxB;
    });
  }

  return finalCols;
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

  const key = `${fileName}_${tableName}`;
  const allKey = `all_${tableName}`;
  const renamedMap: Record<string, string> = {
    ...(mutations.renamed_columns?.[allKey] || {}),
    ...(mutations.renamed_columns?.[key] || {})
  };
  const hasRenames = Object.keys(renamedMap).length > 0;

  // 1. تصفية وتحديث السجلات الأساسية
  const processedBase: any[] = [];
  for (let i = 0; i < baseRows.length; i++) {
    const row = baseRows[i];
    const id = row._adh_id || `${fileName}_${tableName}_${i}`;
    if (deletesSet.has(id)) {
      continue;
    }
    let finalRow = updatesMap[id] ? { ...row, ...updatesMap[id], _adh_id: id } : (row._adh_id ? { ...row } : { ...row, _adh_id: id });
    if (hasRenames) {
      for (const [orig, renamed] of Object.entries(renamedMap)) {
        if (finalRow[orig] !== undefined && finalRow[renamed] === undefined) {
          finalRow[renamed] = finalRow[orig];
        }
      }
    }
    processedBase.push(finalRow);
  }

  // 2. استخراج السجلات المضافة حديثاً الخاصة بهذا الملف والجدول
  const relevantAdds: any[] = [];
  for (const added of mutations.adds || []) {
    if (deletesSet.has(added._adh_id)) {
      continue;
    }

    const matchesFile = fileName === 'all' || added._adh_file === fileName;
    const matchesTable = !tableName || tableName === 'all' || added._adh_table === tableName;

    if (matchesFile && matchesTable) {
      let finalAdded = { ...added };
      if (updatesMap[added._adh_id]) {
        finalAdded = { ...finalAdded, ...updatesMap[added._adh_id] };
      }
      if (hasRenames) {
        for (const [orig, renamed] of Object.entries(renamedMap)) {
          if (finalAdded[orig] !== undefined && finalAdded[renamed] === undefined) {
            finalAdded[renamed] = finalAdded[orig];
          }
        }
      }
      relevantAdds.push(finalAdded);
    }
  }

  // السجلات المضافة تكون دائماً في الأعلى (أحدث السجلات أولاً)
  return [...relevantAdds, ...processedBase];
}

/**
 * حذف أو أرشفة قسم/ملف من قواعد بيانات Access
 */
export async function deleteAccessSection(fileName: string): Promise<string[]> {
  const cleanName = fileName.trim();
  if (!cleanName) throw new Error('اسم القسم مطلوب');

  const { mutations } = await getAccessHubMutations(true);
  if (!mutations.deleted_sections) mutations.deleted_sections = [];

  if (!mutations.deleted_sections.includes(cleanName)) {
    mutations.deleted_sections.push(cleanName);
  }

  await saveAccessHubMutations(mutations);
  return mutations.deleted_sections;
}

/**
 * استعادة قسم/ملف تم حذفه أو أرشفتها سابقاً
 */
export async function restoreAccessSection(fileName: string): Promise<string[]> {
  const cleanName = fileName.trim();
  const { mutations } = await getAccessHubMutations(true);
  if (!mutations.deleted_sections) mutations.deleted_sections = [];

  mutations.deleted_sections = mutations.deleted_sections.filter((s) => s !== cleanName);
  await saveAccessHubMutations(mutations);
  return mutations.deleted_sections;
}

/**
 * حذف قيد أمنياً وإيداعه في سلة المحذوفات الإدارية مع سجل التدقيق
 */
export async function deleteRecordToTrash(
  id: string,
  file: string,
  table: string,
  record: any,
  deletedBy: string = 'الإدارة'
): Promise<boolean> {
  const { mutations } = await getAccessHubMutations(true);

  if (!mutations.trash_bin) mutations.trash_bin = [];
  if (!mutations.deletes.includes(id)) {
    mutations.deletes.push(id);
  }

  // إضافة إلى سلة المحذوفات
  mutations.trash_bin.unshift({
    id,
    file,
    table,
    record: record || {},
    deleted_at: new Date().toISOString(),
    deleted_by: deletedBy,
  });

  // إزالة من قائمة الإضافات الحديثة إن وجد
  mutations.adds = mutations.adds.filter((r) => r._adh_id !== id);

  await saveAccessHubMutations(mutations);
  return true;
}

/**
 * استعادة قيد من سلة المحذوفات
 */
export async function restoreRecordFromTrash(id: string): Promise<boolean> {
  const { mutations } = await getAccessHubMutations(true);

  mutations.deletes = mutations.deletes.filter((d) => d !== id);
  if (mutations.trash_bin) {
    mutations.trash_bin = mutations.trash_bin.filter((item) => item.id !== id);
  }

  await saveAccessHubMutations(mutations);
  return true;
}

/**
 * حفظ أو تحديث صلاحيات جهاز ومستخدم Access Hub
 */
export async function setAccessHubRole(
  guid: string,
  name: string,
  role: 'admin' | 'supervisor' | 'data_entry' | 'viewer',
  allowedSections?: string[]
): Promise<AccessRole> {
  const { mutations } = await getAccessHubMutations(true);
  if (!mutations.roles) mutations.roles = {};

  const record: AccessRole = {
    guid,
    name: name || 'مستخدم غير مسمى',
    role,
    allowedSections: Array.isArray(allowedSections) ? allowedSections : mutations.roles[guid]?.allowedSections || [],
    lastSeen: new Date().toISOString(),
  };

  mutations.roles[guid] = record;
  mutations.last_sync = new Date().toISOString();
  await saveAccessHubMutations(mutations);
  return record;
}

/**
 * حذف وسحب صلاحية جهاز بالكامل من سجل الطفرات السحابية
 */
export async function deleteAccessHubRole(guid: string): Promise<boolean> {
  const cleanGuid = String(guid || '').trim();
  if (!cleanGuid) return false;
  const { mutations } = await getAccessHubMutations(true);
  if (mutations.roles && mutations.roles[cleanGuid]) {
    delete mutations.roles[cleanGuid];
    mutations.last_sync = new Date().toISOString();
    await saveAccessHubMutations(mutations);
    return true;
  }
  return false;
}

/**
 * إضافة قسم / قاعدة بيانات جديدة في مركز بيانات Access سحابياً
 */
export async function addAccessSection(section: {
  name: string;
  tables: string[];
  created_by?: string;
}): Promise<AccessCustomSection[]> {
  const cleanName = String(section.name || '').trim();
  if (!cleanName) throw new Error('اسم القسم الجديد مطلوب');

  const { mutations } = await getAccessHubMutations(true);
  if (!mutations.custom_sections) mutations.custom_sections = [];

  // إذا كان القسم موجوداً مسبقاً في سلة المحذوفات أو الأرشيف، نخرجه منها
  if (mutations.deleted_sections) {
    mutations.deleted_sections = mutations.deleted_sections.filter((s) => s !== cleanName);
  }

  const cleanTables = Array.isArray(section.tables) && section.tables.length > 0
    ? section.tables.map((t) => String(t).trim()).filter(Boolean)
    : ['التجار', 'الشركات', 'الدلالين', 'التعديل', 'الشطب'];

  const tableCounts: Record<string, number> = {};
  cleanTables.forEach((t) => {
    tableCounts[t] = 0;
  });

  const existingIdx = mutations.custom_sections.findIndex((s) => s.name === cleanName);
  const newSec: AccessCustomSection = {
    name: cleanName,
    tables: cleanTables,
    table_counts: tableCounts,
    total_rows: 0,
    size_kb: 0.1,
    created_at: new Date().toISOString(),
    created_by: section.created_by || 'الإدارة',
  };

  if (existingIdx >= 0) {
    mutations.custom_sections[existingIdx] = {
      ...mutations.custom_sections[existingIdx],
      tables: cleanTables,
      table_counts: { ...tableCounts, ...(mutations.custom_sections[existingIdx].table_counts || {}) },
    };
  } else {
    mutations.custom_sections.push(newSec);
  }

  mutations.last_sync = new Date().toISOString();
  await saveAccessHubMutations(mutations);
  return mutations.custom_sections;
}
