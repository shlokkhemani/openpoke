const serverBase = process.env.PY_SERVER_URL || 'http://localhost:8001';
const historyPath = `${serverBase.replace(/\/$/, '')}/api/v1/chat/history`;

async function forward(method: 'GET' | 'DELETE') {
  try {
    const res = await fetch(historyPath, {
      method,
      headers: { Accept: 'application/json' },
      cache: 'no-store',
    });

    const bodyText = await res.text();
    const headers = new Headers({ 'Content-Type': 'application/json; charset=utf-8' });
    return new Response(bodyText || '{}', { status: res.status, headers });
  } catch (error: unknown) {
    const message = error instanceof Error ? error.message : 'Failed to reach Python server';
    return new Response(JSON.stringify({ error: message }), {
      status: 502,
      headers: { 'Content-Type': 'application/json; charset=utf-8' },
    });
  }
}

export async function GET() {
  return forward('GET');
}

export async function DELETE() {
  return forward('DELETE');
}
