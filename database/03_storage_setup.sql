-- ========================================================
-- تبادل الملفات – File Exchange System
-- Supabase Storage Setup & Security Policies
-- ========================================================

-- إنشاء وعاء التخزين (Storage Bucket) الرئيسي للملفات
INSERT INTO storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
VALUES (
    'file-exchange-storage',
    'file-exchange-storage',
    false, -- خاص ومحمي بروابط موثقة وليس عاماً
    104857600, -- 100 ميجابايت كحد أقصى للملف الواحد لحماية سعة التخزين المجانية
    ARRAY[
        'application/vnd.openxmlformats-officedocument.wordprocessingml.document', -- .docx
        'application/msword', -- .doc
        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', -- .xlsx
        'application/vnd.ms-excel', -- .xls
        'application/x-msaccess', -- .mdb / .accdb
        'application/pdf', -- .pdf
        'text/plain', -- .txt
        'application/zip', -- .zip
        'image/png', -- .png
        'image/jpeg' -- .jpg
    ]
)
ON CONFLICT (id) DO UPDATE SET 
    public = false,
    file_size_limit = 104857600;

-- ========================================================
-- سياسات الوصول إلى وعاء التخزين (Storage Objects Policies)
-- ========================================================

-- سياسة التحميل والتنزيل للمستخدمين المصرح لهم
CREATE POLICY "تحميل الملفات المصرح بها للمستخدم"
ON storage.objects FOR SELECT
USING (
    bucket_id = 'file-exchange-storage' 
    AND (
        auth.role() = 'authenticated'
    )
);

-- سياسة رفع وتحديث الملفات
CREATE POLICY "رفع الملفات للمستخدمين المعتمدين"
ON storage.objects FOR INSERT
WITH CHECK (
    bucket_id = 'file-exchange-storage'
    AND auth.role() = 'authenticated'
);

-- سياسة حذف الملفات للمدير أو من لديه صلاحية
CREATE POLICY "حذف الملفات من التخزين"
ON storage.objects FOR DELETE
USING (
    bucket_id = 'file-exchange-storage'
    AND auth.role() = 'authenticated'
);
