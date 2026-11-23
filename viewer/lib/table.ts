import fs from "node:fs/promises";
import path from "node:path";

// 管理表の場所。TABLE_PATH で変えられる(既定は sample チャンネルの表)
export const MD_PATH = path.resolve(process.cwd(), "..", process.env.TABLE_PATH ?? "channels/sample/table.md");
const BACKUP_DIR = path.resolve(process.cwd(), ".backup");

export const CHECK_COLUMNS = ["下書き", "予約投稿完了"] as const;
export type CheckColumn = (typeof CHECK_COLUMNS)[number];

export type Row = {
  no: number;
  youtubeUrl: string;
  title: string;
  noteTitle: string;
  scheduledAt: string;
  noteUrl: string;
  draft: boolean;
  scheduled: boolean;
};

const splitCells = (line: string) => line.trim().replace(/^\||\|$/g, "").split("|").map((c) => c.trim());

export async function readRows(): Promise<Row[]> {
  const text = await fs.readFile(MD_PATH, "utf-8");
  const lines = text.split("\n").filter((l) => l.startsWith("|"));
  const header = splitCells(lines[0]);
  const idx = (name: string) => header.indexOf(name);
  const col = {
    no: idx("#"), url: idx("URL"), title: idx("元の動画の名前"), noteTitle: idx("note記事の名前"), at: idx("投稿予定日時"),
    note: idx("noteのURL"), draft: idx("下書き"), sched: idx("予約投稿完了"),
  };
  return lines.slice(2).map((l) => {
    const c = splitCells(l);
    return {
      no: Number(c[col.no]), youtubeUrl: c[col.url], title: c[col.title], noteTitle: c[col.noteTitle] ?? "",
      scheduledAt: c[col.at] ?? "", noteUrl: c[col.note] ?? "",
      draft: c[col.draft] === "☑", scheduled: c[col.sched] === "☑",
    };
  });
}

/** 該当番号行のチェック列だけを書き換える。他の行・セルは1文字も触らない。 */
export async function setCheck(no: number, column: CheckColumn, value: boolean): Promise<void> {
  const text = await fs.readFile(MD_PATH, "utf-8");
  const lines = text.split("\n");
  const header = splitCells(lines.find((l) => l.startsWith("|"))!);
  const ci = header.indexOf(column);
  if (ci < 0) throw new Error(`列が見つかりません: ${column}`);

  const li = lines.findIndex((l) => new RegExp(`^\\|\\s*${no}\\s*\\|`).test(l));
  if (li < 0) throw new Error(`番号が見つかりません: ${no}`);

  const cells = lines[li].split("|"); // 先頭と末尾は空文字
  if (cells.length - 2 !== header.length) throw new Error(`列数が不一致のため書き換えを中止: ${no}`);
  cells[ci + 1] = value ? " ☑ " : " ☐ ";
  lines[li] = cells.join("|");

  await fs.mkdir(BACKUP_DIR, { recursive: true });
  await fs.writeFile(path.join(BACKUP_DIR, "channel_url.md.bak"), text, "utf-8");
  const tmp = `${MD_PATH}.tmp`;
  await fs.writeFile(tmp, lines.join("\n"), "utf-8");
  await fs.rename(tmp, MD_PATH);
}
