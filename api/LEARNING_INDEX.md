标准化注释块
"""
---
day: 28
topic: Reranker批量化推理
version: v2-batch
status: superseded  # active | superseded | deprecated | experimental
superseded_by: reranker_v3_singleton.py  # 仅当 status=superseded 时填写
key_learning: Cross-Encoder支持batch输入，吞吐量提升3x，但显存占用增加
tags: [reranker, performance, batch-processing]
---
说明: Day28实现的批量推理版本。相比v1逐条处理性能显著提升，
      但未解决模型重复加载问题，已被Day35的v3单例版取代。
      保留用于对比batch vs sequential的性能差异。
"""

## Reranker 模块演进

| 版本 | Day | 状态 | 关键学习点 | 文件 |
|------|-----|------|-----------|------|
| v1-naive | 12 | superseded | 理解Cross-Encoder基本原理 | reranker_v1_naive.py |
| v2-batch | 28 | superseded | 批量推理吞吐提升 | reranker_v2_batch.py |
| v3-singleton | 35 | **active** | 单例+批量，当前最优 | reranker_v3_singleton.py |

"""
---
day: 50
topic: 结构化日志与Timing输出修复
version: v2-structured
status: active
key_learning: Timing字典需通过extra参数传递，Formatter需支持嵌套序列化
tags: [observability, logging, timing, production-readiness]
---
"""

