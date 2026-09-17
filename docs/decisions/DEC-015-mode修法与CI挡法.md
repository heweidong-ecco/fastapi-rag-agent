# 决策记录:DEC-015 · `mode` 怎么修,以及 CI 怎么"挡掉跑不了的测试"

- 日期:2026-09-17
- 状态:已采纳
- 关联:`api/api_v1_rag.py` · `api/test_rag_search.py` · `api/pytest.ini` · `.github/workflows/ci.yml` · `DEC-013`(M6 的登记)

## 决策事项

一句话:**M6 的三项后续里,有两项各自要在方案间做选择。** 这份记录记的是那两个选择,不是改动本身。

1. **`mode` 静默兜底怎么修** —— 手动校验(返 `AppException`)还是让 schema 层挡?
2. **CI 怎么挡掉"跑不了的测试"** —— `--ignore` 文件名单,还是打 marker?

## 背景与约束

`DEC-013` 记过:业务方 2026-09-17 裁决 **「`mode` 兜底只记录、不写进测试」**(测试不该把缺陷固化成"预期行为"),
**修复另开 PR**。本次就是那笔登记的兑现。当时那个形状是:

```python
if mode == "fast": ...
elif mode == "full": ...
elif mode == "accurate": ...
else:                      # ← 裸 else:`mode=garbage` 静默落进这里
    pipeline = create_accurate_norerank_pipeline()
```

**约束**:① 不能把"静默兜底"换成另一种静默(如悄悄返 200 + 一个 warning 字段);② 新增用例必须**零网络**
(M6 定下的分层:能离线就离线);③ 不能动 `mode` 的**默认值**(`accurate_norerank` 是本机唯一不碰 torch 的默认路径)。

CI 那边(`DEC-013` 已定"CI 只要 redis,不要 postgres"),约束是:**被挡掉的测试必须"看得见"** ——
不能让人以为"CI 绿 = 全绿"。

## 备选方案

**方案一 · `mode` 怎么修**

| 方案 | 思路 | 缺点 |
|---|---|---|
| **甲** | `mode: Literal[...]` + **查表** `PIPELINE_FACTORIES[mode]()` | 要加一个类型别名 + 一个模块级字典 |
| 乙 | 保留 `str`,在函数体里手动判,非法值 `raise AppException(PARAM_INVALID)` | **慢一步**:值先进了函数体才被拒;且 OpenAPI 里没有枚举 |
| 丙 | 保留 `str`,只把 `else` 改成"落到默认值 + 记一条 warning 日志" | 🔴 **还是静默兜底** —— 只是多打了一行日志,调用方看不到 |

**方案二 · CI 怎么挡**

| 方案 | 思路 | 缺点 |
|---|---|---|
| **甲** | 注册 **`needs_db`** marker,4 处打标;CI 跑 `-m "not integration and not needs_db"` | 要动 4 个既有测试文件 |
| 乙 | CI 用 `--ignore` 三个文件 + `--deselect` 一条 | 名单**散在 CI 配置里** —— 脱敏的测试文件改了名/加了新文件,CI 会**静默**接不住 |
| 丙 | CI 也起 postgres service | 要建表/迁移;**推翻 `DEC-013` 已定的"只要 redis"** |

## 评估标准

**拒绝的时机**(越早越好)/ 是否**结构上**消灭了坏分支 / 是否**自描述**(新人能否从测试文件本身看出"它为什么不在 CI")/ 维护成本。

## 方案对比

- **方案一**:丙 被否 —— 它**没解决任何问题**,只是让静默变得"有记录"。**静默的核心是调用方不知道**,日志不改变这一点。
  乙 被否 —— 判据落点太晚:值已经进了函数体。**越早拒越好**。
  甲 还附带一个收益:`mode` 会进 **OpenAPI 的 `enum`**,文档与校验**同源**。
- **方案二**:乙 被否的关键 —— 它的名单在**CI 配置里**,而"哪些测试需要库"是**测试自己的属性**。
  把它写在测试文件里(marker),**改测试的人自然会看到**;写在 CI 里,改测试的人**看不到**。
  丙 被否 —— 前面已定"只要 redis",且加 postgres 要建表,成本档位不同。

## 最终决策 + 理由

**✅ 两个都取甲。**

### 一 · `mode` :`Literal` + 查表(两层,缺一不可)

```python
SearchMode = Literal["fast", "accurate", "accurate_norerank", "full"]
PIPELINE_FACTORIES = {"fast": create_fast_pipeline, ...}
...
pipeline = PIPELINE_FACTORIES[mode]()
```

⚠️ **实测证明"两层各管一段"**:
- **只有查表**:`mode=garbage` 会 `KeyError` ⇒ **500**。比 200 好(不静默了),但仍是**服务端错误**,语义不对。
- **加上 `Literal`**:在**进入函数体之前**就被 FastAPI 挡成 **422**,且 `loc == ["query","mode"]`。

### 二 · CI :`needs_db` marker

**关键区分:`integration` 与 `needs_db` 是两种"跑不了",不能混。**

| marker | 缺什么 | 谁标了 |
|---|---|---|
| `integration` | 真 Postgres **+ DashScope 外网** | `test_rag_search.py::test_search_fast_against_real_stack` |
| `needs_db` | **只要真 Postgres** | `test_documents.py` · `test_integration.py` · `test_search.py`(整篇)+ `test_main.py::test_health`(**单条**) |

📌 **marker 是按需打的,不是整文件一刀切** —— `test_main.py` 里只有 `test_health` 一条需要库
(`/health` 会真探连通性,无库返回 503),另两条**不标**。

## 影响与后续行动

| 验证 | 结果 |
|---|---|
| CI 等价条件(无 `.env` + dummy 变量 + **无 postgres** + redis) | **50 passed / 1 skipped / 11 deselected** |
| 本机口径(带 `rag_test`,只挡 `integration`) | **60 passed / 1 skipped** · **进程真退出** |
| `test_unknown_mode_is_rejected` | `mode=garbage` → **422**;零网络 |
| `test_mode_defaults_to_accurate_norerank` | 不传与显式传默认值**逐字段一致** |
| **变异验证**(把 `SearchMode` 改回裸 `str`) | **1 failed**(`KeyError: 'garbage'`)⇒ 用例有牙 |
| OpenAPI | `mode.enum` = 四个值 · `default = accurate_norerank` · `14`/`59` 逐位未变 |
| 两个 CI job | 加 `timeout-minutes`(`syntax` 5 / `offline-tests` 15) |

- ⚠️ **判据是实测出来的,不是推的**:把 `POSTGRES_PORT` 指向死端口**逐文件**跑,才定下那份 marker 名单。
  顺带发现 **`test_auth.py` 无库也能过**(它的登录用例不走 `auth_headers` 那条路)—— 与"名字里带 auth 就要库"的直觉相反。
- **仍未进 CI 的**:`integration` 与 `needs_db` 两类。**若将来 CI 起 postgres service**,这两类应一并纳入。

## 反悔成本

**低。** 两处都是局部的、可单独 revert:
- `mode` 改回 `str` + `if/elif/else` —— 但会退回**静默兜底**
- marker 改回 `--ignore` 名单 —— 但会退回"名单写在 CI 里、改测试的人看不见"
