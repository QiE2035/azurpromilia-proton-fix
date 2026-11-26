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

## 相关项目（同一问题的其他解法）

同一个「SDK 窗口在 Wine 下不可见」的问题，别人已经用另外两个层次解过，按介入层从深到浅：

| 项目 | 做法 | 代价 |
| --- | --- | --- |
| [suluoMISS/dwproton-11.0-17-azur](https://github.com/suluoMISS/dwproton-11.0-17-azur) | 改 **Wine**（dwproton 11.0-17）：在 `NtUserSetParent` 里把「设父窗口」转成「设 owner」，让分层 ARGB 窗口不被销毁重建；再让这类面板保持 unmanaged，避免被 WM 压回 641×480 | 要重编译 Wine；等上游合入后应切回官方版本 |
| [puji4810/azur-sdk-qt](https://github.com/puji4810/azur-sdk-qt) | **桥接进程**：另起一个宿主加载官方 Qt SDK，用本机 PyQt6 窗口显示 SDK 画面并转发输入 | 多一层进程与输入转发；依赖 PyQt6；协议/验证仍走官方 CEF |
| [rakuyoao/AzurPromilia-SDK-Repair](https://github.com/rakuyoao/AzurPromilia-SDK-Repair) | 上一条的 macOS/CrossOver 版本（Swift + AppKit 原生控件） | 仅 macOS |
| **本项目** | 改 **游戏自带的 `union_pcsdk.dll`** 两条指令：不弹协议门、`SetParent(…, NULL)` 让 SDK 窗口本就是独立顶层窗口 | 不碰 Wine、不加进程；但会改动游戏文件（可一键回滚），且需要按 SDK 版本匹配签名 |

三者的目标一致，互斥但不冲突——Wine 修好之后本项目也可以 `apfix revert` 撤掉补丁。如果你更在意「不动游戏文件」，
优先看 dwproton 那个；如果你连游戏 DLL 都不想改、并且不介意多一个宿主进程，看 azur-sdk-qt。

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
