import { NextResponse } from "next/server";

export const dynamic = "force-dynamic";

export async function GET() {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 2_000);
  try {
    const apiUrl =
      process.env.INTERNAL_API_URL ||
      process.env.NEXT_PUBLIC_API_URL ||
      "http://localhost:8000";
    const response = await fetch(`${apiUrl.replace(/\/$/, "")}/ready`, {
      cache: "no-store",
      signal: controller.signal,
    });
    return NextResponse.json(
      { status: response.ok ? "healthy" : "unavailable" },
      { status: response.ok ? 200 : 503 },
    );
  } catch {
    return NextResponse.json({ status: "unavailable" }, { status: 503 });
  } finally {
    clearTimeout(timeout);
  }
}
