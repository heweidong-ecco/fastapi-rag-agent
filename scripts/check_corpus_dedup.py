#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""语料去重检查器 —— **跨文档** · `docs/说明/语料要求.md` §一#3 / §六#8 · `DEC-118`

    venv/bin/python scripts/check_corpus_dedup.py                        # 默认扫 testdata/demo-corpus/
    venv/bin/python scripts/check_corpus_dedup.py testdata/isolation-seed
    venv/bin/python scripts/check_corpus_dedup.py --no-semantic          # 只跑离线那两层

## 🔴 为什么要有它 —— 原来那套是【三重不可用】

业务方 2026-10-08 的原话：「**去重这块，有脚本，但是不一定好，不一定完整，需要加强**」。
实查（2026-10-08）—— **他说的对，而且比"不完整"更糟**：

| 现成的 | 实测状态 |
|---|---|
| `document_preprocessor.deduplicate_lines`（**按行**） | ✅ 在管道里真跑 —— ⚠️ 但它**只认完全相同**的行，且**只在一篇之内** |
| `document_preprocessor.deduplicate_chunks`（**语义**） | 🔴 **三重不可用**：① **没接线**（调用点被注释）② 阈值 **0.9** ≠ §一#3 的 **0.85** ③ 它要 `sentence-transformers`，而**本机没装** ⇒ 就算接上也只会打印「未安装，跳过」 |
| **跨文档**去重（20–40 篇之间） | 🔴 **根本没有** —— 上面两个都是**单篇内**的 |

⇒ 本脚本补的正是**第三格**：**跨文档**。

## 🔴 三层，逐层降级（⛔ 不静默）

| 层 | 抓什么 | 要联网吗 |
|---|---|---|
| **① 文件级** | 两篇**内容完全相同**（sha256） | ⛔ 不要 |
| **② 行级** | 同一行**逐字**出现在两篇里（跨文档） | ⛔ 不要 |
| **③ 语义级** | 两块**余弦 ≥ 阈值**（默认 **0.85** · §一#3） | ✅ **要**（走本仓 `get_embedding`） |

🔴 **没有 key / 调用失败 ⇒ 那一层【明说跳过了】，⛔ 不许静默当"通过"**
（本仓立场：`--all` 下没跑第 ② 节却在结论行写"覆盖 ①②③" —— 那是一条前科，见 `DEC-076`）。

## 🔴 它**只报不删**

去重是**内容判断**：两块 0.87 相似，可能是重复，也可能是**同一规则的两个角度**（而 §六#5 恰恰
**要求**跨文档交叠存在）。⇒ 脚本给**证据**，裁决在**产出语料那一方**。
⛔ **不自动删、不自动合并** —— 自动改语料 = 静默改变 demo 的回答，而没有任何门会红。
"""
import hashlib
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
API_DIR = REPO_ROOT / "api"
if str(API_DIR) not in sys.path:
    sys.path.insert(0, str(API_DIR))

DEFAULT_DIR = "testdata/demo-corpus"
THRESHOLD = 0.85          # 🔴 §一#3 定死的数（⛔ 不是 0.9 —— 那是 deduplicate_chunks 的旧默认值）
MIN_CHARS = 20            # 与上传端点的 min_length 一致


def _cos(a, b) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(y * y for y in b) ** 0.5
    return 0.0 if na == 0 or nb == 0 else dot / (na * nb)


#: 类别字母 → 档位。**与 `docs/说明/语料要求.md` §8.2 那张表逐字一致** ——
#: ⚠️ 灌库脚本也按这张表给 `doc_type`；⛔ 别在这里另发明一套（两套规则必然漂移）。
_LETTER_TO_DOC_TYPE = {"A": "technical", "B": "legal", "C": "faq",
                       "D": "report", "E": "default"}


def _doc_type_of(path: Path) -> str:
    """按 §8.2 的**文件名即契约**推档位；认不出的字母 ⇒ `default`（兜底档）。"""
    letter = path.name.split("-", 1)[0].strip().upper()
    return _LETTER_TO_DOC_TYPE.get(letter, "default")


#: 🔴 **只认 `<类别字母>-*.md`** —— 这是 `docs/说明/语料要求.md` §8.2 的【文件名即契约】。
#: ⚠️ **它同时修掉一处口径差**：`isolation-seed/README.md` 有 **6200 字**，
#:    而它**不是语料**（是那 9 篇的说明）。§六#7 原来那条 `wc -m …/*.md` 把它算进去了
#:    （实测：含 README **11550** ↔ 不含 **5350**）⇒ **两处判据读出来会不一样**。
#:    ⇒ 现在两边都按字母前缀筛（§六#7 那条命令已同步改）。
_CORPUS_GLOB = "[A-E]-*.md"


def load(dirpath: Path):
    files = sorted(dirpath.glob(_CORPUS_GLOB))
    return {p: p.read_text(encoding="utf-8") for p in files}


def layer1_files(docs):
    seen, hits = {}, []
    for p, text in docs.items():
        h = hashlib.sha256(text.encode("utf-8")).hexdigest()
        if h in seen:
            hits.append((seen[h], p, h[:12]))
        else:
            seen[h] = p
    return hits


#: 🔴 一条行只要有【至少一个】中文或字母数字，才算"内容行"。
#: ⚠️ **这条是实测补的**：第一版拿 `testdata/isolation-seed` 跑，② 层立刻报了一条
#:     `|---|---|---|` —— 那是 **Markdown 表格的分隔行**，⛔ 不是内容。
#:     ⇒ 判据要**排除纯符号行**（表格分隔、代码围栏、`---` 横线…），否则假阳性会把人淹掉，
#:       而"淹没"的下一步就是"这条检查没人看了"（本仓立场：`DEC-076` 那族）。
_CONTENT_RE = __import__("re").compile(r"[0-9A-Za-z\u4e00-\u9fff]")


def layer2_lines(docs):
    """跨文档的**逐字重复行**。

    ⚠️ 两道门槛：① 长度 ≥ 12 ② **至少含一个中文或字母数字**（排除 Markdown 结构行）。
    """
    where, hits = {}, []
    for p, text in docs.items():
        for ln in text.split("\n"):
            s = ln.strip()
            if len(s) < 12 or not _CONTENT_RE.search(s):
                continue
            where.setdefault(s, []).append(p)
    for s, ps in where.items():
        distinct = sorted(set(ps))
        if len(distinct) > 1:
            hits.append((s, distinct))
    return sorted(hits, key=lambda x: -len(x[1]))


def layer3_semantic(docs):
    """跨文档的**语义**重复。返回 `(hits, skipped_reason)`。

    🔴 失败/无 key ⇒ **返回原因**，⛔ 不返回空列表假装"没有重复"。
    """
    from chunker import split_text_with_filter
    from embedding_client import get_embedding

    chunks = []          # (path, idx, text)
    for p, text in docs.items():
        try:
            dt = _doc_type_of(p)
        except Exception as e:                       # noqa: BLE001
            return [], f"分档失败（{p.name}: {e}）"
        for i, c in enumerate(split_text_with_filter(text, doc_type=dt, min_length=MIN_CHARS)):
            chunks.append((p, i, c))

    if len(chunks) < 2:
        return [], None

    try:
        vecs = [get_embedding(c[2]) for c in chunks]
    except Exception as e:                           # noqa: BLE001
        return [], f"embedding 调用失败（{type(e).__name__}: {e}）"

    hits = []
    for i in range(len(chunks)):
        for j in range(i + 1, len(chunks)):
            if chunks[i][0] == chunks[j][0]:         # ⛔ 只报【跨文档】—— 篇内重复是另一件事
                continue
            sim = _cos(vecs[i], vecs[j])
            if sim >= THRESHOLD:
                hits.append((chunks[i], chunks[j], sim))
    return sorted(hits, key=lambda x: -x[2]), None


def main() -> int:
    args = [a for a in sys.argv[1:]]
    no_semantic = "--no-semantic" in args
    args = [a for a in args if not a.startswith("--")]
    dirpath = REPO_ROOT / (args[0] if args else DEFAULT_DIR)

    if not dirpath.is_dir():
        print(f"🔴 目录不存在：{dirpath}")
        print("   ⚠️ 本仓立场「先有内容，再有格子」⇒ 语料还没产出时它本来就不存在。")
        print("   📌 想验本脚本能不能跑，拿现成的当夹具：")
        print("      venv/bin/python scripts/check_corpus_dedup.py testdata/isolation-seed")
        return 2

    docs = load(dirpath)
    if not docs:
        print(f"🔴 {dirpath} 里没有 .md（README 不算）")
        return 2

    total_chars = sum(len(t) for t in docs.values())
    print(f"扫描 {dirpath.relative_to(REPO_ROOT)} —— {len(docs)} 篇 / {total_chars} 字")

    l1 = layer1_files(docs)
    print(f"\n① 文件级（完全相同）：{len(l1)} 处")
    for a, b, h in l1:
        print(f"   🔴 {a.name} ≡ {b.name}  (sha256:{h}…)")

    l2 = layer2_lines(docs)
    print(f"\n② 行级（跨文档逐字重复，行 ≥12 字）：{len(l2)} 处")
    for s, ps in l2[:15]:
        print(f"   🔴 「{s[:40]}{'…' if len(s) > 40 else ''}」 ⇒ {[p.name for p in ps]}")
    if len(l2) > 15:
        print(f"   …… 还有 {len(l2) - 15} 处")

    if no_semantic:
        print("\n③ 语义级：⛔ **【跳过了】**（`--no-semantic`）—— 结论**不覆盖**这一层")
        semantic_state = "skipped-by-flag"
    else:
        hits, why = layer3_semantic(docs)
        if why:
            print(f"\n③ 语义级：⛔ **【跳过了】** —— {why}")
            print("   ⚠️ 结论**不覆盖**这一层，⛔ 别把下面那句读成「没有语义重复」。")
            semantic_state = f"skipped: {why}"
        else:
            print(f"\n③ 语义级（跨文档 · 余弦 ≥ {THRESHOLD}）：{len(hits)} 处")
            for (pa, ia, ca), (pb, ib, cb), sim in hits[:15]:
                print(f"   🟡 {sim:.3f}  {pa.name}#{ia}  ↔  {pb.name}#{ib}")
                print(f"        「{ca[:36]}…」  ↔  「{cb[:36]}…」")
            if len(hits) > 15:
                print(f"   …… 还有 {len(hits) - 15} 处")
            semantic_state = "ran"

    print(f"\n{'=' * 62}")
    print(f"覆盖情况：① 文件级 ✅ · ② 行级 ✅ · ③ 语义级 ⇒ {semantic_state}")
    print("🔴 本脚本【只报不删】—— 重复也可能是「同一规则的两个角度」，"
          "而 §六#5 恰恰【要求】跨文档交叠存在。裁决在产出语料那一方。")
    print("📌 判据（§六#8）：①② 应为 0 处；③ 的命中要**逐条**判断是重复还是交叠。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
