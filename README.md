anthor的内部是字典
资源max限制

时间

Trial 墙钟：76.6 min（UTC 10:13:28 → 11:30:04，本地大约 18:13 → 19:30）。
其中环境/agent 安装约 50s，agent 执行合计 ~63 min，其余是每步 verifier（约 18–20s）和步骤间拷贝。

┌────────────────────────┬───────────────────┬──────────┬────────────┬──────┐
│ 步骤 │ Agent │ Verifier │ Agent 耗时 │ 占比 │
├────────────────────────┼───────────────────┼──────────┼────────────┼──────┤
│ 01_repo_profile │ 18:15:06–18:16:09 │ ~20s │ 1.1 min │ 1.7% │
├────────────────────────┼───────────────────┼──────────┼────────────┼──────┤
│ 02_repo_gate │ 18:16:51–18:17:31 │ ~18s │ 0.7 min │ 1.1% │
├────────────────────────┼───────────────────┼──────────┼────────────┼──────┤
│ 03_environment │ 18:18:23–18:25:23 │ ~19s │ 7.0 min │ 11% │
├────────────────────────┼───────────────────┼──────────┼────────────┼──────┤
│ 04_simula_plan │ 18:26:31–18:27:49 │ ~20s │ 1.3 min │ 2.1% │
├────────────────────────┼───────────────────┼──────────┼────────────┼──────┤
│ 05_task_design │ 18:28:58–18:56:54 │ ~20s │ 28.0 min │ 44% │
├────────────────────────┼───────────────────┼──────────┼────────────┼──────┤
│ 06_task_review │ 18:58:17–19:07:28 │ ~19s │ 9.2 min │ 15% │
├────────────────────────┼───────────────────┼──────────┼────────────┼──────┤
│ 07_verifier_generation │ 19:08:51–19:20:39 │ ~19s │ 11.8 min │ 19% │
├────────────────────────┼───────────────────┼──────────┼────────────┼──────┤
│ 08_verifier_review │ 19:22:11–19:25:36 │ ~19s │ 3.4 min │ 5.4% │
├────────────────────────┼───────────────────┼──────────┼────────────┼──────┤
│ 09_package │ 19:27:12–19:28:11 │ ~20s │ 1.0 min │ 1.6% │
├────────────────────────┼───────────────────┼──────────┼────────────┼──────┤
│ 合计 │ │ │ ~63 min │ 100% │
└────────────────────────┴───────────────────┴──────────┴────────────┴──────┘

时间结构合理：重活在 05 设计 + 07 写 verifier，轻活（01/02/04/09）都在 1 分钟量级。03 的 7 分钟主要是 docker build（记录 build_seconds=101）。

最终打包 5 个任务：repair-rust-bindings / build-suricata-engine / repair-http-rules / migrate-yaml-config / repair-tls-decoder（c5 在 06 被拒）。

---

逐步：有没有按 instruction 做

判断标准：角色边界、先写 handoff、禁止越界写、GATE 命令、工作顺序。Verifier 过了只说明契约文件在，不代表行为完全合规。

01 画像 — 遵循好

- 第一下就 ensure-handoff 01_repo_profile，扫 repo / taxonomy / target_spec，只写了 01_repo_profile.json，跑了 require-handoff + check-profile。
- 没动 /synthesis/output/，没开 02。
- 仓库没有 .git，commit 用了 target_spec 的 d681600f…，没有瞎编。

小瑕疵：entrypoints 写成了源码路径（src/main.c、configure.ac），不是可执行命令；tags 几乎整表抄了 target.tags。都不挡 GATE。

02 门禁 — 基本遵循，顺序略偏

- 只写 02_repo_gate.json，静态看 LICENSE / autogen / CI，没有在 input repo 里 install/build/test。
- hard checks 全 true，分数 0.88–0.95，阈值 0.2，accept。
- 偏差：instruction 要求长检查前先 ensure-handoff。它先 Read/扫树，后半段才 ensure + require + check。

03 环境 — 交付物齐全，有两条明确违规

做对的：

- 先短读再落地 Dockerfile / setup.sh / setup-overlay.sh(noop) / smoke_test.sh / assets/，然后 docker build -t synth-env:03 + smoke，再 GATE。
- git clone 钉 commit，没 COPY input 树，没种 bug，没写 candidates。

没按字面做的：

1. 基镜像装了观察/调试栈。instruction 写得很死：不要装 verifier 栈（python3/pytest/jq…）；观察工具归 05 overlay。setup.sh 里仍有 jq、tshark、gdb、strace、vim-tiny、nano。python3 还能用「Suricata 工具链 / target.languages」辩，jq/gdb/tshark 不行。
2. apt 包没有 pin 版本（只 pin 了 rustc=1.98.0、cbindgen=0.27.0），instruction 要求 pin every package。

这两条 verifier 都不查，所以仍是 1.0。

04 采样计划 — 遵循好

- 只写 04_simula_plan.json。N=6 → G=3、local_k=2、complexified=2（c1/c3），slot 词汇从 global 拷贝，entrypoint 都在 03 列表里，check-simula-plan 过了。
- 没写 candidates、没改 sealed env、没 docker build。

软偏差：primary_input 指向 /data/rules/...、/data/etc/suricata.yaml.in，03 的 assets/ 只有 README。instruction 允许「05 overlay 再补」，但更推荐用已有路径。

05 任务设计 — 契约遵循，过程偏重

顺序是对的：6 份 instruction.md → task.toml → overlay setup-overlay.sh → 05_task_design.json → check-design。
slot id/词汇一字不改；instruction 是 goal-first ASCII 段落；task.toml 用了 factory overlay（schema_version=1.4、network_mode=public、hard 带宽 240min、junior=2x、timeout=14400）。

过程偏差：

- instruction 说 不要端到端 Docker 原型，纸上设计，最多抽查一条命令。实际跑了 synth-env:03、合成 pcap、scratch-merge 后 docker build 证明 6 个 overlay。28 分钟里很大一块是这个。
- 加了 setup-overlay.sh 之后做 scratch-merge 证明 env_build=passed，这条反而是 overlay 规则要求的，所以 05 超时主要是「合规的重活 + 超额探测」叠在一起。

06 评审 — 遵循好，而且真正在审

- 只改 4 个 instruction.md（补绝对路径/成功条件/ASCII 澄清），没改 goal、没改 05 state、没动 sealed env。
- c5 被拒（difficult=0.55，essential_difficulty=fail）：tiny pcap 计数 + 三条 threshold，不够 hard 的 3–6h。这是少见的按 rubric 否决，不是全过。
- 通过 5 个：c1/c2/c3/c4/c6。

07 写 verifier — 大体遵循，骨架时机含糊

- 只给 06 批准的 5 个写 tests/test.sh，跳过 c5；没改 instruction/toml/sealed env。
- 先 ensure-handoff 07_verifier，再写测试和 golden，最后 check-verifiers。
- 有负向 smoke（未修复镜像应得 0）和 c4 正向探测。

偏差：instruction 要求 先落地 skeleton test.sh，再做长 docker 探测。日志里 ensure-handoff 之后很快就 docker run synth-cand-\* 挖 ground truth，和「先骨架后探针」不完全一致。另外在 Docker 挂载上耗了不少时间（环境问题，不是越界）。

08 审 verifier — 最小修改合格，handoff 偏晚

- 只改 tests/test.sh：所有脚本先把 reward.txt 写成 0；c1 加 C header 标记；c2 强制 --prefix=/usr/local。没改 instruction，没改 07_verifier.json。
- 偏差：08 前 8 个 tool 全是 Read；ensure-handoff 和 GATE 挤在最后。instruction 要求评分前先落 skeleton。

09 打包 — 遵循好

- 纯组装：bash 拷贝，没有 Write、没有 docker build、没有改 sealed env。
- 按 08 的批准列表顺序打 5 个 kebab slug，README.md 写了 provenance，check-package 过了。

---

总评

┌───────────────────────────────────────────────┬───────────────────────────────────────────────────────────────────┐
│ 维度 │ 判断 │
├───────────────────────────────────────────────┼───────────────────────────────────────────────────────────────────┤
│ 角色隔离（每步只写自己的 state/目录） │ 强。没有跨步改 03 env、没有 07 改 instruction、没有 09 重设计。 │
├───────────────────────────────────────────────┼───────────────────────────────────────────────────────────────────┤
│ Hard gate 文件 + GATE 脚本 │ 强。9/9 require-handoff/check-\*，verifier 全 1.0。 │
├───────────────────────────────────────────────┼───────────────────────────────────────────────────────────────────┤
│ 工作顺序（ensure → 干活 → GATE） │ 中上。01/03/04/05/07/09 较好；02/08 检查完才 ensure。 │
├───────────────────────────────────────────────┼───────────────────────────────────────────────────────────────────┤
│ 行为禁令（少装工具、少 Docker 原型、静态 02） │ 中。03 工具装多、05 Docker 过重，是最实质的 instruction 偏离。 │
├───────────────────────────────────────────────┼───────────────────────────────────────────────────────────────────┤
│ 内容质量信号 │ 中上。06 真拒了过易的 c5；07/08 的 verifier 不是 existence-only。 │
└───────────────────────────────────────────────┴───────────────────────────────────────────────────────────────────┘

一句话：agent 把「写对文件、跑过 GATE、不越权改别人的产物」执行得很稳；没有把 instruction 里那些「别装 jq、别在 05 里把 Docker 跑穿、先 ensure 再探」当成硬约束。 所以 reward=1.0 和「严格遵循 instruction」不是一回事——当前 verifier 只锁契约形状，锁不住这些过程纪律。
