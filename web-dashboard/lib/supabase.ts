import { createClient } from '@supabase/supabase-js';

const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL || 'https://placeholder.supabase.co';
const supabaseAnonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY || 'placeholder_anon_key';

// العميل العام للواجهة
export const supabase = createClient(supabaseUrl, supabaseAnonKey);

// عميل الخادم ذو الصلاحيات الإدارية (يُستخدم فقط في مسارات API الخاصة بالخادم)
export const getAdminClient = () => {
  const serviceKey = process.env.SUPABASE_SERVICE_ROLE_KEY;
  if (!serviceKey) {
    throw new Error('مفتاح SUPABASE_SERVICE_ROLE_KEY غير مضبوط في متغيرات البيئة.');
  }
  return createClient(supabaseUrl, serviceKey);
};
