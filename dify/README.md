# 记仇的客栈老板

一个可以接着玩的对话。客人说自己对老板做了什么，Dify 编排回复；PowerContext 保存这句话。重新开一场对话后，老板仍会提起上一件坏事。

分工：

- Dify 负责接输入、调用模型、按顺序调用两个 HTTP 节点并输出回复。
- PowerContext 负责保存和读回旧账。Dify 自己的会话记忆不作为记仇依据。验证时必须新开一场对话。

没有使用 seekdb。

## 运行环境

- Dify 1.x，能导入 DSL。云端或本机都可以。
- PowerContext Server，Python 3.11+。本机默认地址 `http://127.0.0.1:8000`。
- 一个已在 Dify 里配置好的对话模型。DSL 里的模型名只是占位，导入后改成你自己的供应商和模型。
- 如果 Dify 跑在云端，它访问不到你电脑上的 `127.0.0.1`。把 PowerContext 放到 Dify 能访问的地址，或改用本机 Dify。

不要把真实的模型密钥或 PowerContext token 写进仓库。下面的配置都用占位值。

## 启动

1. 启动 PowerContext，并确认健康检查通过。

```bash
uv tool install --force "powercontext[cli,server] @ git+https://github.com/oceanbase/powercontext.git@master"
powercontext server run
```

另一个终端：

```bash
curl --fail --silent --show-error http://127.0.0.1:8000/health/live
```

2. 创建本应用使用的 scope。重复执行会返回同一个 id。

```bash
python dify/init_scope.py
```

3. 在 Dify 中导入 `dify/innkeeper-grudge.yml`。
4. 打开该应用的环境变量：
   - `POWERCONTEXT_URL`：PowerContext 的根地址，不要带路径，例如 `http://127.0.0.1:8000`。
   - `POWERCONTEXT_SCOPE`：上一步打印的 scope id，替换掉 `REPLACE_WITH_SCOPE_ID`。
5. 打开「老板开口」节点，把模型改成当前工作区已经可用的对话模型。
6. 若 PowerContext 开启了鉴权，在两个 HTTP 节点的 Header 里追加 `Authorization: Bearer <token>`。token 放在 Dify 的密钥配置里，不要提交到仓库。默认的本地服务不需要这一步。
7. 发布应用，从 Dify 的对话页面进入。

导入时如果提示 DSL 版本较旧，选择升级后继续。两个 HTTP 节点的地址分别是：

- `POST /v1/context/prepare`
- `POST /v1/memory/remember`

## 验证样例

初始状态：新的 scope，里面还没有「客栈记仇」记录。`init_scope.py` 使用固定的 `idempotency_key`，所以每次脚本得到的是同一个 scope。要重测时，换一个新的 key 建新 scope，或在 PowerContext 里清空该 scope 的 memory。

第一场对话，只发送这一句：

```text
我把你的招牌酒换成了醋
```

预期：老板把这当作第一次见面，不提起更早的恶作剧。Dify 运行记录里，「读取旧账」返回 `status` 为 `empty` 或 `content` 为空；「记下这次」返回成功，正文里含有「客栈记仇」和「招牌酒换成了醋」。

然后点击新对话，不要沿用第一场会话。第二场只发送：

```text
老板，我又来了
```

预期：回复点名「招牌酒」或「醋」。不能改成另一件没有发生过的事。运行记录里，「读取旧账」的 `content` 含有第一场那句话。

恢复初始状态：用另一个 `idempotency_key` 重新运行 `init_scope.py`，把新的 scope id 填回 Dify。

## 需要留下的证据

评审要看到可运行的应用，不只要文档。请附上：

- 导入后的应用页面。
- 第一场和第二场的对话截图。第二场必须是新对话。
- 两场对话中「读取旧账」和「记下这次」两个节点的输入、输出和状态码。
- `init_scope.py` 打印出的 scope id。可以打码，但要能对上环境变量里的值。

这些截图不要放进公开仓库。和 DSL、本说明一起交给提测平台。
