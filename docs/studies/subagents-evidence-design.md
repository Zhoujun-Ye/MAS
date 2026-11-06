# Claude Code Subagents：Shared Evidence Workspace

状态：设计与实现说明，2026-11-05。按用户要求合并为一个 Shared Evidence Workspace，通用能力归入 harness。核心存储、hook/MCP 和独立原生接入已实现，服务器假 provider 验证见 `shared-evidence-native.md`。没有付费实验，真实决策收益尚未验证，不修改冻结基线。原 `del-protocol.md` 保留为历史草案，不继承裁决者、闸门或实验预算。

## 1. 目标与边界

第一版研究问题：在保留 lead 最终决策权的情况下，能否让分散在 subagent 中的候选、依据和反证更完整地进入最终决策？

一个共享组件内保留三个严格区分的层次：Observations 记录实际观测；Issues & Candidates 加 Evidence Links 登记解释、假设和依据；Selections 记录 lead 的选择与理由。下文“观测库”和“账本”仅指逻辑视图，不是独立系统。它不自动判断真伪，不保证准确率提高，不用参考答案指导运行。

- 基础运行时：项目固定的 Claude Code 2.1.286，普通原生 subagents，Teams 关闭。
- 上下文、模型调用、并发调度、生命周期由 Claude Code 管理；不引入 SDK、模型循环或自建调度器。
- 新组织仅作为显式开启的研究条件。基线 prompt、工具与权限保持不变；限时等任务规则向所有条件一致提供。
- 不增加固定专家阵容、强制分解、投票、自动裁决、租约、自动提交或自动重试。
- DataClaw/HDR 的受保护材料仅留在私有运行环境；gold 不进入 solver、观测库或账本。

## 2. 最小组织

```text
用户任务 -> lead
              | 原生 Agent 委派具体子任务
              +-> evidence-worker 实例 A
              +-> evidence-worker 实例 B ...（数量由任务需要决定）
              |
所有角色的工具调用 -> 自动采集 -> Shared Evidence Workspace / Observations
所有角色的候选与论证 <-------> 同一工作空间 / Claims & Evidence
              |
lead 查看分歧与证据 -> 记录选择理由 -> 按原协议提交
```

当前只设计一种可复用角色 `evidence-worker`，承担具体取证与计算；不是固定求解者/审稿者流水线，worker 的任务和数量由任务需要决定。第一版优先做好观测库与决策账本，独立视角角色留待后续单独设计，不作为当前实现或验证的依赖。

### Lead 的协作约定

1. 按需要委派工作，brief 包含目标、相关账本项、已知事实的观测引用、未决问题、可写目录和共享任务限制。
2. 明确区分已观察事实与自己的暂定解释；需要独立探索时，不在 brief 中预先提供推荐答案，并记录实际披露了哪些内容。
3. worker 返回后检查相关候选及反证；不按支持者数量替代证据判断。
4. 最终选择记录采用、拒绝或暂缓的主要候选及理由。可以保持原答案，也可以登记新候选后选择；不要求为展示协作而改答案。

### Worker 的协作约定

- 工具能力按子任务需要配置，不是只读推理角色；仍遵守原任务工具权限。
- 脚本和中间产物写入独立子目录，避免覆盖其他角色的工作；这不是 OS 隔离保证。
- 登记明确的候选或发现，附假设、依据、限制及尚需的证据。允许“未找到”“执行失败”“不能区分”。
- 原生返回消息只需给出条目 ID、主要变化和未决问题；不强制把完整长报告塞回 lead 上下文。
- 不写最终 submission。此项是研究角色约定，不声称已由沙箱强制实现。

## 3. 观测库

### 3.1 记录单位

一个 observation 是一次工具调用的可追溯结果，不是 agent 的观点。每条包括：

| 字段 | 含义 |
|---|---|
| run_id / obs_id | 运行内身份；相同内容的不同调用仍保留不同事件 |
| session_id / agent_id / tool_call_id | 原生来源；缺失时标 unknown，不猜测身份 |
| tool_name / input_ref | 工具及原始参数的私有快照 |
| output_ref / output_hash | 输出内容地址和哈希；保留原始文本/结构 |
| status / timestamp | 成功、失败、取消或未知，以及采集时间 |
| artifact_refs | 可定位的脚本、数据、查询版本及哈希；无法追溯的依赖明确标缺失 |
| completeness | 完整、被截断、仅指针或缺失；不把部分输出当完整证据 |

只对可明确定位的输入和产物绑定版本，不声称能从任意 Bash 调用恢复所有依赖。大型只读数据可引用现有 manifest；可变脚本与结果应在调用附近保存快照。重演执行不是观测库第一版功能。

### 3.2 采集与检索

- 使用原生工具事件捕获输入、成功和失败输出；调用开始但无结束事件时保留 incomplete。与现有 transcript 只读对账，不重跑工具。
- 为 obs_id 建立与原生 tool_call_id 的索引，并通过 post hook additionalContext 回传引用；仍可通过索引查询，不伪造成功引用。
- 对账本自身的查询不递归生成 observation，避免读取观测又产生观测的无限膨胀；其访问仅记录为审计事件。
- `obs.list(filters, cursor)`、`obs.search(query, filters)`、`obs.read(id, span)` 提供分页、关键词查找和按片段读取。第一版不引入 embedding 或模型摘要服务。
- 摘要若由 agent 编写，应作为账本主张并引用原文，不覆盖原始输出。观测中的指令性内容是数据，不是系统命令。
- 哈希可用于存储去重，但不合并独立调用身份，更不把相同来源的重复计算当独立支持证据。

### 3.3 共享边界

默认 lead 与 evidence-worker 可查询共享观测，但不自动把全部内容推入上下文。记录读取事件只证明内容被返回，不证明模型理解或采用。

普通 worker 的“独立探索”不能仅靠 brief 中一句话保证：它仍可能访问共享文件和账本。当前设计不包含盲态角色或两阶段可见性，不宣称探索彼此独立。

## 4. 决策账本

核心是 **Unresolved Analytical Decisions（未解决的分析决策）**：分析中尚未确定、可能影响样本、计算或结果解释的选择，而不是一般待办问题。例如缺失值处理、实体键、时间窗口、聚合权重和输出尺度。账本把这些选择与实际执行及结果连接起来；是否真的影响答案，需要执行证据，不能仅凭提出分叉就断言。

### 4.1 三类对象与证据关系

| 对象 | 最小内容 |
|---|---|
| Issue | 分析决策或最终答案问题、来源片段、关联分析步骤与影响范围；状态 open/resolved/unresolved，另有 needs_review 标记 |
| Candidate | 所属 Issue、具体备选、成立假设、execution_ref、outcome_ref、depends_on、提出者与版本；独立记录 freshness |
| Selection | Issue、选中 Candidate 或 unresolved、考虑过的候选、理由、证据引用、替代的旧 Selection |

Issue 可以是中间口径，也可以是最终答案问题；不能将两者混为同一个候选池。open 表示尚在分析，unresolved 表示已明确记录目前无法判别，resolved 表示已记录当前选择，不代表该选择已被证明正确。

Candidate 的执行绑定：

| 字段 | 作用与约束 |
|---|---|
| execution_ref（可选） | 引用具体 SQL、脚本快照或参数化分析配置；绑定代码/查询哈希、参数和输入数据版本，不只保存会被覆盖的文件路径。存在该引用不代表已执行 |
| outcome_ref（可选） | 引用上述方案某次实际执行的结果记录，绑定 execution_ref 的精确版本、执行 ID、状态、结果产物/哈希及 obs_id。失败或取消保留状态，不冒充有效分析结果 |
| depends_on | 引用该候选依赖的中间 Selection 的 ID 与版本；必要时引用上游 Candidate 的精确版本，形成可追踪的依赖图 |
| freshness | current / stale / unknown；current 只表示相对已登记依赖有效，不表示答案正确。依赖不完整时为 unknown |

两个可选引用可在提出时留空，后续以新版本补充。纯口径提案无需先执行；有 outcome_ref 时必须能追溯其 execution_ref，不允许把数值与产生它的方案脱离。多次执行保留各自记录，不能覆盖旧结果。未来 Counterfactual Executor 可以沿用同一契约写入执行与结果，无需改变三类对象；本版不实现执行器或自动展开方案。

例如，缺失值处理 Issue 可登记“删除缺失观测”和“填零”两个 Candidate，分别绑定对应 SQL/脚本及执行结果。codebook 中“未获得测量值”的定义可以反驳“缺失等于零”，但不能单独证明删除没有偏差；Selection 若选删除，应同时记录剩余假设和限制。这样既关联实际分析，也不把参考定义过度解释为唯一正确方案。

`EvidenceLink` 将观测片段连到 Candidate 或 Issue，包含：

- `relation`：supports / contradicts / contextual；
- `claim`：它具体支持或反驳哪句话；
- `scope`：证明计算、数据事实、题意解释，还是单位约定；
- `obs_id + span`：原始依据；题面等非工具材料用明确类型的 source_ref，不伪装成工具观测；
- `limitation`：适用条件、来源依赖和仍然未知的部分。

纯推测允许登记，但标记 hypothesis，不假装拥有观测支持。不强迫每个主张捏造引用。

### 4.2 最小接口

- `ledger.open_issue(question, source_refs, analysis_scope)`
- `ledger.propose(issue_id, alternative, assumptions, execution_ref=None, outcome_ref=None, depends_on=[])`
- `ledger.revise_candidate(candidate_id, expected_revision, changes, rationale)`：补充执行结果、更新依赖或重新确认；生成新版本，保留旧记录
- `ledger.attach(target_id, evidence_link)`
- `ledger.view(issue_id, since_revision)`：并列显示备选、支持与反证、未决问题和依赖，不按票数排序。
- `ledger.record_selection(issue_id, choice, rationale, considered_ids, evidence_refs, expected_revision)`

所有 agent 可提出备选和证据；lead 记录当前选择。纠错以新版本 supersede 旧条目，不能静默删除异议。worker 可对已有选择补充反证或提出重新考虑，不限制为必须有“新 obs_id”：旧证据的新解释同样可能有效。

字段校验确保引用存在、片段有效、版本一致，不校验自然语言推理是否成立。证据数量、引用次数、schema 合规均不当作可信度分数。

### 4.3 依赖失效与重新确认

中间 Issue 的当前 Selection 产生新版本、改选或转为 unresolved 时，账本自动将依赖旧版本的 Candidate 标记为 stale，并沿已登记依赖递归传播到下游候选，包括最终答案候选。不能只留下历史引用而继续把旧结果展示为当前有效。

- 记录失效来源、旧/新依赖版本和触发事件；已选中 stale 候选的 Issue 标记 needs_review，原 Selection 保留但显示依赖已失效。
- 选择更新和失效传播在同一事务中完成；新登记的候选若引用过期 Selection，立即标 stale。依赖引用必须存在，拒绝循环依赖，避免并发时漏标或无限传播。
- 首版保守地对 Selection 的任何新版本触发失效，包括仅修改理由；后续是否减少这类失效应另行验证，不能静默假设语义未变。
- stale 不代表原执行记录错误：它仍准确记录旧假设下的历史结果，但不能自动支持新假设下的最终答案。
- 清除 stale 必须生成新的 Candidate 版本，绑定最新依赖并提供重新确认依据。分析逻辑或输入改变时，应补充新的执行结果；若只是理由变化且计算配置不变，可明确说明并引用适用性证据复用旧结果。不得仅改一个状态字段。
- 重新执行得到相同数值也必须保留新的执行关联；上游重新确认不自动清除下游 stale，下游同样需要确认。并发期间依赖再次变化，确认操作应拒绝或继续标 stale。

`ledger.view` 必须显示 freshness、失效原因及待确认链路。未知依赖不能视为 current；自动传播只覆盖已登记依赖，不声称能发现脚本中所有隐含依赖。

### 4.4 更新不是裁决

新证据关联到已选择的 Issue 时，将该项标为 needs_review，并在视图中展示变化；不自动推翻选择、不阻止提交。lead 可以记录 retain、revise 或 unresolved 以及理由。未处理的变化在审计中保留。

needs_review 表示需要重新审视判断；stale 表示候选的依赖版本已经过期，二者不能混用。系统自动传播 stale，但不自动重跑、改选或接管提交。最终选择若仍引用 stale/unknown 候选，必须显式披露，审计记录为未完成依赖确认，不能算作有效确认链路。

例如两个过滤条件分别产生 A、B：执行输出只能证明各自结果；题面或数据定义才可能支持选择哪个条件。如果仍无法区分，记录不确定性。匹配评测 gold 不能成为运行时的裁决依据。

## 5. 存储与一致性

实现采用单个每运行证据存储：原始观测只追加，解释与决策版本化。使用 SQLite 事务保存索引、账本和事件，输出正文为内容寻址文件；先原子写 blob，再提交索引，避免悬空引用。

`workspace.trace` 从候选追溯到观测，也从观测反查引用的候选及选择；结果保留版本并限制规模。候选可以追加修订或撤回，证据关系可以撤回，但原始观测不随解释修改。无有效证据关联的主张明确显示为 hypothesis。

同一个组件支持 `observations` 和 `full` 两种运行配置，前者只暴露观测、产物读取与追溯，后者增加结构化候选、证据和选择。模式在运行初始化时绑定，不在同一运行中切换，后续消融使用独立工作空间。

原生 MCP 客户端可能为不同角色启动多个 stdio 服务实例；它们连接同一个 run store，而不是各建账本。事务、busy timeout、操作幂等键和 expected_revision 处理并发写入；冲突显式返回，不覆盖他人修改。数据库重试仅限本地事务，不触发模型或外部工具重试。

hook 写观测，MCP 暴露读取观测与写账本接口。所有存储限当前运行；run_id、路径和引用校验禁止跨运行访问及路径穿越。私有原文不写入公共报告。

同 UID 的 solver 有 Bash 时，文件权限和 MCP 接口不是对抗性只读隔离；第一版仅保证接口语义并离线检测不一致，不能宣传防篡改或身份认证。主机原始证据继续独立保留。

采集或存储失败必须标 degraded，保留原始 transcript 并披露缺失；不能静默声称完整。不得为补全采集重新执行付费调用。原生 lead 仍可正常完成原任务。

## 6. 原生集成与待验证项

源码位于 `harness/evidence_mas/`，这是我们自己的 MAS harness，而非一次性 study 脚本。`EvidenceMASCLI` 提供独立显式接入，加载 lead 研究提示、原生 evidence-worker 定义、合并 hooks 和同源 MCP 配置。探针在 `scripts/probes/evidence_mas.py`，只读跨运行分析归 `analysis/`。目录职责见 `harness/evidence_mas/README.md` 和 `harness/README.md`。

现有基线适配器及冻结提示保持原样。新适配器只在自己的启动参数中合并 hooks、替换空 MCP 配置和添加 worker。lead 可记录选择，worker 的 MCP 不暴露该工具，hook 另行拒绝原生 worker 使用 lead 选择工具。这是接口限制，不是同 UID 身份认证或安全沙箱。

`stale` 采用事务快照内的依赖图推导，而非异步更新缓存标记：Selection 写入提交后，所有后续视图立即递归显示失效原因。事件与历史版本足以追溯变化；不自动清除下游失效。`ledger.history` 提供版本读取，`artifact.read` 读取绑定内容。执行快照由调用者明确登记，不声称任意 Bash 的全部依赖已自动捕获。

服务器原生假 provider 已验证 lead 与后台 worker 的 MCP 可见性、自动观测、跨角色读取、候选证据到 lead 选择和双向追溯。以下仍需进一步验证，不能由一次成功探针推广：

1. foreground worker 与更多委派模式；当前探针覆盖原生后台 worker。
2. 真实模型是否遵守共享任务规则、理解并合理使用证据；假 provider 不能验证。
3. 原生失败/取消事件及大输出完整性的完整矩阵；组件测试不替代原生覆盖。
4. 高并发多 worker 冲突与异常中断后的原生进程状态；当前验证不代表穷尽这些情况。

参考：项目 `docs/cli-adapters.md`、`harness/_claude_hooks.py`；官方 [subagents](https://code.claude.com/docs/en/sub-agents) 与 [hooks](https://code.claude.com/docs/en/hooks)。官方在线文档可能超前于项目 pin；它们是扩展方向依据，不是本地兼容性证明。

## 7. 分阶段验证，不把整个 DEL 一次装上

第一步实现与验证数据结构、引用、并发和故障处理；本次已获授权在服务器执行离线测试。fake 事件与本地 MCP 子进程不证明真实决策收益，也不替代原生 Claude 探针。具体测试结果另行记录，不将未来的付费阶段视为已授权。

账本离线测试应覆盖：空执行引用、结果与执行版本不匹配、失败结果保存、多级依赖失效、无关分支不受影响、重复事件幂等、循环依赖拒绝、并发选择更新与候选登记、选择撤回、重新执行/有依据复用后的逐级确认，以及漏登记依赖时的 unknown。不得为测试触发真实模型或付费工具。

第二步可用现有轨迹回填观测和人工标注的小型账本，验证能否区分：已计算、已提出、已送达、已考虑、已选择。事后回填不能证明当时的 agent 会如何更新。

第三步如获单独付费授权，再比较同一研究组织的三种信息组织方式：原报告、报告加可检索观测、观测加结构化账本。保持模型、lead 决策权、任务规则和授权预算一致；观察总成本及新增检索负担。

固定候选/证据包的选择测试与端到端探索分开：前者隔离信息组织对选择的影响；后者才可能体现覆盖变化。候选池构造不得利用 gold 补入缺失答案；gold 仅用于运行后 host-side 评分。

重点指标：

- 最终答案候选覆盖率与覆盖条件下选择成功率；不把偶然数值出现计为提出候选。
- 候选/依据送达率、未处理反证、选择变化和记录理由；访问或自述不是理解的证明。
- 错改对、对改错、净收益；与参考约定冲突的案例单列。
- token、耗时、存储与检索开销；语义重复需人工定义与抽样审计，不能拿字面哈希代替。

成功首先意味着证据流可检查，其次才检验是否改善决策。若仅增加记录成本而没有减少信息丢失或改善选择，应报告负结果，不用它推导“必须取消 lead”。
