# Agent 多任务演示

## Demo 1：研究型任务
**场景**：帮我研究量子计算的最新进展，生成报告
**命令**：curl -X POST "..." 
**展示能力**：Plan-and-Execute、web_search、fetch_webpage、execute_python
**预期结果**：生成一份包含引用的结构化报告

## Demo 2：数据处理型任务
**场景**：帮我分析销售数据
**命令**：...
**展示能力**：代码生成、安全沙箱执行、错误修复
**预期结果**：计算各产品占比、平均值、极值，给出优化建议

## Demo 3：多轮记忆型任务
**场景**：记住偏好并基于偏好回答
**命令**：...
**展示能力**：Mem0 长期记忆、个性化回答、表格形式输出
**预期结果**：回答自动以表格形式展示，包含代码示例

///////////////////////////////

# Demo 录制演示素材，能让面试官或协作者在无法直接运行系统时，也能直观地看到效果。

推荐的录制方案

方案	工具	适用场景	优点
终端录制	macOS 自带 QuickTime	录制 curl 命令和终端输出	免费、无需安装、操作简单
GIF 录制	GIPHY Capture (免费)	录制简短操作流程	体积小、可直接嵌入 Markdown
全屏录制	OBS Studio (免费)	录制浏览器操作、Swagger UI	功能强大、支持画中画
终端文本录制	asciinema	录制纯终端操作	文本格式、体积极小、可嵌入网页
推荐组合：

Demo 1-2（curl 命令）：用 asciinema 录制终端操作，体积小，可直接嵌入 README。
Demo 3（多轮对话）：用 QuickTime 录制 Swagger UI 操作，展示记忆保持效果。
录制步骤（以 asciinema + QuickTime 为例）

1. 安装 asciinema

bash
brew install asciinema
2. 录制 Demo 1（研究型任务）

bash
# 开始录制
asciinema rec docs/demos/demo1_research.cast

# 执行 Demo 1 的命令
curl -X POST "http://localhost:8000/api/v1/agent/plan_execute?goal=帮我研究2026年量子计算的最新进展，包括重要突破、主要参与公司和未来展望，最后生成一份300字的结构化报告" \
  -H "Authorization: Bearer <你的Token>"

# 结束录制（按 Ctrl+D 或输入 exit）
exit
3. 录制 Demo 2（数据处理任务）

bash
asciinema rec docs/demos/demo2_data_analysis.cast

# 先插入测试数据
curl -X POST "http://localhost:8000/api/v1/rag/insert" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <你的Token>" \
  -d '{"content":"2026年7月销售数据：产品A销售额120万，产品B销售额85万，产品C销售额63万，产品D销售额41万","source":"sales_data"}'

# 让 Agent 分析数据
curl -X POST "http://localhost:8000/api/v1/agent/mcp_chat?question=帮我分析7月的销售数据，计算各产品的占比、平均销售额、最高和最低销售额，并给出优化建议&thread_id=demo-data" \
  -H "Authorization: Bearer <你的Token>"

exit
4. 录制 Demo 3（多轮记忆任务，使用 QuickTime）

由于 Demo 3 需要多轮对话展示记忆效果，建议用 QuickTime 录制 Swagger UI 操作：

打开 QuickTime Player → 文件 → 新建屏幕录制。
打开浏览器，访问 http://localhost:8000/docs。
依次执行 Demo 3 的步骤：添加记忆 → 提问 → 观察回答中的表格格式。
录制完成后，保存为 docs/demos/demo3_memory.mov。
5. 将 asciinema 转为 GIF（可选）

如果需要嵌入 Markdown，可以用 asciicast2gif 转换：

bash
npm install -g asciicast2gif
asciicast2gif docs/demos/demo1_research.cast docs/demos/demo1_research.gif
将 Demo 素材整理到项目文档中

在 docs/demos.md 中增加以下内容：

markdown
# Agent 多任务演示

## Demo 1：研究型任务——量子计算研究报告

**场景：** Agent 自主规划步骤，搜索量子计算最新进展，并生成结构化报告。

**演示视频：**
![Demo 1 演示](demos/demo1_research.gif)

**或查看 asciinema 录制：**
```bash
asciinema play docs/demos/demo1_research.cast
核心步骤：

规划器将任务分解为：搜索新闻 → 筛选关键文章 → 抓取网页 → 整理数据 → 生成报告
Agent 依次调用 web_search、fetch_webpage、execute_python 工具
最终生成包含标题、分类和来源引用的 300 字结构化报告
Demo 2：数据处理型任务——销售数据统计分析

场景： Agent 自主编写 Python 代码，在安全沙箱中执行，分析销售数据。

演示视频：
https://demos/demo2_data_analysis.gif

核心步骤：

用户提供销售数据（产品A/B/C/D 的销售额）
Agent 调用 execute_python，编写代码计算各产品占比、平均销售额、最高/最低销售额
代码在 Docker 沙箱中安全执行
Agent 基于计算结果给出优化建议
Demo 3：多轮记忆型任务——个性化偏好回答

场景： Agent 记住用户的偏好（喜欢表格形式），跨会话保持记忆，并自动以表格形式回答。

演示视频：
查看 Demo 3 视频

核心步骤：

用户通过记忆接口添加偏好："喜欢表格形式展示数据"
用户提问"对比 Python 和 Go 在 Web 开发中的优劣"
Agent 自动检索到用户的偏好记忆
回答以表格形式展示，而非大段文字描述
切换到新对话窗口，偏好记忆仍然生效
text

---

### 录制前的准备清单

-   [ ] 确保 API 服务正在运行（`bash dev.sh`）
-   [ ] 准备好 Token（先登录获取，避免在录制中暴露登录信息）
-   [ ] 清理终端历史（`clear` 命令），让录制画面干净
-   [ ] 调整终端字体大小（建议 14px 以上），保证录制可读
-   [ ] 测试一遍命令，确保不会出错

---

现在你可以开始录制了。录制完成后，把文件放到 `docs/demos/` 目录下，然后在 `demos.md` 中引用它们。这些素材将成为你项目展示中最亮眼的部分。