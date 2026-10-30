import { env, pipeline } from "https://cdn.jsdelivr.net/npm/@huggingface/transformers@3.7.6";

const MODEL = "Xenova/all-MiniLM-L6-v2";
const DTYPE = "fp16";
const BATCH = 8;
const HOSTS = ["https://huggingface.co/", "https://hf-mirror.com/"];

const backendEl = document.querySelector("#backend");
const statusEl = document.querySelector("#status");
const libraryEl = document.querySelector("#library");
const importLog = document.querySelector("#import-log");
const searchLog = document.querySelector("#search-log");
const resultsEl = document.querySelector("#results");
const measureLog = document.querySelector("#measure-log");
const buttons = [...document.querySelectorAll("button")];

let extractor;
let device = "wasm";
let deviceReason = "";
let modelHost = HOSTS[0];
let onnxBytes = 0;

env.allowLocalModels = false;
env.useBrowserCache = true;
if (env.backends?.onnx?.wasm) env.backends.onnx.wasm.numThreads = 1;

function setBusy(busy) {
  for (const button of buttons) button.disabled = busy;
}

async function post(url, body) {
  const response = await fetch(url, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.error || "请求失败");
  return payload;
}

function currentLibrary() {
  return libraryEl.value || "demo";
}

function renderState(state) {
  const names = state.libraries.includes(state.library)
    ? state.libraries
    : [state.library, ...state.libraries];
  libraryEl.innerHTML = names.map((name) => `<option value="${name}">${name}</option>`).join("");
  libraryEl.value = state.library;
  const modelLine = onnxBytes
    ? `模型 ${MODEL} FP16，ONNX ${onnxBytes} 字节，来源 ${modelHost}。`
    : "";
  statusEl.textContent = `当前知识库 ${state.library}，seekdb 中共 ${state.count} 条。检索由 ${state.engine} 完成。${modelLine}`;
}

function showBackend() {
  const fallback = device === "wasm" ? `。${deviceReason}` : "";
  backendEl.textContent = `推理后端 ${device.toUpperCase()}，精度 FP16${fallback}`;
  backendEl.classList.toggle("wasm", device === "wasm");
}

async function chooseDevice() {
  if (!navigator.gpu) return { device: "wasm", reason: "浏览器没有 WebGPU，已改用 WASM" };
  try {
    const adapter = await navigator.gpu.requestAdapter();
    if (!adapter) return { device: "wasm", reason: "没有可用的 WebGPU 适配器，已改用 WASM" };
    return { device: "webgpu", reason: "" };
  } catch (error) {
    return { device: "wasm", reason: `WebGPU 初始化失败，已改用 WASM：${error.message}` };
  }
}

async function loadExtractor(dtype, requestedDevice, onProgress) {
  let lastError;
  for (const host of HOSTS) {
    env.remoteHost = host;
    const sizes = {};
    try {
      const started = performance.now();
      const created = await pipeline("feature-extraction", MODEL, {
        dtype,
        device: requestedDevice,
        progress_callback(progress) {
          if (progress.file && progress.total) sizes[progress.file] = progress.total;
          onProgress?.(progress);
        },
      });
      const onnx = Object.entries(sizes)
        .filter(([file]) => file.endsWith(".onnx"))
        .reduce((sum, [, total]) => sum + total, 0);
      return {
        extractor: created,
        host,
        onnxBytes: onnx,
        loadMs: performance.now() - started,
      };
    } catch (error) {
      lastError = error;
    }
  }
  throw lastError;
}

async function embed(model, texts) {
  const output = await model(texts, { pooling: "mean", normalize: true });
  return output.tolist();
}

async function embedAll(model, texts) {
  const vectors = [];
  for (let index = 0; index < texts.length; index += BATCH) {
    vectors.push(...await embed(model, texts.slice(index, index + BATCH)));
  }
  return vectors;
}

function chunksFromText(raw) {
  return raw.split(/\n\s*\n/).map((part) => part.trim()).filter(Boolean).slice(0, 16);
}

async function writeDocs(library, docs, vectors) {
  const payload = docs.map((doc, index) => ({
    id: doc.id,
    title: doc.title,
    text: doc.text,
    embedding: vectors[index],
  }));
  const reports = [];
  for (let index = 0; index < payload.length; index += BATCH) {
    reports.push(await post("/api/documents", {
      library,
      docs: payload.slice(index, index + BATCH),
    }));
  }
  return reports;
}

function median(values) {
  const sorted = [...values].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  return sorted.length % 2 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2;
}

function recallAt3(ids, relevant) {
  return ids.slice(0, 3).includes(relevant) ? 1 : 0;
}

function ndcgAt3(ids, relevant) {
  const rank = ids.slice(0, 3).indexOf(relevant);
  if (rank < 0) return 0;
  return 1 / Math.log2(rank + 2);
}

async function bootstrap() {
  const choice = await chooseDevice();
  device = choice.device;
  deviceReason = choice.reason;
  showBackend();
  statusEl.textContent = "正在下载并加载 FP16 模型。计算发生在这台电脑的浏览器里。";
  const loaded = await loadExtractor(DTYPE, device, (progress) => {
    if (progress.status === "progress" && progress.file) {
      statusEl.textContent = `正在下载 ${progress.file} ${Math.round(progress.progress || 0)}%`;
    }
  });
  extractor = loaded.extractor;
  modelHost = loaded.host;
  onnxBytes = loaded.onnxBytes;
  statusEl.textContent = `FP16 模型已加载，来源 ${modelHost}，ONNX ${onnxBytes} 字节，耗时 ${Math.round(loaded.loadMs)} 毫秒。`;
  renderState(await fetch("/api/state").then((response) => response.json()));
  setBusy(false);
}

document.querySelector("#use-library").addEventListener("click", async () => {
  renderState(await post("/api/library", { name: currentLibrary() }));
});

document.querySelector("#create-library").addEventListener("click", async () => {
  const name = document.querySelector("#new-library").value.trim();
  renderState(await post("/api/library", { name }));
});

document.querySelector("#import-text").addEventListener("click", () => importPlain());
document.querySelector("#import-sample").addEventListener("click", () => importSample());
document.querySelector("#reset-library").addEventListener("click", async () => {
  const result = await post("/api/reset", { library: currentLibrary() });
  importLog.textContent = `${result.library} 已清空。`;
  renderState(await fetch("/api/state").then((response) => response.json()));
});
document.querySelector("#search").addEventListener("click", () => runSearch());
document.querySelector("#query").addEventListener("keydown", (event) => {
  if (event.key === "Enter") runSearch();
});
document.querySelector("#measure").addEventListener("click", () => runMeasure());

async function importPlain() {
  const parts = chunksFromText(document.querySelector("#source").value);
  if (parts.length === 0) {
    importLog.textContent = "先粘贴文本。";
    return;
  }
  const docs = parts.map((text, index) => ({
    id: `note-${Date.now().toString(36)}-${index}`,
    title: text.slice(0, 16),
    text,
  }));
  await importDocs(docs);
}

async function importSample() {
  const corpus = await fetch("/corpus.json").then((response) => response.json());
  await importDocs(corpus.documents);
}

async function importDocs(docs) {
  setBusy(true);
  try {
    importLog.textContent = `正在本地向量化 ${docs.length} 条。`;
    const started = performance.now();
    const vectors = await embedAll(extractor, docs.map((doc) => doc.text));
    const embedMs = Math.round(performance.now() - started);
    const reports = await writeDocs(currentLibrary(), docs, vectors);
    const failed = reports.filter((report) => !report.searchable);
    importLog.textContent = `向量化 ${embedMs} 毫秒，写入 ${reports.length} 批。索引刷新 ${reports.map((report) => report.refreshMs).join("/")} 毫秒。${failed.length === 0 ? "刷新后新文档可以被检索到。" : "有批次在刷新后没有被检索到。"}`;
    renderState(await fetch("/api/state").then((response) => response.json()));
  } catch (error) {
    importLog.textContent = error.message;
  } finally {
    setBusy(false);
  }
}

async function runSearch() {
  const text = document.querySelector("#query").value.trim();
  if (!text) return;
  setBusy(true);
  resultsEl.innerHTML = "";
  try {
    const embedStarted = performance.now();
    const [embedding] = await embed(extractor, [text]);
    const embedMs = Math.round(performance.now() - embedStarted);
    const found = await post("/api/search", {
      library: currentLibrary(),
      text,
      embedding,
      limit: 5,
    });
    searchLog.textContent = `查询向量 ${embedMs} 毫秒，seekdb 混合检索 ${found.searchMs} 毫秒。${found.engine}`;
    resultsEl.innerHTML = found.results.map((row) => `
      <li>
        <strong>${row.metadata?.title || row.id}</strong>
        <span class="score">${row.id} · score ${row.score ?? "无"}</span>
        <p>${row.text}</p>
      </li>
    `).join("") || "<li>没有结果</li>";
  } catch (error) {
    searchLog.textContent = error.message;
  } finally {
    setBusy(false);
  }
}

async function timeEmbeddings(model, texts) {
  const runs = [];
  for (let run = 0; run < 3; run += 1) {
    const started = performance.now();
    await embedAll(model, texts);
    runs.push(performance.now() - started);
  }
  return median(runs);
}

async function timeSingle(model, texts) {
  const runs = [];
  for (let run = 0; run < 3; run += 1) {
    const started = performance.now();
    for (const text of texts) await embed(model, [text]);
    runs.push(performance.now() - started);
  }
  return median(runs);
}

async function measureConfig(corpus, label, dtype, requestedDevice) {
  measureLog.textContent += `\n${label}：加载模型`;
  const loaded = await loadExtractor(dtype, requestedDevice);
  const model = loaded.extractor;
  await embed(model, [corpus.documents[0].text]);
  const texts = corpus.documents.map((doc) => doc.text);
  const embedMs = await timeEmbeddings(model, texts);
  const vectors = await embedAll(model, texts);
  const library = label.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "").slice(0, 32);
  await post("/api/reset", { library });
  const writes = await writeDocs(library, corpus.documents, vectors);
  const queryRuns = [];
  for (let run = 0; run < 3; run += 1) {
    for (const item of corpus.queries) {
      const embedStarted = performance.now();
      const [embedding] = await embed(model, [item.text]);
      const embedQueryMs = performance.now() - embedStarted;
      const found = await post("/api/search", {
        library,
        text: item.text,
        embedding,
        limit: 5,
      });
      const ids = found.results.map((row) => row.id);
      queryRuns.push({
        embedQueryMs,
        searchMs: found.searchMs,
        e2eMs: embedQueryMs + found.searchMs,
        recall: recallAt3(ids, item.relevant),
        ndcg: ndcgAt3(ids, item.relevant),
      });
    }
  }
  const mean = (key) => queryRuns.reduce((sum, row) => sum + row[key], 0) / queryRuns.length;
  const row = {
    label,
    dtype,
    device: requestedDevice,
    host: loaded.host,
    onnxBytes: loaded.onnxBytes,
    loadMs: Math.round(loaded.loadMs),
    embedMs: Math.round(embedMs),
    embedDocsPerSec: Number((texts.length / (embedMs / 1000)).toFixed(2)),
    writeMs: writes.reduce((sum, report) => sum + report.writeMs, 0),
    refreshMs: writes.reduce((sum, report) => sum + report.refreshMs, 0),
    searchable: writes.every((report) => report.searchable),
    queryEmbedMs: Math.round(median(queryRuns.map((row) => row.embedQueryMs))),
    searchMs: Math.round(median(queryRuns.map((row) => row.searchMs))),
    e2eMs: Math.round(median(queryRuns.map((row) => row.e2eMs))),
    recallAt3: Number(mean("recall").toFixed(3)),
    ndcgAt3: Number(mean("ndcg").toFixed(3)),
  };
  if (dtype === "fp16" && requestedDevice === "wasm") {
    row.batch1Ms = Math.round(await timeSingle(model, texts));
    row.batch8Ms = Math.round(embedMs);
  }
  await model.dispose?.();
  measureLog.textContent += `\n${JSON.stringify(row)}`;
  return row;
}

async function runMeasure() {
  setBusy(true);
  measureLog.textContent = "测量开始。FP32 与 FP16 会各下载一次模型。";
  try {
    const corpus = await fetch("/corpus.json").then((response) => response.json());
    const rows = [];
    rows.push(await measureConfig(corpus, "fp32-wasm", "fp32", "wasm"));
    const gpu = await chooseDevice();
    if (gpu.device === "webgpu") {
      rows.push(await measureConfig(corpus, "fp16-webgpu", "fp16", "webgpu"));
    } else {
      rows.push({ label: "fp16-webgpu", skipped: gpu.reason });
      measureLog.textContent += `\n跳过 WebGPU：${gpu.reason}`;
    }
    rows.push(await measureConfig(corpus, "fp16-wasm", "fp16", "wasm"));
    const report = {
      model: MODEL,
      measuredAt: new Date().toISOString(),
      userAgent: navigator.userAgent,
      rows,
    };
    await post("/api/report", report);
    measureLog.textContent += "\n已写入 results/latest.json。正在重新加载页面使用的 FP16 模型。";
    const restored = await loadExtractor(DTYPE, device);
    extractor = restored.extractor;
    onnxBytes = restored.onnxBytes;
  } catch (error) {
    measureLog.textContent += `\n${error.message}`;
  } finally {
    setBusy(false);
  }
}

bootstrap().catch((error) => {
  statusEl.textContent = error.message;
});
