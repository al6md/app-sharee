import { NextRequest, NextResponse } from 'next/server';
import { GET as streamGET, HEAD as streamHEAD } from '../../../stream/route';
import { updateDriveFileContent } from '@/lib/googleDrive';

export const dynamic = 'force-dynamic';
export const maxDuration = 60;

/**
 * مسار بث بصيغة /api/drive/file/<id>/<اسم الملف.docx>
 * يدعم بروتوكول Microsoft Office (WebDAV / MS-WDV):
 * - OPTIONS: إعلام Office بدعم WebDAV الكامل (DAV: 1, 2) وإتاحة الحفظ المباشر.
 * - PUT: حفظ التعديلات المباشرة (Ctrl+S) مباشرة في Google Drive على نفس الملف دون تكرار نسخه!
 * - GET / HEAD: قراءة وبث محتوى الملف.
 */
function rewrite(req: NextRequest, id: string): NextRequest {
  const url = new URL(req.url);
  const incoming = url.searchParams;
  const target = new URL(`${url.origin}/api/drive/stream`);
  target.searchParams.set('id', decodeURIComponent(id));
  if (incoming.get('download') === '1') target.searchParams.set('download', '1');
  return new NextRequest(target, { method: req.method, headers: req.headers });
}

export async function GET(req: NextRequest, { params }: { params: { id: string; name: string } }) {
  return streamGET(rewrite(req, params.id));
}

export async function HEAD(req: NextRequest, { params }: { params: { id: string; name: string } }) {
  return streamHEAD(rewrite(req, params.id));
}

export async function OPTIONS() {
  const headers = new Headers();
  headers.set('DAV', '1, 2');
  headers.set('MS-Author-Via', 'DAV');
  headers.set('Allow', 'GET, HEAD, POST, OPTIONS, PUT, PROPFIND, LOCK, UNLOCK');
  headers.set('Access-Control-Allow-Origin', '*');
  headers.set('Access-Control-Allow-Methods', 'GET, HEAD, POST, OPTIONS, PUT, PROPFIND, LOCK, UNLOCK');
  headers.set('Access-Control-Allow-Headers', '*');
  headers.set('Access-Control-Expose-Headers', 'DAV, MS-Author-Via, Lock-Token, Content-Length, Content-Range, Content-Disposition, Accept-Ranges, X-File-Size, X-File-Name');
  headers.set('Access-Control-Max-Age', '86400');
  return new NextResponse(null, { status: 204, headers });
}

export async function PUT(req: NextRequest, { params }: { params: { id: string; name: string } }) {
  try {
    const fileId = decodeURIComponent(params.id);
    const bodyBytes = await req.arrayBuffer();
    const buffer = Buffer.from(bodyBytes);

    if (buffer.length === 0) {
      return new NextResponse(null, { status: 400 });
    }

    const contentType = req.headers.get('content-type') || 'application/octet-stream';
    await updateDriveFileContent(fileId, buffer, contentType);

    const headers = new Headers();
    headers.set('DAV', '1, 2');
    headers.set('MS-Author-Via', 'DAV');
    headers.set('Access-Control-Allow-Origin', '*');
    headers.set('Access-Control-Allow-Methods', 'GET, HEAD, POST, OPTIONS, PUT, PROPFIND, LOCK, UNLOCK');
    headers.set('Access-Control-Allow-Headers', '*');

    return new NextResponse(null, { status: 204, headers });
  } catch (error: any) {
    console.error('[WebDAV PUT Save Error]:', error);
    return NextResponse.json({ error: error?.message || 'فشل حفظ الملف في السحابة' }, { status: 500 });
  }
}
