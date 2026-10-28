import { NextRequest, NextResponse } from 'next/server';
import { 
  getAllCloudFiles, 
  createCloudFolder, 
  ensureCloudFolderPath,
  ensureCloudFolderPathsBatch,
  uploadFileToDrive, 
  initResumableUpload,
  uploadResumableChunk,
  getResumableUploadStatus,
  deleteDriveItem, 
  restoreDriveItem, 
  permanentDeleteDriveItem, 
  renameDriveItem, 
  moveDriveItem,
  batchMoveDriveItems,
  batchTrashDriveItems,
  batchRestoreDriveItems,
  batchPermanentDeleteDriveItems,
  ROOT_FOLDER_ID 
} from '@/lib/googleDrive';

export const dynamic = 'force-dynamic';
export const revalidate = 0;
export const fetchCache = 'force-no-store';
export const maxDuration = 60;

// GET: جلب شجرة الملفات والأقسام الحية من Google Drive
export async function GET(req: NextRequest) {
  try {
    const url = new URL(req.url);
    const forceRefresh = url.searchParams.get('refresh') === '1' || url.searchParams.get('force') === '1';
    const data = await getAllCloudFiles(forceRefresh);
    return NextResponse.json(
      { success: true, ...data },
      {
        headers: {
          'Cache-Control': 'no-store, no-cache, must-revalidate, proxy-revalidate, max-age=0',
          'Pragma': 'no-cache',
          'Expires': '0',
        },
      }
    );
  } catch (error: any) {
    console.error('Drive API GET Error:', error);
    return NextResponse.json({ success: false, error: error.message || 'فشل جلب البيانات السحابية' }, { status: 500 });
  }
}

// POST: رفع ملف جديد (مباشر أو مجزأ) أو إجراء عمليات (إنشاء مجلد، إعادة تسمية، استرجاع، إلخ)
export async function POST(req: NextRequest) {
  try {
    const contentType = req.headers.get('content-type') || '';

    // العمليات القائمة على JSON
    if (contentType.includes('application/json')) {
      const body = await req.json();

      if (body.action === 'CREATE_FOLDER') {
        if (body.folderPath) {
          const folderId = await ensureCloudFolderPath(body.folderPath, body.parentId || ROOT_FOLDER_ID);
          return NextResponse.json({ success: true, folder: { id: folderId, name: body.name || body.folderPath } });
        }
        const folder = await createCloudFolder(body.name, body.parentId || ROOT_FOLDER_ID);
        return NextResponse.json({ success: true, folder });
      }

      if (body.action === 'ENSURE_FOLDER_PATH') {
        const folderId = await ensureCloudFolderPath(body.folderPath || '', body.parentId || ROOT_FOLDER_ID);
        return NextResponse.json({ success: true, folderId });
      }

      if (body.action === 'ENSURE_FOLDER_PATHS_BATCH') {
        const folderMap = await ensureCloudFolderPathsBatch(
          Array.isArray(body.folderPaths) ? body.folderPaths : [],
          body.parentId || ROOT_FOLDER_ID
        );
        return NextResponse.json({ success: true, folderMap });
      }

      if (body.action === 'INIT_UPLOAD') {
        const origin = req.headers.get('origin') || body.origin || undefined;
        const initData = await initResumableUpload({
          fileName: body.fileName,
          mimeType: body.mimeType || 'application/octet-stream',
          fileSize: typeof body.fileSize === 'number' ? body.fileSize : undefined,
          folderId: body.folderId || ROOT_FOLDER_ID,
          folderPath: body.folderPath || undefined,
          origin,
        });
        return NextResponse.json({ success: true, ...initData });
      }

      if (body.action === 'CHECK_UPLOAD_STATUS') {
        const { sessionUri, totalSize } = body;
        if (!sessionUri || typeof totalSize !== 'number') {
          return NextResponse.json({ success: false, error: 'بيانات استعلام الجلسة غير مكتملة' }, { status: 400 });
        }
        const statusData = await getResumableUploadStatus(sessionUri, totalSize);
        return NextResponse.json({ success: true, ...statusData });
      }

      if (body.action === 'RENAME') {
        const updated = await renameDriveItem(body.id, body.name);
        return NextResponse.json({ success: true, item: updated });
      }

      if (body.action === 'MOVE') {
        const moved = await moveDriveItem(body.id, body.targetFolderId || ROOT_FOLDER_ID, body.targetFolderPath);
        return NextResponse.json({ success: true, item: moved });
      }

      if (body.action === 'BATCH_MOVE') {
        const result = await batchMoveDriveItems(
          Array.isArray(body.ids) ? body.ids : [],
          body.targetFolderId || ROOT_FOLDER_ID,
          body.targetFolderPath
        );
        return NextResponse.json({ success: true, ...result });
      }

      if (body.action === 'RESTORE') {
        await restoreDriveItem(body.id);
        return NextResponse.json({ success: true, message: 'تم استرجاع الملف بنجاح' });
      }

      if (body.action === 'BATCH_RESTORE') {
        const result = await batchRestoreDriveItems(Array.isArray(body.ids) ? body.ids : []);
        return NextResponse.json({ success: true, ...result });
      }

      if (body.action === 'DELETE' || body.action === 'TRASH') {
        await deleteDriveItem(body.id);
        return NextResponse.json({ success: true, message: 'تم نقل الملف إلى سلة المحذوفات بنجاح' });
      }

      if (body.action === 'BATCH_DELETE' || body.action === 'BATCH_TRASH') {
        const result = await batchTrashDriveItems(Array.isArray(body.ids) ? body.ids : []);
        return NextResponse.json({ success: true, ...result });
      }

      if (body.action === 'PERMANENT_DELETE') {
        await permanentDeleteDriveItem(body.id);
        return NextResponse.json({ success: true, message: 'تم الحذف النهائي بنجاح' });
      }

      if (body.action === 'BATCH_PERMANENT_DELETE') {
        const result = await batchPermanentDeleteDriveItems(Array.isArray(body.ids) ? body.ids : []);
        return NextResponse.json({ success: true, ...result });
      }
    }

    // رفع ملف أو جزء من ملف (FormData)
    const formData = await req.formData();
    const action = (formData.get('action') as string) || '';

    if (action === 'UPLOAD_CHUNK') {
      const sessionUri = formData.get('sessionUri') as string;
      const chunk = formData.get('chunk') as File;
      const start = Number(formData.get('start') || 0);
      const end = Number(formData.get('end') || 0);
      const total = Number(formData.get('total') || 0);

      if (!sessionUri || !chunk) {
        return NextResponse.json({ success: false, error: 'بيانات الجزء المرفوع غير مكتملة' }, { status: 400 });
      }

      const chunkBytes = await chunk.arrayBuffer();
      const chunkBuffer = Buffer.from(chunkBytes);
      const res = await uploadResumableChunk({
        sessionUri,
        chunkBuffer,
        start,
        end,
        total,
      });
      return NextResponse.json({ success: true, ...res });
    }

    const file = formData.get('file') as File;
    const targetFolderId = (formData.get('folderId') as string) || ROOT_FOLDER_ID;
    const targetFolderPath = (formData.get('folderPath') as string) || undefined;
    const customFileName = (formData.get('fileName') as string) || undefined;

    if (!file) {
      return NextResponse.json({ success: false, error: 'لم يتم إرفاق ملف' }, { status: 400 });
    }

    const bytes = await file.arrayBuffer();
    const buffer = Buffer.from(bytes);

    const uploaded = await uploadFileToDrive(
      buffer,
      customFileName || file.name,
      file.type || 'application/octet-stream',
      targetFolderId,
      targetFolderPath
    );
    return NextResponse.json({ success: true, file: uploaded });
  } catch (error: any) {
    console.error('Drive API POST Error:', error);
    return NextResponse.json({ success: false, error: error.message || 'فشل معالجة الطلب السحابي' }, { status: 500 });
  }
}

// DELETE: حذف ملف أو نقله لسلة المحذوفات
export async function DELETE(req: NextRequest) {
  try {
    const { searchParams } = new URL(req.url);
    const id = searchParams.get('id');
    const permanent = searchParams.get('permanent') === 'true';

    if (!id) {
      return NextResponse.json({ success: false, error: 'المعرف مطلوب' }, { status: 400 });
    }

    if (permanent) {
      await permanentDeleteDriveItem(id);
      return NextResponse.json({ success: true, message: 'تم الحذف النهائي بنجاح' });
    } else {
      await deleteDriveItem(id);
      return NextResponse.json({ success: true, message: 'تم نقل الملف إلى سلة المحذوفات بنجاح' });
    }
  } catch (error: any) {
    return NextResponse.json({ success: false, error: error.message }, { status: 500 });
  }
}
