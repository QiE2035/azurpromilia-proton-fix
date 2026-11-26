# 这游戏在 Linux 上到底卡在哪

这份文档记录定位过程，方便以后游戏更新出问题时快速复现思路。

## 1. 三个连续的坎

```
dwproton ./AzurPromilia.exe
        └── 弹窗「请使用启动器启动游戏」          (缺启动参数)
dwproton waitforexitandrun ./AzurPromilia.exe -start=azurpromilia_launcher
        ├── 黑屏 + blockInput，无任何可交互 UI        (mj_sdk 协议窗不可见)
        └── 绕过协议后：只有背景立绘，点不到登录框    (mj_sdk 登录窗不可见)
```

### 坎一：启动参数

`AzurPromilia_Game/1.0.2.2/launcher.exe` 是个 Electron 应用，`resources/app.asar` 里
`main.js` 的启动逻辑是：

```js
const { launchEntry, launchParams } = res.data;   // 来自服务端接口
spawn(exePath, launchParams.split(" "), { detached: true, cwd: rootPath });
```

服务端下发的值是（Electron 缓存 `AppData/Cache/Cache_Data/data_1` 里能找到原文）：

```json
{"launchEntry": "AzurPromilia.exe", "launchParams": "-start=azurpromilia_launcher"}
```

所以手动启动必须带 `-start=azurpromilia_launcher`。缺少它时弹的对话框文案
（`only_launcher`）只存在于 `AzurPromilia_Data/resources.assets` 的本地化表里，
游戏本体是按 key 查表的，所以直接搜二进制搜不到。

另外 `dwproton` 封装脚本在参数 ≥2 个时不会自动补 verb：

```bash
# 错：Proton: Need a verb.
dwproton ./AzurPromilia.exe -start=azurpromilia_launcher
# 对：
dwproton waitforexitandrun ./AzurPromilia.exe -start=azurpromilia_launcher
```

### 坎二：协议窗（`mj_agr::AgreementWidget`）

启动日志（游戏目录 `pcsdk_log.txt`）：

```
[agreement]Failed to open file: ".../Game_35_C000_SC000/agreement.json" 找不到路径。
RequestDomain: agreement not agreed, url: /sdk/client/union/getconfiglist
[agreement]from 2 to 0                       # 服务端把状态改回未同意
notify CheckAgreementFinished due to no agreed policy
[agreement]to open main agreement wnd
[SdkController::SendBlockInputEvent] sdk window exists: true
<日志到此为止>
```

`agreement.json` 只是缓存：即使手写 `{"agreed": 2, "company_version": 999}` 让它
`load agreement cache` 成功，随后的 `getconfiglist` 响应仍会把状态压回 0。
所以只改缓存不行，要在二进制层面让"该弹窗"的分支不被走。

### 坎三：Qt 覆盖窗在 Wine 下不可见

SDK 的 UI 是 Qt 写的，全部通过 `SetParent(winId, 游戏窗口)` 变成 **Unity 窗口的子窗口**：

```
Unity 主窗口 (D3D11 → DXVK → Vulkan swapchain，直接画到 X11 window)
└── mj_base::MjBaseWnd 子窗口  ← 协议窗 / 登录窗 / CEF 容器
```

在 Wine 里，子窗口的 GDI 绘制和父窗口的 swapchain 输出抢同一块 X11 drawable，
结果就是：X 树里这些窗口只有 `1x1`、截图纯黑、`xdotool` 点不动。
CEF 浏览器进程（`manjuu_sdk_browser.exe`）虽然是独立进程，但它的宿主窗口依然是子窗口，
所以同样看不见。

## 2. 两条补丁

见 [patches.md](patches.md)。一句话：

| 补丁 | 手段 | 效果 |
| --- | --- | --- |
| `skip-agreement-gate` | 把 `OnCheckAgreementFinished` 里决定"弹窗 + blockInput"的 `jbe` 换成 6 个 NOP | 不再有协议门 |
| `detach-overlay-window` | 把 `SetParent(winId, parent)` 的 `parent` 换成 `NULL` | Qt 窗口成为独立 X11 toplevel，可见可交互 |

第二条是真正解决问题的那一刀：**不是**让 Unity 别挡住，而是让窗口根本不是子窗口。

## 3. 为什么用签名而不是偏移

```
文件偏移 = VA - 0x180001000 + 0x400      # 只对当前这版 union_pcsdk.dll 成立
```

游戏一更新，`.text` 里前面的函数长度变一点，后面所有东西整体平移，硬编码偏移立刻失效，
而且**失效的方式是静默的**：你会在错误的地址上改掉 4 个字节，游戏随后崩在随机位置。

签名定位把"可变部分"显式排除：

```
skip-agreement-gate
  48 8B 49 18            mov rcx,[rcx+0x18]
  E8 ?? ?? ?? ??         call <变，通配>
  90                     nop
  83 7D 98 01            cmp dword [rbp-0x68], 1
  [6 字节 gap]           ← 补丁改写的目标，通配
  33 C9                  xor ecx,ecx
  E8                     call <变，通配>
```

`before + gap + after` 拼成的签名**在打补丁前后都能命中**，于是：

- 命中且 gap 是原字节 → `pending`
- 命中且 gap 是补丁字节 → `applied`
- 一个都命中不到 → `mismatch`，工具直接拒绝写入，不会静默写坏文件

## 4. 验证手段

- `apfix status` / `apfix info`：签名命中位置、当前字节、所在节
- 回滚后 `sha256` 与原始 DLL 完全一致（`tests/test_engine.py` 里有对应断言）
- 实机验证：打补丁后登录框可见，手机号能输入（KWin/EIS 注入与真实键鼠都正常）

## 5. 排查时用过的工具

| 目的 | 命令 |
| --- | --- |
| 找字符串引用 | `objdump -d` + 自己算 rip-relative，比 `rizin /r` 靠谱 |
| 反编译 | `rizin -q -c 'aa; s 0xADDR; af; pdg' union_pcsdk.dll` |
| 函数边界 | 用 `.pdata` 反查（见 `scripts/pdata.py`） |
| 抓窗口 | `xwininfo -root -tree`、`import -window`、KWin 截图 |
| 注入输入 | `xdotool` 对子窗口无效；KWin EIS（`ydotool` / kwin-mcp）有效 |
