## 改了什么

<!-- 一句话说清动机。涉及新补丁的，请说明在哪个游戏版本上验证过。 -->

## 检查清单

- [ ] `uv run ruff check .` 通过
- [ ] `uv run ruff format --check .` 通过
- [ ] `uv run pytest -q` 全过
- [ ] 新补丁：`len(original) == len(replacement)`，且签名在打补丁前后都能唯一命中
- [ ] 没有提交游戏文件、DLL、`.apfix-backup`、manifest、日志或截图

## 验证（新补丁必填）

- 游戏版本 / `union_pcsdk.dll` sha256：
- `apfix info` 关键输出：

```
```

- 实机验证：黑屏是否消失、登录框是否可见可输入
