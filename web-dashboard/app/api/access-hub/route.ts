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
  getCustomColumns,
  deleteAccessSection,
  restoreAccessSection,
  deleteRecordToTrash,
  restoreRecordFromTrash,
  setAccessHubRole
} from '@/lib/accessCloudStore';

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
  const filePath = path.join(DATA_DIR, `${fileName}.json`);
  if (!fs.existsSync(filePath)) {
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

      baseColumns = colsOrder;
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

      // الأعمدة بنفس ترتيبها الأصلي 100% من ملف Access
      baseColumns = content.columns?.[activeTable] || [];

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
      return NextResponse.json({ success: true, message: 'تم تحديث صلاحية الجهاز بنجاح', roleRecord: record });
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

    // 6. إضافة قيد بيانات جديد (Standard Record Add)
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
