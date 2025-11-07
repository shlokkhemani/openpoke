export const runtime = 'nodejs';

export async function POST(req: Request) {
  let body: unknown;
  try {
    body = await req.json();
  } catch {
    return new Response('Invalid JSON', { status: 400 });
  }

  const { timezone } = (body as Record<string, unknown>) || {};
  if (!timezone || typeof timezone !== 'string') {
    return new Response('Missing or invalid timezone', { status: 400 });
  }

  const serverBase = process.env.PY_SERVER_URL || 'http://localhost:8001';
  const url = `${serverBase.replace(/\/$/, '')}/api/v1/meta/timezone`;

  try {
    const upstream = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ timezone }),
    });

    if (!upstream.ok) {
      const text = await upstream.text();
      return new Response(text || 'Failed to set timezone', { status: upstream.status });
    }

    const data = await upstream.json();
    return new Response(JSON.stringify(data), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    });
  } catch (e: unknown) {
    const message = e instanceof Error ? e.message : 'Server error';
    return new Response(message, { status: 502 });
  }
}
