# AIO Sandbox — 未决事项

**这份文件只记还欠的东西。** 做完的条目删掉，不留勾；实现细节去看代码和 `README.md`。

方向：从"跑 Harbor 构造任务的传输层"变成**通用脚手架**——不同业务方带着自己的 plan、
初始环境和提示词进来做构造工作。Harbor 是它的第一个租户，不是它本身。

主机侧是 `sbx` 包（入口 `sbx.sh`），沙箱内是 `runner/`，四个挂载点由 `sbx/mounts.py`
一张表生成，应用当前是 revision 9。循环在真沙箱里跑通过，见
`examples/hello-world/README.md`。

---

## 0. 平台实测（参考，不是待办）

这一节不是待办，是**从代码里读不出来的平台行为**——记在这里免得下一个人再花一轮沙箱去撞。
全部来自 2026-09-10 的三个探测沙箱（`probe-1/2/3`，镜像 AIO 1.9.0）和 2026-09-11 的
`hello-1/2`。

**挂载**

- **实例级 TOS 配置是叠加，不是替换。** `probe-1` 只窄化 `/mnt/template` 和 `/mnt/task`，
  容器里三个 TOS 挂载点都在，应用级的 `/mnt/runtime` 好好挂着。注意 `DescribeSandbox`
  **只回显实例级那两条**，所以它不能用来判断这件事。一次请求挂两个实例级 TOS 挂载点服务端认。
- **只读是内核层面的，不是约定。** `mount` 显示 `virtiofs (ro,relatime)`，往里写抛 `OSError`。
- **只读挂载要求后端前缀先存在**，而 `_runtime/v1` / `_templates/*` 恰恰要先挂上去才能往里
  推东西。解法是 `sbx app sync` 先给每个前缀补 `.keep` 空对象。**读写挂载不受这个限制**，
  空前缀照样能挂。
- **NAS 会自动创建不存在的 `remote_path`**，所以 NAS 侧不需要 `.keep`。
- **`NasMountPoint` 没有 `read_only`**（只有 `local_mount_path` / `remote_path`）。
  NAS 的只读性只能靠我们自己的代码保证。TOS 那边 `TosMountPoint` 有。
- **`UpdateFunction` 只发非 None 字段**，所以只带挂载配置的 sync 不会把 `command`、`port`、
  83 个环境变量清空。实测前后一个不少。

**沙箱生命周期**

- `CreateSandbox.Metadata` 服务端**接受并回显**；`ListSandboxes(metadata=…)` 是**真过滤**。
- `SetSandboxTimeout` 对运行中的沙箱**生效**，且**从调用时刻起算**，不是从创建时刻。
- **没有退出钩子可用。** 平台 SDK 没有 preStop/lifecycle；镜像自带的
  `SANDBOX_SHUTDOWN_HOOKS` 实测在 `KillSandbox` 时**也没跑**（钩子往 NAS 和 TOS 各写一行
  时间戳，两处都没有，而脚本本身确实在挂载上）。"退出时能跑代码"不能当依赖。
- `RUN_HOOK_INIT` / `RUN_HOOK_PRE_SERVICES` / `RUN_HOOK_POST_READY` 确实会跑，而且**能按
  沙箱变化**——它们是普通环境变量，`CreateSandbox.Envs` 里传就只影响这一个实例，不必动
  应用级配置。`bootstrap.sh` 现在就是这么起的（`RUN_HOOK_POST_READY`），注入 Command
  只负责 `exec` 应用本身。**post-ready 在挂载起来之后才触发**，所以原来那个轮询 waiter
  不再需要。
- **`GetFunctionInstanceLogs` 就是 stdout 通道**，能读到注入的 Command 原文和镜像启动过程。
  runner 自己的输出不在里面（重定向到文件再发 TOS），两个通道互补。

**镜像与模型**

- **注入的启动命令跑在 `uid=0(root)`**，而 `claude --dangerously-skip-permissions`
  **拒绝以 root 运行**。NAS 按 `uid=gid=1000` 挂，镜像自己的用户就是 `gem`（HOME
  `/home/gem`）。所以**跑模型的进程降权到 `gem`，装机的进程留在 root**——`npm install -g`
  以 `gem` 跑会因为写不了 root 拥有的全局前缀退出 243。
- **`claude -p` 的目录边界是真的。** 不加标志问它读 `/mnt/template/roles/probe.md` 答
  `CANNOT-READ`，加 `--add-dir /mnt/template` 就答出了文件里的暗号。
- **`claude -p` 默认文本输出不是实时的**，结束时整块吐（8 秒沉默后一次性出现）。
  要流式得用 `--output-format stream-json`。
- **镜像里没有 `claude`**（1.9.0），但有 node v22.23.2 + npm 10.9.8，出网通
  （npm registry 200、api.anthropic.com 404——404 也是连通的证据）。以 root 跑
  `npm i -g @anthropic-ai/claude-code` 实测 13–14 秒。
- **镜像默认在 `0.0.0.0:8080` 上不带认证**，启动日志自己警告了。见第 8 节。

---

## 1. 业务方接口（做减法，别加回来）

业务方交三样东西，**三样的生命周期完全不同**，别揉在一起：

```
模板（一份，多次复用，发版本，只读挂载）
  PROMPT.md      必需。脚手架只认这一个文件
  init.sh        可选。每个沙箱起来跑一次，装依赖、起服务、造数据
  verify.sh      可选。退出 0 = 程序意义上的完成
  roles/*.md     可选。PROMPT.md 自己去引用，脚手架不认识"角色"

初始树（一个任务一份，业务方上传**压缩包**到 seed 前缀，转 NAS 时统一解压）
  <随便什么>
  STATE.md       跑起来之后模型自己在这里读写

task.env（单独交给接入方，注入成环境变量，不进沙箱也不进仓库）
```

契约就一句：**我们会在你的工作树里反复跑 `claude -p < PROMPT.md`，直到你写下 `.done`。**

一个沙箱内的顺序：attach → `init.sh` → 迭代 `claude -p` → checkpoint。
`task.env` 不在这条链上——它在建沙箱之前就已经变成环境变量了。

模板和初始树分开的理由跟第 4 节的 `/mnt/runtime` 一模一样：同一个 `PROMPT.md` 配 50 棵
不同的初始树是常态，塞进每个 seed 就是 50 份拷贝，改一个字要重推 50 次，而且哪个任务在
跑哪一版无从查。

面向业务方的文档现在是两份：`ONBOARDING.md`（从零跑起第一个任务的顺序，共用现有应用、
自带 AK/SK）和 `examples/hello-world/`（一个能直接抄的模板 + 一页 README）。

- [ ] 把 hello-world 从"一个例子"提成"一份规格"，长度上限一页
- [ ] 规格里要补第三句：**模板是只读的**，要留痕就写进工作树
批量形态见 `docs/superpowers/specs/2026-09-14-batch-construction-design.md`。后置项
（冻结模板、归档保留、续期、Daytona 硬闸）记在该文第 7 节，不在这里重复。

### 初始树必须是压缩包，不是散文件

这条现在就是这么实现的（`sbx task create` 打包 → 推 → `archive.restore` 解压），
是对外规则不是实现细节。三条理由都已经踩过，别放松：

- **`/mnt/task` 是 virtiofs，会把权限位压成 777**；`/home/app` 是真 NFS，保留权限。
  散文件过 TOS 就丢模式位，可执行脚本到了 NAS 上不可执行。**只有 tar 包能完整穿过去。**
- **散文件没有"传完了"的信号**，attach 可能在上传中途开始读。压缩包 + `.sha256`
  边车（边车最后写、没边车一律当不存在）就是为这个设计的。
- 空目录和软链在对象存储里根本存不住。

- [ ] 修 attach 的报错：现在没边车只在日志里留一行 `skip ...: no sidecar`，抛出来的却是
      `nothing to attach from`，业务方看了完全不知道发生了什么。要直说"找到了包但没有
      .sha256"

### `init.sh` 的三条语义（要写进规格，不写一定踩）

- **它按 root 跑，迭代循环按 `gem` 跑，中间脚手架把工作区 chown 过去。** 所以装到系统里
  的东西（`npm i -g`、`apt install`）在下一相位的 `PATH` 上，写进树里的东西属主是对的。
  反过来说，`init.sh` 里判断"当前用户"的代码会得到 root，别据此做分支。
- **每个沙箱跑一次，不是每个任务跑一次。** 容器是新的、树是旧的——沙箱到期换一个，
  `apt install` 的东西没了但 `node_modules` 还在。所以它必须能重复跑，且重复跑要便宜
  （先判断再装，别无条件重装）。
- **它写进工作树的东西会被归档。** 装到树里的依赖会进每个 checkpoint 包；装到系统里的
  不会，但下个沙箱要重装。这个取舍归业务方，脚手架不猜。

非零退出是硬失败、循环根本不开始，这条已经实现在相位 4a。

### 凭证

`task.env` **只在建沙箱时读一次，注入成环境变量，文件本体不进沙箱**（详见第 8 节）。
业务方按 `KEY=VALUE` 交一个文件，接入方放在主机侧；默认找 `tasks/<task-id>.env`。

- [ ] preflight 检查环境里有没有模型凭证，没有就**当场失败**——否则第一轮 `claude -p`
      会以一个跟原因毫无关系的方式报错

**故意没有的东西**，以后想加回来先想想为什么当初砍掉：`task.json` 清单、`plan.json`
步骤表、进度文件、产物 glob、每步预算、`on_interrupt`/`skip_if`、一组步骤环境变量。
准则是：**能是约定就不做成 schema，能是默认值就不做成开关；等第二个租户真的需要不一样了
再加。**

---

## 2. runner 还欠的

迭代循环、相位 4a/4b 的权限分工、停滞检测、`.attached` 的原子发布、相位 4c 的
`verify.sh` 判定（`verified` / `failed` / 没有脚本就 `claimed`）都已经落地。剩下的：

- [ ] 每轮迭代结束把 `~/.claude/projects/**/*.jsonl` 拷进树。**不做退出钩子**——
      SIGKILL/OOM/宿主机故障都不给机会，而且当前注入结构下 runner 是被 reparent 的孤儿
      进程，SIGTERM 大概率发给 PID 1 而不是它；镜像自带的 `SANDBOX_SHUTDOWN_HOOKS`
      也不能救（第 0 节）。每轮拷严格地更好。
- [ ] checkpoint 策略：每轮迭代边界打一个；fingerprint 没变就跳过；距上次不足 10 分钟就
      跳过；保留最近 3 个 + 最后一个 verified（那个是交付物，永久留）。
      （`workspace.fingerprint` 已经在了，目前只用于停滞检测；归档覆盖判定、GC 活性代理、
      写进归档 manifest 都还没接上。）
- [ ] **删掉 `lease.py` 的心跳线程和 `LEASE_*` 调参**。互斥上移到主机侧（第 3 节）。
      NAS 上留一个 owner 文件，降级为诊断信息（"上次是哪个沙箱、什么时候碰的"），不再是
      门禁。顺带解掉一个已知缺陷：`lease.py` 注释声称"相位循环会检查 `held`"，而
      `__main__.py` 从来不读它——被抢占的运行会继续跑完并可能删掉别人的树。
- [ ] 观测：stdout 给沙箱 UI / terminal 看，**不再往 TOS 推进度**。`RunLog` 那套"本地
      缓冲 + 每相位整体重发"是为了绕开对象存储不能追加写，前提没了。`runs/` 可以瘦掉大半。
      TOS 只承载 checkpoint 和产物。

---

## 3. 主机侧

准入的前一半已经落地：`sbx task create` 建之前
`ListSandboxes(metadata={"task": id})`，有活的就拒绝并让人去 `sbx task kill`。

- [ ] 补上 check-then-act 的那半——**本机一个 flock**。创建入口是单一调度器，不需要
      分布式的东西，但现在两条 `task create` 并发仍然可能都查到"没有活的"。
- [ ] 沙箱到期前自动续期：先试 `SetSandboxTimeout`，续不了再让下一个沙箱接力，上限
      1440 分钟是硬的。**注意续期从调用时刻起算**（第 0 节），所以要按"还想再跑多久"
      传值，不是按"总共跑多久"。`sbx probe timeout` 是手动的那一半。

命名去 Harbor 化只做了沙箱内的路径（`/mnt/task`、`/home/app`、`/mnt/runtime`、
`/mnt/template`）。**后端前缀没换**：TOS 还在 `harbor-artifacts` 桶的 `/sandbox` 下，
NAS 还在 `/harbor` 下——换它们会让已有的树够不着，而沙箱内路径改名是免费的。

**火山 AK/SK 绝对不进实例。** 里面跑的是 `--dangerously-skip-permissions` 的 agent，等于
无人监督。所有 API 调用留在主机侧。这条守住了，"业务方能提供镜像和任意命令"才不至于变成
"业务方能拿到 AK/SK"。→ 因此**不要为了在实例内调 API 而给 `RoleTrn`**。
（业务方自己的凭证是另一回事，见第 8 节。）

---

## 4. 共性 / 个性分层

两层共性，同一个道理：按任务复制的东西，改一次要推 N 次。`runner/*.py` 是一层
（脚手架的），`PROMPT.md` / `init.sh` / `verify.sh` / `roles/` 是另一层（业务方的）。
**只有初始树是真正一份一个的。**

```
/sandbox/
  _runtime/v<N>/           脚手架的 runner   → /mnt/runtime  只读，**应用级**
  _templates/<name>/       业务方的模板      → /mnt/template 只读，实例级，无版本
  <task-id>/
    seed/                  业务方上传的初始树压缩包 + .sha256
    archives/              产出
    runs/
```

`/mnt/runtime` 是**应用级**的：它不带 task id，每个实例完全一样，没有理由在每次 create 里
重复声明——顺带把"某次创建忘了声明 runtime"从可能变成不可能。实例级只剩
`/mnt/template`（只读）和 `/mnt/task`（读写）。**应用级后端一律指向 `_unassigned` 死前缀**，
忘了窄化拿到的是空目录，不是别人的数据。

只读挂载顺带把一件事从"约定"变成"做不到"：**模型没法往模板上写字**。`STATE.md`、`.done`
只能落在工作树里，因为别的地方物理上写不了。挂载点变多也不破坏"挂载即隔离"：新增的两个
都是只读的，且不含任何任务数据。唯一破坏它的是第 5 节的 GC 根挂载。

### `claude -p` 的工作区边界会撞上 `roles/`

`claude -p` 默认把文件访问限制在 cwd 那棵树里。cwd 是 `/home/app/workspace`，模板在
`/mnt/template`，两者不嵌套——所以模板里任何**由模型在运行时读**的东西都在边界外。

数下来只有一样在这条线上：`PROMPT.md` 是管道喂 stdin 的（从来不作为文件被读），
`init.sh` / `verify.sh` 是 runner 跑的，**只有 `roles/*.md` 是 PROMPT.md 让模型自己去读的**。
而它恰好是"模型自己路由到角色"那一环，绕不开。

所以循环里的 `--add-dir $TEMPLATE_MOUNT_PATH` 是显式写下的意图，不是可选项，而且 argv 由
runner 定死不由模板给——否则模板能把 `--dangerously-skip-permissions` 拿掉或把 `--add-dir`
指到别处。**别指望 `--dangerously-skip-permissions` 顺带免掉目录边界**：就算成立也是附带的，
哪天标志语义收窄，`roles/` 会以一个跟原因毫无关系的方式失效。

也**别**用"把模板拷进工作区"来绕——那样它进每一个 checkpoint 包，而且重新变成可写的，
等于把只读挂载刚拿到的两条性质一起退回去。

业务方初始树里的 `.claude/settings.json` 会生效（他们可以自己加 `additionalDirectories`）。
是口子也是能力，反正第 6 节已写明这不是安全边界。

### 树为什么不能直接就是挂载根

挂载根要容纳三个兄弟——`workspace/`、`.lease/`、`.restore-<pid>/`。暂存必须是同文件系统上的
兄弟，因为恢复是"解到暂存 → rename 落位"，而 rename 只在单个文件系统内原子。那个原子性就是
"恢复被打断也绝不在树的位置留半棵树"的全部保证，而半棵树正好是 attach 会拒绝启动的状态。

想让树字面上就在 `/home/app`，只剩两条，都不划算：

- 挂到 `/home` —— 遮蔽镜像里的 HOME（`/home/gem`），`~/.claude` 会落到 NFS 上并被多个沙箱并发写）。
  `/home/app` 不撞镜像正是因为两个是兄弟目录，不是一个。
- 软链 `/home/app` → `/mnt/nas/workspace` —— 软链两侧路径不一致，transcript 里会自相矛盾

### 模板不做版本，runtime 做——两边不一样是有意的

模板前期就是高速迭代出来的，钉版本等于每改一个字都要重建任务，拦住的是自己。
所以 `_templates/<name>/` 直接挂，改了立刻生效。代价写在第 6 节。

runtime 保留 `v<N>`，理由不同：**炸的范围不一样**。模板写坏只影响那一个业务方的构造
质量；runner 写坏是所有租户一起遭殃，而且它是唯一会写归档、（GC 里）会删 NAS 树的东西。
回滚能力在那边值钱，在这边不值。

**但 runtime 改成应用级之后，选版本的位置也跟着变了**——从"每次 create 传个参数"变成
"应用发哪个版本"。连带的三条，是简化也是限制，写下来免得当成 bug：

- 升级 = 发一个指向 `_runtime/v4` 的新版本；回滚 = 把版本切回 `v3`。
  **所以 `v<N>` 目录还是要留**，不能直接覆盖 `_runtime/`，否则回滚得重传旧代码。
- **没法灰度**。新版本一发，之后建的所有沙箱一起换，不能只让一个任务先试。
- **同时跑的任务不可能用不同 runner 版本**，也就不能把某个任务钉在旧版本上。
  metadata 里的 `runtime` 标签从"选了什么"降级成"当时应用是什么"——仍然值得记，
  但它是观测不是控制。

现阶段这些都能接受：一个 runner 版本对应一次发布，没有矩阵要管。哪天需要灰度，
就得把 runtime 挪回实例级——**那条路是通的**（第 0 节），所以这是个能随时走回头的决定。

哪天模板稳定到"跑着的任务不该被改动影响"，再加钉版本——做法记在这里免得重推一遍：
建任务时把指针解析成具体版本、写进 metadata 标签和归档 manifest，接力的沙箱读钉住的
那个。指针要用一个对象（TOS 没有软链，virtiofs 挂前缀也跟不过去），且指针前缀本身
永远不挂载。

---

## 5. GC（唯一会删 NAS 的地方）

主机挂不了 NAS，所以执行必须在沙箱里；但**判断**必须在主机侧，因为判据里有
`ListSandboxes`，而实例不带凭证。挂 NAS 根 + TOS 根的 sweep 沙箱是对的做法，代价是
**破坏了"挂载即隔离"**——到目前为止沙箱里没有任何路径带 task id，所以任何代码都没能力
寻址到别的任务；根挂载之后路径变成插值的，而这偏偏是全系统唯一以删除为业的进程。

分两个 sweep，风险差一个量级：

| | 干什么 | 频率 | 要名单 |
|---|---|---|---|
| 补归档 | 遍历 NAS，树比最新归档新的就补一份到对应 TOS 前缀 | 勤 | 否 |
| 回收 | 按名单删 NAS 树 | 稀 | **是** |

- [ ] 补归档 sweep（只写不删，可以自己判断）。顺带兜住"沙箱被杀导致最后一段没归档"，
      这也是不做退出钩子的底气。
- [ ] 顺便报出**孤儿树**：NAS 上有目录但 TOS 上没有任何对应记录（建了沙箱没推 seed、
      task id 打错、早期实验残留）。只报告，不自动处理。
- [ ] 回收 sweep，五条约束一条都不能少：
  - [ ] **主机出名单，沙箱复核，两边都同意才删。** 沙箱拒绝自己推导名单——"决定删谁"
        这一步要发生在犯错不致命的地方。
  - [ ] fingerprint 复核，顺带盖住 TOCTOU（主机出名单到执行之间任务可能被重新开跑；
        真在跑树就在变，对不上就拒）。再加"最近 30 分钟被改过就不碰"兜住空转间隙。
  - [ ] 默认 dry-run，真删要显式开关
  - [ ] `/home/app/.gc-disabled` 急停文件
  - [ ] 单次爆炸半径上限（N 个任务或 M GB）
- [ ] 任务状态机，每一档都能程序化判定：
      `working` → `stopped` → `claimed`(.done 但没裁判) → `verified` → `archived`
      → `reclaimable`。**只有最后一档能自动回收。**
- [ ] 报告勤快、删除保守。空间紧张但没有 `verified` 的时候列出来给人看，别让 GC 自己想
      办法——省点空间和删掉几小时未归档的工作，代价完全不成比例。

---

## 6. 已知取舍（记下来，免得以后重新辩论）

- **模型可以"看起来在干活"地永远转下去**：不停改文件、不停更新 STATE.md、永不收敛。
  停滞检测抓不到（树确实在变）。能抓到的只有迭代上限、沙箱期限和账单。这是换取"能表达
  带循环的 plan"的价格。缓解手段在提示词里而不在代码里：让 PROMPT.md 要求模型每轮写明
  第几轮、收敛判据、离它还有多远。
- **交付是整棵树的包**（可能含 `node_modules`），业务方自己挑。等有人抱怨再做产物选择。
- **模板没有版本，跑着的任务会跟着模板漂。** 一次构造跨多个沙箱，沙箱 #1 用的是改之前的
  `PROMPT.md`，沙箱 #2 接力时用的是改之后的——同一个任务的前后半段按不同指令施工，
  归档里没有任何东西记录这件事。**前期这是要的**：模板会改正是因为跑着跑着发现要改，
  改完下一个沙箱立刻生效，等于给长任务留了个免费的转向舵。稳定期再钉版本，做法记在
  第 4 节。**别当 bug 修**——是选的。
- **步骤靠文件名/标记识别，重命名 = 重跑。** 反直觉，但也是"想重跑某步就删标记或改名"
  的正面用法。
- **这不是安全边界。** 业务方能提供镜像和任意命令，大家共用同一个 veFaaS 应用和账号。
  给互相信任的团队用的脚手架，不是多租户平台。
- **被杀的任务永远到不了 `verified`，所以 GC 永远不回收它**，直到有人再开个沙箱跑完。
  用空间的代价换掉误删的风险，是有意的。

---

## 7. 遗留

- [ ] **大体积下的静默截断仍未测到**。实测包只有 367 KiB，截断没有空间显形。
      211 MiB 那个包才是能验出来的。
- [ ] NAS 树灭失的兜底——用户明确说暂不考虑。
- [ ] 平台到底发不发 SIGTERM、留多少宽限期。**优先级低**：已经用
      `SANDBOX_SHUTDOWN_HOOKS` 做过一次等价实验，不成立（第 0 节），自己装 handler
      成立的概率也不高。真要测就在 runner 里装个 handler，收到往 NAS 写一行时间戳，
      然后 `KillSandbox` 看有没有那行。

---

## 8. 凭证边界

三种凭证，处理方式各不相同，别混为一谈：

| | 谁给 | 怎么进实例 | 为什么 |
|---|---|---|---|
| 火山 AK/SK | 接入方 | **不进** | 所有 API 调用留在主机侧，实例不需要它就能干活 |
| 模型 token | **业务方** | 注入成环境变量 | agent 自己要花的钱，不给它就没法工作 |
| 业务方自己的密钥 | 业务方 | 注入成环境变量 | 构造过程要调他们自己的东西 |

后两行**只有值进去，没有文件进去**。

第一行是守得住的边界，也是"业务方能提供镜像和任意命令"不至于变成"业务方能拿到 AK/SK"的
原因——因此**不要为了在实例内调 API 而给 `RoleTrn`**。

后两行排除不掉，但它们同属一件事：**跟着 `task.env` 走，谁的构造花谁的额度。** 接入方
既不替所有租户垫钱，也不替他们保管 token；租户自己决定给多大额度、什么时候吊销。
`.env.example` 里因此没有模型凭证。

要提醒业务方的：实例里跑的是 `--dangerously-skip-permissions` 的 agent，无人监督。
**给专用的、有额度上限的、能单独吊销的 token，别用日常那个。**

### task.env 只注入，不落地

`task.env` **在主机侧读一次，变成 `CreateSandboxRequest.envs`，文件本体不进沙箱。**
这样凭证从来没有以文件形式在任何地方静止过：不在 TOS 上、不在 NAS 树里、不在归档包里。
值得记下来免得以后有人"顺手"改回文件形式：

- **归档是整棵树打包**，凭证在树里就会进**每一个** checkpoint——一次泄漏变成几十份，
  散在 TOS 上一个跟"密钥"毫无关系的路径下。
- **业务方拿走的交付包**里因此也不含凭证。
- **轮换**变成"下次建沙箱时读到新值"，不用去改任何已经写出去的对象。

诚实地说，注入只是把暴露面**换小**了，不是消掉了：环境变量大概率能在 veFaaS 控制台上
看到，也能被容器里任何进程读到（后者本来就是的）。另外**多行的凭证塞不进环境变量**
（service account JSON、PEM 私钥），目前没有路径，真遇到再说。

### 镜像默认不设防：0.0.0.0:8080 没有认证

镜像自己在启动日志里打了出来：

> WARNING: SECURITY RISK - NO AUTHENTICATION CONFIGURED … The sandbox is listening on
> 0.0.0.0:8080 without any authentication. Anyone on the network can execute arbitrary
> code in this container.

这不是理论风险：那个端口后面就是 AIO 的执行 API，而容器里有整棵工作树、`task.env` 注入的
模型 token 和全部业务方密钥。**现在唯一挡着它的是网络形状**——应用配了
`enable_vpc=True` + `enable_shared_internet_access=False`，所以暴露面是 VPC 内网而不是
公网。这是"暂时没被打到"，不是"配好了"。

镜像给了两条出路，选哪条取决于 8080 上的 API 到底有没有人用：

| | 代价 |
|---|---|
| `PUBLIC_LISTEN_IPV4=127.0.0.1` | 只监听回环，网络上根本够不着。**但沙箱 UI / terminal 那套也跟着没了** |
| `SANDBOX_API_KEY=<随机>` | 留着 API，加一道认证。要连带决定这个 key 从哪来、谁拿得到 |

- [ ] 定这一条。**倾向 `PUBLIC_LISTEN_IPV4=127.0.0.1`**：到目前为止主机侧的窗口一直是
      TOS（`sbx task status` / `logs`），没有任何代码走 8080，那就别留一个没人用的洞。
      哪天真要沙箱 UI，再换成 `SANDBOX_API_KEY` 并把 key 一起注进 `envs`。
- [ ] 无论选哪条，都**别依赖 VPC 当唯一防线**——第 6 节写明这不是安全边界，但那说的是
      租户之间互相信任，不是"网段里任何人都能执行代码"。

---

## 9. 旧词汇对照

留着只为一件事：`docs/superpowers/specs/2026-09-10-aio-sandbox-transport-design.md`
**还没跟上**，读它的人需要知道词汇换过一轮。那份 spec 更新之后这一节就可以整节删掉。

| spec 里的说法 | 现在 |
|---|---|
| `pack-task.sh` / `push-task.py` / `create-sandbox.py` / `watch-status.py` | 一个 `sbx` 包，入口 `sandbox/aio/sbx.sh` |
| `/mnt/tos`（任务读写） | `/mnt/task` |
| `/mnt/nas`（NAS 工作区） | `/home/app`，树是 `/home/app/workspace` |
| 应用声明两个挂载点 | 四个，由 `sbx/mounts.py` 一张表生成 |
| runner 按任务推到每个前缀 | `/mnt/runtime` 共享只读挂载，`sbx runtime publish` |
| 7 相位，含相位 6 清理 | 没有清理相位（相位号留了空档），回收交给 GC |
| `.outcome.json` + `CLEAN_WORKSPACE` | 无条件归档 + `done` 布尔 |
| 单条 `CONSTRUCT_COMMAND` | 4a `init.sh` + 4b `PROMPT.md` 迭代循环 |
| `/app` 是 NAS 工作区的 bind mount | 没有 bind mount，也没有 build-capsule 契约要保 |

三个角色（NAS 工作区 / 沙箱执行环境 / TOS 归档）**没有变**，seed 与 archives 分前缀
也没有变。变的是上面那层生命周期词汇。

- [ ] 更新那份 spec，然后删掉这一节

---

## 10. CLI：业务方自助

当前形态（`sandbox/aio/sbx/`，入口 `sbx.sh`）：

```
sbx app show                        核对应用的四个挂载点、stable 版本、revision 列表
sbx app sync [--dry-run] [--writable-all]
                                    补 .keep → 从 mounts.py 生成四条 → UpdateFunction → Release
sbx runtime publish [--version vN]  bootstrap.sh + runner/ → _runtime/vN/
sbx template publish <dir>          → _templates/<name>/，直接覆盖，无版本
sbx task create <id> <dir> --template <name> [--dry-run] [--env K=V]
                                    CLI 打包 + 算 sha256 + 传 <id>/seed/ + CreateSandbox（带 metadata）
sbx task push|status|logs|get|list|kill
sbx probe describe|instances|logs|revision|timeout
```

**"自动转到 NAS"不用新建**：业务方把初始树传到 `<task-id>/seed/`，第一个沙箱的 attach
就会把它展开到 NAS（`workspace._pick_source`，archives 优先于 seed）。CLI 只负责上传。

- [ ] `sbx app sync` 目前一次改全部四条。要不要支持只改一条，等真的需要再说

### 这个形态逼出来的一个问题：业务方拿什么权限上传

TOS 桶是接入方的。业务方要自己 `publish` 和 `create`，就得能往桶里写。三条路：

| | 代价 |
|---|---|
| a. 给业务方**前缀受限**的 TOS 凭证（policy 限死 `_templates/<name>/*` 和他们的 task 前缀） | 业务方从此持有一个桶凭证 |
| b. 业务方把目录交给接入方，接入方推 | 不 scale，但两三个团队时最诚实 |
| c. 接入方跑一个小服务，CLI 调它 | 要维护一个控制面 |

**倾向 (a)**，因为第 6 节已经写明"这不是安全边界，是给互相信任的团队用的脚手架"，
而 (c) 的成本明显超出当前规模。但要说清楚：**这跟"接入方的 .env 只用来跑通 sandbox"
是有出入的**——(a) 之后业务方手里也有凭证了，只是范围被 policy 限死。

注意 `create` 比 `publish` 要的多：它还要调 `CreateSandbox`，而**火山 AK/SK 绝对不能给
业务方**（第 3 节）。所以 (a) 真正能自助的只有 `template publish` 和 `task push`，
`task create` 无论如何都得由接入方或一个控制面来发——这条在选之前就得摆平。

- [ ] 定这一条。它决定 CLI 是本地直连 TOS 还是走服务，改起来不便宜。
      **现在 `sbx` 是接入方专用的**（`.env` 里就是接入方的 AK/SK），先按这个用着
- [ ] 选 (a) 的话，把 policy 模板也放进仓库，别让每个接入方自己拼
