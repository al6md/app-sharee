-- ========================================================
-- تبادل الملفات – File Exchange System
-- Seed Data & Automated Triggers
-- ========================================================

-- دالة ومحفز (Trigger) لإنشاء ملف تعريف تلقائي فور تسجيل مستخدم جديد
CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS TRIGGER AS $$
BEGIN
    INSERT INTO public.profiles (id, full_name, email, role)
    VALUES (
        new.id,
        COALESCE(new.raw_user_meta_data->>'full_name', 'مستخدم جديد'),
        new.email,
        COALESCE(new.raw_user_meta_data->>'role', 'user')
    );
    RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;
CREATE TRIGGER on_auth_user_created
    AFTER INSERT ON auth.users
    FOR EACH ROW EXECUTE PROCEDURE public.handle_new_user();

-- إنشاء المجلدات المشتركة الافتراضية
INSERT INTO public.shared_folders (id, name)
VALUES 
    ('11111111-1111-1111-1111-111111111111', 'الكتب الرسمية والمراسلات (Word)'),
    ('22222222-2222-2222-2222-222222222222', 'جداول البيانات والتقارير المالية (Excel)'),
    ('33333333-3333-3333-3333-333333333333', 'قواعد بيانات المؤسسة (Access)'),
    ('44444444-4444-4444-4444-444444444444', 'النماذج والتعاميم العامة')
ON CONFLICT (id) DO NOTHING;
