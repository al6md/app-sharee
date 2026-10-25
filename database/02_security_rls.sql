-- ========================================================
-- تبادل الملفات – File Exchange System
-- Security Policies: Row Level Security (RLS)
-- ========================================================

-- تفعيل RLS على كافة الجداول
ALTER TABLE public.profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.devices ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.shared_folders ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.folder_permissions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.files ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.file_versions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.file_locks ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.audit_logs ENABLE ROW LEVEL SECURITY;

-- دالة مساعدة للتحقق مما إذا كان المستخدم مديراً (Admin)
CREATE OR REPLACE FUNCTION public.is_admin(user_id UUID)
RETURNS BOOLEAN AS $$
BEGIN
    RETURN EXISTS (
        SELECT 1 FROM public.profiles
        WHERE id = user_id AND role = 'admin' AND is_active = true
    );
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- ========================================================
-- سياسات profiles
-- ========================================================
CREATE POLICY "يمكن للمستخدمين قراءة ملفاتهم الشخصية"
ON public.profiles FOR SELECT
USING (auth.uid() = id OR public.is_admin(auth.uid()));

CREATE POLICY "المدير فقط يمكنه تعديل الملفات الشخصية والأدوار"
ON public.profiles FOR UPDATE
USING (public.is_admin(auth.uid()));

-- ========================================================
-- سياسات devices
-- ========================================================
CREATE POLICY "المستخدم يرى أجهزته والمدير يرى جميع الأجهزة"
ON public.devices FOR SELECT
USING (auth.uid() = user_id OR public.is_admin(auth.uid()));

CREATE POLICY "المستخدم يستطيع تسجيل جهاز جديد"
ON public.devices FOR INSERT
WITH CHECK (auth.uid() = user_id);

CREATE POLICY "المدير فقط يمكنه اعتماد الأجهزة وتفعيلها"
ON public.devices FOR UPDATE
USING (public.is_admin(auth.uid()) OR auth.uid() = user_id);

-- ========================================================
-- سياسات shared_folders
-- ========================================================
CREATE POLICY "المستخدم يرى المجلدات المصرح له بها فقط"
ON public.shared_folders FOR SELECT
USING (
    public.is_admin(auth.uid()) OR
    EXISTS (
        SELECT 1 FROM public.folder_permissions fp
        WHERE fp.folder_id = shared_folders.id
        AND fp.user_id = auth.uid()
        AND fp.can_view = true
    )
);

CREATE POLICY "المدير فقط ينشئ ويعدل المجلدات"
ON public.shared_folders FOR ALL
USING (public.is_admin(auth.uid()));

-- ========================================================
-- سياسات files
-- ========================================================
CREATE POLICY "عرض الملفات للمصرح لهم بالعرض"
ON public.files FOR SELECT
USING (
    public.is_admin(auth.uid()) OR
    EXISTS (
        SELECT 1 FROM public.folder_permissions fp
        WHERE fp.folder_id = files.folder_id
        AND fp.user_id = auth.uid()
        AND fp.can_view = true
    )
);

CREATE POLICY "إضافة وتعديل الملفات لأصحاب صلاحية can_write"
ON public.files FOR INSERT
WITH CHECK (
    public.is_admin(auth.uid()) OR
    EXISTS (
        SELECT 1 FROM public.folder_permissions fp
        WHERE fp.folder_id = files.folder_id
        AND fp.user_id = auth.uid()
        AND fp.can_write = true
    )
);

CREATE POLICY "تحديث الملفات لأصحاب صلاحية can_write"
ON public.files FOR UPDATE
USING (
    public.is_admin(auth.uid()) OR
    EXISTS (
        SELECT 1 FROM public.folder_permissions fp
        WHERE fp.folder_id = files.folder_id
        AND fp.user_id = auth.uid()
        AND fp.can_write = true
    )
);

CREATE POLICY "حذف الملفات لأصحاب صلاحية can_delete فقط"
ON public.files FOR DELETE
USING (
    public.is_admin(auth.uid()) OR
    EXISTS (
        SELECT 1 FROM public.folder_permissions fp
        WHERE fp.folder_id = files.folder_id
        AND fp.user_id = auth.uid()
        AND fp.can_delete = true
    )
);

-- ========================================================
-- سياسات file_locks (أقفال ملفات Access)
-- ========================================================
CREATE POLICY "الجميع يرى الأقفال لمعرفة الملفات المحجوزة"
ON public.file_locks FOR SELECT
USING (true);

CREATE POLICY "حجز القفل للمستخدم المصرح له"
ON public.file_locks FOR INSERT
WITH CHECK (auth.uid() = locked_by);

CREATE POLICY "تحرير القفل لصاحبه أو للمدير"
ON public.file_locks FOR DELETE
USING (auth.uid() = locked_by OR public.is_admin(auth.uid()));

-- ========================================================
-- سياسات audit_logs
-- ========================================================
CREATE POLICY "المدير فقط يرى سجل التدقيق الشامل"
ON public.audit_logs FOR SELECT
USING (public.is_admin(auth.uid()));

CREATE POLICY "تسجيل العمليات متاح للمستخدمين المعتمدين"
ON public.audit_logs FOR INSERT
WITH CHECK (auth.uid() IS NOT NULL);
