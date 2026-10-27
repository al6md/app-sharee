import { google } from 'googleapis';
import { Readable } from 'stream';

const CLIENT_ID = process.env.GDRIVE_CLIENT_ID;
const CLIENT_SECRET = process.env.GDRIVE_CLIENT_SECRET;
const REFRESH_TOKEN = process.env.GDRIVE_REFRESH_TOKEN;
export const ROOT_FOLDER_ID = process.env.GDRIVE_FOLDER_ID || '1BF6mDMuwuaS5c4Ekq9KPcEXaAOxGOmfB';

const FOLDER_MIME = 'application/vnd.google-apps.folder';
const IGNORED_EXACT = new Set(['desktop.ini', 'thumbs.db', '.ds_store']);
const IGNORED_SUFFIXES = ['.tmp', '.laccdb', '.ldb', '.crdownload', '.partial', '~'];

function isIgnoredName(name?: string | null): boolean {
  if (!name) return true;
  const low = name.toLowerCase();
  if (IGNORED_EXACT.has(low)) return true;
  if (name.startsWith('~$') || name.startsWith('.') || name.startsWith('~WRL')) return true;
  return IGNORED_SUFFIXES.some((s) => low.endsWith(s));
}

function qEscape(val: string): string {
  return val.replace(/\\/g, '\\\\').replace(/'/g, "\\'");
}

const oauth2Client = new google.auth.OAuth2(CLIENT_ID, CLIENT_SECRET);
oauth2Client.setCredentials({ refresh_token: REFRESH_TOKEN });

export const drive = google.drive({ version: 'v3', auth: oauth2Client });

export interface CloudFolderItem {
  id: string;
  name: string;
  path: string;
  parentPath: string;
  department: string;
  modifiedTime?: string | null;
}

async function listChildrenBatch(parentIds: string[]) {
  const qParents = parentIds.map((id) => `'${id}' in parents`).join(' or ');
  const query = `(${qParents}) and trashed = false`;
  const all: any[] = [];
  let pageToken: string | undefined = undefined;
  do {
    const res: any = await drive.files.list({
      q: query,
      fields: 'nextPageToken, files(id, name, size, mimeType, modifiedTime, webViewLink, webContentLink, parents)',
      pageSize: 1000,
      pageToken,
    });
    if (res.data.files) {
      all.push(...res.data.files);
    }
    pageToken = res.data.nextPageToken || undefined;
  } while (pageToken);
  return all;
}

/**
 * جلب أقسام المستوى الأول من سحابة Google Drive مباشرة
 */
export async function getCloudFolders() {
  const res = await drive.files.list({
    q: `'${ROOT_FOLDER_ID}' in parents and mimeType = '${FOLDER_MIME}' and trashed = false`,
    fields: 'files(id, name, modifiedTime)',
    orderBy: 'name',
    pageSize: 500,
  });
  return (res.data.files || []).filter((f) => !isIgnoredName(f.name));
}

/**
 * إنشاء مجلد / قسم جديد (مع إعادة استخدام المجلد إن كان موجوداً بنفس الاسم داخل نفس الأب لمنع التكرار)
 */
export async function createCloudFolder(name: string, parentId: string = ROOT_FOLDER_ID) {
  const cleanName = name.trim();
  const check = await drive.files.list({
    q: `'${parentId}' in parents and name = '${qEscape(cleanName)}' and mimeType = '${FOLDER_MIME}' and trashed = false`,
    fields: 'files(id, name, mimeType)',
    pageSize: 5,
  });
  if (check.data.files && check.data.files.length > 0) {
    return check.data.files[0];
  }
  const res = await drive.files.create({
    requestBody: {
      name: cleanName,
      mimeType: FOLDER_MIME,
      parents: [parentId],
    },
    fields: 'id, name, mimeType',
  });
  return res.data;
}

/**
 * جلب الشجرة الكاملة لكافة الأقسام والمجلدات الفرعية والمستندات (بأي عمق وبترقيم صفحات كامل)
 */
export async function getAllCloudFiles() {
  const idToPath = new Map<string, string>([[ROOT_FOLDER_ID, '']]);
  const allFolders: CloudFolderItem[] = [];
  const rawActiveFiles: { file: any; relFolder: string }[] = [];

  let currentLevel = [ROOT_FOLDER_ID];
  const visited = new Set<string>([ROOT_FOLDER_ID]);

  while (currentLevel.length > 0) {
    const nextLevel: string[] = [];
    for (let i = 0; i < currentLevel.length; i += 25) {
      const chunk = currentLevel.slice(i, i + 25);
      const children = await listChildrenBatch(chunk);
      for (const item of children) {
        const parentId = item.parents?.[0];
        if (!parentId || !idToPath.has(parentId)) continue;
        const parentPath = idToPath.get(parentId) || '';
        const name = item.name || '';
        if (isIgnoredName(name)) continue;

        const relPath = parentPath ? `${parentPath}/${name}` : name;

        if (item.mimeType === FOLDER_MIME) {
          if (visited.has(item.id!)) continue;
          visited.add(item.id!);
          idToPath.set(item.id!, relPath);
          const dept = relPath.split('/')[0];
          allFolders.push({
            id: item.id!,
            name,
            path: relPath,
            parentPath,
            department: dept,
            modifiedTime: item.modifiedTime,
          });
          nextLevel.push(item.id!);
        } else {
          if (String(item.mimeType || '').startsWith('application/vnd.google-apps.')) continue;
          rawActiveFiles.push({ file: item, relFolder: parentPath });
        }
      }
    }
    currentLevel = nextLevel;
  }

  allFolders.sort((a, b) => a.path.localeCompare(b.path, 'ar'));

  const departments = allFolders
    .filter((f) => !f.parentPath)
    .map((f) => ({ id: f.id, name: f.name, modifiedTime: f.modifiedTime }));

  const activeFiles = rawActiveFiles
    .sort((a, b) => String(b.file.modifiedTime || '').localeCompare(String(a.file.modifiedTime || '')))
    .map(({ file, relFolder }) => {
      const deptName = relFolder ? relFolder.split('/')[0] : 'القسم العام';
      const subFolder = relFolder.includes('/') ? relFolder.split('/').slice(1).join('/') : '';
      return {
        id: file.id!,
        name: file.name!,
        size: Number(file.size || 0),
        mimeType: file.mimeType || 'application/octet-stream',
        modifiedTime: file.modifiedTime!,
        folder: relFolder || 'القسم العام',
        department: deptName,
        subFolder,
        folderId: file.parents?.[0],
        previewUrl: file.webViewLink,
        downloadUrl: file.webContentLink,
        isDeleted: false,
      };
    });

  // جلب ملفات سلة المحذوفات
  let trashFiles: any[] = [];
  try {
    const trashRes = await drive.files.list({
      q: `trashed = true and mimeType != '${FOLDER_MIME}'`,
      fields: 'files(id, name, size, mimeType, modifiedTime, webViewLink, webContentLink, parents)',
      orderBy: 'modifiedTime desc',
      pageSize: 100,
    });
    trashFiles = (trashRes.data.files || [])
      .filter((file) => !isIgnoredName(file.name))
      .map((file) => {
        const parentId = file.parents?.[0];
        const relFolder = (parentId && idToPath.get(parentId)) || 'القسم العام';
        const deptName = relFolder.split('/')[0] || 'القسم العام';
        const subFolder = relFolder.includes('/') ? relFolder.split('/').slice(1).join('/') : '';
        return {
          id: file.id!,
          name: file.name!,
          size: Number(file.size || 0),
          mimeType: file.mimeType || 'application/octet-stream',
          modifiedTime: file.modifiedTime!,
          folder: relFolder,
          department: deptName,
          subFolder,
          folderId: parentId,
          previewUrl: file.webViewLink,
          downloadUrl: file.webContentLink,
          isDeleted: true,
        };
      });
  } catch (e) {
    console.error('Error fetching trash files:', e);
  }

  return {
    folders: departments,
    allFolders,
    files: [...activeFiles, ...trashFiles],
  };
}

/**
 * رفع ملف لسحابة Google Drive داخل مجلد محدد
 */
export async function uploadFileToDrive(
  buffer: Buffer,
  fileName: string,
  mimeType: string,
  folderId: string = ROOT_FOLDER_ID
) {
  const stream = new Readable();
  stream.push(buffer);
  stream.push(null);

  const check = await drive.files.list({
    q: `'${folderId}' in parents and name = '${qEscape(fileName)}' and mimeType != '${FOLDER_MIME}' and trashed = false`,
    fields: 'files(id)',
    pageSize: 5,
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
 * نقل ملف أو مجلد إلى سلة المحذوفات
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
