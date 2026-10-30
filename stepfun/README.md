# 端侧迷你知识库

浏览器把笔记编码成向量，seekdb 保存原文、向量和知识库名称，并在一次混合检索里同时做全文和向量排序。

分工：

- 浏览器里的 Transformers.js 负责加载模型、选择 WebGPU 或 WASM、批量计算文档向量和查询向量。
- seekdb-js 负责建集合、写入、`refresh_index()`，以及 `hybridSearch()`。后者会生成一条 `DBMS_HYBRID_SEARCH.SEARCH`，融合在数据库内完成。
- 这个 Node 进程只转发浏览器已经算好的向量，不加载 embedding 模型，也不调用云端推理接口。

## 运行环境

- Node.js 22 或更新版本。`@oceanbase/seekdb-node` 1.4.0 带有 Windows x64、Linux x64/arm64、macOS Apple Silicon 的运行时。
- Chrome 或 Edge 最新版本。
- 安装依赖时保留 optional dependencies，平台运行时靠它安装。

模型是 [Xenova/all-MiniLM-L6-v2](https://huggingface.co/Xenova/all-MiniLM-L6-v2)，来自 [sentence-transformers/all-MiniLM-L6-v2](https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2)。页面默认加载其中的 FP16 ONNX：`onnx/model_fp16.onnx`。权重从 Hugging Face 下载；如果主站连不上，页面会改用 `https://hf-mirror.com/`。下载的是模型文件，向量计算仍在本机浏览器。

## 启动

在本目录执行：

```bash
npm install
npm start
```

浏览器打开 `http://127.0.0.1:8787`。等页面写明推理后端和 FP16 已加载。

`npm start` 会用 `@oceanbase/seekdb-node` 在 `stepfun/data/seekdb` 启动本机 seekdb，再用 seekdb-js 连接。不需要另外部署数据库。第一次初始化比之后再次启动更久，内存预算是 1G。

## 验证

1. 点「导入内置语料」。页面会显示本地向量化耗时，以及索引刷新后新文档可以被检索到。
2. 搜索 `老板把酒换成了什么`。第一条应是「客栈招牌酒」，正文里能看到醋。
3. 再搜索 `VINEGAR8841`。同一条笔记应靠全文记号被找回来。
4. 在文本框再贴一条新笔记并导入。导入日志写明刷新完成后，立刻用该笔记里的原句搜索，结果里应出现这条新笔记。
5. 把知识库切换到一个新名称后再搜索，结果只来自当前知识库。

内置语料和 8 个查询在 `public/corpus.json`。查询旁的 `relevant` 是测量用的相关文档，检索界面不会把它当作答案填进去。

服务端自检不加载模型，只用两条人工向量确认混合检索同时能命中全文记号和向量近邻：

```bash
npm run self-check
```

## 测量

页面底部的「开始测量」会按题面的三行配置跑完：FP32 + WASM、FP16 + WebGPU、FP16 + WASM。WebGPU 不可用时，第二行记为跳过，日常使用的黄色后端提示就是降级结果。

每次配置先预热一次，再把向量化和查询各重复 3 次，记录中位数。页面把原始记录写到 `stepfun/results/latest.json`。已提交的一次实测在 `measurement.json`，汇总表在 `TECH.md`。

## 已知限制

- 全文索引用 ngram，token 长度为 2，用来切中文。非常长的查询仍原样交给 seekdb。
- WASM 固定单线程，避免浏览器缺少 SharedArrayBuffer 时加载失败。
- 向量维度固定为 384，和所选 MiniLM 一致。
