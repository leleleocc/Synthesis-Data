# 新接入方上手

从零到跑起自己的第一个构造任务。**共用现有的 veFaaS 应用和镜像，用你自己的 AK/SK。**

写给要自己建 template、自己跑构造流程的人。系统为什么长这样看 `README.md`，还欠什么看
`TODO.md`，模板怎么写看 `examples/hello-world/README.md`。

---

## 0. 有两条命令不是你的

`sbx` 的命令按影响范围分两类，先说清楚免得踩：

| | 影响范围 |
|---|---|
| `sbx app sync` | **改应用配置并 Release，所有租户一起换。** 不要跑 |
| `sbx runtime publish` | 覆盖 `_runtime/<version>/` 的 runner，**所有租户共用这一份**。不要跑 |
| `sbx template publish` | 只影响 `_templates/<你的模板名>/`，是你的 |
| `sbx task *` | 只影响 `<你的 task-id>/`，是你的 |
| `sbx batch *` | 只影响 `<你的 batch>/` 及其候选，是你的 |
| `sbx probe *` | 只读，随便用 |

前两条是应用级的：`/mnt/runtime` 在 `sbx/mounts.py:92` 那一行是 `instance=None`，意思是
它**不能按实例窄化**，只能从应用配置来。所以"换 runner 版本"这件事没有"只给我自己换"
的形态，一发全体生效。

**最好的做法是让 policy 替你记住这件事**——见第 2 节，不给 `UpdateFunction` / `Release`
权限，跑错了会直接被拒，不用靠自觉。

应用和镜像已经配好，你不需要碰：`VEFAAS_FUNCTION_ID`、`SANDBOX_IMAGE*` 用仓库里现成的
值即可。

---

## 1. 填 `.env`

```sh
cp sandbox/aio/.env.example sandbox/aio/.env
chmod 600 sandbox/aio/.env
```

要你自己填的只有两个：

```
VOLC_ACCESSKEY=<你自己的>
VOLC_SECRETKEY=<你自己的>
```

沿用现成值、**不要改**的：`VEFAAS_FUNCTION_ID`、`SANDBOX_IMAGE` / `SANDBOX_IMAGE_ID`、
`SANDBOX_IMAGE_PORT`、`TOS_BUCKET`、`TOS_BUCKET_PATH`（`/sandbox`）、`NAS_REMOTE_PATH`
（`/harbor`）、`RUNTIME_VERSION`。

改 `RUNTIME_VERSION` 不会只影响你——它只决定 `app sync` 往应用配置里写哪个路径，而那是
第 0 节说的全局操作。

模型凭证**不在这个文件里**，它走 `task.env`，见第 4 节。

---

## 2. 权限

你要的是**同一个火山账号下的子账号**，不是另一个账号——应用 ID 是账号内的，跨账号拿
不到。权限自己去开，形状是这样：

**veFaaS（要）**
`CreateSandbox`、`ListSandboxes`、`KillSandbox`、`DescribeSandbox`、`SetSandboxTimeout`、
`GetFunction`、`GetFunctionInstanceLogs`

**veFaaS（明确不要）**
`UpdateFunction`、`Release`——这两个就是第 0 节那两条命令的底层调用。不给，
`sbx app sync` 就会失败而不是生效。

**TOS**（桶是接入方的，按前缀限死）
- 读写 `<bucket>/sandbox/_templates/<你的模板名>/*`
- 读写 `<bucket>/sandbox/<你的 task-id 或 batch 前缀>/*`
  （批量时前缀是 `<batch>/`，下面每个候选一棵树）
- **只读** `<bucket>/sandbox/_runtime/*`

**NAS**：不需要。主机侧根本挂不了 NAS，所有 NAS 操作都发生在沙箱里。

模板名和 task-id 前缀自己挑一个不会撞的。`_templates/<name>/` **没有版本，直接覆盖**
（这是有意的，见 `TODO.md` 第 4 节），撞名字就是把别人的模板盖掉。

---

## 3. 写你的 template

抄 `examples/hello-world/template/`：

```
template/
  PROMPT.md      必需。每轮迭代管道喂给 agent 的 stdin
  init.sh        可选。每个沙箱起来跑一次，以 root
  roles/*.md     可选。PROMPT.md 自己按路径去读
```

`examples/hello-world/README.md` 是正经教程，整份读一遍。**最要紧的是 43-51 行**：agent
每轮都是全新进程、没有上一轮的记忆。写成一次性指令（"实现一个 X"）会让它每轮从头开始、
永远不收敛。要写成"**先看树 → 做下一件缺的 → 满足什么条件就写 `.done`**"。

发布：

```sh
sbx template publish <你的目录> --name <你的模板名>
```

模板没有版本，改完再发一次立刻生效——**包括对正在跑的任务**（`TODO.md` 第 6 节记了这个
取舍，是选的不是 bug）。

---

## 4. 模型凭证

```sh
cp sandbox/aio/tenants/harbor-constructor/task.env.example sandbox/aio/tasks/<task-id>.env
```

按 `KEY=VALUE` 填。查找顺序：

- 平铺 id：`tasks/<task-id>.env`，然后 `task.env`
- 嵌套 id（`<batch>/<candidate>`）：`tasks/<batch>.env`，然后 `task.env` —— 整批一份

它在主机侧读一次，变成 `CreateSandbox` 的环境变量注进去，**文件本体不进沙箱**，所以凭证
不会进任何 checkpoint 归档。

沙箱里跑的是 `--dangerously-skip-permissions` 的 agent，无人监督。**给专用的、有额度
上限、能单独吊销的 token，别用你日常那个。**

---

## 5. 跑

```sh
sbx task create <task-id> <你的 seed 目录> --template <你的模板名>
sbx task status <task-id> --follow
sbx task trace  <task-id> --follow      # agent 在说什么
sbx task logs   <task-id>               # bootstrap / runner 日志
sbx task kill   <task-id>
```

卡在 `4b iterate` 就先 `task trace --follow`，再不行 `sbx probe instances` /
`sbx probe logs <sandbox-id>`。

`kill` 和下一次 `create` **至少隔 30 秒**：被 kill 的沙箱没有退出钩子，租约留在 NAS 上，
未过期时新沙箱会让位并空转。

循环停止只有三种原因：workspace 里出现 `.done`（成功）、连续三轮没有文件变化（停滞）、
`CONSTRUCT_MAX_ITERATIONS`（默认 10）跑完。只有第一种会让 `result.json` 里 `done: true`。

---

## 6. 一批候选 seed

一个子目录就是今天你会交给 `task create` 的那棵树。目录名机械变成 task-id：

```
my-batch/                     ← 目录名 = batch 名
  sglang-fp8/                 ← 子目录名 = 候选名 → task-id `my-batch/sglang-fp8`
    …                         内容和单条 `task create` 的 seed 一样
  sglang-int4/
```

命名：`[A-Za-z0-9._-]`，不以 `_` 或 `.` 开头；候选名不能是 `seed` / `archives` / `runs`；
batch 名不能等于任何已有的平铺 task-id。

```sh
sbx batch push my-batch/ --template <你的模板名>   # 只上传，不开沙箱
sbx batch list                                     # 各 batch 的模板、候选数、活沙箱
# cron，每 10–15 分钟一次，没人调就不会开下一个沙箱：
sbx batch reconcile my-batch
sbx batch status my-batch                          # 这一个 batch 里每条线一行
```

`push` 幂等：新子目录成为新成员；已跑过的候选重推 seed 是空操作（archives 压过 seed）；
删子目录什么都不发生。凭证按第 4 节，整批一份 `tasks/<batch>.env`。

模板要在 `/home/app/workspace/` 写两个和 `.done` 同级的空文件，否则对账器是瞎的：

| 文件 | 谁写 | 不写的后果 |
|---|---|---|
| `.measuring` | 测量开始 touch、结束 rm | Daytona 闸只按沙箱数，可能把 250 核打爆 |
| `.blocked` | agent 要人裁决时 touch | 需要人的线会一直续沙箱，直到撞每线上限 |

一条线的终态：`verified`（取归档）、`blocked`（看 resume.md，`rm .blocked` 恢复）、
`stopped`（沙箱数撞上限）。`.done` 但 verify 失败不是终态，会继续跑。

完整契约见
`docs/superpowers/specs/2026-09-14-batch-construction-design.md` 第 1 节。
