# 决策记录：DEC-032 · RAGAS 与【中文 + DeepSeek + DashScope】的三处不兼容

- 日期：2026-09-21
- 状态：**已采纳并执行**（三处均**实测定位 + 实测验证修法**）
- 关联：`DEC-031`（依赖隔离与 judge 改走 `.env`）· `ROADMAP.md` 剩余待办 **#5**

## 决策事项

RAGAS 冒烟跑通后，**4 个指标里 2 个是 `nan`**。**怎么办？**
（先定根因，再谈修法 —— 见下方「**先做了什么**」。）

## 🔴 先做了什么：**定根因，不是先提修法**

**四步，每步都拿实测结果说话：**

1. **逐指标单独跑 + `raise_exceptions=True`** ⇒ 让异常浮出来，不再被吞成 nan
2. 从**报错原文**里抓线索（`Invalid n value` / `No statements were generated`）
3. **读三方源码**（RAGAS / langchain-openai）定位可疑那一行
4. **做决定性对照实验** —— 这是关键一步（见下）

> 📌 **第 4 步是必须的**：`faithfulness` 那条**连 `raise_exceptions=True` 都不抛**，
> 是**静默 nan**。**光读代码不下结论** —— 必须让它正反两面各跑一次。

## 🔴 三处不兼容（**都不是本仓 RAG 系统的错**）

三处**分别属于三个不同的系统** —— 这是它们难查的原因：症状在 RAGAS，根因分散在三方。

### ① `faithfulness` 对**中文答案恒为 `nan`** —— **RAGAS 自己的 bug** 🔴

**位置**：`ragas/metrics/_faithfulness.py:216`

```python
sentences = [s for s in sentences if s.strip().endswith(".")]   # ← 只认 ASCII 句点
```

**后果链条**：中文答案以 `。` 结尾 ⇒ 这一句把它们**全部滤掉** ⇒ 提示里 **0 条语句** ⇒
LLM 输出 0 条 ⇒ `_compute_score` 走 `logger.warning("No statements were generated from the answer.")`
⇒ **`score = np.nan`**。

⚠️ **它是【静默】的**：不抛异常，**`raise_exceptions=True` 也不抛**（那是给 LLM 调用失败用的）。

**✅ 决定性对照实验**：

```
中文答案 "…广泛应用于 Web 开发。它也是…数据科学领域。"
  → 切出 2 句 → 按 endswith('.') 过滤后 = 【0 条】 ⇒ nan
英文答案 "Python is an interpreted language. It is used in data science."
  → 切出 2 句 → 按 endswith('.') 过滤后 = 【2 条】 ⇒ 正常
```

**修法**：子类覆盖 `_create_statements_prompt`，**只放宽"句末标点"这一条判断**
（`。．.！？!?；;`），**其余逻辑一个字不动**。

**实测**：`nan` → **`0.857`** ✅

### ② `answer_relevancy`：`strictness=3` ⇒ 向 judge 要 `n=3` —— **DeepSeek 不支持**

**报错原文**：`BadRequestError(400): Invalid n value (currently only n = 1 is supported)`

RAGAS 的 `answer_relevancy` 要**为每个答案生成 `strictness` 个问题**再算相似度，
默认 `strictness = 3` ⇒ 发 `n=3` ⇒ **DeepSeek 明确拒绝**。

**修法**：`answer_relevancy.strictness = 1`。
✅ **这是 RAGAS 官方参数**，不是我们发明的开关。

⚠️ **代价**：`strictness=1` 比 3 的方差大一些。**已知并接受** —— DeepSeek 下没有别的选择。

### ③ `OpenAIEmbeddings` 默认把文本**转成 token id** 再发 —— **DashScope 不认**

**报错原文**：`400 InvalidParameter: contents is neither str nor list of str.: input.contents`

**根因**：`langchain_openai.OpenAIEmbeddings` 的 `check_embedding_ctx_length` **默认为 `True`**
⇒ 它先 **tokenize**，把 `input` 发成 **`list[int]`（token id 数组）**。
**OpenAI 官方接口接受这种形式，DashScope 的兼容接口不接受。**

⚠️ **这条最容易误判**：连 `embed_query("一句普通中文")` **都会挂** ——
与**问题长短、中英文、单条还是批量，全都无关**。所以它看起来像"embedding 服务挂了"。
📌 而**应用自己**的 embedding 是好的（RAG 检索正常返回）⇒ **是客户端配置差异，不是服务不可用**。

**✅ 决定性对照实验**：

```
check_embedding_ctx_length=True （默认） → ❌ 400 contents is neither str nor list of str
check_embedding_ctx_length=False        → ✅ 维度 1536
```

**修法**：`OpenAIEmbeddings(..., check_embedding_ctx_length=False)`。

## 备选方案

| 方案 | 一句话 | 本次 |
|---|---|---|
| **甲 · 三处都修**（**采纳**） | 按上述三条分别打最小补丁 | ✅ |
| 乙 · 只报能跑的指标（recall / precision），另两个标 N/A | 不碰 RAGAS | ⬜ |
| 丙 · 换 judge（回到能 `n>1` 的模型） | 但 DashScope chat **额度已耗尽 403** | ⬜ 不可行 |

**甲。** 两条理由：

1. **不修就等于「中文场景下 RAG 最重要的两个指标永远缺失」** ——
   `faithfulness`（答案有没有根据）和 `answer_relevancy`（答得切不切题）**正是 RAG 的核心**。
   只剩 recall/precision 的话，这份评估**答不了"RAG 好不好"**，那 RAGAS 就白接了。
2. **三处修法都是【最小、可验证、可回退】的** ——
   ① 一个子类覆盖一个方法；② 一个官方参数；③ 一个官方参数。
   **都不改 RAGAS 安装包本身**（不 fork、不打 site-packages 补丁）⇒ `venv-ragas` 重装即回到原状。

**丙 不可行的理由**：`DEC-031` 已记 —— DashScope 的 chat 免费额度**已耗尽（403）**。

## 执行内容

`api/evaluate_with_ragas.py`：

1. `eval_embeddings` 加 `check_embedding_ctx_length=False`
2. `answer_relevancy.strictness = 1`
3. 新增 `class ZhFaithfulness(Faithfulness)` 覆盖 `_create_statements_prompt`，
   实例 `zh_faithfulness` **替换** `main()` 里 metrics 列表中的 `faithfulness`
   （实测 `zh_faithfulness.name` 仍是 `'faithfulness'` ⇒ **报告循环不用改**）

**验证（1 条问答，四指标全开，`raise_exceptions=True`）**：

```
结果 = {'faithfulness': 1.0,
        'answer_relevancy': 0.886,
        'context_recall': 1.0,
        'context_precision': 0.583}
NaN 的指标 = 无 ✅
```

## ⬜ 遗留 / 已知不确定

1. 🔴 **`strictness=1` 的方差代价没量化** —— 只跑了 1 条。全量跑完再看。
2. ⚠️ **`ZhFaithfulness` 是【子类覆盖】，不是上游修复** ——
   升级 ragas 后 `_create_statements_prompt` 若改名/改签名，**这个子类会静默失效**
   （覆盖不到 ⇒ 又变回 nan）。⇒ **判据是"跑完看有没有 nan"**，不是"代码里有没有这个类"。
3. ⚠️ **`ragas==0.1.21` 与 `requirements.txt` 的 `ragas>=0.1.18` 不一致**（沿用 `DEC-031` §遗留②）。
4. ⚠️ **本次三处都是"让指标能出数"，不是"指标对不对"** ——
   RAGAS 指标本身的有效性（阈值该定多少、能不能反映真实质量）**未评估**。

## 反悔成本

**极低** —— 三处都在 `evaluate_with_ragas.py` 一个文件里，`git revert` 即回到"两个 nan"的旧状态。
`venv-ragas` 里的 ragas **一个字节没动**（没 fork、没打 site-packages 补丁）。

## 变更记录

- 2026-09-21 建立（三处不兼容均由**决定性对照实验**定位，修法**均实测验证**）。
