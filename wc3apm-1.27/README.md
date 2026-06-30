# WC3 APM Overlay (1.27)

WC3 1.27 全屏模式下实时显示 APM（Actions Per Minute）的 overlay 工具。

通过 DLL 注入方式在游戏窗口上层绘制一个透明窗口，实时统计键鼠操作并显示 APM。

## 文件说明

| 文件 | 说明 |
|---|---|
| `wc3apm.cpp` | APM overlay DLL 源码（编译产物为 `wc3apm.dll`） |
| `wc3apm-loader.c` | DLL 注入器源码（编译产物为 `wc3apm.exe`） |
| `wc3apm-loader.rc` | exe 图标资源定义 |
| `wc3apm-loader.manifest` | UAC 提权声明（嵌入 exe 后双击自动请求管理员权限） |
| `wc3apm.ico` | exe 图标文件 |

## 编译

**环境要求**：MinGW32 (MSYS2 / msys64)

### 编译 DLL

```bash
g++ -shared -o wc3apm.dll wc3apm.cpp -lgdi32 -O2 -static-libgcc -static-libstdc++
```

### 编译 EXE（带图标）

```bash
windres wc3apm-loader.rc -o wc3apm-loader.res --output-format=coff
gcc -o wc3apm.exe wc3apm-loader.c wc3apm-loader.res -m32 -O2
```

### 编译 EXE（不带图标）

```bash
gcc -o wc3apm.exe wc3apm-loader.c -m32 -O2
```

## 使用方法

1. 将 `wc3apm.dll` 和 `wc3apm.exe` 放在同一目录下
2. 启动魔兽争霸 III 1.27
3. 双击 `wc3apm.exe`（或右键"以管理员身份运行"）
4. 控制台显示 `SUCCESS! APM overlay is now active.` 即注入成功
5. 切回游戏，屏幕正上方会显示 APM 信息

**注意**：注入器需要管理员权限才能打开 war3.exe 进程。如果双击后注入失败，请右键"以管理员身份运行"。

## APM 算法

采用**自适应滑动窗口**算法：

- 窗口长度 = min(已游戏时长, 60秒)
- 开局前几秒就能显示合理 APM（如 5 秒内操作 15 次显示 180 APM）
- 满 60 秒后等价于标准的 60 秒滑动窗口

显示两行信息：
- 第一行：实时 APM（颜色随数值变化：绿 < 60 < 蓝 < 120 < 橙 < 200 < 红）
- 第二行：全程平均 APM、键盘次数、鼠标次数、游戏时长

## 统计时机

只有当 WC3 窗口在前台（玩家实际在游戏中操作）时才计入键鼠操作，登录界面和菜单中的点击不会被统计。

## 调试模式

默认关闭日志输出。如需调试，编辑 `wc3apm.cpp` 将 `g_debug = false` 改为 `g_debug = true`，重新编译后会生成 `D:\wc3apm_log.txt`。

## 已知限制

- 全屏模式下 overlay 依赖于 `WS_EX_TOPMOST` 窗口置顶，部分情况下可能被游戏画面遮挡
- 仅支持 WC3 1.27（未测试重制版）
- 低级键盘/鼠标钩子需要在安装钩子的线程跑消息循环才能触发回调（已处理）
