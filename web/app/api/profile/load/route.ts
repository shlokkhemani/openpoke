import { NextResponse } from 'next/server';

export const dynamic = 'force-dynamic';
export const revalidate = 0;

const resolveServerBase = () =>
  process.env['PY_SERVER_URL'] || process.env['NEXT_PUBLIC_PY_SERVER_URL'] || 'http://localhost:8001';

export async function GET() {
  try {
    const serverBase = resolveServerBase();
    const response = await fetch(`${serverBase}/api/v1/profile/load`, {
      method: 'GET',
      headers: {
        'Content-Type': 'application/json',
      },
      cache: 'no-store',
    });

    const data = await response.json();

    if (!response.ok) {
      return NextResponse.json(
        { ok: false, error: data.detail || 'Failed to load profile' },
        { status: response.status }
      );
    }

    return NextResponse.json(data);
  } catch (error: unknown) {
    const message = error instanceof Error ? error.message : 'Failed to load profile';
    return NextResponse.json(
      { ok: false, error: message },
      { status: 500 }
    );
  }
}
