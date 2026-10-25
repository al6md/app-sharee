-- ========================================================
-- تبادل الملفات – File Exchange System
-- Database Schema: PostgreSQL for Supabase (نظام بدون كلمة مرور - Passwordless)
-- ========================================================

-- تفعيل الامتدادات المطلوبة
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ========================================================
-- 1. جدول الحسابات الشخصية (Profiles)
-- ========================================================
CREATE TABLE IF NOT EXISTS public.profiles (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    full_name TEXT NOT NULL DEFAULT 'مستخدم نظام تبادل الملفات',
    email TEXT DEFAULT 'shared@app-sharee.local',
    role TEXT NOT NULL DEFAULT 'admin',
    is_active BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now()),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now())
);

-- مستخدم افتراضي للنظام المشترك (لتسهيل الربط بدون تسجيل دخول)
INSERT INTO public.profiles (id, full_name, email, role, is_active)
VALUES ('00000000-0000-0000-0000-000000000000', 'مستخدم النظام المشترك', 'shared@app-sharee.local', 'admin', true)
ON CONFLICT (id) DO NOTHING;

-- ========================================================
-- 2. جدول الأجهزة المصرح لها (Authorized Devices)
-- ========================================================
CREATE TABLE IF NOT EXISTS public.devices (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES public.profiles(id) ON DELETE SET NULL,
    device_name TEXT NOT NULL,
    machine_guid TEXT NOT NULL UNIQUE,
    os_info TEXT DEFAULT 'Windows',
    ip_address TEXT,
    is_authorized BOOLEAN NOT NULL DEFAULT true, -- اعتماد فوري لجميع أجهزة المؤسسة
    last_sync_at TIMESTAMPTZ,
    last_seen_at TIMESTAMPTZ DEFAULT timezone('utc'::text, now()),
    created_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now())
);

CREATE INDEX IF NOT EXISTS idx_devices_machine_guid ON public.devices(machine_guid);

-- ========================================================
-- 3. جدول المجلدات المشتركة (Shared Folders)
-- ========================================================
CREATE TABLE IF NOT EXISTS public.shared_folders (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name TEXT NOT NULL,
    parent_id UUID REFERENCES public.shared_folders(id) ON DELETE CASCADE,
    created_by UUID REFERENCES public.profiles(id) ON DELETE SET NULL,
    is_archived BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now()),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now())
);

-- ========================================================
-- 4. جدول صلاحيات المجلدات (Folder Permissions)
-- ========================================================
CREATE TABLE IF NOT EXISTS public.folder_permissions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    folder_id UUID NOT NULL REFERENCES public.shared_folders(id) ON DELETE CASCADE,
    user_id UUID REFERENCES public.profiles(id) ON DELETE CASCADE,
    can_view BOOLEAN NOT NULL DEFAULT true,
    can_download BOOLEAN NOT NULL DEFAULT true,
    can_write BOOLEAN NOT NULL DEFAULT true,
    can_delete BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now())
);

-- ========================================================
-- 5. جدول الملفات المشتركة الحالية (Files Metadata)
-- ========================================================
CREATE TABLE IF NOT EXISTS public.files (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    folder_id UUID REFERENCES public.shared_folders(id) ON DELETE SET NULL,
    file_name TEXT NOT NULL UNIQUE,
    file_path TEXT NOT NULL,
    file_size BIGINT NOT NULL DEFAULT 0,
    mime_type TEXT,
    sha256_hash TEXT,
    current_version INT NOT NULL DEFAULT 1,
    storage_path TEXT NOT NULL,
    last_modified_by UUID REFERENCES public.profiles(id) ON DELETE SET NULL,
    last_modified_device UUID REFERENCES public.devices(id) ON DELETE SET NULL,
    last_modified_by_name TEXT DEFAULT 'جهاز محلي',
    is_deleted BOOLEAN NOT NULL DEFAULT false,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now()),
    created_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now())
);

CREATE INDEX IF NOT EXISTS idx_files_path ON public.files(file_path);
CREATE INDEX IF NOT EXISTS idx_files_name ON public.files(file_name);

-- ========================================================
-- 6. جدول تاريخ إصدارات الملفات (File Versions History)
-- ========================================================
CREATE TABLE IF NOT EXISTS public.file_versions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    file_id UUID NOT NULL REFERENCES public.files(id) ON DELETE CASCADE,
    version_num INT NOT NULL,
    storage_path TEXT NOT NULL,
    file_size BIGINT NOT NULL,
    sha256_hash TEXT,
    change_summary TEXT,
    modified_by UUID REFERENCES public.profiles(id) ON DELETE SET NULL,
    modified_device UUID REFERENCES public.devices(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now())
);

CREATE INDEX IF NOT EXISTS idx_file_versions_lookup ON public.file_versions(file_id, version_num);

-- ========================================================
-- 7. جدول حجز وأقفال الملفات (File Locks - حماية ملفات Access)
-- ========================================================
CREATE TABLE IF NOT EXISTS public.file_locks (
    file_id TEXT PRIMARY KEY,
    locked_by UUID REFERENCES public.profiles(id) ON DELETE SET NULL,
    locked_by_name TEXT DEFAULT 'مستخدم في الشبكة',
    device_id UUID REFERENCES public.devices(id) ON DELETE SET NULL,
    device_name TEXT DEFAULT 'جهاز ويندوز',
    lock_type TEXT NOT NULL DEFAULT 'exclusive',
    locked_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now()),
    expires_at TIMESTAMPTZ NOT NULL DEFAULT (timezone('utc'::text, now()) + INTERVAL '2 hours')
);

-- ========================================================
-- 8. جدول سجل العمليات والتدقيق (Audit Logs)
-- ========================================================
CREATE TABLE IF NOT EXISTS public.audit_logs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES public.profiles(id) ON DELETE SET NULL,
    device_id UUID REFERENCES public.devices(id) ON DELETE SET NULL,
    action TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    entity_id TEXT,
    entity_name TEXT NOT NULL,
    details JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now())
);

CREATE INDEX IF NOT EXISTS idx_audit_created_at ON public.audit_logs(created_at DESC);

-- ========================================================
-- 9. تفعيل بث الأحداث اللحظية (Supabase Realtime)
-- ========================================================
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_publication_tables 
        WHERE pubname = 'supabase_realtime' AND tablename = 'files'
    ) THEN
        ALTER PUBLICATION supabase_realtime ADD TABLE public.files;
    END IF;
    
    IF NOT EXISTS (
        SELECT 1 FROM pg_publication_tables 
        WHERE pubname = 'supabase_realtime' AND tablename = 'file_locks'
    ) THEN
        ALTER PUBLICATION supabase_realtime ADD TABLE public.file_locks;
    END IF;
END $$;

-- ========================================================
-- 10. تفعيل RLS وسياسات الوصول بدون باسورد (Passwordless)
-- ========================================================
ALTER TABLE public.profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.devices ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.shared_folders ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.folder_permissions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.files ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.file_versions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.file_locks ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.audit_logs ENABLE ROW LEVEL SECURITY;

-- حذف أي سياسات سابقة لتفادي التكرار
DROP POLICY IF EXISTS "الوصول المباشر للملفات" ON public.files;
DROP POLICY IF EXISTS "الوصول المباشر للمجلدات" ON public.shared_folders;
DROP POLICY IF EXISTS "الوصول المباشر للأجهزة" ON public.devices;
DROP POLICY IF EXISTS "الوصول المباشر لأقفال الملفات" ON public.file_locks;
DROP POLICY IF EXISTS "الوصول المباشر لسجل التدقيق" ON public.audit_logs;
DROP POLICY IF EXISTS "الوصول المباشر للإصدارات" ON public.file_versions;
DROP POLICY IF EXISTS "الوصول المباشر للملفات الشخصية" ON public.profiles;
DROP POLICY IF EXISTS "الوصول المباشر لصلاحيات المجلدات" ON public.folder_permissions;

-- إنشاء سياسات السماح التلقائي عبر مفتاح anon بدون طلب أي باسورد
CREATE POLICY "الوصول المباشر للملفات" ON public.files FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "الوصول المباشر للمجلدات" ON public.shared_folders FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "الوصول المباشر للأجهزة" ON public.devices FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "الوصول المباشر لأقفال الملفات" ON public.file_locks FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "الوصول المباشر لسجل التدقيق" ON public.audit_logs FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "الوصول المباشر للإصدارات" ON public.file_versions FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "الوصول المباشر للملفات الشخصية" ON public.profiles FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "الوصول المباشر لصلاحيات المجلدات" ON public.folder_permissions FOR ALL USING (true) WITH CHECK (true);

-- ========================================================
-- 11. إعداد وعاء التخزين السحابي (Supabase Storage Bucket)
-- ========================================================
-- إنشاء وعاء تخزين عام ومباشر بدون تسجيل دخول
INSERT INTO storage.buckets (id, name, public, file_size_limit)
VALUES ('file-exchange-storage', 'file-exchange-storage', true, 104857600)
ON CONFLICT (id) DO UPDATE SET public = true, file_size_limit = 104857600;

-- سياسات التخزين السحابي بدون باسورد
DROP POLICY IF EXISTS "تحميل الملفات بدون باسورد" ON storage.objects;
CREATE POLICY "تحميل الملفات بدون باسورد"
ON storage.objects FOR SELECT
USING (bucket_id = 'file-exchange-storage');

DROP POLICY IF EXISTS "رفع الملفات بدون باسورد" ON storage.objects;
CREATE POLICY "رفع الملفات بدون باسورد"
ON storage.objects FOR INSERT
WITH CHECK (bucket_id = 'file-exchange-storage');

DROP POLICY IF EXISTS "تحديث الملفات بدون باسورد" ON storage.objects;
CREATE POLICY "تحديث الملفات بدون باسورد"
ON storage.objects FOR UPDATE
USING (bucket_id = 'file-exchange-storage');

DROP POLICY IF EXISTS "حذف الملفات بدون باسورد" ON storage.objects;
CREATE POLICY "حذف الملفات بدون باسورد"
ON storage.objects FOR DELETE
USING (bucket_id = 'file-exchange-storage');

-- ========================================================
-- 12. بيانات المجلدات الافتراضية
-- ========================================================
INSERT INTO public.shared_folders (id, name)
VALUES 
    ('11111111-1111-1111-1111-111111111111', 'الكتب الرسمية والمراسلات (Word)'),
    ('22222222-2222-2222-2222-222222222222', 'جداول البيانات والتقارير المالية (Excel)'),
    ('33333333-3333-3333-3333-333333333333', 'قواعد بيانات المؤسسة (Access)'),
    ('44444444-4444-4444-4444-444444444444', 'النماذج والتعاميم العامة')
ON CONFLICT (id) DO NOTHING;
