import { NextRequest, NextResponse } from 'next/server';

export const dynamic = 'force-dynamic';
export const revalidate = 0;

const resolveServerBase = () =>
  process.env['PY_SERVER_URL'] || process.env['NEXT_PUBLIC_PY_SERVER_URL'] || 'http://localhost:8001';

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    const serverBase = resolveServerBase();

    const response = await fetch(`${serverBase}/api/v1/profile/save`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(body),
    });

    const data = await response.json();

    if (!response.ok) {
      return NextResponse.json(
        { error: data.detail || 'Failed to save profile' },
        { status: response.status }
      );
    }

    return NextResponse.json(data);
  } catch (error: unknown) {
    const message = error instanceof Error ? error.message : 'Failed to save profile';
    return NextResponse.json(
      { error: message },
      { status: 500 }
    );
  }
}
