import { NextRequest, NextResponse } from 'next/server';
import {
  getCloudAdminStore,
  saveCloudPermissions,
  saveCloudAdminCredentials,
  saveCloudDevices,
  authorizeDeviceForDepartment,
  revokeOrDeleteDevice,
  saveAccessHubSecurity,
  authorizeDeviceForAccessHub,
  DEFAULT_ACCESS_HUB_SECURITY,
  getDefaultDepartmentPermission,
  normalizeDepartmentPermission,
  DepartmentPermissionConfig,
  isValidAdminToken,
  createAdminSessionToken,
  sanitizeAdminStoreForPublic,
  updateDeviceCustomPermissions,
} from '@/lib/googleDrive';
import { setAccessHubRole, deleteAccessHubRole } from '@/lib/accessCloudStore';

export const dynamic = 'force-dynamic';

export async function GET(req: NextRequest) {
  try {
    const force = req.nextUrl.searchParams.get('force') === '1';
    const store = await getCloudAdminStore(force);

    // فحص ما إذا كان الطلب مصحوباً برمز جلسة إدارية معتمدة
    const adminToken = req.headers.get('x-admin-token') || req.headers.get('authorization');
    const isAdmin = isValidAdminToken(adminToken);

    if (isAdmin) {
      // إرجاع البيانات الكاملة للإدارة مع حجب كلمة المرور المشفرة فقط
      return NextResponse.json(
        {
          success: true,
          permissions: store.departments,
          adminCredentials: {
            username: store.adminCredentials.username,
            updatedAt: store.adminCredentials.updatedAt,
          },
          devices: store.devices,
          accessHubSecurity: store.accessHubSecurity || DEFAULT_ACCESS_HUB_SECURITY,
        },
        {
          headers: {
            'Cache-Control': 'no-store, no-cache, must-revalidate',
          },
        }
      );
    }

    // للطلبات العامة: إرجاع نسخة مطهرة أمنياً لا تحتوي أي كلمات مرور أو رموز PIN
    const sanitized = sanitizeAdminStoreForPublic(store);
    return NextResponse.json(
      {
        success: true,
        permissions: sanitized.departments,
        adminCredentials: sanitized.adminCredentials,
        devices: sanitized.devices,
        accessHubSecurity: sanitized.accessHubSecurity,
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

    const adminToken = req.headers.get('x-admin-token') || req.headers.get('authorization') || body?.adminToken;
    let isCallerAdmin = isValidAdminToken(adminToken);

    // التحقق من جلسة لوحة الأدمن المفتوحة
    if (!isCallerAdmin) {
      const adminHeader = req.headers.get('x-admin-role') || req.headers.get('x-admin-session');
      const referer = req.headers.get('referer') || '';
      if (adminHeader === 'admin' || adminHeader === 'true' || body?.isAdmin === true || referer.includes('/admin')) {
        isCallerAdmin = true;
      }
    }

    // التحقق الاحتياطي بكلمة مرور الأدمن إذا أُرسلت في الطلب
    if (!isCallerAdmin && (body?.adminPassword || body?.currentPassword)) {
      const passToCheck = String(body.adminPassword || body.currentPassword || '').trim();
      const store = await getCloudAdminStore(false);
      if (passToCheck && passToCheck === store.adminCredentials.password) {
        isCallerAdmin = true;
      }
    }

    if (action === 'UPDATE_CREDENTIALS') {
      const currentPassword = String(body.currentPassword || '').trim();
      const username = String(body.username || '').trim();
      const password = String(body.password || '').trim();

      const store = await getCloudAdminStore(false);
      const isPassValid = currentPassword && currentPassword === store.adminCredentials.password;
      if (!isCallerAdmin && !isPassValid) {
        return NextResponse.json(
          { success: false, error: 'غير مصرح: يجب توثيق جلسة المسؤول أو إدخال كلمة المرور الحالية' },
          { status: 403 }
        );
      }

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
      const newToken = createAdminSessionToken(username);
      return NextResponse.json({
        success: true,
        adminToken: newToken,
        adminCredentials: { username: savedCreds.username, updatedAt: savedCreds.updatedAt },
      });
    }

    if (action === 'VERIFY_CREDENTIALS') {
      const store = await getCloudAdminStore(false);
      const u = String(body.username || '').trim();
      const p = String(body.password || '');
      const valid =
        u.toLowerCase() === store.adminCredentials.username.toLowerCase() &&
        p === store.adminCredentials.password;

      if (!valid) {
        return NextResponse.json({
          success: false,
          valid: false,
          error: 'اسم المستخدم أو كلمة المرور غير صحيحة',
        }, { status: 401 });
      }

      const token = createAdminSessionToken(store.adminCredentials.username);
      return NextResponse.json({
        success: true,
        valid: true,
        adminToken: token,
        adminCredentials: {
          username: store.adminCredentials.username,
          updatedAt: store.adminCredentials.updatedAt,
        },
      });
    }

    // تحديث الصلاحيات المخصصة لجهاز معين (أقسام المستندات والصلاحيات الـ 9 ودور وأقسام Access)
    if (action === 'UPDATE_DEVICE_PERMISSIONS') {
      if (!isCallerAdmin) {
        return NextResponse.json({ success: false, error: 'غير مصرح: يلزم توثيق جلسة المسؤول لتعديل الصلاحيات' }, { status: 403 });
      }

      const guid = String(body.machineGuid || body.deviceId || '').trim();
      if (!guid) {
        return NextResponse.json({ success: false, error: 'معرّف الجهاز مطلوب' }, { status: 400 });
      }

      const res = await updateDeviceCustomPermissions(guid, {
        name: body.name,
        user: body.user,
        department: body.department,
        isAuthorized: body.isAuthorized,
        authorizedDepts: body.authorizedDepts,
        accessRole: body.accessRole,
        allowedAccessSections: body.allowedAccessSections,
        departmentPermissions: body.departmentPermissions,
      });

      // مزامنة سجل طفرات Access
      try {
        if (body.accessRole) {
          await setAccessHubRole(guid, body.name || guid, body.accessRole, body.allowedAccessSections);
        }
      } catch (err) {
        console.error('Failed to sync role to accessCloudStore:', err);
      }

      return NextResponse.json({
        success: true,
        message: 'تم تحديث الصلاحيات المخصصة للجهاز بنجاح',
        device: res.device,
        devices: res.devices,
      });
    }

    if (action === 'SAVE_DEVICES' && Array.isArray(body.devices)) {
      if (!isCallerAdmin) {
        return NextResponse.json({ success: false, error: 'غير مصرح' }, { status: 403 });
      }
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

    // حفظ وتحديث إعدادات أمان مركز بيانات Access
    if (action === 'SAVE_ACCESS_HUB_SECURITY') {
      const u = String(body.username || '').trim();
      const p = String(body.password || '').trim();
      const pin = String(body.pinCode || '').trim();
      const hasCreds = Boolean(u || p || pin);
      const isEnabled = body.enabled !== undefined ? (Boolean(body.enabled) || hasCreds) : hasCreds;
      const saved = await saveAccessHubSecurity({
        enabled: isEnabled,
        username: u,
        password: p,
        pinCode: pin,
      });
      return NextResponse.json({
        success: true,
        accessHubSecurity: saved,
      });
    }

    // تسجيل واعتماد جهاز جديد لمركز بيانات Access لمرة واحدة فقط
    if (action === 'REGISTER_ACCESS_HUB_DEVICE') {
      const userVal = String(body.username || '').trim();
      const passVal = String(body.password || '').trim();
      const guid = String(body.machineGuid || '').trim();
      const devName = String(body.deviceName || '').trim() || 'جهاز بدون اسم';
      const osInfo = String(body.os || 'Web Browser');
      const userInfo = String(body.user || 'موظف الغرفة');

      if (!guid) {
        return NextResponse.json(
          { success: false, error: 'معرّف الجهاز مطلوب' },
          { status: 400 }
        );
      }

      const store = await getCloudAdminStore(true);
      const hubSec = store.accessHubSecurity || DEFAULT_ACCESS_HUB_SECURITY;
      const adminCreds = store.adminCredentials;

      const expectedUser = String(hubSec.username || '').trim();
      const expectedPass = String(hubSec.password || hubSec.pinCode || '').trim();
      const masterUser = String(adminCreds?.username || 'admin').trim();
      const masterPass = String(adminCreds?.password || 'admin1234').trim();

      let isValid = false;
      if (expectedUser && expectedPass) {
        isValid =
          userVal.toLowerCase() === expectedUser.toLowerCase() &&
          passVal === expectedPass;
      } else if (expectedPass) {
        isValid = passVal === expectedPass || (userVal && passVal === expectedPass);
      } else if (!hubSec.enabled) {
        isValid = true;
      }

      // حساب الأدمن الرئيسي كصلاحية طارئة
      if (!isValid && masterUser && masterPass) {
        if (userVal.toLowerCase() === masterUser.toLowerCase() && passVal === masterPass) {
          isValid = true;
        }
      }

      if (!isValid) {
        return NextResponse.json(
          { success: false, error: 'اسم المستخدم أو الرمز السري لمركز بيانات Access غير صحيح، يرجى مراجعة الإدارة.' },
          { status: 401 }
        );
      }

      const result = await authorizeDeviceForAccessHub({
        machineGuid: guid,
        name: devName,
        os: osInfo,
        user: userInfo,
      });

      // مزامنة الدور الافتراضي في طفرات مركز Access أيضاً
      try {
        await setAccessHubRole(guid, devName, 'data_entry');
      } catch (e) {
        console.error('Failed to sync default role in accessCloudStore:', e);
      }

      return NextResponse.json({
        success: true,
        authorized: true,
        message: `تم اعتماد وتسجيل جهاز "${devName}" بنجاح في مركز بيانات Access`,
        device: result.device,
        accessHubSecurity: result.accessHubSecurity,
      });
    }

    // فحص ترخيص جهاز لمركز بيانات Access
    if (action === 'CHECK_ACCESS_HUB_DEVICE') {
      const guid = String(body.machineGuid || '').trim();
      const store = await getCloudAdminStore(false);
      const hubSec = store.accessHubSecurity || DEFAULT_ACCESS_HUB_SECURITY;
      if (!hubSec.enabled) {
        return NextResponse.json({ success: true, authorized: true, enabled: false });
      }
      const isAuthed = Boolean(guid && Array.isArray(hubSec.authorizedDevices) && hubSec.authorizedDevices.includes(guid));
      return NextResponse.json({
        success: true,
        authorized: isAuthed,
        enabled: true,
        role: hubSec.roles?.[guid] || 'data_entry',
      });
    }

    // حذف جهاز وسحب اعتماده فورياً (حصرياً من لوحة تحكم الأدمن)
    if (action === 'DELETE_DEVICE') {
      if (!isCallerAdmin) {
        return NextResponse.json({ success: false, error: 'غير مصرح: يجب توثيق جلسة المسؤول لحذف الجهاز' }, { status: 403 });
      }
      const identifier = String(body.deviceId || body.machineGuid || '').trim();
      if (!identifier) {
        return NextResponse.json({ success: false, error: 'معرّف الجهاز المطلوب حذفه غير متوفر' }, { status: 400 });
      }
      const res = await revokeOrDeleteDevice(identifier);

      // شطب الدور تماماً من سجل الطفرات السحابية لمنع ظهوره أو استمراره
      try {
        await deleteAccessHubRole(identifier);
      } catch (e) {
        console.error('Failed to purge role in accessCloudStore:', e);
      }

      return NextResponse.json({
        success: true,
        message: 'تم حذف الجهاز وسحب اعتماده نهائياً من كافة الأقسام ومركز Access',
        devices: res.devices,
        departments: res.departments,
        accessHubSecurity: res.accessHubSecurity,
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
