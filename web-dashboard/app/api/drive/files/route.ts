import { NextRequest, NextResponse } from 'next/server';
import { 
  getAllCloudFiles, 
  createCloudFolder, 
  uploadFileToDrive, 
  deleteDriveItem, 
  restoreDriveItem, 
  permanentDeleteDriveItem, 
  renameDriveItem, 
  ROOT_FOLDER_ID 
} from '@/lib/googleDrive';

export const dynamic = 'force-dynamic';

// GET: جلب شجرة الملفات والأقسام الحية من Google Drive
export async function GET() {
  try {
    const data = await getAllCloudFiles();
    return NextResponse.json({ success: true, ...data });
  } catch (error: any) {
    console.error('Drive API GET Error:', error);
    return NextResponse.json({ success: false, error: error.message || 'فشل جلب البيانات السحابية' }, { status: 500 });
  }
}

// POST: رفع ملف جديد أو إجراء عمليات (إنشاء مجلد، إعادة تسمية، استرجاع، إلخ)
export async function POST(req: NextRequest) {
  try {
    const contentType = req.headers.get('content-type') || '';

    // العمليات القائمة على JSON
    if (contentType.includes('application/json')) {
      const body = await req.json();

      if (body.action === 'CREATE_FOLDER') {
        const folder = await createCloudFolder(body.name, body.parentId || ROOT_FOLDER_ID);
        return NextResponse.json({ success: true, folder });
      }

      if (body.action === 'RENAME') {
        const updated = await renameDriveItem(body.id, body.name);
        return NextResponse.json({ success: true, item: updated });
      }

      if (body.action === 'RESTORE') {
        await restoreDriveItem(body.id);
        return NextResponse.json({ success: true, message: 'تم استرجاع الملف بنجاح' });
      }

      if (body.action === 'DELETE' || body.action === 'TRASH') {
        await deleteDriveItem(body.id);
        return NextResponse.json({ success: true, message: 'تم نقل الملف إلى سلة المحذوفات بنجاح' });
      }

      if (body.action === 'PERMANENT_DELETE') {
        await permanentDeleteDriveItem(body.id);
        return NextResponse.json({ success: true, message: 'تم الحذف النهائي بنجاح' });
      }
    }

    // رفع ملف (FormData)
    const formData = await req.formData();
    const file = formData.get('file') as File;
    const targetFolderId = (formData.get('folderId') as string) || ROOT_FOLDER_ID;

    if (!file) {
      return NextResponse.json({ success: false, error: 'لم يتم إرفاق ملف' }, { status: 400 });
    }

    const bytes = await file.arrayBuffer();
    const buffer = Buffer.from(bytes);

    const uploaded = await uploadFileToDrive(buffer, file.name, file.type || 'application/octet-stream', targetFolderId);
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
