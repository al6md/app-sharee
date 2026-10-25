import { NextRequest, NextResponse } from 'next/server';
import { getAdminClient } from '@/lib/supabase';

/**
 * توليد رابط موقع (Signed Upload URL) للرفع المباشر إلى Supabase Storage
 * هذا المسار يضمن عدم مرور محتويات الملفات الكبيرة عبر خوادم Vercel Serverless
 * لتفادي حد 4.5MB المفروض في الخطة المجانية لـ Vercel!
 */
export async function POST(req: NextRequest) {
  try {
    const { filePath, folderId } = await req.json();

    if (!filePath) {
      return NextResponse.json({ error: 'مسار الملف مطلوب' }, { status: 400 });
    }

    const adminSupabase = getAdminClient();

    // إنشاء رابط رفع موقع صالح لمدة 15 دقيقة
    const { data, error } = await adminSupabase.storage
      .from('file-exchange-storage')
      .createSignedUploadUrl(`shared/${filePath}`);

    if (error) {
      return NextResponse.json({ error: error.message }, { status: 500 });
    }

    return NextResponse.json({
      signedUrl: data.signedUrl,
      token: data.token,
      path: data.path,
      message: 'تم توليد رابط الرفع المباشر بأمان'
    });
  } catch (err: any) {
    return NextResponse.json({ error: err.message || 'خطأ غير متوقع' }, { status: 500 });
  }
}
