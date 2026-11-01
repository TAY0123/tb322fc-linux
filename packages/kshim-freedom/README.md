# kShim 启动交付

此包提供 AArch64 打包工具、kShim runtime、AVB 工具、F2FS initramfs 生成器和 pacman hooks。默认从固定来源原生构建；也支持显式传入 `KSHIM_TOOLS_BUNDLE` 及其 SHA256 使用已核验的工具归档。原生工具和 BusyBox 保持构建后的原字节，不再进行 makepkg strip。产物的实机验证状态需单独记录。

2026-10-29 的 DPU 同步仅更新内核来源清单和不变的 boot builder 引用。Runtime 单独固定到已验证的 Freedom `244b745` 加本地兼容补丁；更新的上游默认启用原生 UFS 设置存储，其 I/O 生命周期与 DPU 无关，需另行验证后更新 runtime。本次可使用当前安装且哈希核验通过的原生工具 bundle。

原厂 boot 基底与 AVB 私钥不放入软件包。设备配置 `/etc/kshim-freedom/config.json` 指定其本地路径、原厂镜像哈希、根 PARTUUID、cmdline、早期固件及 pkgbase；私钥位于 root 限权目录，权限须为 0600。部署目标固定为本项目的 Linux boot_a，拒绝其他机型或根分区不匹配的环境。

生成 boot 时，未显式指定的控制台参数默认使用 `fbcon=rotate:1`、
`fbcon=font:TER16x32` 和 `vconsole.font=latarcyrheb-sun32`，使已有配置也能获得
横屏大字体。需要内核启用 framebuffer console rotation、内置 TER16x32 字体，
并安装 `kbd`。用户在 `cmdline` 中显式指定的旋转或字体优先于这些默认值；
`vconsole.font` 会按 systemd 的规则覆盖 `/etc/vconsole.conf` 的 `FONT`。

软件包还可在 `/usr/lib/kshim-freedom/cmdline.d/*.conf` 提供默认启动参数。
这些文件按名称排序读取，仅解析参数及注释，不执行 shell；设备 `cmdline` 中的同名参数优先。
补充的参数放在显式参数之前，避免 `quiet` 重置管理员指定的 `loglevel`。
Plymouth 机型配置包使用这一机制启用动画和自身的横屏绘制。新增或移除配置后需重新生成 boot；
可在设备配置中使用 `splash=verbose` 默认显示文字，或 `plymouth.enable=0` 禁用 Plymouth。

打包器还会执行 `/usr/lib/kshim-freedom/initramfs.d/*.sh` 中可执行的资源收集脚本，
参数是临时 initramfs 目录；任何收集失败都会中止生成，不刷入缺失依赖的镜像。
openSUSE 的 Plymouth 机型包通过此接口加入主题、字体、udev 与按键布局，
在寻找根分区之前显示动画，并通过 `update-root-fs` 将同一进程交给真实根的 systemd。
原有根分区选择、Android 分区写保护和挂载失败文字提示保持不变。

`freedom-kernel-update --kernel <release> --stage-only` 生成并校验候选，`--deploy` 在完整备份后写 A 并回读；配置 `deploy_boot_a` 可让更新 hook 自动部署。程序不重启系统，不写 B/recovery。候选、打包检查、签名和部署结果位于 `/var/lib/kshim-freedom/candidates/`，最新结果见 `latest.json`。

自动部署只选择仍归属于配置内核包的模块目录，避免 ALS/DKMS 更新 hook 误选保留的回退目录；显式 `--kernel` 仍可选择指定版本。

95 hook 在 DKMS 之后运行，要求必需模块已能由 modinfo 找到。60 pre-transaction hook 在旧模块被移除前保存模块与 boot。首次安装应先检查候选，完成真实启动验证后再启用自动部署。

替换 Android 内核基底使用 `kshim-android-base-replace /path/to/boot.img`，默认重打当前运行的 Linux 内核，也可用 `--kernel <release>` 指定。`--check-only` 只验证输入。输入须满足当前 Freedom 打包器和签名器的条件：与原基底等长的 boot v4、未压缩 ARM64 内核、boot 内无 ramdisk/boot signature、有效 AVB footer 与可验证的 SHA256_RSA4096 boot 描述符。压缩内核、init_boot、无 footer 或不兼容签名模板会在替换前拒绝，不会自动转换。

脚本先对输入的私有副本校验、试打包并校验候选，成功后才原子替换配置指定的基底文件、更新 `stock_boot_sha256`。和内核更新共用锁，试打包强制 `--stage-only`，即使配置开启自动部署也不会刷入或重启。失败恢复原配置/基底和 latest 指针；原文件、配置及结果保留在 `/var/lib/kshim-freedom/base-*/`。候选位置见输出的 `candidate.image`。校验和打包通过不代表新 GKI 的 Android KMI、设备模块或实际启动已验证。

菜单重启修正使用 `patches/kshim/0002-qcom-reboot-v7-spmi.patch`：允许共享 CrDK 已支持的 v7 PMIC arbiter，保留通道所有权和窗口边界检查。固定 Freedom 版本原来的重启适配器只允许 v8/v8.5，导致 SM8750 在写入 reboot reason 前失败。主机测试直接覆盖真实适配器和 CrDK；设备受控调用同一重启函数已进入真正的 bootloader Fastboot。

Recovery 与 bootloader 是不同路径。本机 recovery 镜像没有内核，借用 boot_a 中被 kShim 包装的 Android 内核；请求 Recovery 后经过 kShim，选择 Android 已验证可进入 TWRP。当前普通启动与 Recovery 均缺少 `androidboot.force_normal_boot`，不能用标记缺失来自动选择 Android。此包不加入该启发式判断，Recovery 仍需手动选择 Android。Linux 的 `systemctl reboot --reboot-argument=bootloader` 已验证进入真正的 Fastboot；`fastboot`/fastbootd 不能与 `bootloader` 混称。
