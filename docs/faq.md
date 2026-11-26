# FAQ

### 这算不算作弊 / 会不会被反作弊处理？

补丁只做两件事：不在启动时锁输入、不把 UI 窗口塞进游戏窗口当子窗口。**没有**改任何游戏逻辑、
网络协议、付费或账号校验，也没有内存读写、没有注入 DLL。用的是游戏自带的 SDK，只是让它显示出来。

不过 `mj_sdk` 里带着 ACE（AntiCheatExpert），它对**文件完整性**的处理策略由厂商决定，
本项目无法保证。要不要用、用不用在正式账号上，请你自己判断；出问题 `apfix revert` 一秒回滚。

### 有没有别的做法？谁更好？

有，而且层次不同：改 Wine（`NtUserSetParent` 里把设父窗口转成设 owner）、
起一个桥接宿主用本机 Qt 画 SDK 画面、以及 macOS 上的原生控件版。
三者的手法、代价和适用场景对比见 README 的「相关项目与横向对比」，那里有打分和选择建议。

### 为什么不做成 DLL 注入 / LD_PRELOAD 补丁？

两条路都能做，但都更脆：

- 注入要在运行时定位同样这几条指令，还得处理加载时机、反调试、签名校验；
- `LD_PRELOAD` 只能拦 Unix 侧调用，拦不到 Win32 的 `SetParent`。

静态补丁的可验证性最好：改完的字节可以 `sha256` 对比，出问题直接回滚，不留后台进程。
如果你要做成运行时补丁，签名引擎（`apfix.signature`）可以直接复用。

### 为什么不直接伪造 `agreement.json`？

试过：SDK 会先 `load agreement cache` 成功，但随后 `getconfiglist` 的服务端响应把状态
从 2 压回 0，协议窗照样弹。缓存不是权威来源。

### 支持 Steam 版 / 其他区服吗？

补丁按 `union_pcsdk.dll` 的指令形状匹配，理论上同一套 SDK 的任何区服版本都能命中，
但只在国服 `Game_35_C000_SC000` 上验证过。其他版本跑 `apfix status` 看是否 `mismatch` 即可，
命中就能用。

### 会改游戏文件吗？会不会影响更新？

会原地改 `union_pcsdk.dll`，并在同目录留：

- `union_pcsdk.dll.apfix-backup`（第一次打补丁时的原件）
- `union_pcsdk.dll.apfix.json`（manifest：原始 sha256、补丁列表、时间）

游戏更新会覆盖 DLL，补丁自然消失，重跑 `apfix apply` 即可；不需要先回滚。

### 能用在 Windows / macOS 上吗？

不需要。Windows 上本来就是正常的（窗口是子窗口但在 D3D 下能正常合成）；
macOS 不运行这个 SDK。

### 为什么 CLI 用 Python？

签名扫描、PE 解析、进程检查都是几十行的事，Python 改起来最快；
`pefile` 负责 PE 结构，`click`/`rich` 负责 CLI，没有自己造轮子。
性能上 20 MB 的 DLL 全量扫描 < 100 ms，够用。
