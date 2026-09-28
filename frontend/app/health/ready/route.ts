export const dynamic = 'force-dynamic';

function backendBase() {
  return (process.env.BACKEND_URL || 'http://127.0.0.1:8000').replace(/\/$/, '');
}

export async function GET() {
  const rid = crypto.randomUUID();
  try {
    const response = await fetch(backendBase() + '/health/ready', { cache: 'no-store' });
    if (!response.ok) throw new Error('backend not ready');
    return Response.json({ status: 'ready', backend: 'ready' });
  } catch {
    return Response.json(
      {
        error: {
          code: 'unavailable',
          message: 'CareCredits API is unavailable.',
          request_id: rid,
        },
      },
      { status: 503, headers: { 'X-Request-Id': rid } },
    );
  }
}
