# 0903 批次 SOP 复盘

证据截止点：2026-09-04 16:39:55 +0800。

本报告冻结当时工作区中的 `candidates-0903/`、
`jobs/production-construction-20260903/`、
`jobs/production-construction-round2-20260904/`、`instances-round2/`、
`instances-round3/` 和两份 `exports/quality-passed-*`。以 `jobs/*/artifacts/build/`
里的 raw Harbor evidence 为事实源；实例目录和 exports 只用于核对复制与交付关系，不重复计算
同一轮。所有分数均由当前 `parse_scores.py` 从具体 trial 的
`verifier/reward-details.json` 重读，不采用 `resume.md` 中的外推值。

本批次共有 27 个候选、27 个首批 job 入口、17 个至少留下一个 `round-NNNN` 的任务、7 个拥有
“可读的最新双臂 round + 与最终 task 一致的 digest”的任务。另有 3 个任务只以可运行反例
支持“明确错误”类规则，不参加分差策略的跨任务复现计数。

## 证据清单

| 任务 | 纳入/排除 | 使用的 round | digest / validity | 原因 |
| --- | --- | --- | --- | --- |
| `1410f840-5034-497d-90ab-db7004351f1a` | 纳入 | life1 `0001→0002` | `0002` 匹配；target `4/0`，solver `4/0` | 最终轮可读且达标；有明确的判据修复前后链。 |
| `1c854112-927a-4765-b694-d3d442c2eeef` | 排除 | — | 无 result、无 artifact、无 round | 没有可用于任务设计的 raw evidence。 |
| `22ca05d3-8c78-4c45-ae57-3e577c2939c4` | 排除 | — | Daytona 环境失败；无 round | 运行故障只说明证据不可用。 |
| `26117e32-539f-4866-bf2e-ef0245723ffa` | 纳入（仅明确错误） | life1 `0001`；`0002` 作废 | `0001` 混编且不匹配最终 task；`0002` 无 included trial | raw 证据证明运行中修改 tests 会产生混编轮；不用于 R 或策略结论。 |
| `287f5217-e3f6-42ca-a010-a9b329d1e786` | 纳入（仅明确错误） | life1 `0001`、life2 `0002`；本地 alt 反例 | life2 `0002` target `4/0`、solver `4/0`，但不匹配最终 task | round 只记进度；持久化的行为等价反例可证明文本绑定和共享前置失真。 |
| `2ccb050c-1b54-4586-a547-b819de4567c3` | 纳入 | life1 `0001→0002→0003` | `0003` 匹配；target `3/0`，solver `3/0` | 三轮可比修改，最终轮可读且达标。 |
| `387bef85-101a-41c6-a103-1ef39c2d219c` | 排除 | — | outer `UnknownApiError`；无 scoring round | 只有运行进度。 |
| `453cbac9-2f9e-4e51-9315-0a3cdc67305c` | 排除 | — | 无 result、无 artifact、无 round | 没有 raw evidence。 |
| `49bb6e22-8ce0-4b4a-8152-3012de4ecf5f` | 排除 | life1 `0001→0003` 仅作反证 | 最终 `0004` 无 included trial；此前 round 均不匹配最终 task | 可说明过程现象，但不能支撑最终 task 或跨任务因果。 |
| `52efdaea-1808-4432-a4c9-2285a08f5de7` | 纳入 | life1 `0001→0002→0003→0004` | `0004` 匹配；target `3/0`，solver `2/1` | 完整的负向对照：四轮有效但一直未形成足够分差。 |
| `667b8927-a860-4674-9e33-6e58799250e1` | 排除 | life1 `0001→0002` | 两轮均缺少 parser 所需 job config | 不可比较的证据。 |
| `69dfba31-0bda-451c-8c06-28db4b536c9c` | 纳入 | life1 `0001→0002` | `0002` 匹配；target `4/0`，solver `4/0` | 最终轮可读，是“去掉白送信息并不必然增大分差”的反证。 |
| `78e9cba6-adae-43ff-8f83-41217669a2ad` | 排除 | — | Daytona 环境失败；无 round | 运行故障，无任务设计结论。 |
| `7d289736-da89-49d4-85c1-d3fd3bb91be8` | 排除 | life1 `0001→0002` | 两轮可读，但均不匹配最终 task | 只记录任务仍在变化，不能归因。 |
| `84204b2d-dfe9-4c11-96f8-5d5ff0fbbd76` | 排除 | life1 `0001` | 无 included resolved model | 无有效双臂读数。 |
| `87d51bdf-695f-47d9-b6fa-2153f48dba69` | 排除 | — | 无 result、无 artifact、无 round | 没有 raw evidence。 |
| `8818d381-1e17-42ad-bc27-5352437c8f84` | 排除 | — | Daytona 环境失败；无 round | 运行故障，无任务设计结论。 |
| `8a9ab226-d68e-4d2d-9e20-3742b8cbb93a` | 排除 | — | agent 非零退出；无 round | 只有运行故障。 |
| `95713311-3076-425a-a708-fff42aee6f28` | 排除 | life1 `0001→0002` | `0002` target `1/1`、solver `2/0`；两轮均不匹配最终 task | 最新 task 已变化，旧读数只说明进度。 |
| `a3e92222-6399-4c51-99a4-f2af6b5d5c72` | 纳入 | life1 `0001→0002→0003` | `0003` 匹配；target `3/0`，solver `2/1` | 完整的负向对照：三个能力轴均饱和。 |
| `ade66e4d-8b3f-4bd4-ad4d-3f93c67a47bf` | 排除 | — | 无 result、无 artifact、无 round | 没有 raw evidence。 |
| `b1b9aff6-c15e-4374-a965-111bda5c89b4` | 纳入 | life1 `0001→0002→0003→0004` | `0004` 匹配；target `3/0`，solver `2/1` | 四轮可比修改，最终轮可读且达标。 |
| `b4f12661-03e5-45ce-a820-6ee382d03074` | 排除 | life1 `0001→0003` | `0001/0002` 无 job config，`0003` 无 included trial | 没有一轮可读双臂证据。 |
| `bf76425d-07b8-4940-b4bc-17b682a886e3` | 纳入 | life1 `0002`；本地单点反例 | `0002` 匹配；target `2/0`，solver `2/0` | 最终轮可读且达标；`0001` 因默认 attempt 元数据缺失不用于因果。 |
| `c0ae3ac3-50ec-4262-a7b7-c0ac0f7f0188` | 纳入（仅明确错误） | life1 `0001` 的 verifier 失败 + `preflight.py` 复现 | 两轮均无完整双臂 included trial | 完整 tests layout 中的非法 judge 名可在任何 programmatic criterion 前杀死 verifier。 |
| `c43673d3-3a47-4b31-a6a0-9260e7ba217d` | 排除 | — | outer `UnknownApiError`；无 round；空 resume | 无任务设计证据。 |
| `eeb26954-397b-4062-aedb-8b4fc03a21dc` | 排除 | life1 `0001` | 无 included resolved model | 本地检查可作旁证，但不计跨任务 round 复现。 |

### 可读 round 汇总

| 任务 | round | target_mean | solver_mean | R | 与最终 task |
| --- | --- | ---: | ---: | ---: | --- |
| `1410f840…` | `0001→0002` | `0.6165→0.6591` | `0.9432→0.9858` | `0.5299→0.4957` | `0002` 匹配 |
| `2ccb050c…` | `0001→0002→0003` | `0.6848→0.9883→0.6024` | `1.0000→1.0000→0.8655` | `0.4603→0.0118→0.4368` | `0003` 匹配 |
| `52efdaea…` | `0001→0002→0003→0004` | `0.9254→0.8922→0.8782→0.8920` | `0.9378→0.9503→0.9643→0.9373` | `0.0134→0.0652→0.0981→0.0508` | `0004` 匹配 |
| `69dfba31…` | `0001→0002` | `0.7998→0.8961` | `0.9446→0.9188` | `0.1810→0.0253` | `0002` 匹配 |
| `a3e92222…` | `0001→0002→0003` | `0.9861→0.9962→0.9945` | `0.9861→0.9962→0.9959` | `0→0→0.0014` | `0003` 匹配 |
| `b1b9aff6…` | `0001→0002→0003→0004` | `0.9257→0.7664→0.4967→0.3333` | `1.0000→0.8662→1.0000→0.9941` | `0.0802→0.1302→1.0132→1.9823` | `0004` 匹配 |
| `bf76425d…` | `0002` | `0.4684` | `0.9684` | `1.0675` | `0002` 匹配 |

注意：`52efdaea…/resume.md` 曾把外推值写进实测表，raw round 重读后的 `0003` 是
`0.8782 / 0.9643 / 0.0981`，不是该文件旧记录里的 `0.9358 / 0.9641 / ~0.030`。
本报告只使用上表的 raw 值。

## 逐任务证据链

### `1410f840-5034-497d-90ab-db7004351f1a`

- **可观察修改：** 在 `0001→0002` 之间补齐自查程序合同，并把裸文本匹配改成只识别真实调用；
  target `0.6165→0.6591`，solver `0.9432→0.9858`，R 保持在 `0.4957`。
- **机制判断：** 修复后 solver 提升而 target 的六个自查能力项仍成簇失败；跨两轮 8 个 target
  均未通过命名常量要求、8 个 solver 均通过，支持真实能力差而非抽样波动。
- **明确缺陷：** solver 独立计算预期但在注释里提到被测函数名，旧判据按裸子串误判；
  `resume.md` 给出了可运行反例和 `_code_only()` / `_calls()` 修复。
- **被推翻判断：** target/solver 在 `derives_expectation` 上共同失败不是删 test 的充分理由；
  先复现后确认是文本绑定，修复后仍保留真实难度。
- **尚未跨任务复现：** “交付一个会主动找出自身错误的上位机自查程序”作为能力轴只在本任务验证。
- **raw：** `jobs/production-construction-20260903/1410f840-*/artifacts/build/evidence/round-000{1,2}`。

### `2ccb050c-1b54-4586-a547-b819de4567c3`

- **可观察修改：** `0001→0002` 把本应从固件推导的宽度和滚动规则直接写进题面，target
  `0.6848→0.9883`、R `0.4603→0.0118`；`0002→0003` 撤掉答案式散文、补组合 fixture
  并按推理量组织 criterion，target 降到 `0.6024`、R 回到 `0.4368`。
- **机制判断：** `0003` 的 target 呈两低一高双峰，存在 `0.9649` trial 证明规则可由公开固件
  推出，两个 `0.4211` trial 又证明发现与组合过程有区分度；不是欠定或共同失败。
- **明确缺陷：** 初始 Dockerfile 带入与纯 Python 任务无关的多套构建链；若干变异不敏感，
  后用 `pair.json` 与 mutation scan 关掉覆盖空洞。运行成本改进不用于 R 因果。
- **被推翻判断：** “把推导结论讲得更清楚不会伤害分差”被 `0002` 直接推翻。
- **尚未跨任务复现：** “题面只指向权威固件、让候选自行推导关键语义”只有本任务形成清晰的
  修改前后闭环，故只进技巧附录。
- **raw：** `jobs/production-construction-20260903/2ccb050c-*/artifacts/build/evidence/round-000{1,2,3}`；
  定向变异在同一 build 的 `evidence/analysis/`。

### `52efdaea-1808-4432-a4c9-2285a08f5de7`

- **可观察修改：** 连续增加 `render`、`ingest`、`downlink` 能力轴并重排权重，四轮 target
  始终在 `0.8782–0.9254`，R 始终不超过 `0.0981`；最终 `0004` 为 `0.8920 / 0.9373 / 0.0508`。
- **机制判断：** 最终轮 87.6% 的 criterion weight 两臂都满分，只有 4.7% 的正向分差质量；
  新轴仍处在两个模型共同饱和区，不是单纯增加 mass 就能解决。
- **明确缺陷：** 旧 notes 把权重外推值误记为实测并一度影响方向；raw 文件重读纠正。
  若干源码不能定案的值被主动排除，避免凭空发明行为。
- **被推翻判断：** “新轴 + 高权重 + 本地 naive 低分即可预测真实 target 低分”被四轮 raw 结果推翻。
- **尚未跨任务复现：** 本地 naive / gbk 错臂适合淘汰明显无效判据，但其绝对分数不能估计 target。
- **raw：** `jobs/production-construction-20260903/52efdaea-*/artifacts/build/evidence/round-000{1,2,3,4}`。

### `69dfba31-0bda-451c-8c06-28db4b536c9c`

- **可观察修改：** `0001→0002` 移除私有命名绑定，把题面从逐条答案改为合同 + 源码指针，并把
  权重温和移向集成；target `0.7998→0.8961`，R `0.1810→0.0253`，没有得到预期提升。
- **机制判断：** 两臂共同满分的 weight 从 59.8% 升到 80.1%，正向分差质量只剩 5.2%；
  说明主要问题是能力面饱和与白送权重，不是某一条低通过率 test。
- **明确缺陷：** 初始 599/1056 weight 绑定题面未声明的私有字段/变量命名；另有一次把
  `GROUP_DISPLAY` 来源误写成只有四组的规则表，已用实际消费方代码纠正。
- **被推翻判断：** “只删答案式散文或只把六个 decoupling 判据提权即可过线”均被实测否定。
- **尚未跨任务复现：** 把第三个消费方纳入统一规则表是域内设计，不具备通用 SOP 价值。
- **raw：** `jobs/production-construction-20260903/69dfba31-*/artifacts/build/evidence/round-000{1,2}`。

### `a3e92222-6399-4c51-99a4-f2af6b5d5c72`

- **可观察修改：** `0001→0002` 增加运行期缓存语义，`0002→0003` 换到只给症状的字节级缺陷
  定位；三轮 R 分别为 `0`、`0`、`0.0014`。
- **机制判断：** 最终轮 99.2% weight 两臂共同满分；规格重构、运行期细节、已有代码缺陷定位
  三条轴均饱和，结果跨轮稳定，不是采样噪声。
- **明确缺陷：** 旧 tooling criteria 绑定参考实现私有列名和逐字文本，改成行为 probe；
  本地 nop/oracle 与替代布局验证修复后没有恢复缺陷。
- **被推翻判断：** “把要求写得更细”与“改成症状式故障单”都不足以自动形成模型能力差。
- **尚未跨任务复现：** 从零实现新协议、规模化机械工作等只是下一步假设，没有 round，不沉淀。
- **raw：** `jobs/production-construction-20260903/a3e92222-*/artifacts/build/evidence/round-000{1,2,3}`。

### `b1b9aff6-c15e-4374-a965-111bda5c89b4`

- **可观察修改：** `0001` 的 rote 形状任务为 `0.9257 / 1.0 / 0.0802`；`0002` 增加现场绑定后
  为 `0.7664 / 0.8662 / 0.1302`；修掉三条错误 mutation 并把能力轴换成“测试层逐项锁住
  现场”后，`0003` 为 `0.4967 / 1.0 / 1.0132`，最终 `0004` 为
  `0.3333 / 0.9941 / 1.9823`。
- **机制判断：** `0003/0004` 的差几乎全部来自 7 条 suite-lock + 3 条 benchmark-suite；
  target 没有写出能随单点现场变异转红的新测试，solver 稳定写出，属于能力与预算管理差异。
- **明确缺陷：** `0002` 的 close-window mutation 同时触发另一窗口；profit-lock oracle 按峰值
  开锁但现场按当日累计开锁，三条共同失败均由可运行反例确认后修正。
- **被推翻判断：** “链路运行时跟现场绑定就够难”以及“测试应再次调用现场来推期望”均被否；
  后者会让测试与被测实现一起变化，永远锁不住行为。
- **尚未跨任务复现：** 让候选编写能在现场单点漂移时转红的测试层，只有本任务有完整成功链。
- **raw：** `jobs/production-construction-20260903/b1b9aff6-*/artifacts/build/evidence/round-000{1,2,3,4}`。

### `bf76425d-07b8-4940-b4bc-17b682a886e3`

- **可观察修改：** `0001` 缺少可解析 attempt 元数据，不能作正式前后轮；最终 `0002` 为
  `0.4684 / 0.9684 / 1.0675`，digest 匹配且机械两极成立。
- **机制判断：** 最终 50% weight 的客户端能力项形成稳定分差；target 把预算耗在后端、未进入
  前端，solver 在预算内完成两半，属于效率差而非 provider fault。
- **明确缺陷：** 原 probe 的整体 import/整体 spec 使一个模块或 Vue 文件失败时整簇无关 case
  归零；惰性 loader 与按 reducer/panel/wiring 拆分后，单点删除只影响依赖 case。
- **被推翻判断：** “整体加载能更严格地评完整交付”被单点反例否定；它只制造不成比例悬崖。
- **尚未跨任务复现：** 把两半 contract 调到各约 0.5、降低做题顺序影响，只在本任务验证。
- **raw：** `jobs/production-construction-20260903/bf76425d-*/artifacts/build/evidence/round-0002`。

### `26117e32…`、`287f5217…`、`c0ae3ac3…` 的明确错误证据

- `26117e32…`：`round-0001-defects.md` 记录第一条 solver trial 按 22 条 criteria 打分、后两条按
  26 条打分；verifier 在评分时读取活的 `/app/build/task/tests`。`round-0002/SUPERSEDED.md`
  进一步记录 trial 尚在 agent 阶段时 task 又加入新 tests，整轮必须作废。这个反例只支持“round
  运行期间冻结 task”，不支持任何 R 结论。
- `287f5217…`：`defects/text-binding-repro.md` 的行为等价 helper 只因精确正则判 0；
  `defects/round2-changes.md` 的 `alt-drop` 证明共享 `EXPORTS.every(...)` 守卫会让一个缺失导出
  连带约 30 条无关 criteria 归零，改成逐场景依赖后只失 4 条。life2 `0002` 与最终 task
  digest 不匹配，因此 round 变化不进因果，只采用持久化反例。
- `c0ae3ac3…`：`evidence/preflight.py` 可在完整 tests layout 上重现过长 judge criterion 名称
  导致 rewardkit discovery 在 programmatic tests 运行前失败；旧本地检查删除 `judge.toml`
  后代跑，因而漏检。该反例只支持完整 layout preflight。

## 建议写入 SOP

### 1. 机械门必须发现完整 verifier layout

- **去向：** SOP 正文，明确错误。
- **生命周期节点：** 第 2 步“建立机械有效性”。
- **支持任务与证据：** `c0ae3ac3…` life1 `0001` 两臂均无 included programmatic 读数；
  `artifacts/build/evidence/preflight.py` 在完整 layout 上复现非法 judge 名在 discovery 阶段杀死
  verifier。
- **作用机制或可运行反例：** 只删除 agent judge 后跑 programmatic poles，会跳过 TOML、名称、
  group shape 等完整 verifier 的发现期错误；nop/oracle 分数即使正确，也不代表交付 verifier
  能启动。
- **反证检查：** agent judge 仍不进入 R；这里只要求完整 layout 能被发现，不要求本地调用 judge
  或取得 judge 分数。
- **最小替换措辞：** 在第 2 步第一段“重复检查均能读数”之后加入：

  > 机械检查还必须让与交付完全相同的 `tests/` 布局完成 verifier discovery，包括
  > `judge.toml`、所有 reward 配置、criterion 名称和 group 形状；不得通过删除诊断 judge 后的
  > 子集运行代替完整布局检查。诊断 judge 不进入 R，也不要求在机械门中实际调用模型。

### 2. 一个 round 从首个 trial 启动到两臂结束期间冻结 task

- **去向：** SOP 正文，明确错误。
- **生命周期节点：** 第 3 步“取得当前 task 的真实双臂读数”。
- **支持任务与证据：** `26117e32…/round-0001-defects.md` 的 22/26 criteria 混编；
  `round-0002/SUPERSEDED.md` 记录 task 在 trial 运行期间加入新 tests 后整轮作废。
- **作用机制或可运行反例：** trial lock 固定的是启动时 task digest，但 verifier 可能在评分时读取
  活的 tests；运行中改 task 会让同一 round 不同 trial 使用不同判据集合，无法比较。
- **反证检查：** 修改 evidence、notes 或独立分析脚本不会改变 task，可继续进行；冻结范围只覆盖
  `task/`。
- **最小替换措辞：** 在第 3 步首段加入：

  > 从某个 round 的第一个 trial 启动起，到 target 与 solver 的选定 run 全部结束为止，冻结
  > `task/`。不得在尚有 trial 运行时修改 instruction、tests、solution、environment 或 task
  > 配置；同一 round 若出现多个 task digest 或 criterion schema，整轮只记进度并新开 round。

### 3. 成片失败先验证依赖隔离，再解释为能力差

- **去向：** SOP 正文，明确错误。
- **生命周期节点：** 第 4 步“检查判据差异”。
- **支持任务与证据：** `bf76425d…` 的整体 import/spec 悬崖；`287f5217…` 的共享
  `EXPORTS.every(...)` 守卫与 `alt-drop`；`eeb26954…` 的写死 javac 闭包是同类旁证。
- **作用机制或可运行反例：** 一个缺失组件可通过共享 loader、全局 guard 或写死编译闭包把无关
  criteria 一起归零，制造看似稳定的分差或共同失败。
- **反证检查：** 真正依赖同一前置能力的 criteria 可以一起失败；要求的是写清依赖并用单点变异
  验证失败范围，不是强迫所有 criteria 完全独立。
- **最小替换措辞：** 在第 4 步“target 和 solver 共同失败本身不是缺陷证据”之前加入：

  > 若多个 criteria 因同一个 loader、导出守卫、编译闭包或场景前置而成片归零，先构造只缺失
  > 一个组件的最小变体，确认只有实际依赖它的 criteria 翻转。单点缺失使无关 criteria 连带归零
  > 时，先拆分前置或缩小编译/加载范围，再解释模型差异。

### 4. 用判据质量识别饱和轴，不能只看 criterion 数量

- **去向：** SOP 正文，构造策略。
- **生命周期节点：** 第 4 步“检查判据差异”。
- **支持任务与前后 round：**
  - `2ccb050c…`：`0002` 100% weight 两臂共同满分、R `0.0118`；`0003` 把共同满分质量降到
    38.6%，正向分差质量 26.3%，最终 R `0.4368`。
  - `b1b9aff6…`：`0001` 85.1% weight 两臂共同满分、R `0.0802`；换到 suite-lock 轴后
    `0003/0004` R 为 `1.0132/1.9823`。
  - 反证：`52efdaea…` 最终 87.6%、`69dfba31…` 最终 80.1%、`a3e92222…` 最终 99.2%
    weight 两臂共同满分，继续加同类要求或仅调权重均未过线。
- **作用机制：** 大量 both-pass weight 给两臂相同高地板；同一饱和机制下增加 criteria 只增加
  死质量。先计算质量分布和 target 跨过 0.7 所需的实际丢分质量，才能判断当前轴是否有数学
  杠杆。
- **反证检查：** both-pass criteria 仍可保护任务完整性，不能为制造分差而随意删除；饱和分析
  只决定下一轮难度投向，不改变交付合同。
- **最小替换措辞：** 在第 4 步 parser 读数要求之后加入：

  > 同时按 criterion weight 统计两臂共同通过、共同失败、正向 delta 和反向 delta 的质量，
  > 并计算 target 降到 0.7 以下还需失去多少质量。共同通过项仍保留其合同作用，但若当前非饱和
  > 质量不足以跨线，不得靠继续增加同机制 criteria 或只重配权重推断可达；下一次设计修改应换
  > 到有独立行为面的能力轴。

### 5. 新难度在花真实 round 前先用定向错臂证伪

- **去向：** SOP 正文，构造策略。
- **生命周期节点：** 第 5 步“做一次连贯的任务设计修改”。
- **支持任务与前后 round：**
  - `2ccb050c…` 的 `analysis/mutate_v2.py` / `sensitivity_v2.json` 用“宽度宽松”“没有滚动”等
    整簇误读验证判据质量，`0003` 的低分 target trial 随后确实成簇失去同类能力面。
  - `b1b9aff6…` 对 7 个现场锚点逐个 mutation；修掉会误伤忠实实现的三个 case 后，suite-lock
    在 `0003/0004` 上形成稳定 target/solver 分差。
  - 反证：`52efdaea…` 本地 naive 为 `0.4721`，真实 `0004` target 却为 `0.8920`，说明错臂
    只能证伪判据和检查隔离，不能替代真实模型读数。
- **作用机制：** 定向错臂能在低成本下发现“不敏感 fixture”“假锁”“无关连带失分”和错误
  oracle，减少把一个完整 round 花在不可判或错误的难度上。
- **反证检查：** 错臂由构造者定义，不能证明目标模型会犯同一种错，也不能用于 R、reward 或
  交付；真实双臂 round 仍是唯一模型分差证据。
- **最小替换措辞：** 在第 5 步“修改后重新完成机械有效性检查”之前加入：

  > 对新增的主要难度先构造一个只体现预期误读的最小错臂或 mutation，确认它会使目标
  > criteria 翻转、不会使无关 criteria 连带翻转，并确认 oracle 仍通过。错臂只用于证伪判据
  > 敏感性与隔离性，不用于估计 target/solver 分数，也不替代修改后的真实双臂 round。

## 技巧附录候选

### 题面“指路但不代做推导”

- **有效任务与证据：** `2ccb050c…` 的 `0001→0002→0003` 是完整正例：把推导答案写进题面后
  target 接近满分，撤回答案并保留权威固件指针后恢复分差。
- **适用边界：** 只能隐藏可从公开 workspace 权威来源确定的中间推导，外部接口、验收行为和
  workspace 中无法定案的约定仍必须显式写清。
- **尚缺复现：** `52efdaea…` 删除答案式散文后的 `0004` 没改善，`69dfba31…` 也出现反向结果；
  尚不满足跨任务 SOP 策略门槛。

### 把 timeout asymmetry 作为机制诊断

- **有效任务与证据：** `bf76425d…` 与 `b1b9aff6…` 的 target 有分数后撞 3600s，分差体现长程
  完成效率；`2ccb050c…` 则是 solver 撞上限，压低了 R。
- **适用边界：** `timed_out_scored` 仍是有效 trial，但必须查看哪一臂被截断；修改 timeout 会改
  task digest，必须重采样。
- **尚缺复现：** 没有一个任务完成“只改 timeout 后重跑”的可比 round，不能写成调参策略。

### 用“测试能否锁住现场漂移”构造长程能力轴

- **有效任务与证据：** `b1b9aff6…` 的 suite-lock 轴让 target/solver 分差从 `0002` 的
  `0.1302` 提升到 `0003` 的 `1.0132`。
- **适用边界：** 被测实现应运行时跟随现场；测试期望应固定可观察结果并在单点现场变异时转红，
  不能再次调用同一现场逻辑生成期望。
- **尚缺复现：** 只有一个任务验证，先保留为技巧。

## 明确不沉淀

- **各任务把 `network_mode` 从 `no-network` 改为 `public`：** 已经是 SOP 第 2/5 步的硬规则，
  重复出现只说明执行必要，不需要新增同义文字。
- **provider、Daytona、agent stream 中断与未启动 job：** 只决定纳入/排除，不产生任务设计结论。
- **`attempts=1` 被 Harbor 默认值序列化省略：** 是 runner/parser 元数据兼容问题，应该进入工具
  issue 或脚本修复，不写进任务构造策略。
- **瘦身 Dockerfile、删除无关 SDK/构建链：** 有明确运行成本价值，但本批次没有可比墙钟与分差
  证据，暂不写成 SOP 规则。
- **固定领域技巧、文件名、权重和实现细节：** 包括 OSScan 自查程序、固件滚动算法、IoT
  downlink/ingest 陷阱、Phoenix suite-lock 的七个锚点、具体 weight 档位，均不跨任务沉淀。
- **未经 round 验证的下一手：** `a3e92222…` 的新协议/规模化工作、`52efdaea…` 的更多矛盾源、
  其他 resume 中的备用难度都只是建议，不当作经验。
- **用外推分数替代 raw round：** 被 `52efdaea…` 的误记反例否定；当前批次复盘 SOP 已明确 raw
  evidence 为事实源，无需重复改正文。可在 notes 中把外推单独标注，但不得进入实测表或交付判断。

## 选择建议

建议一次性接受正文候选 1–5。前 3 条是由可运行反例证明的证据完整性/判据有效性修复；后 2 条
由 `2ccb050c…` 与 `b1b9aff6…` 两个不同任务的前后 round 独立支持，并由
`52efdaea…`、`69dfba31…`、`a3e92222…` 给出适用边界。三条技巧保留在非规范性附录候选，
本轮不写进正文。

本报告没有修改 R、reward、criterion weight 的职责、trial 有效性或交付标准，也没有修改
`template/environment/method/sop.md`。
