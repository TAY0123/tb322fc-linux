# Freedom 同步与 Y700 四代 DPU 旋转（2026-10-29）

本次从 `244b74516d99d06cb0518609ce4b842ab278be8a` 同步到
[`9788014a0293dc26745b000d02854ad88ef73e88`](https://github.com/mydanyi/armadaos-freedom/tree/9788014a0293dc26745b000d02854ad88ef73e88)。
保留 Arch 会话用户发现、桌面会话名、已有 Elden 电源/显示修复及单独维护的软件包。

## 同步范围

- 内核仍是 Linux 7.2.6，首次同步配方为 `7.2.6-20-freedom`，后续旋转性能修正升为 21。采用最新统一补丁链，包括 DPU 旋转通用修正、ASoC 解绑前等待延迟恢复，以及由 DT/机型条件限定的 TB710FU 支持。Gen5 面板方向、SM8850 寄存器及缩放限制保留其硬件条件。
- 上游 0188 已合入 Elden WCN7860 分段扫描扩展，移除配方中重复的 `elden-range-scans.patch`；历史原补丁仍在 `patches/freedom/0002-*`。
- Gamescope 同步完整 Freedom 补丁集：真实模式刷新率发现、边缘手势、FIFO/HUD 统计、可选 Steam UI 60 Hz 上限、游戏内手势和透明占位层修复。帧节奏补丁改用上游编号 0036；本地时钟钳制与 SPI 触摸关联由上游 0034/0035 替代。保留本地 EDID 刷新范围扩展 0031。
- Freedom Control 使用上游指定的 `61a8e9631c0ba597ff0f48bc91ae766eef20bf6a`，同步上述两个开关；后台和 Steam 会话一并支持 `in_game` 手势设置，两个保存值互不覆盖。
- powerd 从 sysfs 在线 CPU 列表选 CPU，避免将离线或不连续编号的 CPU 错算成在线 CPU。
- ALS 桥同步上游的模块清理和带超时、重新认领、lux 单位/数值校验的后台。保留本项目服务名与 SSC 服务依赖；udev 规则限定到桥驱动，避免排除其他真实 ALS。
- 电源键处理器同步上游新行为：游戏模式短按只关/开屏幕，游戏和音频继续；长按仍打开 Steam 电源菜单，合盖仍交给 Steam 休眠。屏幕切换失败会回滚并保留可重试状态，不自动切换到系统休眠。保留本地真实休眠后的安全输入监听重建。
- 其他已引用 Freedom 的源码 pin 对齐；Mesa 三个基础补丁、MTP、诊断、USB 规则、steamos-manager 和 kShim builder 的内容未变化。WCN7860 固件逐文件哈希仍一致，TB710FU 的 WCN7850 固件不替换它。
- Freedom 的 Fedora/OCI 镜像、EDL 安装器、新增设备的用户界面默认值和按 release/latest 获取插件的流程不适用于本项目的 Arch 分包/固定哈希流程，因此不引入这些流程。
- kShim runtime 单独保留已验证的 `244b745` 基线及本地兼容补丁；新上游默认开启原生 UFS 设置存储，本次 DPU 测试不引入这些 I/O 变化。Boot builder 本身的字节未变，更新后的工具包复用已核验的现有原生 runtime/工具 bundle。
- 本机安装配套包时发现，ALS 更新 hook 会枚举保留的旧内核目录。`kshim-freedom` pkgrel 6 增加 pacman 归属检查，自动部署仅选择仍由配置的内核包拥有的目录；手动 `--kernel` 选择仍保留。两个回归用例通过，本机实际查询只选中正在安装的内核包。

### 上游来源与本地改动的区分

这里的同步通过固定源码版本、更新补丁集和重做 Arch 适配完成，没有对本仓库执行 Git cherry-pick。

| 来源 | 今晚实际采用的内容 |
|---|---|
| [902276b](https://github.com/mydanyi/armadaos-freedom/commit/902276bcd63e342e7f79c477239f969be32376a7) | DPU 按旋转高度拆分图层、保留旋转信息参与管线分配、禁止旋转 multirect、方向变化重新分配、按旋转后几何计算时钟；Gamescope 在可见外部 HUD 存在时跳过透明 Steam 占位层。SM8850 专用部分保留硬件条件。 |
| [de26d40](https://github.com/mydanyi/armadaos-freedom/commit/de26d40d3d20c4aa15e87641bbf18e2ee9a7e388) | 游戏内边缘手势、释放触摸后再打开 Steam 菜单，配套 Freedom Control 与独立保存的游戏内手势设置。 |
| [925f1c2 中的 Gamescope 0038](https://github.com/mydanyi/armadaos-freedom/commit/925f1c2c609fe65f1e51c4ef0abf6853bd7dc7da) | 可选 Steam UI 刷新率上限，配套 Control 开关；菜单可以限制到 60 Hz，游戏仍使用自己的刷新率。 |
| [2d66159](https://github.com/mydanyi/armadaos-freedom/commit/2d66159b6acdf6463a1d9a0bc527f85f273e570b) | 游戏模式短按电源键只切换屏幕、保留游戏和音频，失败后恢复可重试状态。长按电源菜单、合盖休眠沿用对应逻辑。本项目保留 Arch 会话及桌面默认值。 |
| [37ff9ec](https://github.com/mydanyi/armadaos-freedom/commit/37ff9ec30083e73357063de04739584200f3eccf) | powerd 从 sysfs 读取真实在线 CPU，处理 CPU 编号不连续或部分离线的情况。 |
| [715faf2](https://github.com/mydanyi/armadaos-freedom/commit/715faf284d84e9ce8b9d39e13f58a423b9172147) | 对齐 ALS 桥的上游实现：模块清理、SensorProxy 超时与重新认领、lux 单位和无效数值检查；保留本地服务依赖与规则限定。ALS 功能本身此前已有。 |
| [bb5575e](https://github.com/mydanyi/armadaos-freedom/commit/bb5575ef24a6464975f7b282dedd403e9f1fe6c6) | 声卡解绑前等待 ASoC 延迟恢复任务结束，避免 ADSP 重启与恢复并发时访问已释放对象。 |
| [c229939](https://github.com/mydanyi/armadaos-freedom/commit/c2299390acf8873f0f65b241a31c5187bf6eb1dd) | Elden WCN7860 range-scan 修复已被上游接收，移除重复本地补丁，改用统一补丁链。 |

此外补齐了 Freedom 中已有、此前本地 Gamescope 配方未完全对齐的刷新率发现、边缘起点判定和 FIFO/HUD 补丁；帧节奏、像素时钟钳制、SPI 触摸关联改用上游版本。统一内核包含新增 TB710FU 支持，但这不表示把该机型的默认配置套到四代。

本地新增的是：四代 `Y700_ROTATION` 选择和内核能力检查、0016 候选 CRTC 带宽汇总、0017 候选 plane 性能与旋转扫描方向计算，以及 kShim 自动部署时的内核包归属检查。尤其 0016/0017 是四代实测后补的修复，不应归为 Freedom 原有成果。此次没有启用新 kShim 原生 UFS 设置存储；Mesa 基础补丁和四代 Wi-Fi 固件内容也没有变化。

## 当前旋转路径与可复用部分

同步前从平板读取到：

- 运行 `7.2.6-18-freedom`，Gamescope 带 `--force-composition-rotation`。
- 活跃 DRM framebuffer 是 `1904x3040`、XR30、QCOM UBWC modifier，plane `rotation=1`（DRM rotate-0）。这表示 GPU 已把横屏画面旋转成原生竖屏后交给 DPU 扫描。
- 虚拟 plane 已存在。`msm.dpu_use_virtual_planes` 默认是 true，但参数权限为 0，不会导出 sysfs 文件；sysfs 中找不到该参数不能作为关闭的证据。

既有 Freedom 0066 已在 SM8750（DPU12）打开 inline rotation v2.0.1，支持 UBWC 和 XR30。
它限制每条旋转管线的**旋转前高度**不超过 1088，四代完整横屏图层 `3040x1904` 因此需要两条 VIG 管线，每条处理 `3040x952`。

五代的 [902276b](https://github.com/mydanyi/armadaos-freedom/commit/902276bcd63e342e7f79c477239f969be32376a7)
不仅增加 SM8850 支持，也修正所有相关 DPU 的拆分与分配：

1. 按旋转高度限制拆分，并在资源分配前保留 rotation。
2. 禁止 90°/270° 图层使用 multirect；方向改变时重新分配管线。
3. 按旋转后维度计算时钟需求。
4. 有可见外部 HUD 时不再额外绘制完全透明的 Steam 占位层，减少所需旋转管线。

这些通用部分已通过最新上游源码进入本配方，无需再写一份重复的四代内核实现。
SM8850 使用 OP_MODE bit15，SM8750 继续使用 FORMAT bit11；补丁按 DPU major 版本区分。
仅 SM8850 的旋转配置有新增 11/5 缩小限制，SM8750 沿用已有 v2.0.1 配置。

核对过 [GEEKiDoS 四代项目](https://github.com/GEEKiDoS/tb322fc-linux) 与
[xiaquwan1001 四代项目](https://github.com/xiaquwan1001/lenovo-legion-y700-gen4-tb322fc-elden-linux)，未找到可直接复用、已验证这套完整旋转扫描路径的四代实现。
这仅覆盖所查项目，不表示所有四代项目都没有实现。

## 启用与回退

2026-10-30 验证时，仓库默认保持 GPU 旋转，设备已按用户要求持久刷入带 0016/0017 的 `7.2.6-21-freedom` 并显式使用 DPU。21 版通过原生 3K / 165 Hz 双图层扫描、会话重进、关屏恢复和一次 s2idle；用户确认恢复后的四角触摸及实体画面正常。首次未含 0016 的 20 版存在画面停住问题，不适合作为 DPU 基线。
新内核包在匹配的 `/usr/lib/modules/<release>/freedom-dpu-rotation` 安装能力文件；
2026-11-01 补齐 openSUSE RPM 的这一文件，并将会话包默认策略改为自动选择：
运行内核有标记就使用 DPU，旧 Freedom 内核没有标记就继续用 GPU，防止仅更新会话包后误启用。

安装匹配的 Image、DTB、模块/headers 及更新后的 Gamescope、会话包，启动新内核并进入游戏会话后，
不需要额外添加用户配置。需要回退 GPU 时，在 `~/.config/gamescope-session-plus/sessions.d/steam` 添加：

```sh
Y700_ROTATION=gpu
```

会话在系统和用户配置全部读取后再应用策略，移除强制 GPU 旋转，并默认使用
`--force-orientation right`（270°，与四代现有自动方向一致）；保留显式 `ORIENTATION` 覆盖。
五代文档中的 `left` 不适合直接作为四代默认值。

删除这一行或改为 `Y700_ROTATION=auto`，然后重启游戏会话，可恢复自动选择。
仍可用 `Y700_ROTATION=dpu` 显式请求 DPU；内核缺少标记时会提示并回退 GPU。
保留旧 boot 镜像和相应模块作为启动回退，不能只回退 Image。

允许 DPU 扫描并不保证所有画面都直接扫描。非 UBWC、格式/色彩/缩放不满足条件、图层超过管线资源时，Gamescope 仍可进行 GPU 合成；Steam 菜单尤其可能走 GPU。

## 验证记录

工作目录：`build/freedom-sync-20261029/`，不进入 Git。主要证据：

- `kernel-prepare.log`、`gamescope-prepare.log`：完整配方补丁均以 `--fuzz=0` 应用；允许上下文一致的行号偏移。
- 内核实际 C 函数夹具：旋转拆分/方向/时钟 49 项，DPU12/13 寄存器 38 项，均通过。
- Gamescope 实际生产代码夹具：游戏内手势 19 项、Steam 占位层 12 项通过；平板独立 Xvfb 会话的菜单派发 2 项通过；Steam UI 上限 6 项、73 个断言通过。
- 本仓库 Python 测试 67 项通过，含四代旋转选择/旧内核回退与两个手势开关的持久化。
- Freedom Control 前端测试、i18n 检查、后台 HomePower 32 项测试和 Rollup 构建通过。
- 适配后的电源键屏幕切换/失败恢复测试通过；ALS 状态机 10 项通过。宿主缺少 GI 的私有 D-Bus 测试改在平板独立测试总线上运行，3 项通过，未接入真实 SensorProxy 或 sysfs。
- 更新后的 ALS 模块在平板以当前 `7.2.6-18-freedom` headers 原生生成 `.ko`，未加载。使用的 Clang 23 与运行内核构建时的 Clang 18 不同，编译/链接/BTF 均完成；这项检查不代替新内核整包验证。
- `package-checksums.json`：核对引用的原始文件与本地输入的 SHA256；`runtime-before.txt` 保存同步前的实机状态。

原生 AArch64 Gamescope `3.16.31.ogc1-5` 完整编译、148 项 Meson 测试及上述 Python 夹具全部通过，已生成包。Control、powerd、两个 ALS 包、电源键处理器、两个会话包和 Decky 插件共 8 包也已在平板构建，产物复制到本机 `artifacts/`。这些包及修正内核枚举的 kShim pkgrel 6 已安装；`userspace-artifacts.json` 记录用户态包哈希。

完整 Image、DTB、1597 个模块和 headers 已构建并在平板原生打包，ALS DKMS 模块也完成新内核构建。首次启动的内核 build ID 为 `6f06ee03f5a537d3658ff3d42cd50ca4a7739337`，由 `/sys/kernel/notes` 直接核验，运行时 BTF 为 8,458,704 字节。签名镜像写入 `boot_a` 后读回哈希一致，`boot_b` 与两个 recovery 分区保持原字节。原始 `boot_a`、旧 18 模块和 12 个已安装包均已备份；Windows 侧也保存原始启动镜像。

首次构建并非有效增量：旧运行内核未开 LTO，新配方采用 ThinLTO，源码路径也变化，导致约 1.2 万个对象重编译。宿主内存不足使主内核 BTF 生成 OOM；最终将同一个中间 ELF 传到平板，用同版本 pahole 和相同语义参数生成 BTF，回传后核验输入/输出 SHA256。临时宿主 swap 已清理。构建目录、工具链和对象保留供后续增量使用；ThinLTO 的全程序链接仍需时间。

### 第一轮实机发现

- 旧 18 内核 GPU 基线四角触摸，用户确认全部命中、方向正常。
- 新 20 内核先以 GPU 路径正常启动，Steam、InputPlumber、内置与 G9 USB 音频均枚举。GPU 对照的 5 秒动画采样为 828 次呈现、828 次 Gamescope GPU submit，DRM 为 `1904x3040`、rotation=1。
- 显式 DPU 配置生效：Gamescope 使用 `--force-orientation right`，没有 `--force-composition-rotation`。DRM 出现 `3040x1904` 的 UBWC 图层、rotation=8，以及两条各取 `3040x952` 的 VIG，证明实际进入 DPU 270° 路径。
- 但切回 Steam 60 Hz 时出现 `30047847kb > 28500000kb` 带宽错误，后续画面提交停住，不能据上述 DRM 状态宣称可用或改善性能。
- 原因是 plane 虽已选择新状态，最终 `dpu_core_perf_aggregate()` 仍汇总已提交 CRTC 的 `new_perf`，会放行超限画面，再阻止降低带宽的提交。本地 [0016](../patches/freedom/0016-dpu-elden-check-pending-bandwidth.patch) 仅对 Elden 汇总本次事务的新 active CRTC 状态，未变 CRTC 沿用已提交状态；不提高硬件上限、不修改提交后的总线投票。
- 新增回归测试直接编译补丁中的实际 C 函数，覆盖降低带宽、拒绝超限首帧、DPMS 恢复、关闭、未变 CRTC、第二个 pending CRTC 和非实时客户端 7 个场景。66 个仓库测试均通过。

### 0016 修复版实机结果

同版本第二次构建的 build ID 是 `28955f5ab6e385ba3888f2a7d13dd290d50cf41e`，与首次失败构建区分。Image SHA256 `099ee838ce983af8ef1f589aa254bcd9fc66ebeab533c16f24c9ce2ece01aa20`；签名启动镜像 SHA256 `e398f5aeabd14e31fba3744f465dc13fcf00a1fcacf8aff20eabc3ae68965e27`。boot_a 写后核验通过，其他启动分区未变。匹配的 Image、DTB、模块和 headers 已安装，实际 build ID 从 `/sys/kernel/notes` 核验。

- 原生 `3040x1904`、rotation=8、两条 `3040x952` VIG 的 DPU 扫描持续工作。
- 用户确认四角触摸都能在原位置变白。第一次测试程序只收 XI2 原生触摸，而 Steam 当时发送鼠标点击；补收两类事件后通过，没有改坐标映射。
- Steam 60 Hz 的 5 秒采样：195 次呈现，Gamescope GPU submit 为 0，两层 AR24 直接扫描。
- 165 Hz 动画稳态的 5 秒采样：822 次呈现，823 次 Gamescope GPU submit。此时仍进行 GPU 合成，合成结果再交给 DPU 旋转，不能宣称所有游戏都免合成。文件早期名 `dpu-fixed-60.txt` 只是测试意图，实际 DRM 模式确认为 165 Hz，已按实测名称另存。
- 会话重启、显示关闭/恢复通过，恢复后呈现计数继续增长。
- 一次 RTC 定时 20 秒 s2idle：success 计数 0→1、boot ID 不变、同一 Gamescope 进程继续呈现，rotation=8 保持。
- 恢复后的实体触摸、HDR、长期压力和耗电尚未覆盖；不能由 GPU 提交次数推算整机节电幅度。

证据位于工作目录 `deployment/dpu-touch-user-confirmation.json`、`dpu-power-regression.json`、`dpu-fixed-steady-165-drm.txt` 及对应 render-path 记录。

### 日志对照

比较原 18、首次 20、带 0016 的 20 和带 0016/0017 的 21 的完整测试启动内核日志，并排除命令行字符串等误匹配。四个启动持续时间及测试负载不同，数量仅用于定位，不作为出错率比较。

- 首次 20 有 107838 次带宽拒绝，伴随 `atomic remove_fb failed with -7` 的两次 WARN 调用栈。
- 0016 版测试期间仍有 7952 次带宽拒绝，但没有上述 WARN，也未观察到 Oops/panic、GPU hang、显示 underrun 或 UFS 错误。带宽日志主要集中在启动、165 Hz 场景和会话切换；稳定 Steam 会话的后续五分钟没有新增。
- 21 版本轮完整采样中，带宽拒绝、CRTC performance check 错误、内核 WARN 调用栈、Oops/panic、GPU fault、显示 underrun 和 UFS 错误均为 0；关屏与 s2idle 后显示计数仍正常增长。既有 Wi-Fi/RTC/PHY 提示仍可能出现，不能概括为整个系统没有任何警告。
- `ath12k sband is NULL`、开机 APM 超时、RTC 初始 1970/校时回跳、`HS-PHY not in L2`、phy0 hwmon 睡眠提示在原 18 已存在，不能归因于本次 DPU 改动。
- InputPlumber 临时 udev 规则缺少 GOTO label 的警告也在原 18 存在，与已经带入的 armada 包补丁不是同一问题。
- G9 断开与 PipeWire ENODEV 时间相符，随后手柄、FF 和 USB 音频重新枚举。结合用户说明，优先视为长期无操作休眠；本轮没有证据认定其为 DPU 回归。

完整计数和日志例子：`deployment/log-comparison.json`。0016 尚存的带宽拒绝在追加 0017 后的本轮覆盖场景中未再出现；这不代表已覆盖长期运行和所有图层组合。


### 2026-10-30 同类高分屏项目复核

| 参考项目与固定版本 | 与本次旋转问题有关的发现 |
|---|---|
| [GEEKiDoS Y700 四代内核 b0c05eb](https://github.com/GEEKiDoS/linux/blob/b0c05eb72e10140f87efd0e499ad840e6c3e6975/drivers/gpu/drm/msm/disp/dpu1/catalog/dpu_12_0_sm8750.h) | SM8750 VIG 仍使用无 inline rotation 的 mask/sblk，不能提供这条硬件旋转路径的验证。 |
| [xiaquwan1001 四代项目 3b7041b](https://github.com/xiaquwan1001/lenovo-legion-y700-gen4-tb322fc-elden-linux/tree/3b7041b6e99815bf72483ab9e15abf82ebc4af0f) | 查阅公开显示、旋转报告及内核补丁，找到 DTS 方向和 Phosh 自动旋转，没有找到经过验证的原生 3K DPU 90°/270° 扫描实现。 |
| [小米 Pad 8 Pro / Piano 57592f4](https://github.com/yzddmr6/linux-sm8750-piano/blob/57592f423dce206c59c83029b5a5e94239770112/drivers/gpu/drm/msm/disp/dpu1/catalog/dpu_12_0_sm8750.h) | 3200×2136 高分屏，但该内核 SM8750 VIG 未启用 inline rotation；SensorProxy/Mutter 自动旋转不等于 DPU 旋转。 |
| [一加 Pad 2 Pro / Erhai 7a81d18](https://github.com/yzddmr6/linux-sm8750-erhai/blob/7a81d184e3098624d4342d8f4eff5e23674bcc9f/drivers/gpu/drm/msm/disp/dpu1/catalog/dpu_12_0_sm8750.h) | 同样使用不含 inline rotation 的 SM8750 mask/sblk，没有可直接移植的旋转带宽修正。 |
| [blu-sharky Piano 453bb56](https://github.com/blu-sharky/linux-piano/blob/453bb567f2fc12423ab3338953ca8938a2f06e16/drivers/gpu/drm/msm/disp/dpu1/catalog/dpu_12_0_sm8750.h) 与 [Yizhou147 Piano 3525084](https://github.com/Yizhou147/linux-piano/blob/352508459733d3e6d349ea5581a8dd2fd8bb4180/drivers/gpu/drm/msm/disp/dpu1/catalog/dpu_12_0_sm8750.h) | 另外两套 Piano 内核也仍使用非旋转 SM8750 VIG 配置。 |
| [SunUEFI afe922b](https://github.com/slwyts/Project-SunUEFI/tree/afe922bc0d9f230dd05dc0dc9435ae6d6322a31b/patches/linux) | 复核公开 7.2.9/7.3 补丁，有显示停机顺序、共享 CTL 和色彩管线改动，未见 DPU inline rotation 补丁。 |
| [Odin 3 SM8750 补丁 ab8f025](https://github.com/arcadematicas/pocknix-odin3-support/blob/ab8f0251430c52a7652feb58d986fe06437cdff1/kernel/patches/20-sm8750/0068-drm-msm-dpu-enable-sm8750-inline-rotation.patch) | 已启用同 SoC v2.0.1 旋转，1088 高度上限、UBWC 和 XR30 策略与 Freedom 的既有实现一致；没有高分辨率两管线旋转带宽解法可追加。 |
| [ROCKNIX a426271](https://github.com/ROCKNIX/distribution/commit/a426271) | 超过旋转高度上限时降低逻辑渲染分辨率，再由 DPU 放大；能作为折中，但会损失渲染分辨率，本机优先保留原生 3K。 |

这些结果只限定在所查公开版本，不能据此宣布 Y700 四代全球首发。现代高通厂商驱动从用户态 `CORE_AB/CORE_IB` 属性取得带宽请求，并没有可直接照搬的同一 `_dpu_plane_calc_bw()` 公式；本地改动按主线扫描模型推导并用实机检验。

### pkgrel 21：候选图层性能与旋转扫描方向

[0017](../patches/freedom/0017-dpu-elden-candidate-plane-performance.patch) 补充两个问题：

1. `plane_fetch_bw`、`plane_clk` 原本在 `atomic_update` 中才写入，复制到候选状态后仍是上一帧的值。Elden 现在直接用候选 pipe 的矩形、像素格式和 adjusted mode 计算，且不改写未变化 plane 的已提交状态，支持仅变刷新率的事务。
2. 原带宽按旋转前的 3040 像素宽估算每根管线，但输出扫描行实际宽 952。旋转情况下交换源宽高，并保留分数缩放比；prefill、120% 余量、最低峰值投票、28.5 GB/s 拒绝上限继续生效。

两层全屏、四根管线、165 Hz 的旧公式恰好得到日志中的 `30047847 kB/s`；新扫描模型为 `9409721 kB/s`。这是模型预测，不能当作实测内存带宽。

实际生产 C 函数测试覆盖旋转/反射/180°、非 Elden 原行为、1.9 倍缩小、短消隐 prefill、原生双图层、刷新率单独变化、删层/隐藏/无 FB、像素格式和几何变化、真实超预算场景，并检查计算不修改 plane 状态。67 个仓库测试、匹配 LLVM18 的驱动对象编译及补丁 fuzz=0 应用通过。

21 版已完成完整内核构建、原生打包、持久刷入和实机验证。运行时 `/sys/kernel/notes` 核验 build ID 为 `448a8e5b47b835ae22bc69cd2f8bdf34ee1c2da0`；Image SHA256 为 `f08cfa4651caf2c7b6a6e995472b657904b7b8c072a013edaf6cb9f6c17f8dff`，最终签名 boot SHA256 为 `f71cdbebc5d3348cf6e4e69065cf354d8365e4f9a4bef76559222560c5663c0f`。`boot_a` 读回一致，`boot_b` 和两个 recovery 分区未变；匹配的 1597 个模块、headers 及 ALS DKMS 已安装。20 版修复后的 boot、模块/headers 包及其哈希保留用于回退。

同一可见 XCB 动画场景、原生 `3040x1904`、165 Hz 的约 5 秒采样：

| 内核 | 完成呈现次数 | Gamescope GPU submit | 实际扫描路径 |
|---|---:|---:|---|
| 20 + 0016 | 827 | 827 | GPU 合成单层 XR30，再由 DPU 旋转 |
| 21 + 0016/0017 | 833 | 0 | 两层全分辨率 UBWC（XR24、AR24），四条 VIG 旋转扫描 |

改善在于该场景省去 Gamescope 的整屏 GPU 合成，不应把采样边界导致的 827/833 差别解释为帧率提升。每层仍拆为两个 `3040x952` 源矩形，没有通过降低渲染分辨率绕过限制。

- 连续约 68 秒的 165 Hz 运行，早、晚两个 5 秒窗口均为 830 次呈现、0 次 Gamescope GPU submit。两个 DSI 接口 underrun 与 frame-done timeout 计数均为 0。
- 会话重启、显示关闭/恢复通过；恢复后呈现计数继续增长。
- RTC 定时 20 秒 s2idle 通过，success 计数 0→1、boot ID 不变、同一 Gamescope 进程继续呈现，rotation=8 保持。
- s2idle 后的 165 Hz 四色界面收到四角目标 0、1、2、3 的事件，用户确认“四块都正常，画面正常”。
- 测试窗口已关闭，正常 Steam 界面恢复为 60 Hz，系统 failed unit 列表为空，InputPlumber 服务运行。最终检查时 G9 已未枚举，结合用户此前说明视作闲置断开，不把它作为本轮手柄复测通过的证据。

主要证据：`captures/fixed20-controlled-render-path.json`、`perf21-controlled-render-path.json`、`perf21-sustained-*.json`，以及 `deployment/perf21-power-regression.json`、`perf21-touch-user-confirmation.json`、`perf21-final-health.json`、`perf21-kernel-monotonic.log`。测试和补丁归档于 `artifacts/freedom-sync-20261029-validation.tar.gz`。

HDR、长期游戏负载及耗电尚未测量；更复杂图层、格式或缩放组合仍可能正常回退 GPU 合成，不能由提交次数推算整机节电幅度。

## 2026-10-30 日常使用反馈

Steam 菜单开启 60 Hz 省电上限后，用户感到动画明显不流畅。关闭上限的同场对照中，屏幕从 60 Hz 回到 165 Hz，5 秒动画回调由 297 次增加到 687 次，用户确认明显改善；已通过 Freedom Control 关闭并保存该偏好。此结果不要求删除可选上限功能。

长时间休眠后的会话还观察到色彩缓存失步：夜间模式仍开启，DPU plane 已选择色彩管线，但其 IGC/3D LUT 实际旁路且数据为空；Home 菜单触发 GPU 合成时色温正常。强制 GPU 合成可持续恢复色温；重新读取 DRM 状态后，撤销强制合成，四个 colorop 恢复有效数据，用户确认主界面和游戏都正常。恢复后 5 秒完成 592 次显示更新、Gamescope GPU 合成提交为零。当时尚未受控复现触发条件，仅做了临时恢复。随后已复现 GPU 合成状态下休眠会清空停用管线的 colorop，并在 Gamescope 重新启用管线时自动恢复，见[夜间模式休眠修复记录](night-mode-20261030.md)。

同一晚游戏运行期间出现 UCHE READ TRANSLATION GPU 错误，退出游戏后停止。现场 Mesa/Turnip 含另行测试的候选补丁；尚未确定错误来源，不能据此归因于 DPU 或任一 Mesa 候选。前述受控 DPU 测试窗口无错误的结论不扩展为整个启动周期无错误。
