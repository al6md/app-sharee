import { NextRequest, NextResponse } from 'next/server';

export const config = {
  matcher: ['/api/drive/file/:path*'],
};

export function middleware(req: NextRequest) {
  const method = req.method.toUpperCase();

  // اعتراض ومعالجة طلبات WebDAV الخاصة بـ Microsoft Office (PROPFIND, LOCK, UNLOCK)
  if (method === 'PROPFIND') {
    const pathname = req.nextUrl.pathname;
    const parts = pathname.split('/').filter(Boolean);
    const fileName = parts.length > 0 ? decodeURIComponent(parts[parts.length - 1]) : 'file';

    const xml = `<?xml version="1.0" encoding="utf-8" ?>
<D:multistatus xmlns:D="DAV:">
  <D:response>
    <D:href>${pathname}</D:href>
    <D:propstat>
      <D:prop>
        <D:displayname>${fileName}</D:displayname>
        <D:resourcetype/>
        <D:supportedlock>
          <D:lockentry>
            <D:lockscope><D:exclusive/></D:lockscope>
            <D:locktype><D:write/></D:locktype>
          </D:lockentry>
        </D:supportedlock>
        <D:lockdiscovery/>
      </D:prop>
      <D:status>HTTP/1.1 200 OK</D:status>
    </D:propstat>
  </D:response>
</D:multistatus>`;

    const headers = new Headers();
    headers.set('Content-Type', 'application/xml; charset=utf-8');
    headers.set('DAV', '1, 2');
    headers.set('MS-Author-Via', 'DAV');
    headers.set('Access-Control-Allow-Origin', '*');
    headers.set('Access-Control-Allow-Methods', 'GET, HEAD, POST, OPTIONS, PUT, PROPFIND, LOCK, UNLOCK');
    headers.set('Access-Control-Allow-Headers', '*');
    headers.set('Access-Control-Expose-Headers', 'DAV, MS-Author-Via, Lock-Token');

    return new NextResponse(xml, { status: 207, headers });
  }

  if (method === 'LOCK') {
    const pathname = req.nextUrl.pathname;
    const token = Math.random().toString(36).substring(2) + Date.now().toString(36);

    const xml = `<?xml version="1.0" encoding="utf-8" ?>
<D:prop xmlns:D="DAV:">
  <D:lockdiscovery>
    <D:activelock>
      <D:locktype><D:write/></D:locktype>
      <D:lockscope><D:exclusive/></D:lockscope>
      <D:depth>0</D:depth>
      <D:owner><D:href>ShareCOC-OfficeUser</D:href></D:owner>
      <D:timeout>Second-3600</D:timeout>
      <D:locktoken>
        <D:href>opaquelocktoken:${token}</D:href>
      </D:locktoken>
      <D:lockroot>
        <D:href>${pathname}</D:href>
      </D:lockroot>
    </D:activelock>
  </D:lockdiscovery>
</D:prop>`;

    const headers = new Headers();
    headers.set('Content-Type', 'application/xml; charset=utf-8');
    headers.set('Lock-Token', `<opaquelocktoken:${token}>`);
    headers.set('DAV', '1, 2');
    headers.set('MS-Author-Via', 'DAV');
    headers.set('Access-Control-Allow-Origin', '*');
    headers.set('Access-Control-Allow-Methods', 'GET, HEAD, POST, OPTIONS, PUT, PROPFIND, LOCK, UNLOCK');
    headers.set('Access-Control-Allow-Headers', '*');
    headers.set('Access-Control-Expose-Headers', 'Lock-Token, DAV, MS-Author-Via');

    return new NextResponse(xml, { status: 200, headers });
  }

  if (method === 'UNLOCK') {
    const headers = new Headers();
    headers.set('DAV', '1, 2');
    headers.set('MS-Author-Via', 'DAV');
    headers.set('Access-Control-Allow-Origin', '*');
    headers.set('Access-Control-Allow-Methods', 'GET, HEAD, POST, OPTIONS, PUT, PROPFIND, LOCK, UNLOCK');
    headers.set('Access-Control-Allow-Headers', '*');
    return new NextResponse(null, { status: 204, headers });
  }

  return NextResponse.next();
}
