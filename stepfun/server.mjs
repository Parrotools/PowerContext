import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { seekdb } from "@oceanbase/seekdb-node";
import {
  FulltextIndexConfig,
  Schema,
  SeekdbClient,
  VectorIndexConfig,
} from "seekdb";

const ROOT = path.dirname(fileURLToPath(import.meta.url));
const PUBLIC_DIR = path.join(ROOT, "public");
const DATA_DIR = path.join(ROOT, "data");
const DB_PATH = path.join(DATA_DIR, "seekdb");
const SESSION_PATH = path.join(DATA_DIR, "session.json");
const RESULTS_DIR = path.join(ROOT, "results");
const PORT = Number(process.env.PORT || 8787);
const DIM = 384;
const COLLECTION = "stepfun_notes";
const DEFAULT_LIBRARY = "demo";
const MAX_BODY = 8 * 1024 * 1024;

const LIBRARY_NAME = /^[a-z0-9][a-z0-9-]{0,31}$/;
const DOC_ID = /^[A-Za-z0-9_-]{1,64}$/;

fs.mkdirSync(DATA_DIR, { recursive: true });
fs.mkdirSync(RESULTS_DIR, { recursive: true });

let client;
let runtime;
let notes;

async function startDatabase() {
  const parameters = { memory_budget: "1G" };
  if (process.platform === "win32") parameters.mysql_port_mode = "random";
  runtime = await seekdb.open(DB_PATH, { parameters });
  const endpoint = runtime.connectionOptions();
  if (endpoint.transport !== "tcp") {
    throw new Error(`seekdb-js 需要 TCP 连接，当前传输是 ${endpoint.transport}`);
  }
  client = new SeekdbClient({
    host: endpoint.host,
    port: endpoint.port,
    user: endpoint.user,
    password: "",
    database: "test",
  });
}

async function stopDatabase() {
  try {
    if (client) await client.close();
  } finally {
    runtime?.close();
  }
}

function readSession() {
  try {
    const parsed = JSON.parse(fs.readFileSync(SESSION_PATH, "utf8"));
    if (LIBRARY_NAME.test(parsed.library)) return parsed.library;
  } catch {
    // A missing session file means the demo library is active.
  }
  return DEFAULT_LIBRARY;
}

function writeSession(library) {
  fs.writeFileSync(SESSION_PATH, JSON.stringify({ library }, null, 2));
}

function assertVector(value) {
  if (!Array.isArray(value) || value.length !== DIM) {
    throw new Error("向量必须是浏览器算好的 384 维数组");
  }
  for (const item of value) {
    if (typeof item !== "number" || !Number.isFinite(item)) {
      throw new Error("向量里有非法数字");
    }
  }
}

function flatten(result) {
  const ids = result.ids?.[0] ?? [];
  const documents = result.documents?.[0] ?? [];
  const metadatas = result.metadatas?.[0] ?? [];
  const distances = result.distances?.[0] ?? [];
  return ids.map((id, index) => ({
    id,
    text: documents[index] ?? "",
    metadata: metadatas[index] ?? {},
    score: distances[index] ?? null,
  }));
}

async function openCollection() {
  if (notes) return notes;
  const schema = new Schema({
    vectorIndex: new VectorIndexConfig({
      hnsw: {
        dimension: DIM,
        distance: "cosine",
        type: "hnsw",
        lib: "vsag",
      },
      embeddingFunction: null,
    }),
    fulltextIndex: new FulltextIndexConfig("ngram", { ngram_token_size: 2 }),
  });
  if (await client.hasCollection(COLLECTION)) {
    notes = await client.getCollection({
      name: COLLECTION,
      embeddingFunction: null,
    });
    return notes;
  }
  notes = await client.createCollection({
    name: COLLECTION,
    schema,
    embeddingFunction: null,
  });
  return notes;
}

async function librariesFromRows() {
  const collection = await openCollection();
  const rows = await collection.get({
    include: ["metadatas"],
    limit: 1000,
  });
  const names = new Set([readSession()]);
  for (const meta of rows.metadatas ?? []) {
    const name = meta?.library;
    if (typeof name === "string" && LIBRARY_NAME.test(name)) names.add(name);
  }
  return [...names];
}

async function statePayload() {
  const collection = await openCollection();
  return {
    library: readSession(),
    libraries: await librariesFromRows(),
    count: await collection.count(),
    engine: "seekdb hybridSearch -> DBMS_HYBRID_SEARCH.SEARCH",
  };
}

async function addDocuments(library, docs) {
  if (!LIBRARY_NAME.test(library)) throw new Error("知识库名称只能使用小写字母、数字和连字符");
  if (!Array.isArray(docs) || docs.length < 1 || docs.length > 16) {
    throw new Error("每次写入 1 到 16 条");
  }
  const collection = await openCollection();
  const ids = [];
  const documents = [];
  const embeddings = [];
  const metadatas = [];
  for (const doc of docs) {
    if (!DOC_ID.test(doc.id)) throw new Error("文档 id 不合法");
    if (typeof doc.text !== "string" || doc.text.length < 1 || doc.text.length > 4000) {
      throw new Error("正文长度需要在 1 到 4000 字");
    }
    assertVector(doc.embedding);
    ids.push(doc.id);
    documents.push(doc.text);
    embeddings.push(doc.embedding);
    metadatas.push({
      library,
      title: String(doc.title || doc.id).slice(0, 80),
    });
  }
  const writeStarted = Date.now();
  await collection.upsert({ ids, documents, embeddings, metadatas });
  const writeMs = Date.now() - writeStarted;
  const refreshStarted = Date.now();
  let refreshMs = 0;
  let refresh = "called";
  try {
    await collection.refresh_index();
    refreshMs = Date.now() - refreshStarted;
  } catch (error) {
    refresh = `skipped: ${error.message}`;
    refreshMs = Date.now() - refreshStarted;
  }
  const verifyStarted = Date.now();
  const probe = docs[docs.length - 1];
  const found = await collection.hybridSearch({
    query: {
      where: { library },
      whereDocument: { $contains: probe.text.slice(0, 48) },
    },
    knn: { queryEmbeddings: [probe.embedding], nResults: 5 },
    nResults: 5,
    include: ["documents", "metadatas", "distances"],
  });
  const searchable = flatten(found).some((row) => row.id === probe.id);
  return {
    added: docs.length,
    writeMs,
    refreshMs,
    refresh,
    verifyMs: Date.now() - verifyStarted,
    searchable,
  };
}

async function searchDocuments(library, text, embedding, limit) {
  if (!LIBRARY_NAME.test(library)) throw new Error("知识库名称不合法");
  if (typeof text !== "string" || text.trim().length < 1 || text.length > 200) {
    throw new Error("查询需要 1 到 200 字");
  }
  assertVector(embedding);
  const n = Math.min(10, Math.max(1, Number(limit) || 5));
  const collection = await openCollection();
  const started = Date.now();
  const result = await collection.hybridSearch({
    query: {
      where: { library },
      whereDocument: { $contains: text.trim() },
    },
    knn: { queryEmbeddings: [embedding], nResults: n },
    rank: { rrf: { rankWindowSize: 20, rankConstant: 60 } },
    nResults: n,
    include: ["documents", "metadatas", "distances"],
  });
  return {
    searchMs: Date.now() - started,
    engine: "seekdb hybridSearch -> DBMS_HYBRID_SEARCH.SEARCH",
    results: flatten(result),
  };
}

async function resetLibrary(library) {
  if (!LIBRARY_NAME.test(library)) throw new Error("知识库名称不合法");
  const collection = await openCollection();
  await collection.delete({ where: { library } });
  return { library, count: await collection.count() };
}

function sendJson(response, status, body) {
  response.writeHead(status, { "content-type": "application/json; charset=utf-8" });
  response.end(JSON.stringify(body));
}

function readBody(request) {
  return new Promise((resolve, reject) => {
    const chunks = [];
    let size = 0;
    request.on("data", (chunk) => {
      size += chunk.length;
      if (size > MAX_BODY) {
        reject(new Error("请求体过大"));
        request.destroy();
        return;
      }
      chunks.push(chunk);
    });
    request.on("end", () => {
      if (chunks.length === 0) {
        resolve({});
        return;
      }
      try {
        resolve(JSON.parse(Buffer.concat(chunks).toString("utf8")));
      } catch {
        reject(new Error("请求体不是 JSON"));
      }
    });
    request.on("error", reject);
  });
}

function contentType(file) {
  if (file.endsWith(".html")) return "text/html; charset=utf-8";
  if (file.endsWith(".js")) return "text/javascript; charset=utf-8";
  if (file.endsWith(".css")) return "text/css; charset=utf-8";
  if (file.endsWith(".json")) return "application/json; charset=utf-8";
  if (file.endsWith(".wasm")) return "application/wasm";
  return "application/octet-stream";
}

function safePublicFile(urlPath) {
  const relative = decodeURIComponent(urlPath.split("?")[0]);
  const file = path.normalize(path.join(PUBLIC_DIR, relative));
  if (!file.startsWith(PUBLIC_DIR)) return null;
  return file;
}

async function handleApi(request, response, url) {
  try {
    if (request.method === "GET" && url.pathname === "/api/state") {
      sendJson(response, 200, await statePayload());
      return;
    }
    if (request.method === "POST" && url.pathname === "/api/library") {
      const body = await readBody(request);
      if (!LIBRARY_NAME.test(body.name)) throw new Error("知识库名称只能使用小写字母、数字和连字符");
      writeSession(body.name);
      sendJson(response, 200, await statePayload());
      return;
    }
    if (request.method === "POST" && url.pathname === "/api/documents") {
      const body = await readBody(request);
      sendJson(response, 200, await addDocuments(body.library, body.docs));
      return;
    }
    if (request.method === "POST" && url.pathname === "/api/search") {
      const body = await readBody(request);
      sendJson(response, 200, await searchDocuments(body.library, body.text, body.embedding, body.limit));
      return;
    }
    if (request.method === "POST" && url.pathname === "/api/reset") {
      const body = await readBody(request);
      sendJson(response, 200, await resetLibrary(body.library));
      return;
    }
    if (request.method === "POST" && url.pathname === "/api/report") {
      const body = await readBody(request);
      const file = path.join(RESULTS_DIR, "latest.json");
      fs.writeFileSync(file, JSON.stringify(body, null, 2));
      sendJson(response, 200, { file: "results/latest.json" });
      return;
    }
    sendJson(response, 404, { error: "没有这个接口" });
  } catch (error) {
    sendJson(response, 400, { error: error.message });
  }
}

function serveStatic(response, urlPath) {
  const requested = urlPath === "/" ? "/index.html" : urlPath;
  const file = safePublicFile(requested);
  if (!file || !fs.existsSync(file) || !fs.statSync(file).isFile()) {
    response.writeHead(404, { "content-type": "text/plain; charset=utf-8" });
    response.end("not found");
    return;
  }
  response.writeHead(200, { "content-type": contentType(file) });
  fs.createReadStream(file).pipe(response);
}

function unitVector(index) {
  const vector = new Array(DIM).fill(0);
  vector[index] = 1;
  return vector;
}

async function selfCheck() {
  const library = "selfcheck";
  await resetLibrary(library);
  const docs = [
    {
      id: "keyword-doc",
      title: "关键词",
      text: "这条记录只包含记号 VINEGAR8841，用来检查全文召回。",
      embedding: unitVector(0),
    },
    {
      id: "vector-doc",
      title: "向量",
      text: "这条记录没有那个记号，用来检查向量召回。",
      embedding: unitVector(1),
    },
  ];
  const written = await addDocuments(library, docs);
  if (!written.searchable) throw new Error("刷新索引后，新写入的文档没有被混合检索命中");
  const byKeyword = await searchDocuments(library, "VINEGAR8841", unitVector(1), 5);
  const byVector = await searchDocuments(library, "ZZZNOMATCH999", unitVector(1), 5);
  const keywordIds = byKeyword.results.map((row) => row.id);
  const vectorIds = byVector.results.map((row) => row.id);
  if (!keywordIds.includes("keyword-doc")) {
    throw new Error(`全文记号没有出现在 seekdb 混合检索结果里: ${keywordIds.join(",")}`);
  }
  if (!vectorIds.includes("vector-doc")) {
    throw new Error(`向量近邻没有出现在 seekdb 混合检索结果里: ${vectorIds.join(",")}`);
  }
  await resetLibrary(library);
  console.log(JSON.stringify({
    ok: true,
    refresh: written.refresh,
    refreshMs: written.refreshMs,
    keywordIds,
    vectorIds,
  }));
}

async function main() {
  await startDatabase();
  await openCollection();
  if (process.argv.includes("--self-check")) {
    try {
      await selfCheck();
      await stopDatabase();
      process.exit(0);
    } catch (error) {
      console.error(error);
      try { await stopDatabase(); } catch { /* already closing */ }
      process.exit(1);
    }
  }
  const server = (await import("node:http")).createServer((request, response) => {
    const url = new URL(request.url, `http://127.0.0.1:${PORT}`);
    if (url.pathname.startsWith("/api/")) {
      handleApi(request, response, url);
      return;
    }
    serveStatic(response, url.pathname);
  });
  server.listen(PORT, "127.0.0.1", () => {
    console.log(`stepfun kb http://127.0.0.1:${PORT}`);
  });
  const shutdown = async () => {
    server.close();
    try { await stopDatabase(); } catch { /* already closed */ }
    process.exit(0);
  };
  process.on("SIGINT", shutdown);
  process.on("SIGTERM", shutdown);
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
