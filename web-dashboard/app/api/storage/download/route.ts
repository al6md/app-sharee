import { NextRequest, NextResponse } from 'next/server';
import { supabase } from '@/lib/supabase';

export const dynamic = 'force-dynamic';

// خريطة شاملة لأنواع MIME لضمان تعرف أنظمة أندرويد وiOS على صيغة المستند فوراً
const MIME_TYPES: Record<string, string> = {
  '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
  '.doc': 'application/msword',
  '.dotx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.template',
  '.xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  '.xls': 'application/vnd.ms-excel',
  '.xltx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.template',
  '.pptx': 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
  '.ppt': 'application/vnd.ms-powerpoint',
  '.pdf': 'application/pdf',
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.jpeg': 'image/jpeg',
  '.webp': 'image/webp',
  '.gif': 'image/gif',
  '.svg': 'image/svg+xml',
  '.accdb': 'application/msaccess',
  '.mdb': 'application/msaccess',
  '.txt': 'text/plain; charset=utf-8',
  '.csv': 'text/csv; charset=utf-8',
  '.zip': 'application/zip',
  '.rar': 'application/x-rar-compressed',
  '.7z': 'application/x-7z-compressed',
};

export async function GET(req: NextRequest) {
  try {
    const { searchParams } = new URL(req.url);
    const storagePath = searchParams.get('path');
    const rawName = searchParams.get('name') || 'document';
    const inline = searchParams.get('inline') === 'true';

    if (!storagePath) {
      return NextResponse.json({ error: 'مسار الملف مطلوب (path parameter is required)' }, { status: 400 });
    }

    let cleanPath = storagePath.startsWith('/') ? storagePath.slice(1) : storagePath;

    // محاولة تنزيل الملف من Supabase Storage
    let { data, error } = await supabase.storage
      .from('file-exchange-storage')
      .download(cleanPath);

    // إذا فشل التنزيل وكان المسار لا يبدأ بـ shared/، نجرب إضافتها
    if ((error || !data) && !cleanPath.startsWith('shared/')) {
      const fallback = await supabase.storage
        .from('file-exchange-storage')
        .download(`shared/${cleanPath}`);
      if (!fallback.error && fallback.data) {
        data = fallback.data;
        error = null;
      }
    }

    if (error || !data) {
      return NextResponse.json(
        { error: error?.message || 'تعذر العثور على الملف في السحابة' },
        { status: 404 }
      );
    }

    // استخراج الامتداد لتحديد نوع MIME بدقة
    const dotIndex = rawName.lastIndexOf('.');
    const ext = dotIndex !== -1 ? rawName.slice(dotIndex).toLowerCase() : '';
    const contentType = MIME_TYPES[ext] || data.type || 'application/octet-stream';

    // تجهيز اسم ملف بالمعايير القياسية العالمية (RFC 5987 / RFC 6266)
    // fallback بالإنجليزية للمتصفحات القديمة + اسم عربي سليم 100% لكافة الهواتف الحديثة
    const asciiFallback = `document${ext}`;
    const encodedName = encodeURIComponent(rawName);
    const dispositionType = inline ? 'inline' : 'attachment';
    const contentDisposition = `${dispositionType}; filename="${asciiFallback}"; filename*=UTF-8''${encodedName}`;

    // تحويل البيانات إلى ArrayBuffer لضمان توافقية وسرعة البث
    const arrayBuffer = await data.arrayBuffer();

    return new NextResponse(arrayBuffer, {
      status: 200,
      headers: {
        'Content-Type': contentType,
        'Content-Disposition': contentDisposition,
        'Content-Length': arrayBuffer.byteLength.toString(),
        'Cache-Control': 'public, max-age=86400, stale-while-revalidate=43200',
        'X-Content-Type-Options': 'nosniff',
      },
    });
  } catch (err: any) {
    console.error('Error serving storage download:', err);
    return NextResponse.json(
      { error: err.message || 'خطأ غير متوقع أثناء معالجة الملف' },
      { status: 500 }
    );
  }
}
