# 批量构造设计

一批候选 seed 上传到 TOS，各自独立跑构造流程，产出 N 个独立交付物。上百条线的规模，
调度器是无状态对账器，状态全在 TOS 上。

不做横向比较（候选之间互不相关），不做续期，不做删除，不做每候选的差异化配置。
这些都讨论过并明确后置，见末节。

## 1. 用户侧契约

这一节是给用户看的全部。用户不需要读后面的节也能把一批跑起来。

### 1.1 你交什么

一个目录。目录名是 batch 名，每个子目录是一个候选：

```
my-batch/                     ← 你起的名字，就是 batch 名
  sglang-fp8/                 ← 一个子目录 = 一个候选；子目录名 = 候选名
    task/ …                      内容 = 今天你交给 `sbx task create` 的那棵树，形状不变
  sglang-int4/
  vllm-spec-decode/
```

**一个候选 = 今天你会传给 `sbx task create` 的那个目录。** 脚手架不看候选目录里面
有什么，那是你的模板和你的 seed 之间的事，跟今天一样。

batch 目录里**不放**清单文件、配置文件。模板名和 `task.env` 整批一份，命令行给。

### 1.2 命名规则

| | 规则 |
|---|---|
| task-id | `<batch>/<candidate>`，由目录名机械拼出，**你不再手敲 id** |
| batch 名、候选名 | `[A-Za-z0-9._-]`，不以 `_` 或 `.` 开头（`.git`、`.DS_Store` 之类自动跳过） |
| 候选名保留字 | `seed`、`archives`、`runs` 不能用 |
| batch 名 | 不能等于任何已有的平铺 task-id（否则会嵌进别人的前缀） |

### 1.3 三条命令

```sh
sbx batch push my-batch/ --template harbor-constructor    # 只上传，不开沙箱
sbx batch status my-batch                                  # 一张表，几秒钟
sbx batch reconcile my-batch                               # 对账一遍：该开的开
```

`push` 把模板名记到 `/sandbox/my-batch/batch.json`，reconcile 从那里读，不用每次再传；
reconcile 加 `--template` 可以临时覆盖。凭证按 `tasks/<batch>.env`、然后 `task.env` 找，
和今天 `task create` 的规则同形，只是粒度从 task 变成 batch。

`push` 可以反复跑：
- 新加的子目录成为新成员，下次 reconcile 会开
- 已经跑过的候选重推 seed **是空操作**（archives 永远压过 seed，今天的语义不变）
- 删掉子目录什么都不发生，脚手架从不删 TOS
- 改子目录名等于新候选，老的继续跑

单条线的钻取用今天的 `sbx task` 命令，id 换成嵌套的：
`sbx task trace my-batch/sglang-fp8`、`sbx task kill my-batch/sglang-fp8`。

### 1.4 你必须做的一件事：定期跑 reconcile

对账器无状态，**没人调用就没人开下一个沙箱**。第一批沙箱到期后整批停摆。
用 cron 或定时任务每 10–15 分钟跑一次 `sbx batch reconcile my-batch`。

### 1.5 你的模板要写的两个标记

和 `.done` 同级、同性质，放在 `/home/app/workspace/` 下的空文件：

| 文件 | 谁写 | 含义 | 不写的后果 |
|---|---|---|---|
| `.measuring` | 模板：测量开始 touch、结束 rm | 这条线正占着共享外部资源（Daytona） | 对账器看不见测量数，**只按沙箱数控并发**，可能把 Daytona 打爆、trial 大面积失败 |
| `.blocked` | agent：判定要人裁决时 touch | 别再给我开沙箱了，来个人 | 需要人的线会一直续沙箱，直到撞每线沙箱上限才停 |

脚手架只抄这两个文件的有无进 `status.json`，**不解释含义**。含义是租户和对账器
之间的约定。人处理完 `rm .blocked`，下次 reconcile 自动恢复。

harbor-constructor 模板的落点：`run-two-models.sh` 起步 touch、结束 rm；
`refine.md` 里"建议人工干预"那一条改成 touch `.blocked`。

### 1.6 一条线怎么到头

| 终态 | 怎么到的 | 你要做什么 |
|---|---|---|
| `verified` | `.done` 且 `verify.sh` 通过 | 取归档，完事 |
| `blocked` | agent 写了 `.blocked` | 看 `resume.md`，处理，`rm .blocked` |
| `stopped` | 沙箱数撞上限（默认 10） | 看 trace 决定：加上限重开，或放弃 |

终态对账器不再碰。整批到头 = `batch status` 汇总行里 working / measuring / idle /
queued 全是 0。

`.done` 但 `verify.sh` 判否**不是终态**：agent 自称完成被打回，继续跑。

### 1.7 整批共享、不能按候选区分的东西

模板、`task.env`、并发上限、每线沙箱上限。要区别对待就拆 batch。

### 1.8 对模板的限制

- 一批只能用一个模板
- 不得把 `SANDBOX_TASK_ID` 当文件名用（里面有 `/`）
- 每条命无状态、从树读状态——已经是要求，不变
- 模板没有版本，改一次立刻影响所有跑着的线。一百条线时这是真风险。
  **本轮不做冻结**，后置；跑批期间请自觉不改模板。

### 1.9 手工 kill 之后

`kill` 和下一次 `create` 之间**至少隔 30 秒**。被 kill 的沙箱没有退出钩子，租约留在
NAS 上，`LEASE_STALE_SECONDS=30` 之内新沙箱会让位并空转一小时。对账器自己不 kill，
只等沙箱到期，天然满足；手工操作要记着。

## 2. TOS / NAS 布局

```
/sandbox/
  _runtime/  _templates/  _unassigned/        （不变）
  my-batch/                                   ← batch 前缀
    sglang-fp8/
      seed/<stamp>.tar.gz + .manifest.json + .sha256    push 写，和今天完全一样
      archives/                                          runner 写
      runs/<run-id>/                                     runner 写
      status.json                                        runner 写，覆盖写
    sglang-int4/
      …
    batch.json                                           push 写：{template, created_at}
```

`batch.json` 是对象不是前缀，delimiter 列举天然把它和候选分开。

NAS：`/harbor/my-batch/sglang-fp8/`。

**batch 的成员 = `/sandbox/my-batch/` 下的一级子前缀**，一次 delimiter 列举拿到，
不另外维护成员清单。

沙箱 metadata 打两个标：`task=my-batch/sglang-fp8`、`batch=my-batch`。后者让
`ListSandboxes` 一次筛出整批的活沙箱。

## 3. status.json 与状态判定

### 3.1 对象

每个候选前缀下一个小对象，runner 在相位切换和每轮迭代边界**覆盖写**：

```json
{"task_id": "my-batch/sglang-fp8",
 "phase": "4b", "iteration": 3, "max_iterations": 10,
 "lives": 48, "sandboxes": 10,
 "done": false, "verified": null,
 "markers": {"measuring": true, "blocked": false},
 "run_id": "…", "updated_at": "…"}
```

`lives` / `sandboxes` 是累计数：runner 启动时读上一份 status.json，`sandboxes` 加一；
每轮迭代 `lives` 加一。没有上一份就从零起。

runner **对所有任务**都写它，包括不在 batch 里的平铺任务。平铺任务白拿一个便宜的
状态对象，`sbx task status` 以后可以借它把 20 分钟降到 1 秒（不在本轮）。

### 3.2 state 的判定顺序

```
verified   status.done && status.verified == "verified"        终态
blocked    markers.blocked                                      终态
stopped    sandboxes ≥ 每线上限 且 !done                        终态
measuring  有活沙箱 && markers.measuring
working    有活沙箱
idle       无活沙箱、非终态                                     → 该开下一个
queued     status.json 不存在                                   → 从未开过
```

"有活沙箱"来自 `ListSandboxes(metadata={"batch": …})`，按 `task=` 归到候选。
**`Failed` 状态的沙箱按活的算**：实测它其实起来了、拿走了租约，直到到期消失。

### 3.3 `sbx batch status` 的样子

```
candidate          state       sbx  lives  iter   updated   note
sglang-fp8         measuring   10   48     3/10   12m ago
sglang-int4        blocked     4    17     —      3h ago
vllm-spec-decode   verified    2    9      —      1d ago
qwen-gptq          queued      0    0      —      —
                     100 candidates: 61 working · 14 measuring · 3 blocked · 12 verified · 4 stopped · 6 queued
```

成本：1 次 delimiter 列举 + 1 次 `ListSandboxes` + N 次 GET。百条几秒钟。

## 4. reconcile 规则

### 4.1 一次 pass

```
1. 取成员      delimiter 列举 /sandbox/my-batch/
2. 取状态      每个候选 GET status.json；没有 = queued
3. 取活沙箱    ListSandboxes()                        → 全局数，闸门用
               ListSandboxes(metadata={"batch": …})   → 本批的，归到候选
4. 算 state    按 3.2
5. 决策        只对 idle 和 queued 动手
6. 打印        status 表 + 本次动作
```

### 4.2 决策

对每条 `idle` / `queued` 的线，按顺序问两个问题，任一"否"就本次不开、下次再看：

```
全局活沙箱数    < --max-sandboxes    默认 60，给别的 batch 和手工任务留余量
本批 measuring  < --max-measuring    默认 24，Daytona 软闸留余量
```

每线沙箱上限（`--max-sandboxes-per-line`，默认 10）不在这里问：撞上限的线在 3.2 已经
判成 `stopped`，根本不会是 `idle`。

两个都过就 `CreateSandbox`，和 `sbx task create` 走同一条代码，metadata 多一个 `batch=`。

顺序：`queued` 先于 `idle`（每条线至少跑起来一次，再给老线续命）；同状态内按候选名
排序。**确定性**：同一时刻两次 pass 得到同一个决定，是 `task create` 准入检查之外的
第二道防双开。

### 4.3 闸门是全局数

`--max-sandboxes` 数的是整个 veFaaS 函数下的活沙箱，不只本批。两个 batch 各看各的
就是 200。

`--max-measuring` 是软闸：对账器拦不住一条已经在跑的线从等待切到测量，所以默认值
留了余量（Daytona 250 核 ÷ 每线约 8 核 ≈ 30，取 24）。硬闸后置。

### 4.4 出错

- 某个 GET 失败：这条线本次跳过，不影响其它线
- `CreateSandbox` 失败：记一行，下次 pass 自然重试（它还是 `idle`）
- 不续期、不 kill：到期让它死，下一次 pass 看到 `idle` 就开新的，树在 NAS 上接力

## 5. 对既有系统的改动

| 哪里 | 改什么 |
|---|---|
| `sbx/cmd_task.py` `_check_task_id` | "禁止 `/`" → "至多一个 `/`，两段都不以 `_` 开头" |
| `sbx/cmd_batch.py`（新） | `push` / `status` / `reconcile`；`push` 写 `batch.json` |
| `sbx/settings.py` `load_task_env` | 嵌套 id 先找 `tasks/<batch>.env` |
| `sbx/faas.py` | `CreateSandbox` metadata 多一个可选 `batch=` |
| `runner/`（约 40 行） | 写 `status.json`；累计 `lives` / `sandboxes`；抄两个标记的有无 |
| `tenants/harbor-constructor/template/method/run-two-models.sh` | 起步 touch `.measuring`、结束 rm |
| `tenants/harbor-constructor/template/roles/refine.md` | "建议人工干预" → touch `.blocked` |
| `TODO.md` 第 1 节 | 租户契约加两个标记；删掉"批量形态未定"那条 |
| `ONBOARDING.md` 第 6 节 | 从"当前没有批量形态"改成指向本文第 1 节 |

`sbx task *` 一行不改，平铺 id 继续合法。

## 6. 动代码前要验证的两个假设

开一个 probe 沙箱，task-id 用 `probe-batch/one`：

1. NAS `remote_path` 嵌套一层（`/harbor/probe-batch/one`）能否自动创建。TODO 第 0 节
   只实测过单层。
2. 沙箱 metadata 值里带 `/`，平台收不收、`ListSandboxes` 过滤还准不准。

**2026-09-15 probe：两条都成立。** `CreateSandbox` 接受 `task=probe-batch/one` 并回显；
`ListSandboxes(metadata={"task": "probe-batch/one"})` 过滤为真（负向 `does-not-exist`
返回空）；NAS 挂上 `/harbor/probe-batch/one`（`df` 一行 `:/enas-…/harbor/probe-batch/one
nfs … /home/app`），preflight `ok NAS mount present`。退路不启用。

## 7. 明确后置的

每条都讨论过，不是遗漏：

- 模板冻结 / 钉版本（TODO 第 4 节有做法）
- 归档保留策略（TODO 第 2 节）。批量后的账：100 条线 × 10 沙箱 × 529 MB ≈ 500 GB
  TOS，NAS 约 360 GB。**这是下一个要做的**
- `SetSandboxTimeout` 续期，减少交接次数
- Daytona 硬闸（主机侧调 Daytona API 数沙箱）
- 每候选覆盖模板 / env
- 横向比较、top-k
- 借 status.json 加速 `sbx task status`
