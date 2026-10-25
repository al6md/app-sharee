import { NextResponse } from 'next/server';
import { ListObjectsV2Command } from '@aws-sdk/client-s3';
import { r2Client, isR2Configured, R2_BUCKET } from '@/lib/r2';

export async function GET() {
  if (!isR2Configured) {
    return NextResponse.json({
      configured: false,
      message: 'Cloudflare R2 غير مهيأ بعد. يرجى إضافة متغيرات R2 في ملف .env',
      files: []
    });
  }

  try {
    const command = new ListObjectsV2Command({
      Bucket: R2_BUCKET,
      Prefix: 'files/',
    });

    const response = await r2Client.send(command);
    const files = (response.Contents || [])
      .filter((item) => item.Key && item.Key !== 'files/')
      .map((item) => ({
        name: item.Key?.replace('files/', '') || '',
        size: item.Size || 0,
        lastModified: item.LastModified?.toISOString() || '',
        storageEngine: 'Cloudflare R2 (10GB Free)',
      }));

    return NextResponse.json({
      configured: true,
      bucket: R2_BUCKET,
      files,
    });
  } catch (error: any) {
    return NextResponse.json(
      { configured: false, error: error.message, files: [] },
      { status: 500 }
    );
  }
}
