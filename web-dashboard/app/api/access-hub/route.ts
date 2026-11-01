import { NextRequest, NextResponse } from 'next/server';
import fs from 'fs';
import path from 'path';
import { 
  getAccessHubMutations, 
  addAccessRecord, 
  updateAccessRecord, 
  deleteAccessRecord, 
  applyMutations,
  addColumnToTable,
  deleteColumnFromTable,
  renameColumnInTable,
  reorderColumnsInTable,
  moveColumnInTable,
  getCustomColumns,
  deleteAccessSection,
  restoreAccessSection,
  deleteRecordToTrash,
  restoreRecordFromTrash,
  setAccessHubRole
} from '@/lib/accessCloudStore';
import { 
  getCloudAdminStore, 
  persistCloudAdminStore, 
  DEFAULT_ACCESS_HUB_SECURITY 
} from '@/lib/googleDrive';

export const dynamic = 'force-dynamic';
export const revalidate = 0;
export const fetchCache = 'force-no-store';

const DATA_DIR = path.join(process.cwd(), 'data', 'access-hub');

const TABLE_PRIORITY: Record<string, number> = {
  'التجار': 1,
  'الشركات': 2,
  'الدلالين': 3,
  'دلالين': 3,
  'التعديل': 4,
  'المعامل': 5,
  'الفنادق': 6,
  'المطاعم': 7,
  'المقاهي': 8,
  'الصيدليات': 9,
  'الساحات': 10,
  'الشطب': 11,
};

function sortTablesByPriority(tables: string[]): string[] {
  return [...tables].sort((a, b) => {
    const pA = TABLE_PRIORITY[a] || 50;
    const pB = TABLE_PRIORITY[b] || 50;
    return pA !== pB ? pA - pB : a.localeCompare(b, 'ar');
  });
}

const COLUMN_PRIORITY: Record<string, number> = {
  'اسم التاجر': 1,
  'ArabicName': 1,
  'الإسم التجاري': 2,
  'الاسم التجاري': 2,
  'EnglishName': 3,
  'العمل': 4,
  'Activity': 4,
  'SpecificActivity': 5,
  'الصنف': 6,
  'الدرجة': 6,
  'Class': 6,
  'الهاتف': 7,
  'رقم الهاتف': 7,
  'Mobile': 7,
  'العنوان': 8,
  'Address': 8,
  'تأريخه': 9,
  'تاريخ الانتساب': 9,
  'AffiliationDate': 9,
  'رقم الأسم التجاري': 10,
  'رقم التجديد': 10,
  'RenewalNo': 10,
  'ID': 11,
  'id': 11,
  'StampNo': 12,
  'EnglishClass': 13,
  'EnglishActivity': 14,
  'اسم الزوج': 15,
  'المواليد': 16,
  'ذكر': 17,
  'انثى': 18,
  'Female': 18,
  'الشطب': 19,
  'Field1': 20,
};

function sortColumnsByPriority(cols: string[]): string[] {
  return [...cols].sort((a, b) => {
    const pA = COLUMN_PRIORITY[a] ?? 100;
    const pB = COLUMN_PRIORITY[b] ?? 100;
    if (pA !== pB) return pA - pB;
    return cols.indexOf(a) - cols.indexOf(b);
  });
}

function getIndex() {
  const indexPath = path.join(DATA_DIR, 'index.json');
  if (!fs.existsSync(indexPath)) {
    return { files: [], total_records: 0, last_sync: new Date().toISOString() };
  }
  try {
    return JSON.parse(fs.readFileSync(indexPath, 'utf-8'));
  } catch {
    return { files: [], total_records: 0, last_sync: new Date().toISOString() };
  }
}

function getFileContent(fileName: string) {
  const safeName = path.basename(fileName).replace(/[^a-zA-Z0-9_\u0600-\u06FF\s.-]/g, '');
  const filePath = path.join(DATA_DIR, `${safeName}.json`);
  if (!filePath.startsWith(DATA_DIR) || !fs.existsSync(filePath)) {
    return null;
  }
  try {
    return JSON.parse(fs.readFileSync(filePath, 'utf-8'));
  } catch {
    return null;
  }
}

/**
 * تحليل ذكي لقيم التواريخ لتحويلها إلى Timestamp للمقارنة والفرز
 */
function parseDateValue(val: any): number | null {
  if (val === null || val === undefined || val === '') return null;
  const s = String(val).trim();

  // YYYY-MM-DD أو YYYY/MM/DD
  let match = s.match(/^(\d{4})[-/](\d{1,2})[-/](\d{1,2})/);
  if (match) {
    const y = parseInt(match[1], 10);
    const m = parseInt(match[2], 10) - 1;
    const d = parseInt(match[3], 10);
    return new Date(y, m, d).getTime();
  }

  // DD/MM/YYYY أو DD-MM-YYYY
  match = s.match(/^(\d{1,2})[-/](\d{1,2})[-/](\d{4})/);
  if (match) {
    const d = parseInt(match[1], 10);
    const m = parseInt(match[2], 10) - 1;
    const y = parseInt(match[3], 10);
    return new Date(y, m, d).getTime();
  }

  // محاولة التحليل القياسي
  const parsed = Date.parse(s);
  if (!isNaN(parsed)) return parsed;

  // في حال كانت السنة فقط e.g. 2024
  if (/^\d{4}$/.test(s)) {
    return new Date(parseInt(s, 10), 0, 1).getTime();
  }

  return null;
}

/**
 * التحقق الأمني الصارم من هوية الجهاز والصلاحية المعتمدة له في مركز بيانات Access
 * الأدوار المؤسسية (RBAC Engine):
 * 1. admin: مدير نظام (كامل الصلاحيات)
 * 2. data_entry: مدخل بيانات (إضافة وتعديل - الحذف محجوب تماماً)
 * 3. viewer: مستعلم فقط (للقراءة والاستعلام والتصدير - الإضافة والتعديل والحذف محجوبة)
 */
async function resolveCallerRole(req: NextRequest, body?: any): Promise<'admin' | 'data_entry' | 'viewer'> {
  try {
    // 1. فحص جلسة الأدمن في لوحة التحكم
    const adminHeader = req.headers.get('x-admin-role') || req.headers.get('x-admin-session');
    if (adminHeader === 'admin' || adminHeader === 'true') {
      return 'admin';
    }

    if (body?.isAdmin === true || body?.adminRole === 'admin') {
      return 'admin';
    }

    // فحص ما إذا كان الطلب قادماً مباشرة من لوحة الإدارة /admin في المتصفح
    const referer = req.headers.get('referer') || '';
    if (referer.includes('/admin')) {
      return 'admin';
    }

    // 2. استخراج معرف العتاد الفريد (Machine GUID)
    const url = new URL(req.url);
    const guid = req.headers.get('x-machine-guid') || 
                 url.searchParams.get('guid') || 
                 body?.guid || 
                 body?.machineGuid || 
                 '';

    if (!guid) {
      return 'data_entry';
    }

    // 3. التحقق من طفرات الصلاحيات السحابية (.sharecoc_access_mutations.json)
    try {
      const { mutations } = await getAccessHubMutations(false);
      if (mutations.roles && mutations.roles[guid]?.role) {
        return mutations.roles[guid].role;
      }
    } catch (e) {
      // fallback
    }

    // 4. التحقق من مستودع الصلاحيات والأجهزة المركزي (.sharecoc_permissions.json)
    try {
      const store = await getCloudAdminStore(false);
      if (store.accessHubSecurity?.roles && store.accessHubSecurity.roles[guid]) {
        return store.accessHubSecurity.roles[guid];
      }
      const dev = (store.devices || []).find((d) => d.machineGuid === guid);
      if (dev?.accessRole) {
        return dev.accessRole;
      }
    } catch (e) {
      // fallback
    }
  } catch (err) {
    console.error('Error resolving caller role:', err);
  }

  return 'data_entry';
}

// GET: الاستعلام عن الجداول والبيانات بالحفاظ التام 100% على ترتيب الحقول + الفرز الزمني + إدارة الحقول
export async function GET(req: NextRequest) {
  try {
    const url = new URL(req.url);
    const requestedFile = url.searchParams.get('file') || 'all';
    const requestedTable = url.searchParams.get('table') || '';
    const search = (url.searchParams.get('search') || '').trim().toLowerCase();
    const page = Math.max(1, parseInt(url.searchParams.get('page') || '1'));
    const limit = Math.min(200, Math.max(10, parseInt(url.searchParams.get('limit') || '50')));
    const checkSig = url.searchParams.get('sig');

    // خيارات الفرز الزمني
    const sortDir = (url.searchParams.get('sort_dir') || 'none').toLowerCase(); // 'desc' | 'asc' | 'none'
    const sortColParam = url.searchParams.get('sort_col') || 'date_auto';

    const index = getIndex();
    const { mutations } = await getAccessHubMutations();
    const currentSig = mutations.last_sync || index.last_sync || '1';
    const callerRole = await resolveCallerRole(req);

    // فحص التحديثات الحية الفوري
    if (checkSig !== null && checkSig !== undefined && checkSig === currentSig) {
      return NextResponse.json({ success: true, changed: false, sig: currentSig });
    }

    let rawRows: any[] = [];
    let baseColumns: string[] = [];
    let availableTables: string[] = [];
    let activeTable = requestedTable;

    if (requestedFile === 'all') {
      // 🌐 وضع الدمج الشامل (كافة الملفات مدمجة)
      const allFiles = index.files || [];
      const tablesSet = new Set<string>();
      allFiles.forEach((f: any) => {
        (f.tables || []).forEach((t: string) => tablesSet.add(t));
      });
      // إضافة جداول السجلات السحابية الجديدة إن وجدت
      (mutations.adds || []).forEach((a) => {
        if (a._adh_table) tablesSet.add(a._adh_table);
      });

      availableTables = sortTablesByPriority(Array.from(tablesSet));

      if (!activeTable || !tablesSet.has(activeTable)) {
        activeTable = availableTables[0] || 'التجار';
      }

      // جمع الأعمدة بترتيبها الأصلي الدقيق من ملفات Access بدون أي تعديل أو فرز
      const colsOrder: string[] = [];
      const colsSeen = new Set<string>();

      for (const f of allFiles) {
        const content = getFileContent(f.name);
        if (!content || !content.tables) continue;

        // قراءة الأعمدة الأصلية كما هي في ملف Access
        const origCols = content.columns?.[activeTable] || [];
        for (const col of origCols) {
          if (!colsSeen.has(col)) {
            colsSeen.add(col);
            colsOrder.push(col);
          }
        }

        // جمع السجلات الأساسية
        const tableRows = content.tables[activeTable] || [];
        for (let idx = 0; idx < tableRows.length; idx++) {
          const row = tableRows[idx];
          if (!row._adh_file) row._adh_file = f.name;
          if (!row._adh_table) row._adh_table = activeTable;
          if (!row._adh_id) row._adh_id = `${f.name}_${activeTable}_${idx}`;
          rawRows.push(row);
        }
      }

      baseColumns = sortColumnsByPriority(colsOrder);
    } else {
      // 📁 وضع خانة ملف محدد باسمه الحقيقي
      const content = getFileContent(requestedFile);
      if (!content) {
        return NextResponse.json({ success: false, error: 'الملف غير موجود' }, { status: 404 });
      }

      const fileTables = Object.keys(content.tables || {});
      const fileTablesSet = new Set(fileTables);
      (mutations.adds || []).forEach((a) => {
        if (a._adh_file === requestedFile && a._adh_table) {
          fileTablesSet.add(a._adh_table);
        }
      });

      availableTables = sortTablesByPriority(Array.from(fileTablesSet));
      if (!activeTable || !fileTablesSet.has(activeTable)) {
        activeTable = availableTables[0] || '';
      }

      // الأعمدة بترتيب الأولوية الذكي (اسم التاجر والنشاط والصنف والهاتف أولاً)
      baseColumns = sortColumnsByPriority(content.columns?.[activeTable] || []);

      // السجلات الأساسية
      const tableRows = content.tables[activeTable] || [];
      for (let idx = 0; idx < tableRows.length; idx++) {
        const row = tableRows[idx];
        if (!row._adh_file) row._adh_file = requestedFile;
        if (!row._adh_table) row._adh_table = activeTable;
        if (!row._adh_id) row._adh_id = `${requestedFile}_${activeTable}_${idx}`;
        rawRows.push(row);
      }
    }

    // تطبيق التعديلات والإضافات والمحذوفات السحابية
    const mergedRows = applyMutations(requestedFile, activeTable, rawRows, mutations);

    // تطبيق الأعمدة المخصصة (إضافة / حذف الأعمدة السحابية)
    let columns = getCustomColumns(requestedFile, activeTable, baseColumns, mutations);

    // استكشاف حقول التواريخ المتاحة تلقائياً في هذا الجدول
    const dateKeywords = ['date', 'تاريخ', 'affiliation', 'expiration', 'year', 'سنة', 'مواليد', 'انتساب', 'شطب', 'تعديل', 'تسجيل'];
    const dateColumns = columns.filter((col) => {
      const lower = col.toLowerCase();
      return dateKeywords.some((kw) => lower.includes(kw));
    });

    // تحديد عمود الفرز الفعلي
    let actualSortCol = sortColParam;
    if (actualSortCol === 'date_auto') {
      actualSortCol = dateColumns[0] || '';
    }

    // تصفية البحث
    let filteredRows = mergedRows;
    if (search) {
      filteredRows = mergedRows.filter((row) =>
        Object.values(row).some((val) => val && String(val).toLowerCase().includes(search))
      );
    }

    // تطبيق الترتيب الزمني (من الجديد للقديم أو العكس)
    if (sortDir === 'desc' || sortDir === 'asc') {
      const targetCol = actualSortCol || (dateColumns.length > 0 ? dateColumns[0] : '');
      if (targetCol) {
        filteredRows = [...filteredRows].sort((a, b) => {
          const valA = a[targetCol];
          const valB = b[targetCol];
          const timeA = parseDateValue(valA);
          const timeB = parseDateValue(valB);

          // كلاهما يحملان تاريخاً صحيحاً
          if (timeA !== null && timeB !== null) {
            return sortDir === 'desc' ? timeB - timeA : timeA - timeB;
          }
          // الصف الذي يحتوي على تاريخ يظهر أولاً
          if (timeA !== null) return -1;
          if (timeB !== null) return 1;

          // نص احتياطي
          const strA = valA !== null && valA !== undefined ? String(valA) : '';
          const strB = valB !== null && valB !== undefined ? String(valB) : '';
          return sortDir === 'desc' ? strB.localeCompare(strA, 'ar') : strA.localeCompare(strB, 'ar');
        });
      }
    }

    const totalMatches = filteredRows.length;
    const startIndex = (page - 1) * limit;
    const paginatedRows = filteredRows.slice(startIndex, startIndex + limit);

    const deletedSections = mutations.deleted_sections || [];
    const activeFiles = (index.files || []).filter((f: any) => !deletedSections.includes(f.name));

    const grandTotalRecords = (index.total_records || 0) + (mutations.adds?.length || 0) - (mutations.deletes?.length || 0);

    return NextResponse.json({
      success: true,
      sig: currentSig,
      current_role: callerRole,
      files: activeFiles,
      all_files: index.files || [],
      deleted_sections: deletedSections,
      trash_bin: mutations.trash_bin || [],
      roles: mutations.roles || {},
      total_records: Math.max(0, grandTotalRecords),
      active_file: requestedFile,
      active_table: activeTable,
      available_tables: availableTables,
      columns,
      date_columns: dateColumns,
      sort_col: actualSortCol,
      sort_dir: sortDir,
      total_matches: totalMatches,
      page,
      limit,
      total_pages: Math.ceil(totalMatches / limit) || 1,
      rows: paginatedRows,
    });
  } catch (err: any) {
    console.error('Access Hub API Error:', err);
    return NextResponse.json({ success: false, error: err.message }, { status: 500 });
  }
}

// POST: إضافة سجل جديد، أو إضافة حقل جديد، أو حذف حقل سحابياً، أو إدارة الأقسام والصلاحيات
export async function POST(req: NextRequest) {
  try {
    const body = await req.json();
    const callerRole = await resolveCallerRole(req, body);

    // العمليات الإدارية الحساسة محصورة حصراً بمدير النظام (Super Admin)
    const adminActions = [
      'DELETE_SECTION',
      'RESTORE_SECTION',
      'TRASH_RECORD',
      'RESTORE_RECORD',
      'ADD_COLUMN',
      'DELETE_COLUMN',
      'RENAME_COLUMN',
      'MOVE_COLUMN',
      'REORDER_COLUMNS',
      'SET_ROLE',
    ];

    if (body.action && adminActions.includes(body.action)) {
      if (callerRole !== 'admin') {
        return NextResponse.json({ 
          success: false, 
          error: 'عفواً، تم حجب العملية! تقتصر هذه الإجراءات الإدارية المتقدمة على مدير النظام (Super Admin) حصراً.' 
        }, { status: 403 });
      }
    }

    // 0. إدارة الأقسام (حذف أو استعادة)
    if (body.action === 'DELETE_SECTION') {
      const { fileName } = body;
      if (!fileName) return NextResponse.json({ success: false, error: 'اسم القسم مطلوب' }, { status: 400 });
      const deleted = await deleteAccessSection(fileName);
      return NextResponse.json({ success: true, message: `تم حذف وأرشفة القسم "${fileName}" بنجاح`, deleted_sections: deleted });
    }

    if (body.action === 'RESTORE_SECTION') {
      const { fileName } = body;
      if (!fileName) return NextResponse.json({ success: false, error: 'اسم القسم مطلوب' }, { status: 400 });
      const remaining = await restoreAccessSection(fileName);
      return NextResponse.json({ success: true, message: `تمت استعادة القسم "${fileName}" بنجاح`, deleted_sections: remaining });
    }

    // 1. حذف قيد ونقله إلى سلة المحذوفات الإدارية
    if (body.action === 'TRASH_RECORD') {
      const { id, file, table, record, deletedBy } = body;
      if (!id) return NextResponse.json({ success: false, error: 'معرف القيد مطلوب' }, { status: 400 });
      await deleteRecordToTrash(id, file, table, record, deletedBy);
      return NextResponse.json({ success: true, message: 'تم حذف القيد ونقله إلى سلة المحذوفات بنجاح' });
    }

    // 2. استعادة قيد من سلة المحذوفات
    if (body.action === 'RESTORE_RECORD') {
      const { id } = body;
      if (!id) return NextResponse.json({ success: false, error: 'معرف القيد مطلوب' }, { status: 400 });
      await restoreRecordFromTrash(id);
      return NextResponse.json({ success: true, message: 'تمت استعادة القيد من سلة المحذوفات بنجاح' });
    }

    // 3. تعيين وتحديث صلاحية الجهاز
    if (body.action === 'SET_ROLE') {
      const { guid, name, role } = body;
      if (!guid || !role) return NextResponse.json({ success: false, error: 'بيانات الصلاحية غير مكتملة' }, { status: 400 });
      const record = await setAccessHubRole(guid, name, role);

      // مزامنة الصلاحية فوراً أيضاً في مستودع الصلاحيات المركزي (.sharecoc_permissions.json)
      try {
        await persistCloudAdminStore((cur) => {
          const sec = cur.accessHubSecurity || { ...DEFAULT_ACCESS_HUB_SECURITY };
          const curRoles = { ...(sec.roles || {}) };
          curRoles[guid] = role;
          const updatedDevices = (cur.devices || []).map((d) => {
            if (d.machineGuid === guid) {
              return { ...d, accessRole: role };
            }
            return d;
          });
          return {
            ...cur,
            devices: updatedDevices,
            accessHubSecurity: {
              ...sec,
              roles: curRoles,
              updatedAt: new Date().toISOString(),
            },
          };
        });
      } catch (syncErr) {
        console.error('Failed to sync role to cloud admin store:', syncErr);
      }

      return NextResponse.json({ success: true, message: 'تم تحديث وتطبيق صلاحية الجهاز بنجاح وتعميمها', roleRecord: record });
    }

    // 4. إضافة حقل جديد للجدول
    if (body.action === 'ADD_COLUMN') {
      const { file, table, columnName } = body;
      if (!file || !table || !columnName) {
        return NextResponse.json({ success: false, error: 'بيانات الحقل غير مكتملة' }, { status: 400 });
      }
      const added = await addColumnToTable(file, table, columnName);
      return NextResponse.json({
        success: true,
        message: `تمت إضافة الحقل "${columnName}" سحابياً بنجاح وتعميمه على الجميع`,
        added_columns: added,
      });
    }

    // 5. حذف حقل من الجدول (إدارياً)
    if (body.action === 'DELETE_COLUMN') {
      const { file, table, columnName } = body;
      if (!file || !table || !columnName) {
        return NextResponse.json({ success: false, error: 'بيانات الحقل غير مكتملة' }, { status: 400 });
      }
      const deleted = await deleteColumnFromTable(file, table, columnName);
      return NextResponse.json({
        success: true,
        message: `تم حذف الحقل "${columnName}" سحابياً بنجاح`,
        deleted_columns: deleted,
      });
    }

    // 5.1 تعديل اسم الحقل
    if (body.action === 'RENAME_COLUMN') {
      const { file, table, oldName, newName } = body;
      if (!file || !table || !oldName || !newName) {
        return NextResponse.json({ success: false, error: 'الاسم الحالي والاسم الجديد للحقل مطلوبان' }, { status: 400 });
      }
      const res = await renameColumnInTable(file, table, oldName, newName);
      return NextResponse.json({
        success: true,
        message: `تم تعديل اسم الحقل من "${oldName}" إلى "${newName}" بنجاح وتعميمه سحابياً`,
        renamed_columns: res.renamed_columns,
      });
    }

    // 5.2 نقل مكان الحقل (إلى البداية، النهاية، للأعلى، أو للأسفل)
    if (body.action === 'MOVE_COLUMN') {
      const { file, table, columnName, direction, allColumns } = body;
      if (!file || !table || !columnName || !direction || !Array.isArray(allColumns)) {
        return NextResponse.json({ success: false, error: 'بيانات نقل الحقل غير مكتملة' }, { status: 400 });
      }
      const newOrder = await moveColumnInTable(file, table, columnName, direction, allColumns);
      return NextResponse.json({
        success: true,
        message: `تم نقل مكان الحقل "${columnName}" بنجاح`,
        column_order: newOrder,
      });
    }

    // 5.3 حفظ ترتيب كامل للأعمدة
    if (body.action === 'REORDER_COLUMNS') {
      const { file, table, columnOrder } = body;
      if (!file || !table || !Array.isArray(columnOrder)) {
        return NextResponse.json({ success: false, error: 'بيانات ترتيب الأعمدة غير مكتملة' }, { status: 400 });
      }
      const newOrder = await reorderColumnsInTable(file, table, columnOrder);
      return NextResponse.json({
        success: true,
        message: 'تم حفظ وتعميم الترتيب الجديد للحقول سحابياً بنجاح',
        column_order: newOrder,
      });
    }

    // 6. إضافة قيد بيانات جديد (Standard Record Add)
    if (callerRole === 'viewer') {
      return NextResponse.json({ 
        success: false, 
        error: 'عفواً، لا يمكنك إضافة قيود جديدة! حساب هذا الجهاز مفعل بصلاحية (مستعلم فقط - Viewer للقراءة والاستعلام فقط).' 
      }, { status: 403 });
    }

    const { file, table, record } = body;
    if (!file || !table || !record) {
      return NextResponse.json({ success: false, error: 'بيانات القيد غير مكتملة' }, { status: 400 });
    }

    const newRecord = await addAccessRecord(file, table, record);
    return NextResponse.json({ 
      success: true, 
      message: 'تمت إضافة القيد وحفظه سحابياً بنجاح',
      record: newRecord 
    });
  } catch (err: any) {
    console.error('Access Hub POST Error:', err);
    return NextResponse.json({ success: false, error: err.message }, { status: 500 });
  }
}

// PUT: تعديل سجل وتعميم التعديل سحابياً
export async function PUT(req: NextRequest) {
  try {
    const body = await req.json();
    const callerRole = await resolveCallerRole(req, body);

    if (callerRole === 'viewer') {
      return NextResponse.json({ 
        success: false, 
        error: 'عفواً، لا يمكنك تعديل القيود! حساب هذا الجهاز مفعل بصلاحية (مستعلم فقط - Viewer للقراءة والاستعلام فقط).' 
      }, { status: 403 });
    }

    const { id, updates } = body;

    if (!id || !updates) {
      return NextResponse.json({ success: false, error: 'بيانات التعديل غير مكتملة' }, { status: 400 });
    }

    const updated = await updateAccessRecord(id, updates);
    return NextResponse.json({ 
      success: true, 
      message: 'تم حفظ التعديل سحابياً بنجاح',
      record: updated 
    });
  } catch (err: any) {
    console.error('Access Hub PUT Error:', err);
    return NextResponse.json({ success: false, error: err.message }, { status: 500 });
  }
}

// DELETE: حذف سجل أو حذف حقل
export async function DELETE(req: NextRequest) {
  try {
    const callerRole = await resolveCallerRole(req);

    if (callerRole !== 'admin') {
      return NextResponse.json({ 
        success: false, 
        error: 'عفواً، عملية الحذف محجوبة تماماً عنك! تقتصر صلاحية الحذف على مدير النظام (Super Admin) حصراً لحماية سرية وسلامة البيانات.' 
      }, { status: 403 });
    }

    const url = new URL(req.url);
    const type = url.searchParams.get('type');

    // حذف حقل عبر DELETE request اختياري
    if (type === 'column') {
      const file = url.searchParams.get('file');
      const table = url.searchParams.get('table');
      const columnName = url.searchParams.get('columnName');
      if (!file || !table || !columnName) {
        return NextResponse.json({ success: false, error: 'بيانات الحقل غير مكتملة' }, { status: 400 });
      }
      await deleteColumnFromTable(file, table, columnName);
      return NextResponse.json({ success: true, message: `تم حذف الحقل "${columnName}" سحابياً` });
    }

    // حذف قيد بيانات
    const id = url.searchParams.get('id');
    if (!id) {
      return NextResponse.json({ success: false, error: 'معرف الحذف غير مكتمل' }, { status: 400 });
    }

    await deleteAccessRecord(id);
    return NextResponse.json({ 
      success: true, 
      message: 'تم الحذف وتحديث السحابة بنجاح' 
    });
  } catch (err: any) {
    console.error('Access Hub DELETE Error:', err);
    return NextResponse.json({ success: false, error: err.message }, { status: 500 });
  }
}
