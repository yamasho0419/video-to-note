import { NextResponse } from "next/server";
import { CHECK_COLUMNS, CheckColumn, setCheck } from "@/lib/table";

export async function POST(req: Request) {
  const { no, column, value } = await req.json();
  if (!Number.isInteger(no) || !CHECK_COLUMNS.includes(column) || typeof value !== "boolean") {
    return NextResponse.json({ error: "bad request" }, { status: 400 });
  }
  try {
    await setCheck(no, column as CheckColumn, value);
    return NextResponse.json({ ok: true });
  } catch (e) {
    return NextResponse.json({ error: String(e) }, { status: 500 });
  }
}
