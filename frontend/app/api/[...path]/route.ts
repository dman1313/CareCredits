import { NextRequest, NextResponse } from 'next/server';

export const dynamic = 'force-dynamic';

function unmatched(request: NextRequest) {
  const rid = request.headers.get('x-request-id') || crypto.randomUUID();
  return NextResponse.json(
    {
      error: {
        code: 'not_found',
        message: 'Not found.',
        request_id: rid,
      },
    },
    { status: 404, headers: { 'X-Request-Id': rid } },
  );
}

export async function GET(request: NextRequest) {
  return unmatched(request);
}
export async function POST(request: NextRequest) {
  return unmatched(request);
}
export async function PUT(request: NextRequest) {
  return unmatched(request);
}
export async function PATCH(request: NextRequest) {
  return unmatched(request);
}
export async function DELETE(request: NextRequest) {
  return unmatched(request);
}
