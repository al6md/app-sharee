import { NextRequest, NextResponse } from 'next/server';
import { getDriveFileStreamResponse, drive } from '@/lib/googleDrive';

export const dynamic = 'force-dynamic';
export const maxDuration = 60;

const EXT_MIME_MAP: Record<string, string> = {
  accdb: 'application/msaccess',
  mdb: 'application/msaccess',
  docx: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
  doc: 'application/msword',
  xlsx: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  xls: 'application/vnd.ms-excel',
  pptx: 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
  ppt: 'application/vnd.ms-powerpoint',
  jpg: 'image/jpeg',
  jpeg: 'image/jpeg',
  png: 'image/png',
  gif: 'image/gif',
  webp: 'image/webp',
  svg: 'image/svg+xml',
  bmp: 'image/bmp',
  ico: 'image/x-icon',
  pdf: 'application/pdf',
  mp4: 'video/mp4',
  webm: 'video/webm',
  mov: 'video/quicktime',
  avi: 'video/x-msvideo',
  mkv: 'video/x-matroska',
  mp3: 'audio/mpeg',
  wav: 'audio/wav',
  ogg: 'audio/ogg',
  m4a: 'audio/mp4',
  txt: 'text/plain; charset=utf-8',
  csv: 'text/csv; charset=utf-8',
  json: 'application/json; charset=utf-8',
  zip: 'application/zip',
  rar: 'application/x-rar-compressed',
  '7z': 'application/x-7z-compressed',
};

export async function OPTIONS() {
  const headers = new Headers();
  headers.set('Allow', 'GET, HEAD, OPTIONS');
  headers.set('Access-Control-Allow-Origin', '*');
  headers.set('Access-Control-Allow-Methods', 'GET, HEAD, OPTIONS');
  headers.set('Access-Control-Allow-Headers', '*');
  headers.set('Access-Control-Max-Age', '86400');
  return new NextResponse(null, { status: 204, headers });
}

export async function HEAD(req: NextRequest) {
  try {
    const fileId = req.nextUrl.searchParams.get('id');
    const download = req.nextUrl.searchParams.get('download') === '1';

    if (!fileId) {
      return new NextResponse(null, { status: 400 });
    }

    const metaRes = await drive.files.get({
      fileId,
      fields: 'id, name, mimeType, size',
    });
    const meta = metaRes.data;

    const fileName = meta.name || 'file';
    const ext = fileName.includes('.') ? fileName.split('.').pop()?.toLowerCase() || '' : '';
    let contentType = meta.mimeType || 'application/octet-stream';
    if (ext && EXT_MIME_MAP[ext]) {
      contentType = EXT_MIME_MAP[ext];
    }

    const resHeaders = new Headers();
    resHeaders.set('Content-Type', contentType);
    const encodedName = encodeURIComponent(fileName);
    const safeAsciiName = fileName.replace(/[^\x20-\x7E]/g, '_') || 'file';
    resHeaders.set(
      'Content-Disposition',
      `${download ? 'attachment' : 'inline'}; filename="${safeAsciiName}"; filename*=UTF-8''${encodedName}`
    );
    resHeaders.set('Accept-Ranges', 'bytes');
    resHeaders.set('Access-Control-Allow-Origin', '*');
    resHeaders.set('Access-Control-Allow-Methods', 'GET, HEAD, OPTIONS');
    resHeaders.set('Access-Control-Expose-Headers', 'Content-Length, Content-Range, Content-Disposition, Accept-Ranges, X-File-Size, X-File-Name');
    resHeaders.set('Cache-Control', 'no-cache, no-store, must-revalidate, max-age=0');
    resHeaders.set('Pragma', 'no-cache');
    resHeaders.set('Expires', '0');

    if (meta.size) {
      resHeaders.set('Content-Length', String(meta.size));
      resHeaders.set('X-File-Size', String(meta.size));
    }
    if (meta.name) {
      resHeaders.set('X-File-Name', encodeURIComponent(meta.name));
    }

    return new NextResponse(null, {
      status: 200,
      headers: resHeaders,
    });
  } catch (error: any) {
    return new NextResponse(null, { status: 500 });
  }
}

export async function GET(req: NextRequest) {
  try {
    const fileId = req.nextUrl.searchParams.get('id');
    const download = req.nextUrl.searchParams.get('download') === '1';

    if (!fileId) {
      return NextResponse.json({ error: 'معرف الملف مطلوب (id)' }, { status: 400 });
    }

    const rangeHeader = req.headers.get('range');
    const { meta, upstreamRes } = await getDriveFileStreamResponse(fileId, rangeHeader);

    const fileName = meta.name || 'file';
    const ext = fileName.includes('.') ? fileName.split('.').pop()?.toLowerCase() || '' : '';
    let contentType = meta.mimeType || upstreamRes.headers.get('content-type') || 'application/octet-stream';
    if (contentType === 'application/octet-stream' && ext && EXT_MIME_MAP[ext]) {
      contentType = EXT_MIME_MAP[ext];
    }

    const resHeaders = new Headers();
    resHeaders.set('Content-Type', contentType);
    const encodedName = encodeURIComponent(fileName);
    const safeAsciiName = fileName.replace(/[^\x20-\x7E]/g, '_') || 'file';
    resHeaders.set(
      'Content-Disposition',
      `${download ? 'attachment' : 'inline'}; filename="${safeAsciiName}"; filename*=UTF-8''${encodedName}`
    );
    resHeaders.set('Accept-Ranges', 'bytes');
    resHeaders.set('Access-Control-Allow-Origin', '*');
    resHeaders.set('Access-Control-Allow-Methods', 'GET, HEAD, OPTIONS');
    resHeaders.set('Access-Control-Expose-Headers', 'Content-Length, Content-Range, Content-Disposition, Accept-Ranges, X-File-Size, X-File-Name');
    resHeaders.set('Cache-Control', 'no-cache, no-store, must-revalidate, max-age=0');
    resHeaders.set('Pragma', 'no-cache');
    resHeaders.set('Expires', '0');

    const contentLength = upstreamRes.headers.get('content-length');
    if (contentLength) {
      resHeaders.set('Content-Length', contentLength);
    } else if (!rangeHeader && meta.size) {
      resHeaders.set('Content-Length', String(meta.size));
    }
    if (meta.size) {
      resHeaders.set('X-File-Size', String(meta.size));
    }
    if (meta.name) {
      resHeaders.set('X-File-Name', encodeURIComponent(meta.name));
    }
    const contentRange = upstreamRes.headers.get('content-range');
    if (contentRange) {
      resHeaders.set('Content-Range', contentRange);
    }

    return new NextResponse(upstreamRes.body, {
      status: upstreamRes.status,
      headers: resHeaders,
    });
  } catch (error: any) {
    console.error('[Stream API Error]:', error);
    return NextResponse.json(
      { error: error?.message || 'فشل تحميل أو معاينة الملف من السحابة' },
      { status: 500 }
    );
  }
}
