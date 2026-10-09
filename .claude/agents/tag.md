**禁止创建subagent**：
- **使用 用户级 ~/.claude/ & 项目级 .claude/ 下 settings.json & commands/ & hooks/ & *.sh 代替 subagents**
- **subagent禁止原因**
  - 烧Token，盲测及验证可用。
- **禁止**自己创建subagent，必须经过人工审核 'HITL'。
- **任务由主agent 及 ~/claude && .claude/ 下 commands chooks .sh 在 main 上串行执行**
  - 所有任务应通过主agent在main上串行执行，避免并发执行带来的不确定性。
  - 使用commands来管理任务的执行顺序和依赖关系，确保任务按预期进行。
