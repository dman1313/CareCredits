import { NextRequest, NextResponse } from 'next/server';

export const dynamic = 'force-dynamic';

function backendBase() {
  return (process.env.BACKEND_URL || 'http://127.0.0.1:8000').replace(/\/$/, '');
}

async function proxy(request: NextRequest, path: string[]) {
  const target = `${backendBase()}/api/v1/${path.join('/')}${request.nextUrl.search}`;
  const headers = new Headers();
  request.headers.forEach((value, key) => {
    if (['host', 'connection', 'content-length'].includes(key.toLowerCase())) return;
    headers.set(key, value);
  });
  const init: RequestInit = { method: request.method, headers, redirect: 'manual' };
  if (!['GET', 'HEAD'].includes(request.method)) {
    init.body = await request.arrayBuffer();
  }
  const upstream = await fetch(target, init);
  const response = new NextResponse(upstream.body, { status: upstream.status });
  upstream.headers.forEach((value, key) => {
    if (['transfer-encoding', 'content-encoding'].includes(key.toLowerCase())) return;
    response.headers.append(key, value);
  });
  return response;
}

type RouteContext = { params: Promise<{ path: string[] }> };

export async function GET(request: NextRequest, context: RouteContext) {
  return proxy(request, (await context.params).path);
}
export async function POST(request: NextRequest, context: RouteContext) {
  return proxy(request, (await context.params).path);
}
export async function PUT(request: NextRequest, context: RouteContext) {
  return proxy(request, (await context.params).path);
}
export async function PATCH(request: NextRequest, context: RouteContext) {
  return proxy(request, (await context.params).path);
}
export async function DELETE(request: NextRequest, context: RouteContext) {
  return proxy(request, (await context.params).path);
}
