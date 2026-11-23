"use client";

import { useMemo, useState } from "react";
import type { Row } from "@/lib/table";

type Filter = "all" | "no-draft" | "draft-only" | "scheduled";
type Column = "下書き" | "予約投稿完了";

const FILTERS: { key: Filter; label: string }[] = [
  { key: "all", label: "すべて" },
  { key: "no-draft", label: "未下書き" },
  { key: "draft-only", label: "下書きのみ(未予約)" },
  { key: "scheduled", label: "予約済み" },
];

export default function Table({ initialRows }: { initialRows: Row[] }) {
  const [rows, setRows] = useState(initialRows);
  const [filter, setFilter] = useState<Filter>("all");
  const [query, setQuery] = useState("");
  const [error, setError] = useState("");

  const total = rows.length;
  const draftCount = rows.filter((r) => r.draft).length;
  const schedCount = rows.filter((r) => r.scheduled).length;

  const visible = useMemo(() => {
    const q = query.trim();
    return rows.filter((r) => {
      if (filter === "no-draft" && r.draft) return false;
      if (filter === "draft-only" && !(r.draft && !r.scheduled)) return false;
      if (filter === "scheduled" && !r.scheduled) return false;
      return !q || r.title.includes(q) || String(r.no) === q;
    });
  }, [rows, filter, query]);

  async function toggle(row: Row, column: Column) {
    const key = column === "下書き" ? "draft" : "scheduled";
    const value = !row[key];
    setError("");
    setRows((prev) => prev.map((r) => (r.no === row.no ? { ...r, [key]: value } : r)));
    const res = await fetch("/api/toggle", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ no: row.no, column, value }),
    });
    if (!res.ok) {
      setRows((prev) => prev.map((r) => (r.no === row.no ? { ...r, [key]: !value } : r)));
      setError(`${row.no}番の保存に失敗しました: ${(await res.json()).error}`);
    }
  }

  return (
    <main>
      <header>
        <h1>note 投稿管理</h1>
        <div className="stats">
          <span>下書き <b>{draftCount}</b> / {total}</span>
          <span>予約投稿完了 <b>{schedCount}</b> / {total}</span>
        </div>
      </header>

      <div className="controls">
        {FILTERS.map((f) => (
          <button key={f.key} className={filter === f.key ? "on" : ""} onClick={() => setFilter(f.key)}>
            {f.label}
          </button>
        ))}
        <input placeholder="タイトル・番号で検索" value={query} onChange={(e) => setQuery(e.target.value)} />
        <span className="count">{visible.length}件</span>
      </div>
      {error && <p className="error">{error}</p>}

      <table>
        <thead>
          <tr>
            <th>#</th><th>タイトル</th><th>投稿予定日時</th><th>YouTube</th><th>note</th><th>下書き</th><th>予約投稿完了</th>
          </tr>
        </thead>
        <tbody>
          {visible.map((r) => (
            <tr key={r.no}>
              <td className="num">{r.no}</td>
              <td className="title">{r.title}</td>
              <td className="at">{r.scheduledAt}</td>
              <td><a href={r.youtubeUrl} target="_blank" rel="noreferrer">動画</a></td>
              <td>{r.noteUrl ? <a href={r.noteUrl} target="_blank" rel="noreferrer">開く</a> : ""}</td>
              <td className="chk"><input type="checkbox" checked={r.draft} onChange={() => toggle(r, "下書き")} /></td>
              <td className="chk"><input type="checkbox" checked={r.scheduled} onChange={() => toggle(r, "予約投稿完了")} /></td>
            </tr>
          ))}
        </tbody>
      </table>
    </main>
  );
}
