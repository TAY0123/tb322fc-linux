# Freedom 内核与 headers 分包

这是 Arch 风格的软件包配方，保留 Freedom 设备源码，不依赖 UEFI。`linux-freedom` 安装 Image、DTB 和模块；`linux-freedom-headers` 安装同一次构建的配置、Module.symvers、BTF/vmlinux 及 AArch64 原生辅助程序。

## 从源码构建

先在系统源码仓库运行 `python scripts/sync-freedom-packaging.py`，同步共享配置、Elden 兼容补丁和 ALS 源码的校验和。将本目录复制到 AArch64 构建环境，运行普通 `makepkg`。配方固定 Linux 7.2.6 和 Freedom commit，应用统一补丁及 Elden 扩展；本配方 release 为 `7.2.6-22-freedom`。升级通过 pkgver/pkgrel 和固定源码 commit 表达，不依赖工作目录的 dirty 标记。

pkgrel 8 通过 Kbuild 的 `CONFIG_LTO_CLANG_THIN=y` 启用 ThinLTO；makepkg 的 `!lto` 保留，避免通用构建参数介入内核的 LTO 策略。配置合并和预编译输入打包均核对该选项，Image、模块和 headers 仍须使用同一次构建。ccache 继续缓存 Clang 的编译输出；完整 ThinLTO 构建和运行验证状态另行记录。

## 交叉编译后原生打包

也可在 x86-64 机器完成内核编译，再导出输入：

```sh
python export-kernel-input.py --source /path/to/linux --output /path/to/out \
  --destination /path/to/kernel-input --helpers ./build-native-helpers.sh
tar --zstd -cf kernel-input.tar.zst -C /path/to kernel-input
```

内核须使用本配方的配置与 `localversion.10-pkgrel`/`localversion.20-pkgname`，并设置空的 `LOCALVERSION` 环境变量；仅关闭 LOCALVERSION_AUTO 仍可能追加 dirty。导出程序核对实际 Image 与 vmlinux build ID，并生成哈希清单。

把输入归档和配方放到 AArch64 构建环境，设置 `FREEDOM_PREBUILT_BUNDLE` 为归档绝对路径，`FREEDOM_PREBUILT_SHA256` 为完整 SHA256，再运行 `makepkg`。包在 AArch64 环境生成，fixdep、modpost、sign-file、resolve_btfids 也在那里原生编译；不会把交叉构建的 x86 程序放入 headers。

安装的 headers Makefile 默认使用 LLVM，使普通外部模块的 `make -C ... M=...` 不必额外了解内核编译器。仍允许命令行覆盖 LLVM；这项默认只放在 headers 包，不改内核运行代码。

## 安装与更新

安装内核、headers、`als-bridge-dkms` 以及 `kshim-freedom`。保留现有 `als-bridge` 用户态包。DKMS 通过标准 pacman hooks 构建模块；95-kshim-freedom hook 在其后生成 initramfs 和签名启动镜像。

kShim 声明在 `/etc/kshim-freedom/config.json`，按 pkgbase 自动找到内核版本，配置中不写死 release。当前运行时仍使用 boot_a 内嵌载荷，不会在开机时扫描 BOOT；生成新 boot.img 无需重编 kShim 核心。`deploy_boot_a` 控制生成后是否部署，默认初始化阶段先暂存验证。尾部 BOOT 不是当前启动内容的来源。

升级/移除前，60-kshim-freedom-backup hook 保存旧模块归档和 boot 镜像至 `/var/lib/kshim-freedom/rollback/<release>/`。回退时需要恢复对应模块与启动镜像，不能只恢复 boot。自动备份失败会中止软件包事务。

## Q6V5 handover 修复（pkgrel 2）

仅新增主线 `bb7c5d6f5b41d192fa81ce404e463f5d3ce70cb3` 的单次 handover IRQ 修复，按固定提交 URL 与 SHA256 引用原补丁。首次 handover 后屏蔽 IRQ；prepare 重新启用，unprepare 同步停用，避免重复通知与中断计数失衡。

`q6v5-attach-keep-handover-masked.patch` 适配 Freedom 的 Baldur attach 分支：接管已经运行的远端时未取得 proxy 资源，保持 handover 屏蔽；后续实际启动仍由 prepare 管理。依据上游 SMP2P 软件屏蔽的评审意见，来源链接保留在补丁头。Elden 的正常 start 路径使用主线修复。没有修改 AudioReach、Iris、USB、SMP2P 状态检测等其他机制。

构建与静态/模拟检查不代表新内核已经部署或完成实机验证；运行版本应通过 uname、build ID 和启动结果另行确认。

## 新版 ARM64 UAPI 与宿主工具

引用主线 `10a47fb67340bca274276faf855d7d460afd9a7a`，为 `tools/include/linux/types.h` 补齐 128 位类型，使旧内核工具可与新版 ARM64 系统头配合。补丁按固定 URL 和 SHA256 引用。完整内核构建保持 `LLVM=1`，不额外覆盖宿主编译器或预加载系统类型头；原生 headers helpers 也不再预加载系统头。

## 四代 USB 主机恢复（pkgrel 3）

将 Freedom 0192 已有的 `xhci_power_lost` 状态跟踪和 xHCI 恢复通知扩展到 `lenovo,elden`。系统休眠实际关闭 DWC3 核心时，恢复侧重建 xHCI 状态；核心保留时仍走原保留路径。补丁只扩展三个机型条件，来源见 [0003 增量补丁](../../patches/freedom/0003-usb-dwc3-enable-elden-power-lost.patch)。构建产物与实机验证状态分别记录。

## 四代共享修复与显示电源管理对照

本地增量继续引用固定 Freedom 源码，扩展 USB 冻结排序/eUSB2 与电源域保留、显示 atomic 状态/VFP/idle refresh、固定 PCIe 插槽标志、panic 中 Wi-Fi 唤醒保护、蓝牙已配置地址和板级 UFS MCQ 资源。DP 插拔专用改动未扩展。

pkgrel 4 合并测试中，MCQ 并发直接读校验和 VFP 切换路径通过，但内核接口及正常电源键休眠均发生重启。pkgrel 5 撤掉新增的显示 iface/GDSC/PLL 电源管理和 bonded 关闭顺序扩展，保留其余改动，用于对照验证；不能把 pkgrel 4 的正常启动或运行时读写通过当作休眠通过。Elden 的 idle refresh 只在不高于 120 Hz 的模式启用。 pkgrel 5 已启动，定时与电源键两轮短时 s2idle 均保持同一 boot ID，用户确认显示、触控和恢复正常；长期休眠未覆盖。恢复后数据校验通过，但 ESI 专用中断未增长、共享 UFS 中断继续增长，仍需独立核对 MCQ 中断恢复。

## UFS 恢复修复（pkgrel 6）

回移上游邮件 [Reprogram ESI after a host controller reset](https://lore.kernel.org/all/20261022165006.1275-1-26rote@gmail.com/)，保留 MSI 消息并在控制器重新配置时恢复 ESI 寄存器，IRQ 仍只申请一次。适配补丁保留作者、Fixes 和来源，见 [0010](../../patches/freedom/0010-ufs-qcom-restore-esi-after-reset.patch)。

同时按固定提交 URL 和 SHA256 引用主线 [b52d695d062095327b944acf7daabbc816ab319b](https://github.com/torvalds/linux/commit/b52d695d062095327b944acf7daabbc816ab319b)：错误处理冻结正常 I/O 时，允许内部恢复命令继续执行，结束时平衡冻结计数。常规休眠通过不等于已覆盖人工注错的错误恢复分支。


## 扫描取消与休眠（pkgrel 7）

`ath12k-scan-cancel.patch` 为本地修复：取消扫描时同步完成待处理的扫描清理，且不允许已完成的 range batch 在取消期间启动下一段。原故障在进入休眠前已有 cfg80211 扫描残留警告，恢复后持续 `SCAN-FAILED ret=-16`；不是凭一次掉线认定 PCIe D3 导致。

同一 7.2.6-6 内核上仅覆盖 ath12k 模块进行对照，模块导出符号校验值一致；扫描期间的 20/60 秒两轮 s2idle 均保持同 boot、联网和直接读校验通过，ESI 中断继续增长，原扫描警告未复现。正式配方升为 7，实际设备当时仍为 6 加测试模块，不能把该记录写成正式 7 内核已启动。F2FS 末尾段越界另行离线核对，本配方不裁剪 discard 来掩盖元数据问题。

## Iris 分辨率切换与退出（pkgrel 12）

按固定 [SunUEFI 提交](https://github.com/slwyts/Project-SunUEFI/tree/be3073644216a413776b973203d4222e8950703a/patches/linux/7.2.9) 的 URL 和 SHA256 引用两份原补丁：空 PSC_LAST 不再误标 ERROR，带错误的 LAST 也更新队列停止状态；退出时先同步中断线程，再取得核心锁，避免等待同一把锁的死锁。配合 `ffmpeg-v4l2m2m` 的用户态补丁验证，保留现有显示电源管理基线。

本地非 LTO 测试使用 `7.2.6-11-freedom`；正式配方保留 ThinLTO，并使用更高的 pkgrel，使后续 CI 包能够正常升级测试包。

## 唤醒显示状态候选（pkgrel 16）

保持原 Elden PHY 电源管理，不扩展0178 runtime PM。三个改动独立保存并顺序测试：

- [0012](../../patches/freedom/0012-dsi-elden-keep-live-link-state.patch)：参考固定 xiaquwan 同型号现场，在重复赋予显示模式时保留已上电链路的配置标志，其他速率/parent检查不变。
- [0013](../../patches/freedom/0013-dsi-sm8750-restore-bonded-slave.patch)：适配固定 SunUEFI 0025，保存/恢复 SM8750 从 PHY 分频器与 mux；覆盖 Freedom 的 Elden 和通用桥接关闭路径，不硬编码寄存器值。
- [0014](../../patches/freedom/0014-dsi-elden-stop-slave-first.patch)：适配固定 SunUEFI 0008，仅调整 Elden 从 DSI host 到主 host 的关闭顺序，不改 DPU 编码器顺序。

本地非LTO内核13/14/15依次增加这三项，每版三次真实关屏恢复及20/60秒定时s2idle通过，各版测试期间boot ID不变、Wi-Fi恢复，未见DSI命令超时或ADSP fatal。最终留在15，画面/触控仍待用户实体确认；正式16保留ThinLTO，未构建或跑新CI。短时恢复通过不代表历史间歇性重启已根治。


## UFS 调频与管理命令死锁（pkgrel 19）

回移上游 [Fix a deadlock between clock scaling and device commands](https://lore.kernel.org/all/20261016124608.46-1-26rote@gmail.com/)，见 [0015](../../patches/freedom/0015-ufs-fix-clock-scaling-command-deadlock.patch)。调频与暂停命令路径先取得 `clk_scaling_lock`，再 quiesce tagset，结束时按相反顺序恢复；调频路径保持 `wb_mutex` 在时钟锁之前。避免管理命令持有读锁却被已暂停的队列挡住，调频线程再等待写锁的循环等待。

2026-10-25 本地15版编译现场捕获到 UFS exception-event 线程等待 `blk_execute_rq()`、devfreq 线程等待时钟写锁，后续 F2FS 与用户进程一起阻塞，与上游报告高度吻合。原有 `b52d695d0620` 仅修复错误恢复路径，不能代替本次修正。修后负载对照见下文；高并发编译是触发条件线索，不据此认定文件系统损坏。

本地非 LTO 测试使用 `7.2.6-18-freedom`；正式配方使用更高的19并保留 ThinLTO，使后续仓库包可正常升级测试包。

2026-10-25 本地18已安装并正常重启，Build ID `abc32eda…`；120秒四路文件校验与5910次UFS查询、35次实际调频通过，一次20秒s2idle同boot恢复。旧15回退保留。尚未覆盖长期负载与休眠。

## 2026-10-29 上游同步

Freedom 固定至 `9788014a0293dc26745b000d02854ad88ef73e88`，纳入 0224 的通用旋转拆分、资源重新分配、时钟计算修正以及 0531 的 ASoC 延迟恢复同步。SM8750 已由既有 0066 开启 inline rotation；DPU13 的寄存器变化仅作用于 DPU13，四代沿用 DPU12 路径。0188 已包含 Elden，因此不再重复应用本地 range-scan 扩展。包随匹配模块目录安装 `freedom-dpu-rotation` 能力文件，供会话核对显式 DPU 选项。

启用方式、回退与实测边界见 [同步记录](../../docs/freedom-sync-20261029.md)。

四代 DPU 实测发现最终带宽汇总仍使用已提交状态，导致高带宽双图层之后连降低带宽的提交也失败。本地 [0016](../../patches/freedom/0016-dpu-elden-check-pending-bandwidth.patch) 让 Elden 检查本次事务的新 CRTC 状态，保持原来的 28.5 GB/s 检查上限和提交后的总线投票。回归测试覆盖降带宽、拒绝超限首帧、DPMS 恢复、关闭以及多 CRTC 汇总。

pkgrel 21 进一步加入 [0017](../../patches/freedom/0017-dpu-elden-candidate-plane-performance.patch)：按候选 plane 的实际几何和刷新率重算性能，解决缓存晚一帧更新的问题；Elden 旋转带宽按旋转后的扫描方向计算。原有硬件上限、prefill 和安全余量仍保留。生产 C 函数测试涵盖旋转方向、分数缩放、短消隐预取、图层删除和仅刷新率变化，实机结果见同步记录。

## 调度与 MGLRU 改进（pkgrel 22）

从 CachyOS 的 Linux 7.2 分支选择五个通用补丁，保留原始作者和提交信息；原补丁存放在 `patches/freedom/0018` 至 `0022`，由 `sync-recipe.py` 同步到配方目录。在 Freedom 和设备补丁之后依次应用：

| 本地补丁 | 来源 | 作用 |
| --- | --- | --- |
| [0018](../../patches/freedom/0018-sched-fair-avoid-repeat-scan.patch) | [d7ea20441344](https://github.com/CachyOS/linux/commit/d7ea20441344fd9a347a70dcd09b5a418159732b) | 持有运行队列锁后设置扫描上限，避免负载均衡重复遍历任务 |
| [0019](../../patches/freedom/0019-sched-inline-finish-task-switch.patch) | [01a771a66fd8](https://github.com/CachyOS/linux/commit/01a771a66fd8711b31c92f2446edf1e59cc9c5d0) | 内联任务切换收尾函数及其辅助函数 |
| [0020](../../patches/freedom/0020-mm-folio-referenced-vma-flags.patch) | [30dd1cccbc66](https://github.com/CachyOS/linux/commit/30dd1cccbc66) | 将 folio 引用检查转换为 vma_flags_t，为后续补丁准备接口 |
| [0021](../../patches/freedom/0021-mm-executable-folio-helper.patch) | [9d4aecaeb029](https://github.com/CachyOS/linux/commit/9d4aecaeb029) | 提取可执行文件页判定函数 |
| [0022](../../patches/freedom/0022-mglru-protect-executable-folios.patch) | [7a19fefa2590](https://github.com/CachyOS/linux/commit/7a19fefa2590bb5f6f0cdff54a40ebf9a0661c45) | MGLRU 在可执行文件页首次使用后提升其回收保护级别 |

MGLRU 改动针对文件支持的可执行页面，不等同于保护所有 FEX 匿名 JIT 页面。保留现有 HZ=250、THP=madvise 和其他调度参数；没有启用 CONFIG_CACHY 或替换调度器。

2026-10-31 在上一版已准备源码的隔离副本上按配方顺序无 fuzz 应用五个补丁，使用相同 Clang 18 和 ThinLTO 配置成功编译 `kernel/sched/core.o`、`kernel/sched/fair.o`、`mm/rmap.o`、`mm/vmscan.o`，release 为 `7.2.6-22-freedom`。尚未完成新版本完整内核链接或实机测试，性能收益未测量。
