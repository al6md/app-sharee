import { NextRequest, NextResponse } from 'next/server';
import {
  getCloudAdminStore,
  saveCloudPermissions,
  saveCloudAdminCredentials,
  saveCloudDevices,
  getDefaultDepartmentPermission,
  normalizeDepartmentPermission,
  DepartmentPermissionConfig,
} from '@/lib/googleDrive';

export const dynamic = 'force-dynamic';

export async function GET(req: NextRequest) {
  try {
    const force = req.nextUrl.searchParams.get('force') === '1';
    const store = await getCloudAdminStore(force);
    return NextResponse.json(
      {
        success: true,
        permissions: store.departments,
        adminCredentials: store.adminCredentials,
        devices: store.devices,
      },
      {
        headers: {
          'Cache-Control': 'no-store, no-cache, must-revalidate',
        },
      }
    );
  } catch (error: any) {
    console.error('[Permissions API GET Error]:', error);
    return NextResponse.json(
      { success: false, error: error?.message || 'فشل جلب الإعدادات والصلاحيات من السحابة' },
      { status: 500 }
    );
  }
}

export async function POST(req: NextRequest) {
  try {
    const body = await req.json();
    const { action, departmentName, permission, permissions } = body || {};

    if (action === 'UPDATE_CREDENTIALS') {
      const username = String(body.username || '').trim();
      const password = String(body.password || '').trim();
      if (!username) {
        return NextResponse.json(
          { success: false, error: 'اسم المستخدم الجديد مطلوب ولا يمكن أن يكون فارغاً' },
          { status: 400 }
        );
      }
      if (!password || password.length < 4) {
        return NextResponse.json(
          { success: false, error: 'كلمة المرور يجب أن تتكون من 4 أحرف أو أرقام على الأقل' },
          { status: 400 }
        );
      }
      const savedCreds = await saveCloudAdminCredentials(username, password);
      return NextResponse.json({
        success: true,
        adminCredentials: savedCreds,
      });
    }

    if (action === 'VERIFY_CREDENTIALS') {
      const store = await getCloudAdminStore(false);
      const u = String(body.username || '').trim();
      const p = String(body.password || '');
      const valid =
        u.toLowerCase() === store.adminCredentials.username.toLowerCase() &&
        p === store.adminCredentials.password;
      return NextResponse.json({
        success: true,
        valid,
        adminCredentials: store.adminCredentials,
      });
    }

    if (action === 'SAVE_DEVICES' && Array.isArray(body.devices)) {
      const savedDevices = await saveCloudDevices(body.devices);
      return NextResponse.json({
        success: true,
        devices: savedDevices,
      });
    }

    if (action === 'RESET_ALL' && Array.isArray(body.departmentNames)) {
      const resetMap: Record<string, DepartmentPermissionConfig> = {};
      for (const name of body.departmentNames) {
        if (name) resetMap[name] = getDefaultDepartmentPermission(name);
      }
      const saved = await saveCloudPermissions(resetMap, true);
      return NextResponse.json({ success: true, permissions: saved });
    }

    if (departmentName && permission) {
      const normalized = normalizeDepartmentPermission(departmentName, permission);
      const saved = await saveCloudPermissions({ [departmentName]: normalized });
      return NextResponse.json({
        success: true,
        permission: saved[departmentName],
        permissions: saved,
      });
    }

    if (permissions && typeof permissions === 'object') {
      const saved = await saveCloudPermissions(permissions);
      return NextResponse.json({
        success: true,
        permissions: saved,
      });
    }

    return NextResponse.json(
      { success: false, error: 'بيانات الصلاحيات المرسلة غير صالحة' },
      { status: 400 }
    );
  } catch (error: any) {
    console.error('[Permissions API POST Error]:', error);
    return NextResponse.json(
      { success: false, error: error?.message || 'فشل حفظ الإعدادات والصلاحيات في السحابة' },
      { status: 500 }
    );
  }
}
