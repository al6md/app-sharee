import { google } from 'googleapis';
import { Readable } from 'stream';

const CLIENT_ID = process.env.GDRIVE_CLIENT_ID;
const CLIENT_SECRET = process.env.GDRIVE_CLIENT_SECRET;
const REFRESH_TOKEN = process.env.GDRIVE_REFRESH_TOKEN;
export const ROOT_FOLDER_ID = process.env.GDRIVE_FOLDER_ID || '1r984fj4btDKUnSfqfJlW2jzrRhVWaROB';

const oauth2Client = new google.auth.OAuth2(CLIENT_ID, CLIENT_SECRET);
oauth2Client.setCredentials({ refresh_token: REFRESH_TOKEN });

export const drive = google.drive({ version: 'v3', auth: oauth2Client });

/**
 * جلب شجرة الأقسام والمجلدات من سحابة Google Drive مباشرة
 */
export async function getCloudFolders() {
  const res = await drive.files.list({
    q: `'${ROOT_FOLDER_ID}' in parents and mimeType = 'application/vnd.google-apps.folder' and trashed = false`,
    fields: 'files(id, name, modifiedTime)',
    orderBy: 'name',
  });
  return res.data.files || [];
}

/**
 * إنشاء مجلد / قسم جديد
 */
export async function createCloudFolder(name: string, parentId: string = ROOT_FOLDER_ID) {
  const res = await drive.files.create({
    requestBody: {
      name,
      mimeType: 'application/vnd.google-apps.folder',
      parents: [parentId],
    },
    fields: 'id, name, mimeType',
  });
  return res.data;
}

/**
 * جلب كافة المستندات والملفات (النشطة والمحذوفة)
 */
export async function getAllCloudFiles() {
  // 1. جلب المجلدات
  const folders = await getCloudFolders();
  const folderMap = new Map<string, string>();
  folders.forEach((f) => folderMap.set(f.id!, f.name!));

  // 2. جلب الملفات النشطة
  const folderIds = [ROOT_FOLDER_ID, ...folders.map((f) => f.id!)];
  const parentQueries = folderIds.map((id) => `'${id}' in parents`).join(' or ');

  const res = await drive.files.list({
    q: `(${parentQueries}) and mimeType != 'application/vnd.google-apps.folder' and trashed = false`,
    fields: 'files(id, name, size, mimeType, modifiedTime, webViewLink, webContentLink, parents)',
    orderBy: 'modifiedTime desc',
    pageSize: 100,
  });

  const activeFiles = (res.data.files || []).map((file) => {
    const parentId = file.parents?.[0];
    const deptName = folderMap.get(parentId || '') || 'المجلد العام';
    return {
      id: file.id!,
      name: file.name!,
      size: Number(file.size || 0),
      mimeType: file.mimeType || 'application/octet-stream',
      modifiedTime: file.modifiedTime!,
      folder: deptName,
      folderId: parentId,
      previewUrl: file.webViewLink,
      downloadUrl: file.webContentLink,
      isDeleted: false,
    };
  });

  // 3. جلب ملفات سلة المحذوفات
  let trashFiles: any[] = [];
  try {
    const trashRes = await drive.files.list({
      q: `trashed = true and mimeType != 'application/vnd.google-apps.folder'`,
      fields: 'files(id, name, size, mimeType, modifiedTime, webViewLink, webContentLink, parents)',
      orderBy: 'modifiedTime desc',
      pageSize: 50,
    });
    trashFiles = (trashRes.data.files || []).map((file) => {
      const parentId = file.parents?.[0];
      const deptName = folderMap.get(parentId || '') || 'المجلد العام';
      return {
        id: file.id!,
        name: file.name!,
        size: Number(file.size || 0),
        mimeType: file.mimeType || 'application/octet-stream',
        modifiedTime: file.modifiedTime!,
        folder: deptName,
        folderId: parentId,
        previewUrl: file.webViewLink,
        downloadUrl: file.webContentLink,
        isDeleted: true,
      };
    });
  } catch (e) {
    console.error('Error fetching trash files:', e);
  }

  return { folders, files: [...activeFiles, ...trashFiles] };
}

/**
 * رفع ملف لسحابة Google Drive داخل قسم محدد
 */
export async function uploadFileToDrive(buffer: Buffer, fileName: string, mimeType: string, folderId: string = ROOT_FOLDER_ID) {
  const stream = new Readable();
  stream.push(buffer);
  stream.push(null);

  // فحص إذا كان الملف موجود مسبقاً بنفس الاسم لتحديثه
  const check = await drive.files.list({
    q: `'${folderId}' in parents and name = '${fileName.replace(/'/g, "\\'")}' and trashed = false`,
    fields: 'files(id)',
  });

  if (check.data.files && check.data.files.length > 0) {
    const existingId = check.data.files[0].id!;
    const res = await drive.files.update({
      fileId: existingId,
      media: {
        mimeType,
        body: stream,
      },
      fields: 'id, name, size, modifiedTime, webViewLink, webContentLink',
    });
    return { ...res.data, isUpdate: true };
  } else {
    const res = await drive.files.create({
      requestBody: {
        name: fileName,
        parents: [folderId],
      },
      media: {
        mimeType,
        body: stream,
      },
      fields: 'id, name, size, modifiedTime, webViewLink, webContentLink',
    });
    return { ...res.data, isUpdate: false };
  }
}

/**
 * نقل ملف إلى سلة المحذوفات
 */
export async function deleteDriveItem(fileId: string) {
  return await drive.files.update({
    fileId,
    requestBody: {
      trashed: true,
    },
  });
}

/**
 * استرجاع ملف من سلة المحذوفات
 */
export async function restoreDriveItem(fileId: string) {
  return await drive.files.update({
    fileId,
    requestBody: {
      trashed: false,
    },
  });
}

/**
 * حذف نهائي لملف
 */
export async function permanentDeleteDriveItem(fileId: string) {
  return await drive.files.delete({
    fileId,
  });
}

/**
 * إعادة تسمية ملف أو مجلد
 */
export async function renameDriveItem(fileId: string, newName: string) {
  const res = await drive.files.update({
    fileId,
    requestBody: {
      name: newName,
    },
    fields: 'id, name',
  });
  return res.data;
}
