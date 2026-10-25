-- ========================================================
-- تبادل الملفات – File Exchange System
-- Database Schema: PostgreSQL for Supabase
-- ========================================================

-- تفعيل الامتدادات المطلوبة
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ========================================================
-- 1. جدول الحسابات الشخصية للمستخدمين (Profiles)
-- ========================================================
CREATE TABLE IF NOT EXISTS public.profiles (
    id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    full_name TEXT NOT NULL,
    email TEXT UNIQUE NOT NULL,
    role TEXT NOT NULL DEFAULT 'user' CHECK (role IN ('admin', 'user')),
    is_active BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now()),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now())
);

-- ========================================================
-- 2. جدول الأجهزة المصرح لها (Authorized Devices)
-- ========================================================
CREATE TABLE IF NOT EXISTS public.devices (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
    device_name TEXT NOT NULL,
    machine_guid TEXT NOT NULL UNIQUE,
    os_info TEXT DEFAULT 'Windows',
    ip_address TEXT,
    is_authorized BOOLEAN NOT NULL DEFAULT false,
    last_sync_at TIMESTAMPTZ,
    last_seen_at TIMESTAMPTZ DEFAULT timezone('utc'::text, now()),
    created_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now())
);

-- فهرس لسرعة البحث عن الأجهزة برقم الجهاز
CREATE INDEX IF NOT EXISTS idx_devices_machine_guid ON public.devices(machine_guid);
CREATE INDEX IF NOT EXISTS idx_devices_user_id ON public.devices(user_id);

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
-- 4. جدول صلاحيات المجلدات للمستخدمين (Folder Permissions)
-- ========================================================
CREATE TABLE IF NOT EXISTS public.folder_permissions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    folder_id UUID NOT NULL REFERENCES public.shared_folders(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
    can_view BOOLEAN NOT NULL DEFAULT true,
    can_download BOOLEAN NOT NULL DEFAULT true,
    can_write BOOLEAN NOT NULL DEFAULT false,
    can_delete BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now()),
    UNIQUE(folder_id, user_id)
);

CREATE INDEX IF NOT EXISTS idx_folder_perms_lookup ON public.folder_permissions(folder_id, user_id);

-- ========================================================
-- 5. جدول الملفات المشتركة الحالية (Files Metadata)
-- ========================================================
CREATE TABLE IF NOT EXISTS public.files (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    folder_id UUID REFERENCES public.shared_folders(id) ON DELETE CASCADE,
    file_name TEXT NOT NULL,
    file_path TEXT NOT NULL, -- المسار النسبي: folder/subfolder/file.docx
    file_size BIGINT NOT NULL DEFAULT 0,
    mime_type TEXT,
    sha256_hash TEXT NOT NULL,
    current_version INT NOT NULL DEFAULT 1,
    storage_path TEXT NOT NULL, -- المسار الداخلي في Supabase Storage
    last_modified_by UUID REFERENCES public.profiles(id) ON DELETE SET NULL,
    last_modified_device UUID REFERENCES public.devices(id) ON DELETE SET NULL,
    is_deleted BOOLEAN NOT NULL DEFAULT false,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now()),
    created_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now()),
    UNIQUE(folder_id, file_name)
);

CREATE INDEX IF NOT EXISTS idx_files_folder_id ON public.files(folder_id);
CREATE INDEX IF NOT EXISTS idx_files_path ON public.files(file_path);

-- ========================================================
-- 6. جدول تاريخ إصدارات الملفات (File Versions History)
-- ========================================================
CREATE TABLE IF NOT EXISTS public.file_versions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    file_id UUID NOT NULL REFERENCES public.files(id) ON DELETE CASCADE,
    version_num INT NOT NULL,
    storage_path TEXT NOT NULL,
    file_size BIGINT NOT NULL,
    sha256_hash TEXT NOT NULL,
    change_summary TEXT,
    modified_by UUID REFERENCES public.profiles(id) ON DELETE SET NULL,
    modified_device UUID REFERENCES public.devices(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now())
);

CREATE INDEX IF NOT EXISTS idx_file_versions_lookup ON public.file_versions(file_id, version_num);

-- ========================================================
-- 7. جدول حجز وأقفال الملفات (File Locks - خاصة لملفات Access)
-- ========================================================
CREATE TABLE IF NOT EXISTS public.file_locks (
    file_id UUID PRIMARY KEY REFERENCES public.files(id) ON DELETE CASCADE,
    locked_by UUID NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
    device_id UUID NOT NULL REFERENCES public.devices(id) ON DELETE CASCADE,
    lock_type TEXT NOT NULL DEFAULT 'exclusive' CHECK (lock_type IN ('exclusive', 'shared')),
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
    action TEXT NOT NULL, -- UPLOAD, DOWNLOAD, CONFLICT, DELETE, LOCK, UNLOCK, AUTH
    entity_type TEXT NOT NULL, -- FILE, FOLDER, DEVICE, USER
    entity_id TEXT,
    entity_name TEXT NOT NULL,
    details JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now())
);

CREATE INDEX IF NOT EXISTS idx_audit_created_at ON public.audit_logs(created_at DESC);

-- ========================================================
-- 9. تفعيل بث الأحداث اللحظية (Supabase Realtime)
-- ========================================================
-- يتيح للأجهزة الـ 10 استلام إشعار فوري عند تعديل أي ملف أو قفله
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
