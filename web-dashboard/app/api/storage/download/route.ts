import { NextRequest, NextResponse } from 'next/server';
import { getDriveFileStreamResponse, inferMimeType } from '@/lib/localStorage';

export const dynamic = 'force-dynamic';

export async function GET(req: NextRequest) {
  try {
    const { searchParams } = new URL(req.url);
    const fileId = searchParams.get('path') || searchParams.get('id');
    const explicitName = searchParams.get('name');

    if (!fileId) {
      return NextResponse.json({ error: 'fileId parameter is required' }, { status: 400 });
    }

    const rangeHeader = req.headers.get('range');
    const { meta, upstreamRes } = await getDriveFileStreamResponse(fileId, rangeHeader);

    const fileName = explicitName || meta.name || 'document';
    const contentType =
      meta.mimeType && meta.mimeType !== 'application/octet-stream'
        ? meta.mimeType
        : inferMimeType(fileName);

    const encodedFilename = encodeURIComponent(fileName);
    const safeAsciiName = fileName.replace(/[^\x20-\x7E]/g, '_') || 'document';

    const headers = new Headers();
    headers.set('Content-Type', contentType);
    headers.set(
      'Content-Disposition',
      `attachment; filename="${safeAsciiName}"; filename*=UTF-8''${encodedFilename}`
    );
    headers.set('Accept-Ranges', 'bytes');

    const contentLength = upstreamRes.headers.get('content-length');
    if (contentLength) {
      headers.set('Content-Length', contentLength);
    } else if (!rangeHeader && meta.size) {
      headers.set('Content-Length', String(meta.size));
    }
    const contentRange = upstreamRes.headers.get('content-range');
    if (contentRange) {
      headers.set('Content-Range', contentRange);
    }

    return new NextResponse(upstreamRes.body, {
      status: upstreamRes.status,
      headers,
    });
  } catch (error: any) {
    const msg = String(error?.message || 'Download failed');
    const status = msg.includes('غير موجود') ? 404 : 500;
    return NextResponse.json({ error: msg }, { status });
  }
}
