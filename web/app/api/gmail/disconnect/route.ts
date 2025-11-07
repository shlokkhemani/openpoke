export const runtime = 'nodejs';

export async function POST(req: Request) {
  let body: Record<string, unknown> = {};
  try {
    body = await req.json();
  } catch {}

  const userId = body?.userId || '';
  const connectionId = body?.connectionId || '';
  const connectionRequestId = body?.connectionRequestId || '';

  const serverBase = process.env.PY_SERVER_URL || 'http://localhost:8001';
  const url = `${serverBase.replace(/\/$/, '')}/api/v1/gmail/disconnect`;
  const payload: Record<string, unknown> = {};
  if (userId) payload.user_id = userId;
  if (connectionId) payload.connection_id = connectionId;
  if (connectionRequestId) payload.connection_request_id = connectionRequestId;

  try {
    const resp = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
      body: JSON.stringify(payload),
    });
    const data = await resp.json().catch(() => ({}));
    return new Response(JSON.stringify(data), {
      status: resp.status,
      headers: { 'Content-Type': 'application/json; charset=utf-8' },
    });
  } catch (e: unknown) {
    const message = e instanceof Error ? e.message : String(e);
    return new Response(
      JSON.stringify({ ok: false, error: 'Upstream error', detail: message }),
      { status: 502, headers: { 'Content-Type': 'application/json; charset=utf-8' } }
    );
  }
}
