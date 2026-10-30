# 硬隔离主实验：在现有代码上的改进方案（TravelPlanner）

状态：设计方案，尚未实现。基于 commit `244eca3`。本文不授权任何付费运行；
每个付费步骤都需要单独授权其规模，并使用新的输出目录。

## 0. 要回答的问题

在固定能力模板和逐任务冻结的 TeamSpec 下，把**信息隔离程度**作为实验因子：

- Q1：硬隔离团队相对于单 agent（信息完全汇总的参照）少解决多少题？
- Q2：同一团队在软隔离（worker 工具重叠）下能挽回多少？
- Q3：失败发生在获取、共享、传递、整合哪一环？在决策点补回事实能否改变决策？

不在范围内：通信策略更新/updater、新角色模板、按条件调提示词、单臂提高预算、BCP 改造。

选择依据：

- 信息可以被重新获取时，可能掩盖通信形式之间的差异；需要隔离对照验证。
- 硬隔离用短任务就能让交流成为唯一的信息通道：成本低，归因和因果回放都更干净。
- TravelPlanner 的每个决策相关事实都是数据库里的一行，可以不用 LLM judge 自动核对。
  官方 test 两阶段工具模式下 GPT-5 (high) 为 21.2%、o3 (high) 为 11.3%（arXiv 2509.25779），整体未饱和。
- 相关工作：HiddenBench（arXiv 2505.11556）和 Silo-Bench（arXiv 2603.01045）已在合成任务上
  展示了分散信息下的整合失败。本研究的区别是：信息要靠工具获取，按决策拆开获取/共享/传递/整合，
  并做因果补回和通信形式比较。

## 1. 实验臂

每题冻结两份规格：团队 TeamSpec（所有团队臂共用，指派文本与现在的 `team_for` 一致）和 solo TeamSpec。

| 臂 | 成员 | 领域工具 | 传递形式 | 作用 |
|---|---|---|---|---|
| `solo` | solver | 全部 5 个 | 无 | 信息完全汇总的参照 |
| `hard-summary`、`hard-structured`、`hard-retrieval`、`hard-adaptive` | leader + researcher + constraint_analyst + data_analyst | 按服务拆分，leader 没有 | 对应形式 | 主处理 |
| `hard-full`（可选） | 同上 | 同上 | full_context | 边界无损参照 |
| `soft-summary` | 同上 | 三个 worker 都有全部 5 个，leader 没有 | summary | 冗余对照 |

硬隔离拆分（`travelplanner-isolation-v1`）：

| 角色 | 工具 |
|---|---|
| researcher | `flight_search`、`distance_search` |
| constraint_analyst | `accommodation_search` |
| data_analyst | `restaurant_search`、`attraction_search` |
| leader | 无，只有通信工具 |

拆分依据：每个工具对应一个独立的服务提供方；全队工具并集覆盖整个任务；每个成员仍拿到完整公开任务；
leader 只做协调，与 `docs/leader-led-team.md:60` 中 Leader 的权限意图一致。拆分在看到任何结果之前冻结，
所有形式一致。

与旧 pilot 的区别：旧 pilot 里 leader 也有全部工具，属于全员冗余，
结果不与本实验合并。

## 2. 代码改动

按依赖顺序实现。每一步都先在服务器上跑离线测试。

### 2.1 隔离档位：`benchmarks/travelplanner/adapter.py`

- 新增 `ISOLATION_VERSION = "travelplanner-isolation-v1"`、`ALL_TOOLS`（5 个工具名，排序）和 `PERMISSION_PROFILES`：

  ```python
  PERMISSION_PROFILES = {
      "hard": {"researcher": ("distance_search", "flight_search"),
               "constraint_analyst": ("accommodation_search",),
               "data_analyst": ("attraction_search", "restaurant_search"),
               "leader": ()},
      "soft": {"researcher": ALL_TOOLS, "constraint_analyst": ALL_TOOLS,
               "data_analyst": ALL_TOOLS, "leader": ()},
      "solo": {"solver": ALL_TOOLS},
  }
  ```

- 新增 `permissions_for(regime, spec, tools)`，校验以下几点，不满足就抛错（属于初始化失败，不算该臂答错）：
  - 每个成员都有绑定，工具名都存在；
  - worker 的工具并集等于全部 5 个工具；
  - hard/soft 下 leader 的工具为空。
- 新增 `solo_for(request)`：`select_team(request, {"solver": SOLO_ASSIGNMENT}, selector="travelplanner-solo-v1")`。建议文本：

  > Plan the complete trip yourself: find feasible transport, lodging, meals and attractions;
  > verify joint constraints (dates, cities, budget, minimum nights, house rules, room type,
  > cuisines); produce the required final JSON itinerary.

- `tasks()` 增加 `horizons=((3, 1),)` 参数，默认行为不变（`adapter.py:48`），为之后的 5 天/2 城任务留接口。
- `team_for` 不改：指派文本属于冻结的 TeamSpec，由所有团队臂共用。
- 不改 `harness/pool.py` 的 `bind_permissions`：这里用显式的环境绑定版本，profile 及其 digest 写进 manifest。

### 2.2 运行时：`harness/agent_team.py`

1. **工具目录。** 团队运行时，在每个成员的初始消息（`agent_team.py:322-327`）里加入
   `tool_directory={role: [tool names]}`，只列工具名，不含任何观察内容。硬隔离下成员必须知道谁能查什么，
   否则"该问谁"会成为没被测量的混杂因素。它由 `permissions` 推出，而 `permissions` 已在 control 里。solo 不加。
2. **solo 收尾一致。** `call()` 中 `agent_team.py:81` 的 `len(self.spec.members) > 1` 让 solo 没有收尾预留：
   solo 用完调用上限会直接 `incomplete`，团队却会进入 `budget_finalization`，对比因此偏向团队。
   去掉这个条件，让 solo 走同一套 `finalize_budget`，并更新受影响的测试。
3. **版本号。** 上面两处改变了消息格式和收尾协议。把 `agent_team.py:68` 的 `explicit-completion-v4` /
   `isolated-encoder-v4` 升到 v5，保证新旧运行不会被合并。
4. **编码器不变，但要写明。** 编码器读取发送者的完整上下文（`agent_team.py:211`），可能补出发送者本没打算说的事实，
   "没共享"这一类会被部分吸收。pilot 保持现状，避免改变处理；确认现象存在后，再考虑做"只看 intent"的消融。

不需要改：ACL、证据 id、读取工具、队列、共享预算。硬隔离下，leader 在 Retrieval/Adaptive 中通过
`read_evidence` 读取 worker 授权的原始行，这正是"付费取回原始证据"的路径。调用自己权限外的工具会得到
`Unknown tool`，不消耗预算（`harness/agent.py` 的 `run_tool`）。

### 2.3 驱动：`scripts/travelplanner/isolation.py`（付费）与 `scripts/travelplanner/isolation_offline.py`

- 每个臂映射为 `(regime, form)`。solo 传一个不起作用的 form（如 `summary`），结果里记录臂名。
  `RunSpec.condition` 用臂名（如 `hard-summary`，可安全用作文件名）。
- 每道题内轮转各臂的执行顺序（沿用现有驱动的做法）。`--concurrency` 写进 manifest，与 BCP 驱动一致。
- control 检查：同一 (task, regime) 内各形式的 control digest 必须相同；不同 regime 之间按设计不同。
- `valid_final` 改为按 `row["days"]` 校验天数，现在写死为 3（`scripts/travelplanner/run.py:28-35`）。
- 评分用 `native.grade`，以 `audited_correct` 为准；环境错误保持 ungraded。
- 授权开关分两档，按实际规模命名，例如 `--authorized-calibration-14-runs`、`--authorized-pilot-140-runs`。
- 停止规则：校准阶段任何非 completed 结果都停下检查（沿用 BCP 的做法）；pilot 阶段只在 `error` 时停。
- manifest 冻结以下内容：任务 id 及选择规则、臂列表、权限 profile 及其 digest、两份 TeamSpec、各项上限、
  模型、价格、并发数、源码 digest、驱动 sha256。

离线版用脚本化策略覆盖全部 7 个臂，每个 worker 只调用自己权限内的工具。另外专门安排一步：
让 leader 尝试调用领域工具，断言调用被拒且预算不变。

### 2.4 任务选择

- 候选：validation 中 3 天/1 城的 60 题，去掉已用过的 1、2、60、61、120、121，剩 54 题。
- 排序：`SHA256("tp-isolation-20261029:" + task_id)`，不看答案，也不看任何结果。
- 校准：按排序取 easy、hard 各 1 题。
- Pilot：从其余题目中按排序取 easy 7、medium 7、hard 6，共 20 题，与校准不重叠。
- 之后的主实验：其余 3 天题，加上 5 天/2 城的 60 题（2.1 已留接口）。

### 2.5 事实账本：`benchmarks/travelplanner/facts.py` 与 `scripts/travelplanner/facts.py`

benchmark 专用代码放在 `benchmarks/`，`analysis/` 保持通用。对每个 run，确定性地回答：最终方案里的每个实体
及其关键属性，是谁获取的、有没有到达决策者、在哪里变了样。

1. **解析最终方案**：航班号、自驾/打车段、三餐、景点、住宿。名字和城市的拆分必须与原生评分器一致：
   在 `native_worker.py` 加一个私有操作 `entities`，复用上游的 `get_valid_name_city`，避免自写解析产生假的"扭曲"。
2. **来源索引**：从 `evidence` 事件（owner、tool、arguments、rows）建立"名字 → [(evidence_id, owner, t, row)]"的索引，
   航班用 Flight Number 作键。失败的工具调用本来就不会进入 evidence。
3. **每个实体的记录**：
   - `acquired_by` / `first_t`：哪些成员的观察里出现过这个精确名字。
   - `in_decider_input` 与 `path`：是否出现在 leader 最后一次决策调用的输入里（复用 `analysis.information.decision_case`），
     以及经由哪条路径到达：自己的观察（只有 solo）、哪条 `incoming_handoff`、哪次 `read_evidence`。
   - `variant_of`：没有精确匹配时，找最接近的已观察名字（例如 difflib 相似度 ≥ 0.85），并定位这个变体第一次
     出现的位置：哪个成员的 assistant 消息 → `peer_queued` → `peer_handoff` → final。这就是 Surachee 那条链的自动版。
   - `qualifiers`：住宿的 minimum nights、maximum occupancy、room type、house_rules、price；
     餐厅的 Cuisines、Average Cost；航班的 FlightDate、Price、DepTime、ArrTime。逐项检查该值是否与实体名
     出现在 leader 输入的同一条消息里。这是 receipt 级的启发式，只记 true / false / unknown。
4. **把原生失败项连到实体**：
   - `is_valid_information_in_sandbox`：实体不在库里，查 `variant_of`，区分扭曲和凭空编造；
   - 住宿相关（最少晚数、`valid_room_rule`、`valid_room_type`）：连到住宿属性；
   - `valid_cuisine`：连到餐厅菜系，注意出发城市的餐不计入；
   - `valid_cost`：连到各项费用；
   - 交通相关：连到交通方式冲突；
   - 其他：记为 `unlinked`。

   每个失败项打一个阶梯标签：`not_acquired`、`acquired_not_in_input`、`distorted_at_boundary`、
   `in_input_but_violated`（到达后仍违反，属于整合或推理问题）、`unlinked`。
5. **冗余指标**（主要用于软隔离）：不同成员重复执行相同 (tool, arguments) 的次数。
6. **输出**：每个 run 一份 JSON，每个臂一份汇总。`semantic_attribution` 保持 `unknown`，`causal_attribution`
   保持 `not_tested`。这些标签不是语义损失率。

测试用合成 trace 覆盖四种情况：获取后经 handoff 到达；获取了但没到达；在边界上被扭曲（Surachee 链）；到达了但仍违反。

### 2.6 因果回放：`harness/replay.py` 与 `scripts/travelplanner/replay.py`（付费）

通用部分只做一件事：重建某次决策调用的精确输入，追加一条补充消息，再调用一次模型。

```python
def decision_messages(events, agent, call_t):
    call = next(e for e in events if e["type"] == "llm_call" and e["t"] == call_t)
    return contexts(events, upto=call_t)[agent][:call["context_len"]]
```

- 重建出的消息（含 `reasoning_content`）应与原始请求逐条一致。`team_state` 本来就记录在 trace 里，可以复现。
  工具 schema 从 trace 中 `team_spec` 的 control 重建（该角色的领域工具加通信工具，按名字排序，与 `Agent.__init__` 一致）。
- 三个回放臂，每臂 k=3 次，模型设置不变。发送同样的工具 schema，但用 `tool_choice="none"`
  （与 `finalize_budget` 相同，保住缓存前缀）：
  - `repeat`：原样重放；
  - `restore`：追加 `{"replay_supplement": {"kind": "observation", "rows": [...]}}`，内容是相关实体的原始
    数据库行；扭曲的情形下用正确实体的行；
  - `control`：同样的信封，内容换成同一工具输出中未被采用、且长度最接近的一行（规则需预注册）。
- 用原生评分器评分，结果写进新的输出目录和 manifest，绝不写回原 run。
- 选例：pilot 中 solo 通过、而某个硬隔离臂失败，且失败项能连到某个已被 worker 获取的实体或属性的情况。
  最多 15 例（上限需预注册）。
- 解读：只说明"在决策点补回这个事实是否改变决策"。单次调用不允许后续工具，所以这不是整条轨迹的因果结论。

### 2.7 HiddenBench 阳性对照（可选，可与 2.5 并行）

- `benchmarks/hiddenbench/adapter.py`：HF 数据集 `YuxuanLi1225/HiddenBench`，固定 revision 和 SHA256，先核实许可证。
- 映射方式：选项和共享事实放进公开任务；每个 worker 的独有事实放在它专属的无参工具 `read_private_briefing` 后面，
  这样证据事件、ACL 和回执都不用改。leader 没有私有工具，最终输出选项 JSON；solo 用一个返回全部事实的工具。
- 臂：`solo`、`hard-summary`、`hard-structured`。
- 结果写成"HiddenBench-derived"，不能与原论文讨论式协议的数字直接比较。
- 作用：证明这个 harness 能复现已知的 hidden-profile 落差，并在最纯的设定下看各形式之间有没有差异。

### 2.8 预注册：`analysis/criteria.py`

新增独立的一块，不动现有 P1–P4 的 `THRESHOLDS`。下面是建议的默认值，需要在校准前定下来：

```python
ISOLATION_V1 = {
    "solo_reference_min": 0.60,  # solo 通过率低于此值时，团队落差无法解读
    "mas_specific_min": 0.20,    # solo 通过且 hard-summary 失败的任务占比
    "boundary_share_min": 0.50,  # 上述失败中带边界类标签的占比
    "restore_pass_min": 2 / 3,   # restore 臂的通过比例
    "control_pass_max": 1 / 3,   # control 臂的通过比例
    "incomplete_max": 0.20,      # 任一臂未完成占比的上限
}
```

pilot 之后的决策：

- solo 通过率低于参照下限：任务对汇总参照也太难，先更换任务档位；
- MAS 特有失败占比不到阈值：TravelPlanner 硬隔离下现象不成立，如实报告负结果；
- 现象成立、边界类标签占多数，且回放能翻转决策：进入主实验。

`scripts/analyze.py` 增加预注册对比的配对 McNemar 检验（`analysis/stats.py` 已有实现）：
solo vs hard-summary、soft-summary vs hard-summary、hard-full vs hard-summary。四种硬隔离形式之间只做探索性比较。
未完成的 run 同时报告两种口径：算作未解决，以及剔除后的敏感性分析。

## 3. 步骤、关口与预算

只有 CNY 0.29/run 是实测单价（TP pilot 03，全员冗余的团队）；其余都是估计，以校准实测为准：
solo 约 0.15、硬隔离团队约 0.4、hard-full 约 0.8。当前账户余额 CNY 214.44。付费步骤避开
工作日高峰（UTC 01–04、06–10，价格翻倍）。

| 步骤 | 内容 | 付费 | 估计花费 |
|---|---|---|---|
| 0 | 实现 2.1–2.5 和 2.8，离线测试全部通过 | 否 | 0 |
| 1 | 校准：2 题 × 7 臂 = 14 runs | 需授权 | CNY 5–10 |
| 2 | 根据校准冻结上限（所有臂相同）、写定阈值、新建目录 | 否 | 0 |
| 3 | Pilot：20 题 × 6 臂（加 hard-full 共 7 臂）= 120–140 runs | 需授权 | CNY 40–60 |
| 4 | 事实账本和复核包 | 否 | 0 |
| 5 | 回放：最多 15 例 × 3 臂 × 3 次，约 135 次单调用 | 需授权 | CNY 3–8 |
| 6 | HiddenBench 子集（可选） | 需授权 | CNY 10–20 |
| 7 | 主实验（过关后）：其余 3 天题加 5 天/2 城，考虑每臂重复 2 次 | 需授权 | 另行估算 |

上限的起点沿用 pilot 03：tool_budget 30、max_calls 48、max_messages 24、max_reads 12、
max_input_chars 800,000、finalization_reserve 1。硬隔离下消息会变多，校准后再定；一旦定下，所有臂相同。

## 4. 需要先拍板的决定

1. 2.8 的阈值，必须在校准前写进代码。
2. 是否包含 `hard-full`：它是硬隔离下的边界无损参照，但单价最高。
3. 编码器是否继续读取发送者的完整上下文。建议 pilot 保持不变。
4. 软隔离臂只配 Summary（建议，省钱），还是配全部四种形式。
5. pilot 是否用 solo 结果做任务准入。建议不做，作为无条件估计；主实验若要做，必须预注册，并重跑团队臂。

## 5. 验收清单

- 服务器上全部测试通过（现有测试加新增测试）。
- 离线驱动的 7 个臂全部 completed，trace 完整；同一 (task, regime) 内 control digest 一致，不同 regime 之间不同。
- 硬隔离下，leader 调领域工具、researcher 调住宿工具都会被拒，且不消耗预算。
- solo 撞上调用上限时进入 `budget_finalization`。
- 事实账本在四种合成 trace 上给出正确标签。
- 回放重建的消息与原始决策输入一致（digest 相等）；restore 和 control 只在追加的那条消息上不同。
- 新 manifest 包含 2.3 列出的全部冻结项。
- 实现后更新 `docs/experiment1.md` 中的候选状态，并在 README 的 Design 列表里加上本文链接。

## 6. 不要做的事

- 不复用旧输出目录，不合并旧 pilot 的结果。
- 不因为某个臂失败，就单独调高它的上限或修改提示词。
- 不从 pilot 失败的任务里挑选主实验样本。
- 不把 receipt 级标签当成语义损失率，也不在回放之外推断"如果 leader 看到了会怎样"。
