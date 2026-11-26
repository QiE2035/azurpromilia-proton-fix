# 补丁清单

所有补丁都作用在 **`AzurPromilia_Data/Plugins/mj_sdk/union_pcsdk.dll`**（PE32+，x86-64，
imagebase `0x180000000`，无 PDB 符号）。改写长度与原始长度一致，不改变任何函数布局。

签名约定：`??` 匹配任意单字节；`[...]` 表示补丁改写的 gap，签名里被通配。

---

## 1. `skip-agreement-gate`

- **函数**：`MjAgrSdk::OnCheckAgreementFinished`
- **原始**：`0F 86 31 01 00 00`（`jbe 0x1801f816e`）
- **改为**：`90 90 90 90 90 90`（6 个 NOP）
- **签名**：

  ```
  48 8B 49 18  E8 ?? ?? ?? ??  90  83 7D 98 01  [?? ?? ?? ?? ?? ??]  33 C9 E8
  ```

### 上下文

```asm
1801f8029  mov  rcx,[rcx+0x18]
1801f802d  call 0x180212570            ; 取协议状态
1801f8032  nop
1801f8033  cmp  dword [rbp-0x68],1     ; 0 = 无需弹窗, >=1 = 需要
1801f8037  jbe  0x1801f816e            ; ← 命中即"要弹窗"分支
1801f803d  xor  ecx,ecx                ; 放行路径
1801f803f  call 0x1801fdb20            ; SetBlockInput(false)
1801f8044  mov  dword [rbp-0x60],2
```

跳转目标 `0x1801f816e` 那一段是：

```asm
1801f816e  mov  cl,1
1801f8173  call 0x1801fdb20            ; SetBlockInput(true) —— 输入被吃掉
           ...                          ; 创建 mj_agr::AgreementWidget
```

### 为什么这样改

`jbe` 一跳，输入就被锁死，而那个协议窗在 Wine 下不可见 ⇒ 永久黑屏。
NOP 掉分支后永远走 `SetBlockInput(false)` 的放行路径。

用 NOP 而不是改成 `jmp`：改成 `jmp` 也会跳进弹窗分支，方向相反；把 `cmp`+`jbe`
一起 NOP 也行，但 6 字节 NOP 与原始长度严格相等，最省事。

---

## 2. `detach-overlay-window`

- **函数**：`mj_base::MjBaseWnd::ChangeParentHwndIfNeeded`
- **原始**：`48 8B 53 30`（`mov rdx,[rbx+0x30]`，即 `SetParent` 的父窗口参数）
- **改为**：`31 D2 90 90`（`xor edx,edx` + 2 NOP，等价于传 `NULL`）
- **签名**：

  ```
  48 89 43 38  [?? ?? ?? ??]  48 8B C8  FF 15 ?? ?? ?? ??  BA 20 03 00 00  41 B8 58 02 00 00
  ```

### 上下文

```asm
1801bd24b  xor  r13d,r13d
1801bd24e  mov  edi,r13d
1801bd251  mov  [rsp+0x20],r13d
1801bd256  mov  rcx,[rcx+0x30]        ; this->parent_hwnd
1801bd25a  test rcx,rcx
1801bd25d  je   0x1801bd778           ; 没有父窗口就直接返回
1801bd263  call qword [IsWindow]
1801bd269  test eax,eax
1801bd26b  je   0x1801bd778
1801bd271  mov  rcx,rbx
1801bd274  call qword [QWidget::winId?]
1801bd27a  mov  [rbx+0x38],rax        ; this->win_id = winId()  ← 后面要用的
1801bd27e  mov  rdx,[rbx+0x30]        ; ← 补丁点：父窗口
1801bd282  mov  rcx,rax
1801bd285  call qword [SetParent]
1801bd28b  mov  edx,0x320             ; 800
1801bd290  mov  r8d,0x258             ; 600  (默认尺寸)
```

### 为什么这样改

`SetParent(winId, NULL)` 把一个子窗口变成没有父窗口的 toplevel，
Wine 就会给它建独立的 X 窗口 —— 立刻可见、可接收输入，且 Qt 自己负责绘制与布局。

### 踩过的坑（别重复）

1. **不要整段跳过 `ChangeParentHwndIfNeeded`**。把入口的 `je 0x1801bd778` 改成无条件的
   `jmp` 曾经试过：进程直接崩在 `unityplayer` 里，因为 `this+0x38`（winId 缓存）没被赋值，
   后续代码解引用空指针。
2. **不要试图只把它 `ShowWindow` 出来**：子窗口的绘制目标仍是父窗口的 drawable，
   swapchain 一出帧就被盖掉，`xdotool` 也点不到（因为父窗口抓着指针）。
3. 改成 toplevel 后，SDK 自己的窗口管理仍然正常（`WndController::UpdateWidgetFocus`
   依旧打印窗口树），说明上层逻辑不依赖父子关系。

---

## 组合效果

| 只打 patch 1 | patch 1 + 2 |
| --- | --- |
| 不再黑屏卡死，能看到标题背景 | 登录框完整显示在画面上 |
| 没有登录框（被盖住），无法登录 | 可以输入手机号/验证码、点按钮 |

---

## 游戏更新后

1. `apfix status` 看是否 `mismatch`；
2. `apfix info` 看哪个签名没命中；
3. 用 `rizin` 在新 DLL 里找同样的指令形状（`cmp dword [rbp-0x68],1` + `jbe`；
   `mov rdx,[rbx+0x30]` + `call SetParent` + `mov edx,0x320`），更新 `src/apfix/patches.py`
   里的 `before` / `after` 上下文即可 —— 不需要碰任何偏移常量。
4. 新签名请附上 DLL 的 sha256 提 issue / PR，方便别人对照版本。
