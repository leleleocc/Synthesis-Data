# Harbor task 构造 SOP

你是在构造 `/app/build/task/` 里的 task，不是在完成它。保持原任务的领域和核心目标；在
`/app/build/evidence/` 累积证据。开始工作、正式 round 结束和交付前，都从 `resume.md`
定位当前步骤。命令参数与证据格式以工具说明为准：

这是无人交互的 solo task。独立选择可逆的下一动作，持续执行到第 6 步交付；不确定性转化为
前向探针。只有外部中断或工具持续不可用才能以 `incomplete` 结束。

存在两个以上独立调查分支时，使用 subagent 分析当前 round 的轨迹、criterion 分组、契约或
scratch probe，并只返回结论与证据位置。主 Agent 独占正式 task 修改、fresh/regrade、
`resume.md` 和最终决策；subagent 不可用时继续本地推进。

```bash
/app/method/run-two-models.sh --help
/app/method/parse_scores.py --help
```

## 1. 恢复当前状态

先读 `/app/build/evidence/resume.md`，再检查当前 task。旧分数是已记录的结论，不是可复用来源；
若 `/app/build/evidence/previous-life/index.md` 存在，紧接着读取这个 index，但不递归打开每个保留
round。已有历史时沿笔记继续；首次运行时完整阅读 instruction、配置、solution、tests、environment
和起始 workspace。

完成标准：能用一句话说明任务目标、当前状态、已排除方向和唯一下一动作。

## 2. 建立机械有效性

首次测量前检查 `/app/build/task/task.toml`：task 必须为 single-step，显式设置
`[verifier].environment_mode = "separate"`，并用 `[[artifacts]] source = "/workspace"`
完整收集 main-service workspace，且其他 artifact 不得与它重叠。`tests/` 是 verifier 的构建上下文，
必须定义 verifier environment 并在镜像中提供 `/tests/test.sh`；最终 task 及其
environment、verifier 和 phase override 均保持 public network。

缺少 Reward Kit 注册、聚合、计分输出或 verifier 接线时，复用
`/app/method/reference/minimal-harbor-task/`；已有可用接线不重构。reference 只提供机械骨架，
兼容性缺口记入 `resume.md` 后返回正式测量。

在同一 task 上验证 nop=0、oracle=1 和稳定的 programmatic 输出。任务可有 agent judge，
不支持 LLM judge；R 只使用 programmatic 分数。实际计分 criterion 原则上收敛到 50 个以内；
超过仅是降噪提示，不单独阻塞交付。省略的 weight 按 1.0，且
`最大 weight / 最小 weight <= 10`。正确性只保留防空实现、固定输出和明显失真的少量底线；
边界、异常恢复和工程规范仅在属于核心目标或真实证据暴露问题时计分。

nop/oracle 的完整 Harbor job 放在 `/app/runtime/harbor-checks/`；`/app/build/evidence/` 只留
结果摘要和必要的小型诊断。机械检查不能把 `jobs/**/artifacts/workspace` 带进回传区。

完成标准：最终交付状态可重复得到 nop=0、oracle=1，满足 public network、artifact 和 weight
约束，并已评估 criterion 数量提示。

## 3. 选择测量环

固定 `[agent].timeout_sec = 3600.0`；保留并解释 `timed_out_scored`，不调整测量窗口。
新 life 的第一次正式测量必须 fresh，也是进入归因和修改的 gate：开局保持 task 内容不变，
只修复阻断 nop/oracle 或 Harbor 接线的机械缺陷；完成 nop/oracle 后立即运行
`run-two-models.sh both`，即使
`resume.md` 或 previous-life reference 含有分数与轨迹。regrade 只复用当前 life 的
`/app/runtime/harbor-evidence`，因此它只在本 life 已产生兼容的 real source 后可用。
首个 fresh both 使用工具默认采样，不传 `--attempts` 或 `--concurrency`；只有有效读数已显示
不稳定时才增采样，缺失或基础设施失败按补 arm 处理。

在同一 life 内，按以下顺序选择第一个适用分支：

- **补 arm**：最后一个 round 不完整、task 未变化，且 current-life runtime source 可用时，只补缺失或失败 arm。
- **轻内环**：current-life real source 兼容、rollout input 未变化，且 `tests/**` 或
  `solution/**` 已变化时，完成 nop/oracle，再运行 `run-two-models.sh regrade`。
- **重外环**：尚无 current-life source，或 instruction、task.toml、environment、README、
  `.gitignore` 等 rollout input 已变化时，完成 nop/oracle，再 fresh both。

同一 life 中 tests/solution 变化优先轻 regrade，再作重 fresh；不完整 regrade 保留后新开 round
执行 regrade。source 缺臂或不可复用时 fresh。regrade 失败不会自动回退到模型运行，也不回退旧分数。

fresh/regrade 是阻塞检查点。运行期间保持 `/app/build/task/` 不变，只监控运行、归因基础设施异常，
或执行 `resume.md` 中唯一问题的 scratch probe；结束并解析后再修改 task。

完成标准：同一正式 round 的 target 与 solver 最新 run 均结束，且各有至少一个有效
programmatic 读数。

## 4. 归因并裁剪 verifier

调用 parser 时始终传 `--final-task /app/build/task`。人类输出末尾的 `NEXT_ACTION` 和
action hint（`--json` 中为同名字段）是本步的执行提示：过线即停止 fresh；只检查列出的红旗和
advisory，没有具体缺陷就交付。parser 只按有效 trials 的多数结果自动分类纯二值
criterion；连续、缺值或平票项列为 `unclassified`，结合其自身成功边界或 delta 判断。

| 两臂主导结果 | 判断与默认动作 |
| --- | --- |
| target 过、solver 过 | **过松/冗余候选**：核心底线留少量；删除重复和非核心项。承担区分作用时，只在现有契约内加强 test 并同步 solution。 |
| target 不过、solver 过 | **难度合适**：确认无 fault、基础设施异常或契约冲突后保留，不继续优化。 |
| target 过、solver 不过 | **方向反转**：确认 oracle 通过且无 verifier/基础设施异常后，删除 criterion 或同机制判据组；正确性底线除外。 |
| target 不过、solver 不过 | **过严候选**：检查超出契约、参考实现绑定、整项归零或共同阻塞；非核心项删除，核心且公平时只留少量。 |

先比较当前 life 的 fresh 证据、测试输出和 parser 证据；当前 life 的 fresh 证据优先。当前 life 跟随 parser/current round 路径
读取 compact trial 的 `reward-details.json`、`result.json`、`lock.json` 和 target/solver trajectory：分数或 verifier 假设读
trial，模型行为假设比较多个 trajectory 样本。previous-life attribution 才按 `/app/build/evidence/previous-life/index.md`
定位命名 real round，再按同一分支读取 compact evidence。当前问题仍未回答时，先检查 current-life
compact evidence 的 trajectory；只有仍未解决的当前问题才进入
`/app/runtime/harbor-evidence` 读取 workspace。两个独立 trial 复现并覆盖多数相关失败、一个反例
否定假设，或相关 trials 全部检查后立即停止。

task 内的 trajectory 只回答一个会改变当前 verifier 动作的已命名模型行为假设；批次级时间分布、
全过程复盘和模型能力画像留给回收阶段。得到结论与证据位置后，主 Agent 直接执行下一动作，不再
重读同一段轨迹。

裁剪低价值 test 不等于认定缺陷。缺陷须有具体证据：交付状态不可复现、与题面或仓库契约矛盾、
可运行的合格反例因私有实现细节失败，或重复验证明显不稳定。低通过率本身只用于定位。

在 `resume.md` 记录一张卡：`round/问题`、`trial 与输出证据`、`动作 → 产物差异 → 分差`、
`判断与决策`；证据不足时写明边界和前向探针，并只留下一个下一动作。

完成标准：能指出当前 target_mean、R，并有一张证据覆盖、因果、判断和决策完整的归因卡。

## 5. 做一次最小修改

新 life 只重置 round 编号和 regrade source，不重置收敛结论。存在
`/app/build/evidence/previous-life/index.md` 时，rollout input 从开局即继承冻结；没有 previous-life
时，取得本 life 首个有效 fresh both 后冻结。随后将当前 compact evidence 作为主证据，
previous-life tree 仅作背景参考。默认只执行第 4 步选出的同机制 tests 修改，按需同步 solution，
然后回到第 2、3 步完成 nop/oracle 和 regrade。

只有可运行反例证明任务无有效解、instruction 自相矛盾、oracle 无法满足公开契约，或 Harbor
接线无法工作时，才解冻 rollout input；做覆盖该缺陷的最小修改并 fresh both，不扩写其他边界。
低通过率、反向分差、solver 对未定义行为的选择和增加区分度，都不足以解冻。

按 parser 的 `NEXT_ACTION` 收敛：`deliver` 直接记录并交付；`inspect_red_flags` 只处理列出的
criterion 或机制。同步 solution 后完成 nop/oracle 和 regrade。修复导致分数变差时仍只在冻结
契约内调整 verifier，不恢复缺陷或扩写 rollout input。

完成标准：task 完整可运行，且能指出本轮为何属于轻内环，或凭哪个可运行反例进入重外环。

## 6. 记录并交付

每次 task 修改、机械检查或正式测量后，立即更新 `resume.md` 的五个既有标题：已尝试方向、
关键结果、已排除假设、当前 task 状态、下一步建议。记录 task/rollout-input identity、
修改与原因、nop/oracle、round/trial 读数、归因结论、current/incomplete/superseded 状态和唯一动作；
其他过程材料放在 evidence 子目录。

采用前向闭环：每轮只处理一个假设，依次完成归因、修改、机械检查、fresh/regrade 和笔记；开始
修改后先闭合本轮，不再返回历史找方向。重复第 3 至第 5 步，其中
`R = (solver_mean - target_mean) / target_mean`。

只有编号最大的 current-life compact two-arm round 与最终 task 一致、两臂均有有效 programmatic 读数，并同时满足
`target_mean < 0.7` 和 `R > 0.2`，才能交付整个 `/app/build/`。达到开头的终止边界时，将准确
恢复位置和下一动作记为 `incomplete`；incomplete 不满足交付条件。

完成标准：最新 compact two-arm round 与最终 task 一致、两臂读数有效、两个分数门槛满足，且
`resume.md` 足以直接恢复；持续自主推进，直到这个 round 可读且 task 可交付。
