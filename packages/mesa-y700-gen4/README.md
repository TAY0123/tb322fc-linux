# Mesa 稳定版（2026-10-24）

恢复自本仓库 `16c5b1b` 的稳定版分包配方，版本由 26.2.3 更新为 26.2.4。
对应 armadaos-freedom `9788014a0293dc26745b000d02854ad88ef73e88`
的 `packages/mesa/BASE.env` 与三个原样基础补丁。构建时从固定 Git 提交引用补丁，不在本仓库复制；不添加其 devel/winnative 变体补丁。
本包沿用 Arch 的 Meson 选项和分包，不能称作 Fedora 二进制或工具链完全相同。

源码 SHA256 固定为 `bce5f7fbebb934373b86c999a064d52fb5065878dc57f287f95346648ec832e9`。
保留所有源码和 crate 的 SHA256 校验；发布包签名已经通过归档公钥验证。
历史版本的 BLAKE2 校验表已删除。
各分包声明与对应 `-git` 包冲突，允许在一个 pacman 事务中整套替换。
默认编译并行数 6，可设置 `MESA_BUILD_JOBS`。仓库只保留稳定版 Mesa 配方。

26.2.5 已发布，本次使用 26.2.4 是为了对齐 Freedom，便于排除开发版差异。
