export const runtime = 'nodejs';

type UIMsgPart = { type: string; text?: string };
type UIMessage = { role: string; parts?: UIMsgPart[]; content?: string };

function uiToOpenAIContent(messages: UIMessage[]): { role: string; content: string }[] {
  const out: { role: string; content: string }[] = [];
  for (const m of messages || []) {
    const role = m?.role;
    if (!role) continue;
    let content = '';
    if (Array.isArray(m.parts)) {
      content = m.parts.filter((p) => p?.type === 'text').map((p) => p.text || '').join('');
    } else if (typeof m.content === 'string') {
      content = m.content;
    }
    out.push({ role, content });
  }
  return out;
}

export async function POST(req: Request) {
  let body: unknown;
  try {
    body = await req.json();
  } catch (e) {
    console.error('[chat-proxy] invalid json', e);
    return new Response('Invalid JSON', { status: 400 });
  }

  const { messages } = (body as Record<string, unknown>) || {};
  if (!Array.isArray(messages) || messages.length === 0) {
    return new Response('Missing messages', { status: 400 });
  }

  const serverBase = process.env.PY_SERVER_URL || 'http://localhost:8001';
  const serverPath = process.env.PY_CHAT_PATH || '/api/v1/chat/send';
  const url = `${serverBase.replace(/\/$/, '')}${serverPath}`;

  const payload = {
    system: '',
    messages: uiToOpenAIContent(messages),
    stream: false,
  };

  try {
    // Set a timeout that's slightly longer than the backend's timeout (60s)
    // to allow the backend to properly handle and respond to errors
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 90000); // 90 seconds

    try {
      const upstream = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Accept: 'text/plain, */*' },
        body: JSON.stringify(payload),
        signal: controller.signal,
      });
      clearTimeout(timeoutId);

      const text = await upstream.text();
      return new Response(text, {
        status: upstream.status,
        headers: { 'Content-Type': 'text/plain; charset=utf-8' },
      });
    } finally {
      clearTimeout(timeoutId);
    }
  } catch (e: unknown) {
    console.error('[chat-proxy] upstream error', e);
    if (e instanceof Error && e.name === 'AbortError') {
      return new Response('Request timeout - the server took too long to respond', { status: 504 });
    }
    const message = e instanceof Error ? e.message : 'Upstream error';
    return new Response(message, { status: 502 });
  }
}
