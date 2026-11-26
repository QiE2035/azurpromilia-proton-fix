# apfix — Azur Promilia on Linux (Proton/Wine)

[![CI](https://github.com/QiE2035/apfix/actions/workflows/ci.yml/badge.svg)](https://github.com/QiE2035/apfix/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

Azur Promilia（蓝色星原：旅谣）在 Linux + Proton 下能跑起来，但会被 `mj_sdk`
挡住：**用户协议窗和登录窗都是 Qt 子窗口，在 Wine 里被 Unity 的 D3D/Vulkan 输出完全盖住**
——黑屏、看不见按钮、也点不动。

`apfix` 用两条**字节签名补丁**修掉这个问题，不需要硬编码偏移：

| 补丁 | 作用 |
| --- | --- |
| `skip-agreement-gate` | 不再因为协议状态不一致而 `blockInput` + 弹不可见的协议窗 |
| `detach-overlay-window` | SDK 的 Qt 窗口不再被 `SetParent` 进 Unity 窗口，变成独立顶层窗口，可见可交互 |

补丁按**指令特征**定位（`??` 通配会变的相对地址/立即数），游戏更新后通常不需要改代码；
真的失配时工具会明确报"signature not found"，而不是把二进制写坏。

---

## 快速开始

```bash
# 1) 安装：直接从仓库装成工具（本仓库不发 PyPI 包）
uv tool install git+https://github.com/QiE2035/azurpromilia-proton-fix
# 或者克隆下来用（开发模式）
git clone https://github.com/QiE2035/azurpromilia-proton-fix && cd azurpromilia-proton-fix
uv venv && uv pip install -e . && uv run apfix status --game-dir ~/Games/AzurPromilia/AzurPromilia_Game

# 2) 看一眼现状（只读）
apfix status --game-dir ~/Games/AzurPromilia/AzurPromilia_Game

# 3) 打补丁（自动备份 + 写 manifest）
apfix apply  --game-dir ~/Games/AzurPromilia/AzurPromilia_Game

# 4) 启动
cd ~/Games/AzurPromilia/AzurPromilia_Game
dwproton waitforexitandrun ./AzurPromilia.exe -start=azurpromilia_launcher
```

`apfix doctor` 会检查 Proton、prefix、DLL 和残留进程；`apfix revert` 一键回滚
（字节级反向改写，有备份时也可以 `--from-backup`）。

> **启动参数别漏**：`dwproton` 在参数 ≥2 个时不会自动补 verb，必须自己写
> `waitforexitandrun`；`-start=azurpromilia_launcher` 是启动器下发的参数，没有它游戏会停在
> "请使用启动器启动游戏"。仓库里的 [`scripts/run-game.sh`](scripts/run-game.sh) 两件事都做了。

---

## 原理（一句话版）

```
Unity 窗口 (D3D/Vulkan swapchain 直接画到 X11 window)
└── SDK Qt 子窗口  ← Wine 里画不出来，输入也进不去
```

把 `SetParent(winId, game_hwnd)` 的第二个参数换成 `NULL`，Qt 窗口就变成独立 toplevel，
Wine 会为它创建自己的 X 窗口 —— 立刻可见、可点击。

细节、汇编、失败尝试都在 [docs/how-it-works.md](docs/how-it-works.md)。

---

## 命令

```
apfix status   显示每个补丁的状态（applied / pending / mismatch）
apfix apply    打补丁（--dry-run 只报告；--no-backup 不留备份）
apfix revert   回滚（--from-backup 直接用备份覆盖）
apfix info     逐条诊断：签名、命中的文件偏移、当前字节
apfix list     列出已知补丁及理由
apfix doctor   环境体检：游戏目录 / DLL / prefix / dwproton / 残留进程
```

`status --quiet` 只返回退出码（0 = 两个补丁都在，1 = 还没打，2 = 找不到 DLL），方便写进启动脚本。

`--game-dir` 省略时会从当前目录往上找 `AzurPromilia.exe`。

---

## 文档

| 文档 | 内容 |
| --- | --- |
| [docs/how-it-works.md](docs/how-it-works.md) | 卡死的完整链路、PE/VA 换算、为什么选签名而不是偏移 |
| [docs/patches.md](docs/patches.md) | 每个补丁的汇编上下文、改写字节、为什么这么改、踩过的坑 |
| [docs/troubleshooting.md](docs/troubleshooting.md) | 黑屏、看不见窗口、输入没反应、补丁失配、游戏更新后怎么办 |
| [docs/faq.md](docs/faq.md) | 会不会被反作弊盯上、能不能用于其他游戏、为什么不做成 DLL 注入 |
| [CONTRIBUTING.md](CONTRIBUTING.md) | 开发环境、加补丁的流程、签名写法约定 |

---

## 仓库结构

```
src/apfix/
  signature.py   签名匹配（?? 通配、锚点扫描、before+gap+after 组合）
  patches.py     补丁定义（只有指令形状，没有任何硬编码偏移）
  engine.py      apply / revert / 状态判定、原子写、备份、manifest
  locate.py      找游戏目录与 Proton prefix、查残留进程
  pe.py          PE 头解析（节归属）
  cli.py         click 命令
scripts/
  run-game.sh    带正确参数启动（并且先做补丁自检）
  pdata.py       用 .pdata 反查"这个地址属于哪个函数"，定位时很好用
docs/            原理 / 补丁细节 / 排障 / FAQ
tests/           签名、引擎、CLI 三组用例（不依赖游戏文件）
```

## 相关项目与横向对比

同一个「SDK 窗口在 Wine 下不可见」的问题，目前有四个解法，介入层从深到浅：

| 项目 | 改哪里 | 关键手法 | 主要代价 |
| --- | --- | --- | --- |
| [suluoMISS/dwproton-11.0-17-azur](https://github.com/suluoMISS/dwproton-11.0-17-azur) | **Wine**（dwproton 11.0-17） | 在 `NtUserSetParent` 里把「设父窗口」转成「设 owner」，让分层 ARGB 的 X window 不被 `destroy_whole_window()` 销毁重建；再让这类 `WS_POPUP+LAYERED+TOOLWINDOW` 面板永远不进入 managed，免得被 WM 按 `WM_NORMAL_HINTS` 压回 641×480 | 两个 `.so` 锁死 Wine 11.0 的 ABI，升级即失效；需等上游合入 |
| **本项目（apfix）** | 游戏自带的 `union_pcsdk.dll` | 两条字节补丁：NOP 掉协议门的 `jbe`；把 `SetParent(winId, parent)` 的父窗口换成 `NULL`，让 Qt 窗口本来就是顶层窗口 | 改了游戏文件；签名随 SDK 版本要维护 |
| [puji4810/azur-sdk-qt](https://github.com/puji4810/azur-sdk-qt) | 加一个**桥接宿主进程** | 宿主加载官方 Qt SDK，把画面渲染到本机 PyQt6 窗口并把输入转发回去；官方 CEF 仍在 Proton 里跑 | 多一层进程 + 输入转发；依赖 PyQt6；GPL-3.0 |
| [rakuyoao/AzurPromilia-SDK-Repair](https://github.com/rakuyoao/AzurPromilia-SDK-Repair) | macOS / CrossOver | 上一条的 Swift + AppKit 原生控件实现（`azur-sdk-qt` 的上游） | 仅 macOS，FineWine 锁 3.1.2 |

### 打分

权重：有效性 30%、侵入性 25%（越不动别人的东西越高分）、维护成本 20%、安装成本 15%、
被反作弊看到的暴露面 10%。

| 方案 | 有效 | 侵入 | 维护 | 安装 | 暴露 | 加权 |
| --- | --- | --- | --- | --- | --- | --- |
| dwproton-azur（改 Wine） | 9 | 10 | 5 | 8 | 10 | **8.55** |
| azur-sdk-qt（桥接宿主） | 8 | 7 | 9 | 5 | 8 | **7.55** |
| apfix（本项目，改游戏 DLL） | 9 | 5 | 7 | 10 | 5 | **7.20** |
| rakuyoao（仅 macOS） | — | 7 | 9 | 3 | 8 | 不参与排名 |

### 怎么选

- **不想碰游戏文件、且就在 dwproton 11.0-17 上** → dwproton-azur。它打在根因上（Wine 的
  `SetParent` 语义与 Windows 不一致），所有同类 SDK 一起受益，ACE 的完整性检查也看不到变化。
- **想长期跟着官方 SDK 走、不介意多进程** → azur-sdk-qt。它不吃 Wine 版本也不吃游戏版本，
  维护成本最低，代价是装机门槛和 GPL。
- **只想今晚能玩、随时一键撤回** → 本项目。不依赖 Wine 版本，任何 Proton 都能用；
  代价是动了游戏文件，以及签名需要跟着 SDK 版本维护。

三者互斥但不冲突：Wine 修好之后 `apfix revert` 撤掉补丁即可，反向也成立。

## 状态

- 已验证：Proton (dwproton) + Wine 9/10、NVIDIA RTX 3050、`.text` 补丁、登录窗口可见且
  可输入（KWin/EIS 注入与真实鼠标键盘都正常）。
- 输入法、全屏切换等周边兼容性尚未系统测试 —— 欢迎 issue 里补充。

## 免责 / Disclaimer

本项目只修改**本机安装的游戏文件**，用于让游戏在官方未支持的平台上正常显示与操作；
不绕过任何付费、账号或在线校验，不修改游戏逻辑，不提供或分发任何游戏资源。
请在遵守游戏用户协议的前提下自行决定是否使用。代码以 MIT 协议发布，不提供任何担保。

## License

MIT — 见 [LICENSE](LICENSE)。

[![](https://img.shields.io/badge/powered_by-dsh-4D6BFE?style=flat-square&logo=deepseek&logoColor=white)](https://github.com/deepseek-ai/deepseek-harness)
