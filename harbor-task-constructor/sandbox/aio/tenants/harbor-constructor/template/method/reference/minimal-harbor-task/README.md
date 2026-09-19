# minimal-harbor-task

最小合法骨架，供 builder 角色在 `/home/app/workspace/task/` 不存在或无效时复制使用。

## 文件说明

```
minimal-harbor-task/
  task.toml            最小合法 task 配置，满足所有机械约束
  tests/
    Dockerfile         verifier 镜像，安装 Reward Kit
    test.sh            verifier 入口，输出 JSON 格式的评分结果
```

## 使用方法

```bash
cp -r /mnt/template/method/reference/minimal-harbor-task/. /home/app/workspace/task/
```

然后编辑 `task.toml`：
1. 替换 `instruction` 为实际任务描述
2. 替换 `[[verifier.checks]]` 中的 criterion module

编辑 `tests/test.sh`：
1. 实现实际的 criterion 评分逻辑
2. 确保输出包含 Reward Kit 格式的 programmatic score

## 机械约束核对

复制骨架后，确认下列条件全部满足：

- [ ] 不存在 `[[steps]]`
- [ ] `[verifier].environment_mode = "separate"`
- [ ] `[[artifacts]] source = "/workspace"`
- [ ] task、environment、verifier 均有 `network_mode = "public"`
- [ ] criterion 只使用 `kind: programmatic`
- [ ] `max_weight / min_weight <= 10`（排除 group、dimension-aggregation、agent-judge）
- [ ] nop=0, oracle=1

## 注意

这个骨架的 `tests/test.sh` 默认输出空的 `{"criteria": [], "score": 0.0}`，
这会让 nop 和 oracle 都得 0。复制后必须实现真实的 criterion 逻辑才能通过验证。
