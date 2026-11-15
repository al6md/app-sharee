import { NextRequest, NextResponse } from 'next/server';

export const dynamic = 'force-dynamic';

export async function POST(_req: NextRequest) {
  return NextResponse.json({
    url: '/api/drive/files?action=INIT_UPLOAD',
    directEndpoint: '/api/drive/files',
    storageMode: 'local-disk',
  });
}
