import { NextRequest, NextResponse } from 'next/server';
import {
  getCloudAdminStore,
  saveCloudPermissions,
  saveCloudAdminCredentials,
  saveCloudDevices,
  authorizeDeviceForDepartment,
  revokeOrDeleteDevice,
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

    // تسجيل واعتماد جهاز جديد لقسم معين (يخزن اسم الجهاز في لوحة الأدمن)
    if (action === 'REGISTER_DEPARTMENT_DEVICE') {
      const deptName = String(body.departmentName || '').trim();
      const userVal = String(body.username || '').trim();
      const passVal = String(body.password || '').trim();
      const guid = String(body.machineGuid || '').trim();
      const devName = String(body.deviceName || '').trim() || 'جهاز بدون اسم';
      const osInfo = String(body.os || 'Web Browser');
      const userInfo = String(body.user || 'موظف الغرفة');

      if (!deptName || !guid) {
        return NextResponse.json(
          { success: false, error: 'اسم القسم ومعرّف الجهاز مطلوبان' },
          { status: 400 }
        );
      }

      const store = await getCloudAdminStore(false);
      const dept = store.departments[deptName];
      const adminCreds = store.adminCredentials;

      const expectedDeptUser = String(dept?.deptUsername || '').trim();
      const expectedDeptPass = String(dept?.deptPassword || dept?.pinCode || '').trim();
      const masterUser = String(adminCreds?.username || 'admin').trim();
      const masterPass = String(adminCreds?.password || 'admin1234').trim();

      // التحقق من المطابقة: إما بيانات القسم المخصصة، أو رمز القسم، أو حساب الأدمن العام
      let isValid = false;
      if (expectedDeptUser && expectedDeptPass) {
        isValid =
          userVal.toLowerCase() === expectedDeptUser.toLowerCase() &&
          passVal === expectedDeptPass;
      } else if (expectedDeptPass) {
        // إذا كان هناك رمز سري فقط للقسم
        isValid = passVal === expectedDeptPass || (userVal && passVal === expectedDeptPass);
      }

      // حساب الأدمن الرئيسي يدخل دائماً كصلاحية طارئة
      if (!isValid && masterUser && masterPass) {
        if (userVal.toLowerCase() === masterUser.toLowerCase() && passVal === masterPass) {
          isValid = true;
        }
      }

      if (!isValid) {
        return NextResponse.json(
          { success: false, error: 'اسم المستخدم أو الرمز السري لهذا القسم غير صحيح، يرجى مراجعة الإدارة.' },
          { status: 401 }
        );
      }

      const result = await authorizeDeviceForDepartment({
        machineGuid: guid,
        name: devName,
        os: osInfo,
        user: userInfo,
        departmentName: deptName,
      });

      return NextResponse.json({
        success: true,
        authorized: true,
        message: `تم اعتماد وتسجيل جهاز "${devName}" بنجاح في لوحة الأدمن للقسم (${deptName})`,
        device: result.device,
        departments: result.departments,
      });
    }

    // فحص ترخيص جهاز لقسم معين
    if (action === 'CHECK_DEVICE_ACCESS') {
      const deptName = String(body.departmentName || '').trim();
      const guid = String(body.machineGuid || '').trim();

      if (!deptName || !guid) {
        return NextResponse.json({ success: true, authorized: true });
      }

      const store = await getCloudAdminStore(false);
      const dept = store.departments[deptName];
      const hasSecurity = Boolean(dept?.deptUsername || dept?.deptPassword || dept?.pinCode);

      if (!hasSecurity) {
        return NextResponse.json({ success: true, authorized: true });
      }

      const matchingDev = store.devices.find((d) => d.machineGuid === guid);
      const isDeviceActive = matchingDev && matchingDev.isAuthorized !== false;
      const isDeptAllowed =
        Array.isArray(dept?.authorizedDevices) && dept.authorizedDevices.includes(guid);

      const isAuthed = Boolean(isDeviceActive && isDeptAllowed);
      return NextResponse.json({
        success: true,
        authorized: isAuthed,
        device: matchingDev || null,
      });
    }

    // حذف جهاز وسحب اعتماده فورياً (حصرياً من لوحة تحكم الأدمن)
    if (action === 'DELETE_DEVICE') {
      const identifier = String(body.deviceId || body.machineGuid || '').trim();
      if (!identifier) {
        return NextResponse.json({ success: false, error: 'معرّف الجهاز المطلوب حذفه غير متوفر' }, { status: 400 });
      }
      const res = await revokeOrDeleteDevice(identifier);
      return NextResponse.json({
        success: true,
        message: 'تم حذف الجهاز وسحب اعتماده نهائياً من كافة الأقسام',
        devices: res.devices,
        departments: res.departments,
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
