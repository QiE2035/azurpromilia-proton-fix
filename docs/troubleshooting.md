# 排障

先跑一遍体检：

```bash
apfix doctor --game-dir ~/Games/AzurPromilia/AzurPromilia_Game
apfix status --game-dir ~/Games/AzurPromilia/AzurPromilia_Game
```

---

## 启动阶段

### `Proton: Need a verb.`

`dwproton`（和 `proton`）在参数 ≥2 个时不会自动补 verb：

```bash
dwproton waitforexitandrun ./AzurPromilia.exe -start=azurpromilia_launcher
```

### 弹「请使用启动器启动游戏」

缺 `-start=azurpromilia_launcher`。这个参数由启动器从服务端拿，见
[how-it-works.md](how-it-works.md#坎一启动参数)。

### 游戏进程起来但秒退，`pcsdk_log.txt` 只写了几行

多半是 `union_pcsdk.dll` 被改坏了（比如手工改了错误偏移）。先回滚：

```bash
apfix revert --from-backup      # 有备份
apfix revert                    # 没备份也能按字节反向还原
```

---

## 画面阶段

### 一片黑，`Player.log` 正常（D3D11 设备创建成功）

协议窗不可见导致 `blockInput`。`apfix status` 应显示两个补丁都是 `applied`。

### 只有背景立绘/标题，没有登录框

`detach-overlay-window` 没打上。检查：

```bash
apfix info | grep -A4 detach-overlay-window
```

另外确认没有把 SDK 的 `plugins/` 目录搬走 —— Qt 缺 `qsvg.dll` 只影响图标，
但整个目录缺失会让 SDK 起不来。

### 登录框出现了但点不动 / 打不了字

- 用**物理鼠标键盘**，或 KWin/EIS 注入（`ydotool`、kwin-mcp）。
  `xdotool`（XSendEvent/XTEST 到子窗口）对这种窗口无效，会把点击送给 Unity 窗口。
- 如果之前用 `xdotool windowsize`/`windowmove` 折腾过窗口，重启游戏即可复位。

### 画面撕裂 / 全屏切换后黑屏

与补丁无关，是 DXVK/Proton 侧的问题。试 `PROTON_USE_WINED3D=1`、
`DXVK_HUD=1` 观察，或在游戏内切窗口化。

---

## 补丁阶段

### `signature not found - the game was probably updated`

游戏更新了 `union_pcsdk.dll`。三种选择：

1. 等上游更新签名（附上 `sha256sum union_pcsdk.dll` 提 issue）；
2. 自己按 [patches.md](patches.md#游戏更新后) 的步骤更新 `src/apfix/patches.py`；
3. 确认新版本是否已经官方修好了 Wine 兼容（先 `apfix revert` 再纯跑一次）。

### `signature is ambiguous (N hits)`

新版本里这段指令形状出现了多次。收紧签名：把 `before` / `after` 各自往前/往后多带几条
指令（尽量选带立即数或调用相对地址的部分）。

### `unexpected bytes 90 90 ...`

说明这个位置**已经是补丁后的状态但签名匹配到的却是另一处**，或者上一次用了不同版本的补丁
（例如手工 NOP 了 `cmp`+`jbe` 8 字节）。用 `apfix revert --from-backup` 回到干净状态再 `apply`。

### `game is running (...); close it first`

DLL 正被占用。关掉游戏：

```bash
pkill -f AzurPromilia.exe; pkill -f UnityCrashHandler; pkill -f manjuu_sdk_browser
```

（`apfix apply --force` 可跳过检查，但不建议在游戏运行时改文件。）

---

## 收集信息时附上这些

```bash
apfix info > apfix-info.txt
sha256sum AzurPromilia_Data/Plugins/mj_sdk/union_pcsdk.dll
tail -n 200 pcsdk_log.txt
tail -n 100 "$HOME/.local/share/proton-pfx/0/pfx/drive_c/users/steamuser/AppData/LocalLow/manjuu/AzurPromilia/Player.log"
```
