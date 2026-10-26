import { NextRequest, NextResponse } from 'next/server';

export const dynamic = 'force-dynamic';

export async function POST(req: NextRequest) {
  // Direct Google Drive upload via /api/drive/files is now used
  return NextResponse.json({
    message: 'Google Drive direct upload active',
    directEndpoint: '/api/drive/files'
  });
}
