# Experiment 0: Claude Code Subagents 自然委派轨迹审计

日期：2026-11-03。只分析已有运行；新增 solver / judge 调用均为 0。

## 结论

**值得继续研究，但目前更清楚的证据是“返回的问题没有得到正确裁决”，而不是“子代理返回时丢掉了问题”。**

- `archeology-hard-5`：子代理返回了 BP 年龄的时间方向，父级仍把“later”按更大的 BP 数处理。可以确认局部时间解释错误，但不能据此解释与参考答案的全部差距。
- `astronomy-hard-12`：子代理明确返回“输入没有势场值/公式”和真实 epoch 日期，父级仍提交自建 `g*h` 场及包含 9 月 30 日的结果。缺失信息没有在交接时消失；问题发生在父级如何处理缺口。
- 存在子代理执行/报告错误，但也有父级纠错成功、最终评分正确的反例。不能用题目最终成败替代检查点标注。
- 多个评分失败案例已经完整返回不同口径、完整计算结果及理由。它们主要是待裁决的口径分歧；“报告中有参考数值”和“父级没改答案”均不足以证明交接损失或信心提高。
- 本样本没有确认“子代理内部已发现关键口径问题、返回时却遗漏”的完整链条；也没有确认可单独归入“执行正确、口径确定错误且未被返回指出”的纯净案例。

**本审计支持继续做机制研究，不支持“主要失败/主要成本由信息损失解释”，也不估计总体发生率。**

## 数据与取样

源运行：`outputs/current/runs/claude-code-subagents-20261102-01`，位于服务器项目目录。
原生 CLI：Claude Code 2.1.225；模型记录为 `deepseek-flash[1m]`。这里的“子代理”是被审计运行里的原生委派，不是本次审计另起研究代理。

源 summary 的 SHA-256：`08384c38e82c73499e2970e24a978fe6cf6930e0e71647bacec6243e2f308862`，与已保留三方比较记录一致。
summary 记录 104 题、180 次原生 SubagentStart、104/104 生命周期检查通过；84 道二元题评分 59 正确、25 错误。生命周期通过不是方法正确的证明。

本次先索引全批根上下文的委派请求/返回，再目的性选择 **11 题、21 个根级委派检查点**：2 题最终二元评分正确，9 题评分错误。优先选择有口径分叉、数值验证、原生完整子轨迹的案例，不是随机样本，也不是失败全集。另读了 `legal-hard-1` 和 `biomedical-easy-9` 作候选筛查，未把它们计入这 21 个检查点或已裁决样本。

选择使用最终评分及可见口径分叉，存在选择偏差；以下案例数不能除以 104、180 或 25 当发生率。根级 Agent 调用与原生启动事件也不应不加核对地视为一一对应。

证据目录：[delegation-audit-20261103-01](/Users/zhoujun/Desktop/MAS-information/outputs/current/reports/delegation-audit-20261103-01)。

| 文件 | 内容 |
| --- | --- |
| `source-summary.json` | 原始 summary 的本地副本；未改写原始评分 |
| `checkpoint-index.jsonl` | 全批原题、提交摘要、根级委派请求、TaskOutput 和完成通知索引 |
| `selected-transcripts.jsonl` | 9 个主样本的父子原生可观察消息、工具调用与返回 |
| `additional-transcripts.jsonl` | 另 4 个候选的同类证据，其中 hard-5、hard-12 纳入主样本 |
| `data-spot-checks.json` | 服务器只读独立复算；6 个输入文件的 SHA-256 和 Git blob 一致性 |
| `verify_data.py` | 产生上述原始数据抽查的脚本；不运行原 solver pipeline |

每条 transcript 记录保留服务器原文件绝对路径、原始物理行号、消息 UUID/时间；每份 transcript 有 SHA-256。排除了 thinking 块，不用不可观察心理状态推断信心。工具返回中若仅有 persisted-output 预览，不能把未展开部分当成已经审读的证据。

所有 104 个提交文件在提取时重新核对了评分绑定 SHA-256。本文没有重跑 benchmark、没有改答案/评分，没有部署或修改服务器源代码/环境。

## 标注规则

标注单位为“委派检查点中的具体命题”，不是整道题一个标签。一次返回可以主计算正确、旁支计数错误；同一道题也可以同时有输入不足和父级裁决错误。

| 标签 | 必要证据与排除项 |
| --- | --- |
| 1 子代理执行错误 | 实际给定子任务/数据下有可定位的计算、覆盖或报告错误；注明是否影响最终答案 |
| 2 执行正确，口径错误 | 局部实现正确，且有独立于评分的证据表明目标违背原题；单纯分工较窄不算错误 |
| 3 发现口径问题，返回遗漏 | 子轨迹明确发现关键问题；最终实际返回缺失；父级当时也未从其他渠道获得。工具输出出现某数值不满足这个条件 |
| 4 已返回，父级处理失败 | 问题确实进入父级可用上下文；之后的可观察实现/裁决仍违背已成立约束。“父级没改”本身不满足条件 |
| 5 判别证据不足 | 存在有根据的不同口径，题面/输入不能唯一确定；或任务缺失必要输入。保留替代方案，不靠 gold 反推口径 |

另设“正常/纠错成功”和“参考口径待核查”，否则会把正确委派及 benchmark 问题硬塞进五类错误。
第 4 类应区分“完全没提到问题”“明确拒绝另一解释”“声称已解决但没有充分理由”；不能统称父级忽略。

## A. 已返回的问题，在父级发生错误裁决

### A1. archeology-hard-5：BP 大小与“更晚”方向

结果：`36828.7165`；参考 `66158.3691`；评分 0。两个检查点。
证据：[additional-transcripts.jsonl:1](/Users/zhoujun/Desktop/MAS-information/outputs/current/reports/delegation-audit-20261103-01/additional-transcripts.jsonl:1)。原始父轨迹 `cedec970-82cf-4d0f-80a6-0d838ff5d2cd.jsonl`。

1. **原题**：Malta 的最北 Neolithic 样本；并列取更晚年份；取气候表最近年份的最大 Al。
2. **委派前解释**：父级已发现 14 个 Malta 样本坐标全部相同、经纬度表头疑似互换，`date` 6005–6412，Cal. BC 缺失；尚有“数值更大”与“年代更晚”的分叉。
3. **实际委派**：P95 的 radiocarbon 检查要求明确分别给出 numerical-larger 和 chronologically-later；P99 的 climate 检查只负责多个指定目标年份的最近 Al，不让它决定样本年份。两个子代理的第一条用户消息均保留在证据中。
4. **实际检查**：radiocarbon 子代理读取 Malta 全部 14 行，核对 `date` 与 Cal. BC 的区别、坐标并列、其他行校准字段；climate 子代理核对 Al 配对的 Age_ky、单位、缺失及最近行/并列。
5. **返回排除范围**：前者 S51 明确说较大 BP 更早，chronologically later 是 **6005**，numerically larger 是 **6412**；后者 S32 给出两条完整链：6005→36815.2633，6412→36828.7165。返回原文分别在父 P143、P142 的 queued completion 通知中保留；父级后续也明确引用两份检查。不存在关键信息未返回的证据。
6. **父级随后**：P156 把“later”直接写为 “larger stored year”，选 6412；最终 P184 沿用此说法。服务器原始数据抽查重现两条 Al 链。

**分类：4，局部明确的时间方向裁决错误。** 两个子任务主计算未见错误。但把 6412 改成 6005 也不会得到参考答案；因此不能说已证明这个错误导致了整道题的 gold mismatch。Al 表中出现参考数值 66158.3691，并未建立一条满足全部选择规则的解法。

### A2. astronomy-hard-12：缺失势场，被当成了可自行选场的许可

结果：`4344495.87`；参考 `66822738.84`；评分 0。两个检查点。
证据：[additional-transcripts.jsonl:139](/Users/zhoujun/Desktop/MAS-information/outputs/current/reports/delegation-audit-20261103-01/additional-transcripts.jsonl:139)。原始父轨迹 `58e71a1b-4994-4c74-bc23-b7803bfefb0b.jsonl`。

1. **原题**：9 月 2–29 日 Swarm-A，SP3 位置，对指定 mock geopotential field 插值再平均；给定 R 和 g。
2. **委派前解释**：父级已发现 NPZ 只有网格轴，并打算用自行构造的 `Phi=g*h`；日期按文件产品名选择 28 份文件。
3. **实际委派**：P109 让搜索代理找缺失的场值/公式、核对 SP3 实际时间；P113 让数值代理复算球形/椭球高度、不同能量公式及真实 epoch 日期过滤的结果。后者验证的是明确指定的候选计算，不是证明哪个场就是题目给定场。
4. **实际检查**：搜索代理检查 NPZ ZIP/NPY 结构及数据湖内容；数值代理解析 241,920 个位置，用两种 parser 对照、检查重复/缺失，分别给出全文件与截止 9 月 29 日的结果。
5. **返回排除范围**：数值代理 S42/P171 返回产品名 9/2–29 实际含 epoch **9/3–30**，按真实日期过滤的 `g*h` 均值为 **4344571.69**。搜索代理 S95/P203 明确返回：没有输入势场/公式；workspace 的 `g*h` 是本次求解新写的代码，**不是输入证据**。本次独立抽查确认 NPZ 只有三条轴。
6. **父级随后**：P205 将“没有给定场”推成“因此唯一可构造的是 g*h”；P217 提交全 28 文件结果，并注明真实日期版本是另一个数值，却仍称产品日期“matching the stated range”。

**分类：5（任务缺少场定义）与 4（父级将缺口视作已解决，且未遵守真实日期窗口）。** 可确认候选计算的局部数值验证成功，但不能确认其解决原题；更不能把所有差距归因于日期偏差，两个 `g*h` 均值都远离参考。不是返回遗漏。

## B. 评分正确的反例：局部错误不等于任务失败

### B1. biomedical-hard-7：旁支计数错误被父级纠正

结果/参考均为 `16`；评分 1。两个检查点。
证据：[selected-transcripts.jsonl:724](/Users/zhoujun/Desktop/MAS-information/outputs/current/reports/delegation-audit-20261103-01/selected-transcripts.jsonl:724)。父轨迹 `e266a498-3356-4417-a7a2-0362683e318a.jsonl`。

1. **原题**：significant genes by acetylproteomics 有多少。
2. **委派前解释**：父级已找到 README 描述完全对应的 `mmc3 / D-SE-acetyl`，尚需验证是否表头、其他 acetyl 表是否更合适。
3. **实际委派**：P90 让一个代理检查 XML/全部单元格、隐藏项和相邻列表；P94 让另一个比较 mmc6 的位点级 FDR 分析及 mmc2 缺失 sheet。
4. **实际检查**：主核对代理读取 XML `A1:A16`、核对 16 个唯一基因、无表头；替代解释代理计算多个 FDR 阈值下位点和基因数，核对文档与 workbook 实际 sheet。
5. **返回排除范围**：两者均支持 16；替代解释代理 S52 将相邻两个列表写成 **207/61**，而原始 XML/另一代理为 **208/62**。本次只读抽查确认 208/62/16。这个旁支报告错误没有改变它对 16 的推荐。
6. **父级随后**：P136 明确指出 207/61 错误，使用原始列表尺寸，最终提交 16。父级称其为 header-inference artifact；本审计只确认数字/报告错误，不把父级对错误起因的解释当成已证实因果。

**分类：替代解释检查点有 1；父级纠错成功。** 这是不能把“出现子代理错误”直接标成“失败由交接导致”的对照。

### B2. archeology-easy-11：主口径正确，搜索摘要混用抽样计数

结果/参考均为 `17.4274`；评分 1。两个检查点。
证据：[selected-transcripts.jsonl:219](/Users/zhoujun/Desktop/MAS-information/outputs/current/reports/delegation-audit-20261103-01/selected-transcripts.jsonl:219)。父轨迹 `4f735ba8-3e66-4fef-825a-a368e3b85b2a.jsonl`。

1. **原题**：每国保留人口最多的首都，平均纬度。
2. **委派前解释**：父级已采用 `capital=primary`、每国一行，初算 17.4274。
3. **实际委派**：P70 做独立语义/数值及边界核对；P71 搜索其他首都数据/字段定义。
4. **实际检查**：数值代理核对 250 个 primary、237 国、11 个缺人口但各国唯一首都，比较替代筛选；搜索代理扫描候选文件，并在一次 `nrows=5000` 的读取中计算 capital 分布。
5. **返回排除范围**：数值代理 S56 给出 237 纬度、总和 4130.2976、多方法平均一致；搜索代理 S66 明确保留“湖内没有 primary/admin/minor 定义文档”的限制。但它把前 5000 行的 admin=1311、minor=1067、null=2373 混写进完整数据摘要。其工具 S24/S26 可定位抽样来源；全表实际 admin=3625、minor=7263。本次抽查重现主答案与完整计数。
6. **父级随后**：P81 采用主计算，提交 17.4274，没有使用错误的旁支类别计数来确定答案。未见它像 B1 那样显式纠正这些计数。

**分类：数值检查正常；搜索检查点有 1（样本统计误报为总体摘要），未观察到最终答案受损。** 缺少文档的限制已返回，不是第 3 类。

## C. 不应误标为“返回遗漏”的评分失败

### C1. biomedical-hard-5：参考口径可疑，不能把通过 gold 的逆变换当成正确

结果 `1.6563`；参考 `2.6563`；评分 0。两个检查点。
证据：[selected-transcripts.jsonl:860](/Users/zhoujun/Desktop/MAS-information/outputs/current/reports/delegation-audit-20261103-01/selected-transcripts.jsonl:860)。父轨迹 `c4abb2c7-62a4-423b-87fc-28ae777cdaa0.jsonl`。

1. **原题**：研究内 serous tumors 的 variants/Mbp 中位数。
2. **委派前解释**：父级已找到 metadata，意识到样本纳入规则和 log inverse 是两个问题。
3. **实际委派**：P135 核对 12/13/14 个 serous 样本的 cohort；P136 独立测试 `2^x` 与 `2^x-1`、total 加和及每 Mb territory，要求完整报告所有中位数。
4. **实际检查**：cohort 代理比较 mmc1 排除标记与 mmc7 的 95 肿瘤集合；数值代理在有数据的样本上检查 SNP+INDEL=variant、零 indel 和总数/32.3 Mb 的一致性。
5. **返回排除范围**：数值代理 S50/P138 返回 12 样本下 `2^x-1`→1.6563、`2^x`→2.6563，并说明前者才满足内部关系；cohort 代理 S84/P142 支持 12 样本，但旁支 units note 简单写成 `2**x`，与数值代理冲突。父级没有遗失 2.6563，也不是只收到一个候选值。
6. **父级随后**：P145 明确采用有数值证据的 `2^x-1`；最终 pipeline/提交一致。本次独立只读复算重现两个中位数，`2^x-1` 与 total/32.3 的全表最大偏差约 8.7e-7。

**分类：主要为“参考口径待核查”，不是已确认的第 2/3/4 类。** cohort 代理的旁支转换建议不充分，不能把该冲突隐藏在“两个代理一致”里；父级在这一点作出了有证据的取舍。gold 数字来自已完整返回但被内部一致性检验反对的解法。

### C2. archeology-hard-7：距离定义已完整返回，父级明确选了另一种

结果 `292`；参考 `274`；评分 0。两个检查点。
证据：[selected-transcripts.jsonl:552](/Users/zhoujun/Desktop/MAS-information/outputs/current/reports/delegation-audit-20261103-01/selected-transcripts.jsonl:552)。父轨迹 `adee2260-1e2f-4ce3-b67f-550280523a9f.jsonl`。

1. **原题**：人口 over 100k 的现代城市，有多少距 Roman 城市 within 0.1 degrees。
2. **委派前解释**：父级已识别距离度量分叉；最终报告倾向把 degrees 当球面角距离。
3. **实际委派**：P52 检查古城侧质量/时代；P56 明确要求平面欧氏、经纬度盒、haversine、11.1 km 等多口径，不让子代理替父级裁决。
4. **实际检查**：数值子代理比较全部度量、人口边界、唯一城市/配对计数及临界点；数据代理检查坐标、年代、古城重复与名称匹配。
5. **返回排除范围**：数值 S47 给出 Euclidean=274、haversine=292、盒=295/296 等完整方法；P137/P140 完成通知含返回原文。证明差异来自度量，而非单纯去重/100k 边界；没有证明题目唯一指定哪种度量。
6. **父级随后**：P143 明确并列这些数值，P172 选择球面 292，并称平面为 naive；不是没收到 274，也不是没有讨论。

**分类：5，明确裁决的口径分歧。** 如研究目标是复现 benchmark 约定，可另标“偏离参考约定”；但仅凭题面/gold 不应标为返回遗漏或确定的语义错误。

### C3. legal-easy-19：条件分母分歧，不是交接损失

结果 `0.199`；参考 `0.523`；评分 0。一个检查点。
证据：[selected-transcripts.jsonl:1415](/Users/zhoujun/Desktop/MAS-information/outputs/current/reports/delegation-audit-20261103-01/selected-transcripts.jsonl:1415)。父轨迹 `76be25ec-ef1d-4d9e-bad4-f7ceedb0edbd.jsonl`。

1. **原题**：2024 fraud reporters 中损失 $1–500 的 proportion。
2. **委派前解释**：父级已有 numerator 516,308；知道 all reporters 与 reports with loss 两种分母。
3. **实际委派**：P59 要求两种分母、表脚注、对账及字面解释，不只是检查一个现成答案。
4. **实际检查**：子代理读取 amount-lost 原表及多份报告总数表，对分段、总数、38% loss prevalence 和脚注核对。
5. **返回排除范围**：S65/P107 返回完整 numerator、denominator 与 0.199/0.523 两个结果：516308/2600678 与 516308/987520。推荐全 fraud-report 分母，同时说明 loss-conditioned 读法及 reports≠unique people 的限制。
6. **父级随后**：P110/P121 选 0.199，明确写 0.523 只适用于“已报告金钱损失者”条件化。这是有理由的取舍，不是遗漏了参考解。

**分类：5。** 若另有来源明确定义任务分母，可再改标；当前不能用 gold 的 0.523 代替语义证据。

### C4. environment-hard-16：物理海滩与监测点，返回后被父级拒绝

结果 `75`；参考 `60`；评分 0。两个检查点。
证据：[selected-transcripts.jsonl:1184](/Users/zhoujun/Desktop/MAS-information/outputs/current/reports/delegation-audit-20261103-01/selected-transcripts.jsonl:1184)。父轨迹 `ba1d96e7-9655-416d-a665-262e24f4456b.jsonl`。

1. **原题**：2002–2023 无任何 violation 的 marine beaches 数；无数据年份安全。
2. **委派前解释**：父级已有按记录名分组的计算；知道同名跨社区及缺失标记问题。
3. **实际委派**：P118 从头复算多个 entity key；P122 专门核对 `@` 是否同一海滩的监测站、master list/datasheets 是否提供定义。
4. **实际检查**：两个代理读 22 年 CSV；entity 代理对照 Boston Harbor 清单与多个 beach datasheet 的站点列，计算保留社区/去社区、去站点后缀等方案。
5. **返回排除范围**：A S73 推荐 raw `(Community, Beach Name)`=75；B S128 推荐保留 Community、合并 `@` 站点=62，给出物理海滩/监测点证据；还返回去 Community 的 60。P195/P198 保留两份返回。两者都反对把相异社区的同名实体不加区分地合并。
6. **父级随后**：P201 明确知道 75 vs 62，P207 以“不能从 lake statewide 确定合并”为由选 raw 75；不是没看到实体问题。

**分类：5，另记父级裁决争议，暂不确认 4。** 子代理有支持 62 的实质证据，父级理由值得复核；但局部 master list 不自动决定全州实体映射。返回中有 60 也不证明那条丢失 Community 的链是正确解法。

### C5. environment-hard-7：missing EJ 不能因分布规律自动变成已知零

结果 `10.24`；参考 `10.87`；评分 0。两个检查点。
证据：[selected-transcripts.jsonl:1017](/Users/zhoujun/Desktop/MAS-information/outputs/current/reports/delegation-audit-20261103-01/selected-transcripts.jsonl:1017)。父轨迹 `1d5f3256-4313-4faa-9205-d74e276fa2b2.jsonl`。

1. **原题**：2023 marine samples 中，EJ population >50% 与 <25% 社区的 exceedance rate 差。
2. **委派前解释**：父级已发现 water 社区与 EJ 表覆盖不一致，需要决定 unmatched 社区如何处理。
3. **实际委派**：P80 要求独立比较 EJ 字段、join、样本/社区加权；P84 专门检验缺失=零是否成立、名称变体和对低组的影响。
4. **实际检查**：子代理查 EJ 表最小计数、百分比算术、名称规范、19 个未匹配 coastal communities、1373 样本/88 violations，计算两个 join 下的分组分母。
5. **返回排除范围**：A S57 返回 inner join=10.87、missing=0 的 left join=10.24；B S54 明说 “the file alone cannot prove completeness”，但基于非零下界/表结构推荐缺失=零。这些 caveat 与替代数值都在 P183/P186 返回。
6. **父级随后**：P188 概括“两者同一口径”，最终把未匹配社区称为 genuine zero-EJ，选 10.24。对“结构暗示”到“已知零”的推断缺少独立完整性来源。

**分类：5；另记父级把推断写成事实的风险，不把参考 inner join 自动当正确。** 数据湖记录尚不足唯一判别排除缺失和填零哪一个是原题目标。属于对已返回不确定性的处理问题候选，而非 3。

### C6. archeology-hard-1：端点、时间平均与年代体系均已返回

结果 `8347.1887`；参考 `8577.5298`；评分 0。两个检查点。
证据：[selected-transcripts.jsonl:1](/Users/zhoujun/Desktop/MAS-information/outputs/current/reports/delegation-audit-20261103-01/selected-transcripts.jsonl:1)。父轨迹 `2a2c0f0a-2718-4617-a1ff-37602468957a.jsonl`。

1. **原题**：Maltese area 首末 recorded people 时间的 average potassium，样本间线性插值。
2. **委派前解释**：父级已选 Malta archaeological records 的 min/max `date`，按 /1000 转 Age_ky，并倾向两个端点的均值。
3. **实际委派**：P140 语义/data mapping 代理收到完整题面，要求检验“people”、其他数据、替代口径；P144 climate 代理只收 K 质量和指定 6.005/6.412 两点插值任务。后一项本身是合法的局部核对，不能因未验证完整题意就标错误。
4. **实际检查**：语义代理检查 14 个 Malta archaeological rows、是否 Homo sapiens、date 与 Cal. BC、其他候选和多种均值；climate 代理核对单位、Age_ky 配对和两个插值算法。
5. **返回排除范围**：climate S43 排除配错 K/age、插值实现、单位缩放等局部错误；语义 S110 返回 endpoint 8347.1887、连续区间均值 8477.8648、其他候选，并明确 Malta 无 Homo sapiens、uncalibrated 14C 与 calendar chronology 有校准问题。P220/P230 返回原文。本次抽查重现两个端点和 endpoint mean。
6. **父级随后**：P233 称两份检查收敛到唯一 pairing 与 8347.1887，最终保留 archaeological activity 而非 human remains 的注记，但未让较窄插值核对证明更广的年代可比性。

**分类：5；存在“局部正确被概括成全局已验证”的候选，但不据此确认 2/4。** 不同 estimand 与校准缺口均已返回；本审计没有建立得到 8577.5298 的完整有效链，不能把先前其他运行的 gold 数值出现当本次证据。

### C7. archeology-hard-2：委派公式被返回描述成题目明确规定

结果 `50.25`；参考 `38.42`；评分 0。两个检查点。
证据：[selected-transcripts.jsonl:365](/Users/zhoujun/Desktop/MAS-information/outputs/current/reports/delegation-audit-20261103-01/selected-transcripts.jsonl:365)。父轨迹 `e96c57c1-1f1d-4eac-9106-fc988f7475ab.jsonl`。

1. **原题**：Across the years，wet-dry index increasing 的 years 百分比；没有显式规定 consecutive-difference 分母。
2. **委派前解释**：父级已识别 wet-dry block；在委派公式里把 years 操作化为相邻样本变化。
3. **实际委派**：P53 给出完整题面，同时明确要求 `increases / total valid consecutive differences` 和 time-weighted 对照；P57 搜索其他 wet/dry 数据源。
4. **实际检查**：数值代理读独立 proxy block 的 5993 点、等距 0.5 ka、5992 transitions、正/负/平变化；来源代理扫 header、xlsx 及相关字典。
5. **返回排除范围**：数值 S43 返回 3011/5992=50.25%，等距下 time-weighted 相同，以及反向时间 49.75%；却声称 “the question explicitly defines increases over valid consecutive differences”，实际是父级子任务公式，不是原题的明确约束。完整报告于 P122 返回；来源报告 P131 仅支持来源唯一，不能验证公式唯一。
6. **父级随后**：P125/P135 以独立检查一致为依据提交 50.25。本次原数据抽查重现 5993、3011 和 50.2503%，没有重现参考的 38.42。

**分类：局部计算正常；返回对题面约束的归因存在 1（报告命题错误），原题目标暂为 5。** 这是“父级自定规则在子代理报告中变成题面事实”的可观察现象。尚不能证明换公式能得到合法参考解，也不能推断其提高了父级信心。

## 对研究设计的修订

1. **把三条轴分开标**：局部实现是否正确；执行口径是否由原题/输入充分支持；关键约束在内部发现、返回、父级处理三个位置是否保留。不要先给整题一个“信息损失”标签。
2. **记录验证范围**：每次“检查通过”究竟排除了单位、代码、数据映射、时间方向、样本定义、还是仅一个指定参数下的计算。范围有限本身正常，父级将其当充分性证明才是待检机制。
3. **区分父级反应**：未提及、明确拒绝、保留 caveat、修复并重算、声称缺口已解决但没有新证据。A1/A2 与 C2/C3 的行为不应同标成“报告后没改”。
4. **保留错误但成功的对照**：B1/B2 表明子代理有局部错误不自动导致最终失败；C1 表明评分失败也不自动证明方法错误。
5. **新增 provenance 标记**：original requirement、parent assumption、worker inference、tool observation 必须区分。C7 中公式来源的改写比笼统“压缩损失”更精确。
6. **将“参考口径待核查”列为独立状态**：冻结原评分不改，另记可执行候选链、内部一致性证据和缺少的判别来源；不能以 gold 选择想要的解释。

下一步先固定标注表，再对全 104 题建立每个真实检查点的抽样框，核对根级调用、子级委派和重启/续接。按最终对错、题域、口径敏感性分层随机抽样或完整审计，记录入样概率，以任务为簇计算加权发生率/区间。当前目的性样本不补造抽样权重。

要判断“造成失败/额外成本”，还需明确完整合规替代解或受控干预；自然轨迹中先后出现、报告较长、父级说“confirmed”均不是因果证据。重跑/干预可能产生费用，本次没有授权也没有执行。

## 核验边界

已完成：原 summary 哈希比对、提交文件与原评分的 SHA 绑定、11 题父子可观察轨迹的六步恢复、6 个原始输入的服务器只读抽查。原始数据抽查使用现有 pandas/numpy 和标准库 XML/ZIP，没有安装依赖；首次 openpyxl 路径不可用，改用 workbook XML 后复算成功。

未完成：全部 180 次原生启动的完整机制裁决；其他 93 题的父子细读；独立第二标注者一致性；全题方法学正确性复核；运行环境全锁定验证；置信度/信心的测量；因果反事实与加权发生率、可归因成本估计。

没有运行项目测试或新的 benchmark attempt。本次验证属于已有结果的只读轨迹审计和小范围原始数据复算，不是新的端到端实验结果。
