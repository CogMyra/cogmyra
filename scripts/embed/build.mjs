// scripts/embed/build.mjs
// Build a simple RAG index from files under docs/knowledge/src/*
// Supports .md .txt .csv .tsv (treated as text). Requires: npm i openai@^4.57.0
import fs from "node:fs";
import path from "node:path";
import process from "node:process";
import OpenAI from "openai";

const ROOT = process.cwd();
const SRC_DIR = path.resolve(ROOT, "docs/knowledge/src");
const OUT_FILE = path.resolve(ROOT, "docs/knowledge/index.json");
const MODEL = "text-embedding-3-large";
const DIMS = 3072;

// ---------- helpers ----------
function errExit(msg) {
  console.error(msg);
  process.exit(1);
}

function* chunkText(text, maxLen = 1500, overlap = 200) {
  if (!text) return;
  const n = text.length;
  let i = 0;
  while (i < n) {
    const end = Math.min(i + maxLen, n);
    yield text.slice(i, end);
    if (end >= n) break;
    i = end - overlap;
    if (i < 0) i = 0;
  }
}

function readTextFile(filePath) {
  // Everything is treated as UTF-8 text. CSV/TSV are fine — they’re just text.
  return fs.readFileSync(filePath, "utf8");
}

function findFiles(dir, exts = [".md", ".txt", ".csv", ".tsv"]) {
  if (!fs.existsSync(dir)) return [];
  const items = fs.readdirSync(dir);
  return items
    .map((name) => path.join(dir, name))
    .filter((p) => {
      const st = fs.statSync(p);
      if (!st.isFile()) return false;
      const ext = path.extname(p).toLowerCase();
      return exts.includes(ext);
    })
    .sort();
}

// ---------- main ----------
async function main() {
  const key = process.env.OPENAI_API_KEY || "";
  if (!key || key.includes("YOUR_REAL") || key.startsWith("sk-...")) {
    errExit(
      "Error: OPENAI_API_KEY is not set to a real key. Export your real key then re-run:\n" +
      '  export OPENAI_API_KEY="sk-xxxxxxxxxxxxxxxxxxxxxxxx"\n' +
      "  node scripts/embed/build.mjs"
    );
  }

  const files = findFiles(SRC_DIR);
  if (files.length === 0) {
    errExit(
      `No source files found in ${SRC_DIR}\n` +
      "Put your 13 docs in that folder (md/txt/csv/tsv), then re-run."
    );
  }

  const client = new OpenAI({ apiKey: key });
  const records = [];
  let recId = 1;
  let totalChunks = 0;

  console.log(`\nEmbedding from ${SRC_DIR}`);
  console.log(`Files found: ${files.length}\n`);

  for (const filePath of files) {
    const file = path.basename(filePath);
    const text = readTextFile(filePath);
    const chunks = [...chunkText(text, 1500, 200)];
    console.log(`• ${file}: ${chunks.length} chunk(s)`);

    // embed in small batches to be polite
    for (let i = 0; i < chunks.length; i++) {
      const body = chunks[i];
      try {
        const res = await client.embeddings.create({
          model: MODEL,
          input: body,
        });
        const embedding = res.data?.[0]?.embedding;
        if (!embedding) throw new Error("No embedding returned");
        records.push({
          id: `rec_${recId++}`,
          file,
          chunkIndex: i,
          text: body,
          embedding,
        });
        totalChunks++;
      } catch (e) {
        console.error(`  ✖ Failed on ${file} [chunk ${i}]:`, e?.message || e);
        process.exitCode = 1;
        return;
      }
    }
  }

  const index = {
    created: new Date().toISOString(),
    model: MODEL,
    dims: DIMS,
    count: totalChunks,
    records,
  };

  fs.mkdirSync(path.dirname(OUT_FILE), { recursive: true });
  fs.writeFileSync(OUT_FILE, JSON.stringify(index, null, 2), "utf8");

  console.log(`\nWrote ${OUT_FILE}`);
  console.log(`  dims=${DIMS}, chunks=${totalChunks}`);
}

main().catch((e) => {
  console.error("Embedding failed:", e?.message || e);
  process.exit(1);
});
