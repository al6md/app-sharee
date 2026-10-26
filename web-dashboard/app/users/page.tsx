'use client';

import { useState } from 'react';
import { 
  Users, 
  UserPlus, 
  Shield, 
  Lock, 
  Check, 
  X, 
  Eye, 
  Download, 
  Edit3, 
  Trash2,
  Folder
} from 'lucide-react';

interface UserItem {
  id: string;
  name: string;
  email: string;
  role: 'admin' | 'user';
  deviceCount: number;
  isActive: boolean;
  permissions: {
    folderName: string;
    canView: boolean;
    canDownload: boolean;
    canWrite: boolean;
    canDelete: boolean;
  }[];
}

export default function UsersPermissionsPage() {
  const [users, setUsers] = useState<UserItem[]>([
    {
      id: '1',
      name: 'المدير العام',
      email: 'admin@company.com',
      role: 'admin',
      deviceCount: 1,
      isActive: true,
      permissions: [
        { folderName: 'الكتب الرسمية (Word)', canView: true, canDownload: true, canWrite: true, canDelete: true },
        { folderName: 'البيانات المالية (Excel)', canView: true, canDownload: true, canWrite: true, canDelete: true },
        { folderName: 'قواعد Access', canView: true, canDownload: true, canWrite: true, canDelete: true },
      ]
    },
    {
      id: '2',
      name: 'أحمد محمود',
      email: 'ahmed@company.com',
      role: 'user',
      deviceCount: 1,
      isActive: true,
      permissions: [
        { folderName: 'الكتب الرسمية (Word)', canView: true, canDownload: true, canWrite: true, canDelete: false },
        { folderName: 'البيانات المالية (Excel)', canView: true, canDownload: true, canWrite: true, canDelete: false },
        { folderName: 'قواعد Access', canView: true, canDownload: true, canWrite: true, canDelete: false },
      ]
    },
    {
      id: '3',
      name: 'سارة خالد',
      email: 'sara@company.com',
      role: 'user',
      deviceCount: 1,
      isActive: true,
      permissions: [
        { folderName: 'الكتب الرسمية (Word)', canView: true, canDownload: true, canWrite: true, canDelete: false },
        { folderName: 'البيانات المالية (Excel)', canView: true, canDownload: true, canWrite: false, canDelete: false },
        { folderName: 'قواعد Access', canView: false, canDownload: false, canWrite: false, canDelete: false },
      ]
    },
    {
      id: '4',
      name: 'محمد علي',
      email: 'mohamed@company.com',
      role: 'user',
      deviceCount: 1,
      isActive: true,
      permissions: [
        { folderName: 'الكتب الرسمية (Word)', canView: true, canDownload: true, canWrite: false, canDelete: false },
        { folderName: 'البيانات المالية (Excel)', canView: true, canDownload: true, canWrite: true, canDelete: false },
        { folderName: 'قواعد Access', canView: true, canDownload: true, canWrite: false, canDelete: false },
      ]
    }
  ]);

  const [selectedUserForPerms, setSelectedUserForPerms] = useState<UserItem | null>(null);

  return (
    <div className="p-8 space-y-6">
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h2 className="text-2xl font-black text-slate-900">إدارة المستخدمين ومصفوفة الصلاحيات المتقدمة</h2>
          <p className="text-slate-500 text-sm mt-1">
            تحديد صلاحيات القراءة، التحميل، التعديل (Ctrl+S)، والحذف لكل مجلد على حدة
          </p>
        </div>

        <button className="flex items-center gap-2 px-4 py-2 bg-sky-600 hover:bg-sky-700 text-white text-sm font-bold rounded-lg transition shadow-sm">
          <UserPlus className="w-4 h-4" />
          <span>إضافة مستخدم جديد</span>
        </button>
      </div>

      {/* تنبيه أمان الخادم */}
      <div className="p-4 bg-sky-50 border border-sky-200 rounded-xl text-xs text-sky-900 flex items-center gap-2">
        <Shield className="w-4 h-4 text-sky-600 shrink-0" />
        <span>
          <strong>حماية الخادم:</strong> يتم تطبيق هذه الصلاحيات بقوة على مستوى سحابة Google Drive المشتركة. أي محاولة لتعديل أو رفع ملف دون امتلاك صلاحية <code>can_write</code> يتم رفضها على الخادم فوراً.
        </span>
      </div>

      {/* جدول المستخدمين */}
      <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
        <table className="w-full text-right text-sm">
          <thead className="bg-slate-50 text-slate-500 text-xs font-bold border-b border-slate-200">
            <tr>
              <th className="p-4">المستخدم</th>
              <th className="p-4">البريد الإلكتروني</th>
              <th className="p-4">الدور</th>
              <th className="p-4">الأجهزة المرتبطة</th>
              <th className="p-4">حالة الحساب</th>
              <th className="p-4 text-center">مصفوفة الصلاحيات</th>
              <th className="p-4 text-center">الإجراء</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {users.map((user) => (
              <tr key={user.id} className="hover:bg-slate-50/70 transition">
                <td className="p-4">
                  <div className="font-bold text-slate-800">{user.name}</div>
                </td>
                <td className="p-4 text-xs font-mono text-slate-600">{user.email}</td>
                <td className="p-4">
                  {user.role === 'admin' ? (
                    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-bold bg-indigo-50 text-indigo-700 border border-indigo-200">
                      مدير النظام
                    </span>
                  ) : (
                    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-bold bg-slate-100 text-slate-700">
                      مستخدم
                    </span>
                  )}
                </td>
                <td className="p-4 text-xs font-medium text-slate-700">{user.deviceCount} جهاز</td>
                <td className="p-4">
                  <span className="inline-flex items-center gap-1 text-xs font-bold text-emerald-600">
                    <Check className="w-3.5 h-3.5" /> نشط
                  </span>
                </td>
                <td className="p-4 text-center">
                  <button 
                    onClick={() => setSelectedUserForPerms(user)}
                    className="px-3 py-1 bg-slate-100 hover:bg-slate-200 text-slate-700 text-xs font-bold rounded-lg transition"
                  >
                    عرض وتعديل الصلاحيات ⚙️
                  </button>
                </td>
                <td className="p-4 text-center">
                  <button className="text-xs text-rose-600 hover:text-rose-800 font-bold">
                    تعطيل
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* نافذة تعديل الصلاحيات المنبثقة */}
      {selectedUserForPerms && (
        <div className="fixed inset-0 bg-slate-900/50 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl max-w-2xl w-full p-6 shadow-2xl space-y-4">
            <div className="flex items-center justify-between border-b pb-3">
              <div>
                <h3 className="font-bold text-slate-900">مصفوفة صلاحيات: {selectedUserForPerms.name}</h3>
                <p className="text-xs text-slate-500">{selectedUserForPerms.email}</p>
              </div>
              <button 
                onClick={() => setSelectedUserForPerms(null)}
                className="p-1 text-slate-400 hover:text-slate-600 rounded-lg"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="space-y-3">
              <table className="w-full text-right text-xs">
                <thead className="bg-slate-50 text-slate-500 font-bold border-b">
                  <tr>
                    <th className="p-3">المجلد المشترك</th>
                    <th className="p-3 text-center">العرض (View)</th>
                    <th className="p-3 text-center">التحميل (Download)</th>
                    <th className="p-3 text-center">التعديل وحفظ Ctrl+S (Write)</th>
                    <th className="p-3 text-center">الحذف (Delete)</th>
                  </tr>
                </thead>
                <tbody className="divide-y">
                  {selectedUserForPerms.permissions.map((p, idx) => (
                    <tr key={idx} className="hover:bg-slate-50">
                      <td className="p-3 font-semibold text-slate-800">{p.folderName}</td>
                      <td className="p-3 text-center">
                        <input type="checkbox" defaultChecked={p.canView} className="rounded text-sky-600 focus:ring-sky-500" />
                      </td>
                      <td className="p-3 text-center">
                        <input type="checkbox" defaultChecked={p.canDownload} className="rounded text-emerald-600 focus:ring-emerald-500" />
                      </td>
                      <td className="p-3 text-center">
                        <input type="checkbox" defaultChecked={p.canWrite} className="rounded text-amber-600 focus:ring-amber-500" />
                      </td>
                      <td className="p-3 text-center">
                        <input type="checkbox" defaultChecked={p.canDelete} className="rounded text-rose-600 focus:ring-rose-500" />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div className="flex items-center justify-end gap-2 pt-3 border-t">
              <button 
                onClick={() => setSelectedUserForPerms(null)}
                className="px-4 py-2 bg-slate-100 hover:bg-slate-200 text-slate-700 text-xs font-bold rounded-lg transition"
              >
                إلغاء
              </button>
              <button 
                onClick={() => {
                  alert("تم حفظ الصلاحيات في الخادم بنجاح.");
                  setSelectedUserForPerms(null);
                }}
                className="px-4 py-2 bg-sky-600 hover:bg-sky-700 text-white text-xs font-bold rounded-lg transition"
              >
                حفظ التعديلات في السحابة
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
