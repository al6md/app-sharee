import { NextRequest, NextResponse } from 'next/server';
import { drive } from '@/lib/googleDrive';

export const dynamic = 'force-dynamic';

const MIME_TYPES: Record<string, string> = {
  '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
  '.doc': 'application/msword',
  '.dotx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.template',
  '.xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  '.xls': 'application/vnd.ms-excel',
  '.xltx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.template',
  '.pptx': 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
  '.ppt': 'application/vnd.ms-powerpoint',
  '.pdf': 'application/pdf',
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.jpeg': 'image/jpeg',
  '.webp': 'image/webp',
  '.gif': 'image/gif',
  '.svg': 'image/svg+xml',
  '.accdb': 'application/msaccess',
  '.mdb': 'application/msaccess',
  '.txt': 'text/plain; charset=utf-8',
  '.csv': 'text/csv; charset=utf-8',
  '.zip': 'application/zip',
  '.rar': 'application/x-rar-compressed',
  '.7z': 'application/x-7z-compressed',
};

export async function GET(req: NextRequest) {
  try {
    const { searchParams } = new URL(req.url);
    const fileId = searchParams.get('path') || searchParams.get('id');
    const rawName = searchParams.get('name') || 'document';

    if (!fileId) {
      return NextResponse.json({ error: 'fileId parameter is required' }, { status: 400 });
    }

    const res = await drive.files.get(
      { fileId, alt: 'media' },
      { responseType: 'stream' }
    );

    const ext = rawName.includes('.') ? '.' + rawName.split('.').pop()?.toLowerCase() : '';
    const contentType = MIME_TYPES[ext || ''] || 'application/octet-stream';
    const encodedFilename = encodeURIComponent(rawName);

    const headers = new Headers();
    headers.set('Content-Type', contentType);
    headers.set('Content-Disposition', `attachment; filename*=UTF-8''${encodedFilename}`);

    return new NextResponse(res.data as any, { headers });
  } catch (error: any) {
    return NextResponse.json({ error: error.message }, { status: 500 });
  }
}
