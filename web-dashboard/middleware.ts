import { NextRequest, NextResponse } from 'next/server';

/**
 * دعم كامل لبروتوكول WebDAV المطلوب من قبل Microsoft Office (ms-excel:ofe|u|...)
 * لفتح وحفظ ملفات Excel و Word بوضع التحرير المباشر (Read/Write) وحل مشكلة Read-Only نهائياً.
 *
 * يعالج Middleware الطرق الخاصة بـ WebDAV:
 * - OPTIONS: يعلن دعم DAV 1, 2 و MS-Author-Via: DAV وقائمة الطرق المتاحة.
 * - PROPFIND: يرد بخصائص الملف (207 Multi-Status) كـ XML سليم لـ Office.
 * - LOCK:     يمنح Office رمز قفل صالح (Lock Token) لإلغاء القراءة فقط وتفعيل التعديل.
 * - UNLOCK:   يحرر القفل (204 No Content).
 * - PUT:      يمر إلى route.ts ليقوم برفع وتحديث المحتوى في Google Drive مباشرة.
 */

const DAV_HEADERS: Record<string, string> = {
  DAV: '1, 2',
  'MS-Author-Via': 'DAV',
  Allow: 'GET, HEAD, POST, OPTIONS, PUT, PROPFIND, LOCK, UNLOCK',
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Methods': 'GET, HEAD, POST, OPTIONS, PUT, PROPFIND, LOCK, UNLOCK',
  'Access-Control-Allow-Headers': '*',
  'Access-Control-Expose-Headers':
    'DAV, MS-Author-Via, Lock-Token, Content-Length, Content-Range, Content-Disposition, Accept-Ranges, X-File-Size, X-File-Name, ETag',
  'Cache-Control': 'no-cache, no-store, must-revalidate',
};

const xmlEscape = (s: string) =>
  s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');

function xmlResponse(body: string, status: number, extra: Record<string, string> = {}) {
  return new NextResponse(body, {
    status,
    headers: {
      ...DAV_HEADERS,
      'Content-Type': 'application/xml; charset=utf-8',
      ...extra,
    },
  });
}

function extractLockToken(req: NextRequest): string | null {
  const raw = req.headers.get('if') || req.headers.get('lock-token') || '';
  const m = raw.match(/opaquelocktoken:[0-9a-fA-F-]+/);
  return m ? m[0] : null;
}

function handlePropfind(req: NextRequest) {
  const url = new URL(req.url);
  const name = decodeURIComponent(url.pathname.split('/').pop() || 'file');
  const ext = name.split('.').pop()?.toLowerCase() || '';
  const type =
    ext === 'xlsx'
      ? 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
      : ext === 'xls'
      ? 'application/vnd.ms-excel'
      : ext === 'docx'
      ? 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
      : ext === 'doc'
      ? 'application/msword'
      : 'application/octet-stream';

  const body =
    `<?xml version="1.0" encoding="utf-8"?>\n` +
    `<D:multistatus xmlns:D="DAV:">\n` +
    `  <D:response>\n` +
    `    <D:href>${xmlEscape(url.pathname)}</D:href>\n` +
    `    <D:propstat>\n` +
    `      <D:prop>\n` +
    `        <D:displayname>${xmlEscape(name)}</D:displayname>\n` +
    `        <D:resourcetype/>\n` +
    `        <D:getcontenttype>${xmlEscape(type)}</D:getcontenttype>\n` +
    `        <D:supportedlock>\n` +
    `          <D:lockentry>\n` +
    `            <D:lockscope><D:exclusive/></D:lockscope>\n` +
    `            <D:locktype><D:write/></D:locktype>\n` +
    `          </D:lockentry>\n` +
    `        </D:supportedlock>\n` +
    `        <D:lockdiscovery/>\n` +
    `      </D:prop>\n` +
    `      <D:status>HTTP/1.1 200 OK</D:status>\n` +
    `    </D:propstat>\n` +
    `  </D:response>\n` +
    `</D:multistatus>`;

  return xmlResponse(body, 207);
}

function handleLock(req: NextRequest) {
  const url = new URL(req.url);
  const token = extractLockToken(req) || `opaquelocktoken:${crypto.randomUUID()}`;
  const body =
    `<?xml version="1.0" encoding="utf-8"?>\n` +
    `<D:prop xmlns:D="DAV:">\n` +
    `  <D:lockdiscovery>\n` +
    `    <D:activelock>\n` +
    `      <D:locktype><D:write/></D:locktype>\n` +
    `      <D:lockscope><D:exclusive/></D:lockscope>\n` +
    `      <D:depth>0</D:depth>\n` +
    `      <D:owner><D:href>office</D:href></D:owner>\n` +
    `      <D:timeout>Second-3600</D:timeout>\n` +
    `      <D:locktoken><D:href>${token}</D:href></D:locktoken>\n` +
    `      <D:lockroot><D:href>${xmlEscape(url.pathname)}</D:href></D:lockroot>\n` +
    `    </D:activelock>\n` +
    `  </D:lockdiscovery>\n` +
    `</D:prop>`;

  return xmlResponse(body, 200, { 'Lock-Token': `<${token}>` });
}

export function middleware(req: NextRequest) {
  const method = req.method.toUpperCase();

  switch (method) {
    case 'OPTIONS':
      return new NextResponse(null, { status: 204, headers: DAV_HEADERS });
    case 'PROPFIND':
      return handlePropfind(req);
    case 'LOCK':
      return handleLock(req);
    case 'UNLOCK':
      return new NextResponse(null, { status: 204, headers: DAV_HEADERS });
    default:
      return NextResponse.next();
  }
}

export const config = {
  matcher: ['/api/drive/file/:path*', '/api/drive/stream/:path*'],
};
