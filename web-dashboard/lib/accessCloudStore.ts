import fs from 'fs';
import path from 'path';
import { STORAGE_ROOT, atomicWriteFileSync } from './localStorage';

export const ACCESS_MUTATIONS_FILENAME = '.sharecoc_access_mutations.json';
export const ACCESS_HUB_STORAGE_DIR = path.join(STORAGE_ROOT, 'access-hub');
export const ACCESS_MUTATIONS_PATH = path.join(ACCESS_HUB_STORAGE_DIR, 'mutations.json');
export const SEED_ACCESS_MUTATIONS_PATH = path.join(process.cwd(), 'data', 'access-hub', 'mutations.json');
const SEED_MARKER_PATH = path.join(ACCESS_HUB_STORAGE_DIR, '.mutations_seeded_v1.json');

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

export interface DynamicFileStats {
  name: string;
  tables: string[];
  table_counts: Record<string, number>;
  total_rows: number;
  size_kb: number;
  is_custom?: boolean;
}

export function computeDynamicStats(
  baseFiles: any[],
  customSections: AccessCustomSection[],
  mutations: AccessMutations
): { files: DynamicFileStats[]; total_records: number } {
  const deletedSet = new Set(mutations.deletes || []);
  const addsIdSet = new Set((mutations.adds || []).map((a) => a._adh_id));

  const fileMap = new Map<string, DynamicFileStats>();

  for (const f of baseFiles || []) {
    fileMap.set(f.name, {
      name: f.name,
      tables: Array.isArray(f.tables) ? [...f.tables] : [],
      table_counts: { ...(f.table_counts || {}) },
      total_rows: Number(f.total_rows) || 0,
      size_kb: Number(f.size_kb) || 0.1,
      is_custom: false,
    });
  }

  for (const cs of customSections || []) {
    if (!fileMap.has(cs.name)) {
      fileMap.set(cs.name, {
        name: cs.name,
        tables: Array.isArray(cs.tables) ? [...cs.tables] : [],
        table_counts: { ...(cs.table_counts || {}) },
        total_rows: Number(cs.total_rows) || 0,
        size_kb: Number(cs.size_kb) || 0.1,
        is_custom: true,
      });
    }
  }

  for (const add of mutations.adds || []) {
    if (!add || !add._adh_file || !add._adh_table) continue;
    if (deletedSet.has(add._adh_id)) continue;

    let fObj = fileMap.get(add._adh_file);
    if (!fObj) {
      fObj = {
        name: add._adh_file,
        tables: [],
        table_counts: {},
        total_rows: 0,
        size_kb: 0.1,
        is_custom: true,
      };
      fileMap.set(add._adh_file, fObj);
    }

    if (!fObj.tables.includes(add._adh_table)) {
      fObj.tables.push(add._adh_table);
    }

    fObj.table_counts[add._adh_table] = (fObj.table_counts[add._adh_table] || 0) + 1;
    fObj.total_rows = (fObj.total_rows || 0) + 1;
  }

  const trashLookup = new Map<string, { file: string; table: string }>();
  for (const t of mutations.trash_bin || []) {
    if (t && t.id) {
      trashLookup.set(t.id, { file: t.file, table: t.table });
    }
  }

  const delList = Array.from(deletedSet);
  const allFileObjects = Array.from(fileMap.values());

  for (const delId of delList) {
    if (addsIdSet.has(delId)) continue;

    let fName: string | null = null;
    let tName: string | null = null;

    if (trashLookup.has(delId)) {
      const t = trashLookup.get(delId)!;
      fName = t.file;
      tName = t.table;
    } else {
      for (const f of allFileObjects) {
        const prefix = f.name + '_';
        if (delId.startsWith(prefix)) {
          const rest = delId.slice(prefix.length);
          for (const tbl of f.tables) {
            if (rest.startsWith(tbl + '_') || rest === tbl) {
              fName = f.name;
              tName = tbl;
              break;
            }
          }
          if (fName) break;
        }
      }
    }

    if (fName && fileMap.has(fName)) {
      const fObj = fileMap.get(fName)!;
      if (tName && fObj.table_counts[tName] !== undefined) {
        fObj.table_counts[tName] = Math.max(0, fObj.table_counts[tName] - 1);
      }
      fObj.total_rows = Math.max(0, fObj.total_rows - 1);
    }
  }

  const allFiles = Array.from(fileMap.values());
  const grandTotal = allFiles.reduce((acc, f) => acc + (f.total_rows || 0), 0);

  return { files: allFiles, total_records: grandTotal };
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

function createDefaultMutations(): AccessMutations {
  return {
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
}

function normalizeMutations(raw: any): AccessMutations {
  const parsed = raw && typeof raw === 'object' ? raw : {};
  return {
    adds: Array.isArray(parsed.adds) ? parsed.adds : [],
    updates:
      parsed.updates && typeof parsed.updates === 'object' && !Array.isArray(parsed.updates)
        ? parsed.updates
        : {},
    deletes: Array.isArray(parsed.deletes) ? parsed.deletes : [],
    added_columns:
      parsed.added_columns && typeof parsed.added_columns === 'object' ? parsed.added_columns : {},
    deleted_columns:
      parsed.deleted_columns && typeof parsed.deleted_columns === 'object' ? parsed.deleted_columns : {},
    renamed_columns:
      parsed.renamed_columns && typeof parsed.renamed_columns === 'object' ? parsed.renamed_columns : {},
    column_orders:
      parsed.column_orders && typeof parsed.column_orders === 'object' ? parsed.column_orders : {},
    deleted_sections: Array.isArray(parsed.deleted_sections) ? parsed.deleted_sections : [],
    custom_sections: Array.isArray(parsed.custom_sections) ? parsed.custom_sections : [],
    trash_bin: Array.isArray(parsed.trash_bin) ? parsed.trash_bin : [],
    roles: parsed.roles && typeof parsed.roles === 'object' ? parsed.roles : {},
    last_sync:
      typeof parsed.last_sync === 'string' && parsed.last_sync
        ? parsed.last_sync
        : new Date().toISOString(),
  };
}

function countMutationEntries(m: any): number {
  const addsCount = Array.isArray(m?.adds) ? m.adds.length : 0;
  const updatesCount =
    m?.updates && typeof m.updates === 'object'
      ? Array.isArray(m.updates)
        ? m.updates.length
        : Object.keys(m.updates).length
      : 0;
  return addsCount + updatesCount;
}

let _memoryCache: { data: AccessMutations; ts: number; mtimeMs: number } | null = null;
const CACHE_TTL_MS = 6000;
let _mutationsQueue: Promise<any> = Promise.resolve();
let _seedCheckedOnce = false;

function enqueueMutation<T>(fn: () => Promise<T> | T): Promise<T> {
  const run = () => Promise.resolve().then(fn);
  const next = _mutationsQueue.then(run, run);
  _mutationsQueue = next.catch(() => {});
  return next;
}

function readJsonSafe(filePath: string): any | null {
  try {
    if (!fs.existsSync(filePath)) return null;
    const raw = fs.readFileSync(filePath, 'utf-8');
    if (!raw || !raw.trim()) return null;
    return JSON.parse(raw.replace(/^\uFEFF/, '').trim());
  } catch {
    return null;
  }
}

function ensureMutationsSeededSync(): void {
  fs.mkdirSync(ACCESS_HUB_STORAGE_DIR, { recursive: true });
  const targetExists = fs.existsSync(ACCESS_MUTATIONS_PATH);

  if (targetExists && _seedCheckedOnce) {
    return;
  }
  _seedCheckedOnce = true;

  if (!fs.existsSync(SEED_ACCESS_MUTATIONS_PATH)) {
    if (!targetExists) {
      atomicWriteFileSync(ACCESS_MUTATIONS_PATH, JSON.stringify(createDefaultMutations()));
    }
    return;
  }

  const seedParsed = readJsonSafe(SEED_ACCESS_MUTATIONS_PATH);
  if (!seedParsed) {
    if (!targetExists) {
      atomicWriteFileSync(ACCESS_MUTATIONS_PATH, JSON.stringify(createDefaultMutations()));
    }
    return;
  }

  const seedNormalized = normalizeMutations(seedParsed);
  const seedCount = countMutationEntries(seedNormalized);

  if (!targetExists) {
    atomicWriteFileSync(ACCESS_MUTATIONS_PATH, JSON.stringify(seedNormalized));
    atomicWriteFileSync(
      SEED_MARKER_PATH,
      JSON.stringify({ seededCount: seedCount, seededAt: new Date().toISOString() })
    );
    return;
  }

  const existingParsed = readJsonSafe(ACCESS_MUTATIONS_PATH);
  const existingCount = existingParsed ? countMutationEntries(existingParsed) : 0;
  const marker = readJsonSafe(SEED_MARKER_PATH);

  if (
    (existingCount === 0 && seedCount > 0) ||
    (seedCount > existingCount && (!marker || Number(marker.seededCount || 0) < seedCount))
  ) {
    atomicWriteFileSync(ACCESS_MUTATIONS_PATH, JSON.stringify(seedNormalized));
    atomicWriteFileSync(
      SEED_MARKER_PATH,
      JSON.stringify({ seededCount: seedCount, seededAt: new Date().toISOString() })
    );
  } else if (!marker && existingCount >= seedCount) {
    atomicWriteFileSync(
      SEED_MARKER_PATH,
      JSON.stringify({ seededCount: seedCount, seededAt: new Date().toISOString() })
    );
  }
}

function readMutationsFromDiskSync(): AccessMutations {
  ensureMutationsSeededSync();
  const parsed = readJsonSafe(ACCESS_MUTATIONS_PATH);
  const normalized = normalizeMutations(parsed || createDefaultMutations());
  const stat = fs.existsSync(ACCESS_MUTATIONS_PATH) ? fs.statSync(ACCESS_MUTATIONS_PATH) : null;
  _memoryCache = {
    data: normalized,
    ts: Date.now(),
    mtimeMs: stat ? stat.mtimeMs : 0,
  };
  return normalized;
}

function writeMutationsToDiskSync(mutations: AccessMutations): AccessMutations {
  fs.mkdirSync(ACCESS_HUB_STORAGE_DIR, { recursive: true });
  const normalized = normalizeMutations({
    ...mutations,
    last_sync: new Date().toISOString(),
  });
  atomicWriteFileSync(ACCESS_MUTATIONS_PATH, JSON.stringify(normalized));
  const stat = fs.statSync(ACCESS_MUTATIONS_PATH);
  _memoryCache = {
    data: normalized,
    ts: Date.now(),
    mtimeMs: stat.mtimeMs,
  };
  return normalized;
}

export async function getAccessHubMutations(
  forceRefresh: boolean = false
): Promise<{ mutations: AccessMutations; fileId?: string; storageMode: 'local-disk' }> {
  ensureMutationsSeededSync();
  const now = Date.now();
  const stat = fs.existsSync(ACCESS_MUTATIONS_PATH) ? fs.statSync(ACCESS_MUTATIONS_PATH) : null;
  const diskMtime = stat ? stat.mtimeMs : 0;

  if (
    !forceRefresh &&
    _memoryCache &&
    _memoryCache.mtimeMs === diskMtime &&
    now - _memoryCache.ts < CACHE_TTL_MS
  ) {
    return { mutations: _memoryCache.data, fileId: 'local-disk', storageMode: 'local-disk' };
  }

  const data = readMutationsFromDiskSync();
  return { mutations: data, fileId: 'local-disk', storageMode: 'local-disk' };
}

export async function saveAccessHubMutations(mutations: AccessMutations): Promise<void> {
  await enqueueMutation(() => {
    writeMutationsToDiskSync(mutations);
  });
}

async function mutateAccessHub<T>(
  mutator: (mutations: AccessMutations) => T | Promise<T>
): Promise<T> {
  return enqueueMutation(async () => {
    const mutations = readMutationsFromDiskSync();
    const result = await mutator(mutations);
    writeMutationsToDiskSync(mutations);
    return result;
  });
}

export async function getAccessMutationStats() {
  const { mutations } = await getAccessHubMutations(false);
  return {
    storageMode: 'local-disk' as const,
    path: ACCESS_MUTATIONS_PATH,
    addsCount: mutations.adds.length,
    updatesCount: Object.keys(mutations.updates || {}).length,
    deletesCount: mutations.deletes.length,
    trashCount: (mutations.trash_bin || []).length,
    rolesCount: Object.keys(mutations.roles || {}).length,
    customSectionsCount: (mutations.custom_sections || []).length,
    lastSync: mutations.last_sync,
  };
}

export async function addAccessRecord(file: string, table: string, record: any): Promise<AccessRecord> {
  return mutateAccessHub((mutations) => {
    const newId = `${file}_${table}_${Date.now()}_${Math.random().toString(36).substring(2, 7)}`;
    const newRecord: AccessRecord = {
      ...record,
      _adh_id: newId,
      _adh_file: file,
      _adh_table: table,
      _adh_created_at: new Date().toISOString(),
    };

    mutations.adds.unshift(newRecord);
    return newRecord;
  });
}

export async function updateAccessRecord(
  id: string,
  updates: Record<string, any>
): Promise<Record<string, any>> {
  return mutateAccessHub((mutations) => {
    const addedIndex = mutations.adds.findIndex((r) => r._adh_id === id);
    if (addedIndex !== -1) {
      mutations.adds[addedIndex] = {
        ...mutations.adds[addedIndex],
        ...updates,
        _adh_updated_at: new Date().toISOString(),
      };
    } else {
      const prev = mutations.updates[id] || {};
      mutations.updates[id] = {
        ...prev,
        ...updates,
        _adh_updated_at: new Date().toISOString(),
      };
    }

    return { id, ...updates };
  });
}

export async function deleteAccessRecord(id: string): Promise<boolean> {
  return mutateAccessHub((mutations) => {
    mutations.adds = mutations.adds.filter((r) => r._adh_id !== id);
    if (!mutations.deletes.includes(id)) {
      mutations.deletes.push(id);
    }
    if (mutations.updates[id]) {
      delete mutations.updates[id];
    }
    return true;
  });
}

export async function addColumnToTable(
  file: string,
  table: string,
  columnName: string,
  allTablesInFile?: string[]
): Promise<string[]> {
  const cleanCol = columnName.trim();
  if (!cleanCol) throw new Error('اسم الحقل مطلوب');

  return mutateAccessHub((mutations) => {
    if (!mutations.added_columns) mutations.added_columns = {};
    if (!mutations.deleted_columns) mutations.deleted_columns = {};

    const isAllTables = table === 'all' || table === 'all_categories' || table === 'جميع الأصناف';
    const targetKeys: string[] = [];

    if (isAllTables) {
      targetKeys.push(`${file}_all`);
      targetKeys.push(`all_all`);
      const tables = allTablesInFile && allTablesInFile.length > 0 ? allTablesInFile : [];
      tables.forEach((t) => {
        targetKeys.push(`${file}_${t}`);
      });
    } else {
      targetKeys.push(`${file}_${table}`);
    }

    for (const key of targetKeys) {
      const currentAdded = mutations.added_columns[key] || [];
      if (!currentAdded.includes(cleanCol)) {
        mutations.added_columns[key] = [...currentAdded, cleanCol];
      }
      const currentDeleted = mutations.deleted_columns[key] || [];
      if (currentDeleted.includes(cleanCol)) {
        mutations.deleted_columns[key] = currentDeleted.filter((c) => c !== cleanCol);
      }
    }

    return mutations.added_columns[targetKeys[0]] || [cleanCol];
  });
}

export async function deleteColumnFromTable(
  file: string,
  table: string,
  columnName: string,
  allTablesInFile?: string[]
): Promise<string[]> {
  const cleanCol = columnName.trim();
  if (!cleanCol) throw new Error('اسم الحقل مطلوب');

  return mutateAccessHub((mutations) => {
    if (!mutations.added_columns) mutations.added_columns = {};
    if (!mutations.deleted_columns) mutations.deleted_columns = {};

    const isAllTables = table === 'all' || table === 'all_categories' || table === 'جميع الأصناف';
    const targetKeys: string[] = [];

    if (isAllTables) {
      targetKeys.push(`${file}_all`);
      targetKeys.push(`all_all`);
      const tables = allTablesInFile && allTablesInFile.length > 0 ? allTablesInFile : [];
      tables.forEach((t) => {
        targetKeys.push(`${file}_${t}`);
      });
    } else {
      targetKeys.push(`${file}_${table}`);
    }

    for (const key of targetKeys) {
      const currentAdded = mutations.added_columns[key] || [];
      if (currentAdded.includes(cleanCol)) {
        mutations.added_columns[key] = currentAdded.filter((c) => c !== cleanCol);
      }

      const currentDeleted = mutations.deleted_columns[key] || [];
      if (!currentDeleted.includes(cleanCol)) {
        mutations.deleted_columns[key] = [...currentDeleted, cleanCol];
      }

      if (mutations.column_orders?.[key]) {
        mutations.column_orders[key] = mutations.column_orders[key].filter((c) => c !== cleanCol);
      }
    }

    return mutations.deleted_columns[targetKeys[0]] || [cleanCol];
  });
}

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

  return mutateAccessHub((mutations) => {
    if (!mutations.renamed_columns) mutations.renamed_columns = {};
    if (!mutations.column_orders) mutations.column_orders = {};

    const key = `${file}_${table}`;
    if (!mutations.renamed_columns[key]) mutations.renamed_columns[key] = {};

    let originalKey = cleanOld;
    for (const [orig, cur] of Object.entries(mutations.renamed_columns[key])) {
      if (cur === cleanOld) {
        originalKey = orig;
        break;
      }
    }

    mutations.renamed_columns[key][originalKey] = cleanNew;

    if (mutations.added_columns?.[key]) {
      mutations.added_columns[key] = mutations.added_columns[key].map((c) =>
        c === cleanOld ? cleanNew : c
      );
    }

    if (mutations.column_orders?.[key]) {
      mutations.column_orders[key] = mutations.column_orders[key].map((c) =>
        c === cleanOld ? cleanNew : c
      );
    }

    return { success: true, renamed_columns: mutations.renamed_columns[key] };
  });
}

export async function reorderColumnsInTable(
  file: string,
  table: string,
  orderedColumns: string[]
): Promise<string[]> {
  return mutateAccessHub((mutations) => {
    if (!mutations.column_orders) mutations.column_orders = {};
    const key = `${file}_${table}`;
    mutations.column_orders[key] = [...orderedColumns];
    return mutations.column_orders[key];
  });
}

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

export function getCustomColumns(
  file: string,
  table: string,
  baseColumns: string[],
  mutations: AccessMutations
): string[] {
  const key = `${file}_${table}`;
  const allKey = `all_${table}`;
  const fileAllKey = `${file}_all`;
  const allAllKey = `all_all`;

  const deletedSet = new Set<string>([
    ...(mutations.deleted_columns?.[key] || []),
    ...(mutations.deleted_columns?.[allKey] || []),
    ...(mutations.deleted_columns?.[fileAllKey] || []),
    ...(mutations.deleted_columns?.[allAllKey] || []),
  ]);

  const addedList = [
    ...(mutations.added_columns?.[allAllKey] || []),
    ...(mutations.added_columns?.[fileAllKey] || []),
    ...(mutations.added_columns?.[allKey] || []),
    ...(mutations.added_columns?.[key] || []),
  ];

  const renamedMap: Record<string, string> = {
    ...(mutations.renamed_columns?.[allAllKey] || {}),
    ...(mutations.renamed_columns?.[fileAllKey] || {}),
    ...(mutations.renamed_columns?.[allKey] || {}),
    ...(mutations.renamed_columns?.[key] || {}),
  };

  const finalCols = baseColumns
    .filter((c) => !deletedSet.has(c))
    .map((c) => renamedMap[c] || c);

  for (const col of addedList) {
    const displayCol = renamedMap[col] || col;
    if (!deletedSet.has(col) && !finalCols.includes(displayCol)) {
      finalCols.push(displayCol);
    }
  }

  const customOrder =
    mutations.column_orders?.[key] ||
    mutations.column_orders?.[allKey] ||
    mutations.column_orders?.[fileAllKey] ||
    mutations.column_orders?.[allAllKey];

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
    ...(mutations.renamed_columns?.[key] || {}),
  };
  const hasRenames = Object.keys(renamedMap).length > 0;

  const processedBase: any[] = [];
  for (let i = 0; i < baseRows.length; i++) {
    const row = baseRows[i];
    const id = row._adh_id || `${fileName}_${tableName}_${i}`;
    if (deletesSet.has(id)) {
      continue;
    }
    const finalRow = updatesMap[id]
      ? { ...row, ...updatesMap[id], _adh_id: id }
      : row._adh_id
        ? { ...row }
        : { ...row, _adh_id: id };
    if (hasRenames) {
      for (const [orig, renamed] of Object.entries(renamedMap)) {
        if (finalRow[orig] !== undefined && finalRow[renamed] === undefined) {
          finalRow[renamed] = finalRow[orig];
        }
      }
    }
    processedBase.push(finalRow);
  }

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

  return [...relevantAdds, ...processedBase];
}

export async function deleteAccessSection(fileName: string): Promise<string[]> {
  const cleanName = fileName.trim();
  if (!cleanName) throw new Error('اسم القسم مطلوب');

  return mutateAccessHub((mutations) => {
    if (!mutations.deleted_sections) mutations.deleted_sections = [];
    if (!mutations.deleted_sections.includes(cleanName)) {
      mutations.deleted_sections.push(cleanName);
    }
    return mutations.deleted_sections;
  });
}

export async function restoreAccessSection(fileName: string): Promise<string[]> {
  const cleanName = fileName.trim();

  return mutateAccessHub((mutations) => {
    if (!mutations.deleted_sections) mutations.deleted_sections = [];
    mutations.deleted_sections = mutations.deleted_sections.filter((s) => s !== cleanName);
    return mutations.deleted_sections;
  });
}

export async function deleteRecordToTrash(
  id: string,
  file: string,
  table: string,
  record: any,
  deletedBy: string = 'الإدارة'
): Promise<boolean> {
  return mutateAccessHub((mutations) => {
    if (!mutations.trash_bin) mutations.trash_bin = [];
    if (!mutations.deletes.includes(id)) {
      mutations.deletes.push(id);
    }

    mutations.trash_bin.unshift({
      id,
      file,
      table,
      record: record || {},
      deleted_at: new Date().toISOString(),
      deleted_by: deletedBy,
    });

    mutations.adds = mutations.adds.filter((r) => r._adh_id !== id);
    return true;
  });
}

export async function restoreRecordFromTrash(id: string): Promise<boolean> {
  return mutateAccessHub((mutations) => {
    mutations.deletes = mutations.deletes.filter((d) => d !== id);
    if (mutations.trash_bin) {
      mutations.trash_bin = mutations.trash_bin.filter((item) => item.id !== id);
    }
    return true;
  });
}

export async function setAccessHubRole(
  guid: string,
  name: string,
  role: 'admin' | 'supervisor' | 'data_entry' | 'viewer',
  allowedSections?: string[]
): Promise<AccessRole> {
  return mutateAccessHub((mutations) => {
    if (!mutations.roles) mutations.roles = {};

    const record: AccessRole = {
      guid,
      name: name || 'مستخدم غير مسمى',
      role,
      allowedSections: Array.isArray(allowedSections)
        ? allowedSections
        : mutations.roles[guid]?.allowedSections || [],
      lastSeen: new Date().toISOString(),
    };

    mutations.roles[guid] = record;
    mutations.last_sync = new Date().toISOString();
    return record;
  });
}

export async function deleteAccessHubRole(guid: string): Promise<boolean> {
  const cleanGuid = String(guid || '').trim();
  if (!cleanGuid) return false;
  return mutateAccessHub((mutations) => {
    if (mutations.roles && mutations.roles[cleanGuid]) {
      delete mutations.roles[cleanGuid];
      mutations.last_sync = new Date().toISOString();
      return true;
    }
    return false;
  });
}

export async function addAccessSection(section: {
  name: string;
  tables: string[];
  created_by?: string;
}): Promise<AccessCustomSection[]> {
  const cleanName = String(section.name || '').trim();
  if (!cleanName) throw new Error('اسم القسم الجديد مطلوب');

  return mutateAccessHub((mutations) => {
    if (!mutations.custom_sections) mutations.custom_sections = [];

    if (mutations.deleted_sections) {
      mutations.deleted_sections = mutations.deleted_sections.filter((s) => s !== cleanName);
    }

    const cleanTables =
      Array.isArray(section.tables) && section.tables.length > 0
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
        table_counts: {
          ...tableCounts,
          ...(mutations.custom_sections[existingIdx].table_counts || {}),
        },
      };
    } else {
      mutations.custom_sections.push(newSec);
    }

    mutations.last_sync = new Date().toISOString();
    return mutations.custom_sections;
  });
}
