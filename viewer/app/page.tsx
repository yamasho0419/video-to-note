import { readRows } from "@/lib/table";
import Table from "@/components/Table";

export const dynamic = "force-dynamic";

export default async function Page() {
  const rows = await readRows();
  return <Table initialRows={rows} />;
}
