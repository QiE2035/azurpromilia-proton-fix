# 贡献指南

感谢参与。这个项目很小，规则也就几条，请尽量遵守。

## 环境

Python 一律用 [uv](https://docs.astral.sh/uv/)，不要用 `python -m venv` / `pip install`：

```bash
uv venv
uv pip install -e ".[dev]"
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

改了依赖记得 `uv lock`，并把 `uv.lock` 一起提交。

## 提交前

```bash
uv run ruff format .
uv run ruff check --fix .
uv run pytest -q
```

CI 会跑同样的三条（见 `.github/workflows/ci.yml`），本地过不了就不用推了。

## 报告游戏更新导致补丁失效

这是最常见的 issue，请附上：

1. `apfix status` 与 `apfix info` 的完整输出；
2. `sha256sum AzurPromilia_Data/Plugins/mj_sdk/union_pcsdk.dll`；
3. 游戏版本号（`1.0.2.2/` 这种目录名，或启动器里的版本）；
4. 如果愿意，附 `pcsdk_log.txt` 里从启动到卡住的那一段。

## 新增 / 修复补丁

`src/apfix/patches.py` 里每个 `Patch` 只包含**指令形状**，不包含偏移：

```python
Patch(
    id="my-patch",
    title="一句话说明效果",
    function="Namespace::Function",
    before=[...],  # 目标之前的指令（尽量唯一、带立即数或相对调用）
    original=[...],  # 要被改写的原始字节
    replacement=[...],  # 改写后的字节，长度必须与 original 相同
    after=[...],  # 目标之后的指令
    summary="为什么需要它",
    rationale="指令层面的解释",
)
```

硬性要求：

- `len(original) == len(replacement)`，不改函数布局；
- 签名（`before + ??*n + after`）在**打补丁前后都必须唯一命中**，
  所以不要把手改的字节放进 `before` / `after`；
- `after` 不要取到含重定位或绝对地址的字节（会随版本漂移）；
- 本地跑 `apfix status` 确认是 `pending`/`applied` 而不是 `mismatch`，
  再补一条 `tests/` 里的用例（用合成字节即可，不要提交游戏文件）。

## 不要做的事

- 不要提交任何游戏文件、DLL、`.apfix-backup`、manifest、日志、截图；
- 不要把补丁扩展到游戏逻辑、网络协议、付费或账号校验——本项目只修 Linux 下的窗口与输入；
- 不要引入需要编译期的依赖（保持 `uv pip install -e .` 一把过）。

## 提交信息

`<scope>: <动词开头的短句>`，例如：

```
engine: detect ambiguous signatures with a clearer error
patches: wildcard the call target in skip-agreement-gate
docs: add wine window-hierarchy diagram
```
