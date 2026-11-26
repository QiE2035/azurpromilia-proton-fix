# Changelog

格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，
版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [Unreleased]

## [0.1.0] - 2026-11-26

### Added

- 签名式补丁引擎：`??` 通配、最长锚点扫描、`before + gap + after` 组合签名，
  打补丁前后都能命中同一位置，不依赖任何硬编码文件偏移。
- 补丁 `skip-agreement-gate`：NOP 掉 `OnCheckAgreementFinished` 里的协议门分支，
  解决 Wine 下协议窗不可见导致的永久黑屏 + 输入锁定。
- 补丁 `detach-overlay-window`：把 `SetParent(winId, parent)` 的父窗口改为 `NULL`，
  让 mj_sdk 的 Qt 覆盖窗（协议窗、登录窗）成为独立顶层窗口，可见且可交互。
- CLI：`status` / `apply` / `revert` / `list` / `info` / `doctor`。
- 安全写入：原子替换、`*.apfix-backup` 原件备份、`*.apfix.json` manifest、幂等（重复 apply 无副作用）。
- 按字节反向还原：即使备份丢失也能 `revert`（用 replacement → original 的逆映射）。
- 游戏进程检测：DLL 被占用时拒绝写入（可 `--force` 跳过）。
- 自动发现安装目录与 Proton prefix；`doctor` 检查 dwproton / proton / prefix / DLL / 进程。
- 文档：`how-it-works`（定位过程与原理）、`patches`（两个补丁的汇编上下文与踩坑）、
  `troubleshooting`、`faq`。
- 测试：签名匹配、签名失效检测、apply/revert 无损往返、幂等、dry-run、CLI 全流程。

[Unreleased]: https://github.com/QiE2035/azurpromilia-proton-fix/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/QiE2035/azurpromilia-proton-fix/releases/tag/v0.1.0
