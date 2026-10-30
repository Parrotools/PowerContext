# 技术说明

## 模型与量化

模型是 Xenova/all-MiniLM-L6-v2 的 ONNX 导出，上游为 sentence-transformers/all-MiniLM-L6-v2，输出 384 维，并做 mean pooling 和归一化。页面使用仓库里的 FP16 权重 `onnx/model_fp16.onnx`，由 Transformers.js 按 `dtype: "fp16"` 加载。量化前基线是同一仓库的 `onnx/model.onnx`（FP32）。

体积只统计 ONNX 权重文件，不含两边共用的 tokenizer。2026-10-31 从模型仓库文件列表读到的大小：

| 文件 | 字节 |
| --- | ---: |
| onnx/model.onnx（FP32） | 90387606 |
| onnx/model_fp16.onnx（FP16） | 45297825 |

压缩比 = 90387606 / 45297825 = 1.995。2026-10-31 在页面里再次下载，FP32 与 FP16 的 `onnxBytes` 与上表一致。

检索质量用 `public/corpus.json` 的 8 篇笔记和 8 个查询，指标是 Recall@3 和 nDCG@3，相关文档各只有 1 篇。三种配置的 Recall@3 都是 1.000，nDCG@3 都是 0.954。FP16 相对 FP32 没有质量下降。

## 端侧运行

运行时是 Transformers.js 3.7.6，底层是 ONNX Runtime Web。启动时先调用 `navigator.gpu.requestAdapter()`。拿到适配器就用 `device: "webgpu"`，否则用 `device: "wasm"`，页眉会写明当前后端和降级原因。文档导入和查询框走的是同一条路径。

模型文件可以从 `huggingface.co` 下载，失败后改用 `hf-mirror.com`。下载只取权重和分词器，不调用推理 API。

## seekdb 使用

`@oceanbase/seekdb-node` 1.4.0 在 `stepfun/data/seekdb` 启动本机 seekdb，seekdb-js 1.4.0 通过它返回的 TCP 地址连接。集合 `stepfun_notes` 使用 384 维 cosine HNSW（`lib=vsag`）和 ngram 全文索引（token 长度 2）。创建集合时 `embeddingFunction` 设为空，服务端没有安装默认 embedding 包。

写入调用 `collection.upsert()`，向量来自浏览器。随后调用 `collection.refresh_index()`，再用刚写入的向量做一次混合检索，确认新 id 已经能被返回。

查询调用一次 `collection.hybridSearch()`：全文条件是 `whereDocument.$contains`，向量是浏览器传来的 `queryEmbeddings`，融合方式是 RRF（窗口 20，常数 60），并用 `where.library` 限定当前知识库。SDK 把这次调用编成 `DBMS_HYBRID_SEARCH.SEARCH`。服务端没有第二条查询，也不会把全文结果和向量结果在 Node 里合并。

## 状态与优化

知识库名称存在每条记录的 metadata 里，当前名称另外记在 `data/session.json`。切换名称后，检索条件只保留该名称。连续导入使用 upsert，不清空其他知识库。

优化点：

- 导入按 8 条一批计算向量，并按同样的批大小写入 seekdb。
- 每批只刷新一次索引，而不是每条刷新一次。
- 默认加载 FP16 权重，减少下载和显存占用。
- WebGPU 可用时走显卡。WASM 固定单线程，换取在没有跨域隔离头的页面上仍能跑通。

2026-10-31 的实测环境是 Windows x64、Edge 156。语料 8 篇，查询 8 条。每种配置先预热 1 次，再重复 3 次，下表取中位数。同一次运行的原始记录在 `measurement.json`。

| 配置 | 模型体积 | 向量化吞吐 | seekdb 检索延迟 | 端到端查询延迟 | 检索质量 |
| --- | ---: | ---: | ---: | ---: | --- |
| FP32 + WASM | 90387606 字节 | 23.28 篇/秒 | 10 毫秒 | 29 毫秒 | Recall@3 1.000，nDCG@3 0.954 |
| FP16 + WebGPU | 45297825 字节 | 285.71 篇/秒 | 10 毫秒 | 25 毫秒 | Recall@3 1.000，nDCG@3 0.954 |
| FP16 + WASM | 45297825 字节 | 21.97 篇/秒 | 9 毫秒 | 40 毫秒 | Recall@3 1.000，nDCG@3 0.954 |

FP32 首次加载含下载，耗时 68980 毫秒。FP16 两次加载时权重已在浏览器缓存中，WebGPU 481 毫秒，WASM 360 毫秒。8 篇笔记在 FP16 + WASM 下逐条向量化中位数 558 毫秒，8 条一批为 364 毫秒。三种配置在索引刷新后都能检索到新写入的文档。
