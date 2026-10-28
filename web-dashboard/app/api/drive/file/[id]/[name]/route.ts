import { NextRequest } from 'next/server';
import { GET as streamGET, HEAD as streamHEAD, OPTIONS as streamOPTIONS } from '../../../stream/route';

export const dynamic = 'force-dynamic';
export const maxDuration = 60;

/**
 * مسار بث بصيغة /api/drive/file/<id>/<اسم الملف.docx>
 * برامج Microsoft Office (ms-word / ms-excel / ms-access ...) تحدد نوع المستند من امتداد الملف في المسار نفسه،
 * لذلك نوفر رابطاً ينتهي باسم الملف الحقيقي، ويعيد توجيه الطلب لمحرك البث المشترك.
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
  return streamOPTIONS();
}
