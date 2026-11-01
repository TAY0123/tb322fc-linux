# Cross runtimes built from source with openSUSE's native LLVM toolchain.
%define llvm_version 23.1.4
%define llvm_major 23
%define mingw_commit 9f55f4a2d3b9783dab76d9808be3d6279b99ec2a
%define wrappers_commit 030097eeee87fcfd0f3bfe536b21cbd6e5d3b324
%define toolchain_dir %{_libexecdir}/llvm-mingw-arm64ec
%global debug_package %{nil}
%global _lto_cflags %{nil}
Name:           llvm-mingw-arm64ec
Version:        20260908
Release:        0
Summary:        ARM64EC Windows cross runtimes for the system LLVM compiler
License:        Apache-2.0 WITH LLVM-exception AND MIT AND SUSE-Public-Domain
URL:            https://github.com/mstorsjo/llvm-mingw
Source0:        llvm-mingw-%{wrappers_commit}.tar.gz
Source1:        mingw-w64-%{mingw_commit}.tar.gz
Source2:        llvm-project-%{llvm_version}.src.tar.xz
Source3:        link-check.cpp
Source4:        %{name}-rpmlintrc
Patch0:         suse-clang-paths.patch
ExclusiveArch:  aarch64
BuildRequires:  clang%{llvm_major}
BuildRequires:  llvm%{llvm_major}
BuildRequires:  lld%{llvm_major}
BuildRequires:  gcc
BuildRequires:  gcc-c++
BuildRequires:  cmake
BuildRequires:  ninja
BuildRequires:  make
BuildRequires:  python3
BuildRequires:  file
BuildRequires:  fdupes
Requires:       clang%{llvm_major}
Requires:       llvm%{llvm_major}
Requires:       lld%{llvm_major}
Requires:       %{name}-devel = %{version}-%{release}

%description
MinGW-w64 headers, UCRT import libraries, compiler-rt, libc++ and libunwind
for Windows ARM64EC/ARM64X cross compilation. Compiler wrappers use the
distribution's native Clang and LLD; all target runtime libraries are built
from pinned upstream sources. This package supplies OptiScaler's toolchain.

%package devel
Summary:        Windows ARM64EC/ARM64X headers and libraries for LLVM MinGW
Requires:       clang%{llvm_major}

%description devel
MinGW-w64 headers, UCRT import libraries and the Windows compiler-rt, libc++
and libunwind libraries. These are cross-development files, not native Linux
libraries. The llvm-mingw-arm64ec compiler wrappers depend on this package.

%prep
printf '%%s  %%s\n' 'd2c147b5e315b606f39c79ea48bd7e300ed72b3e27581d41739b4e0634dc9234' '%{SOURCE0}' | sha256sum -c
printf '%%s  %%s\n' '42b54413471ecedb316ea98bc681f0152cade9e93cc631751f8bfdc6ea46e245' '%{SOURCE1}' | sha256sum -c
printf '%%s  %%s\n' '819ecf7351f1a66f76b2d701d8942faaf5faeb324cb90c9d5b090de142434bb2' '%{SOURCE2}' | sha256sum -c
%autosetup -p1 -n llvm-mingw-%{wrappers_commit}
mkdir mingw-w64 llvm-project
tar -xf %{SOURCE1} --strip-components=1 -C mingw-w64
tar -xf %{SOURCE2} --strip-components=1 -C llvm-project

%build
unset CFLAGS CXXFLAGS LDFLAGS
export TOOLCHAIN_ARCHS="aarch64 arm64ec"
export TOOLCHAIN_TARGET_OSES=mingw32
export CORES=%{_smp_build_ncpus}
export WRAPPER_FLAGS="%{optflags}"
prefix="$PWD/toolchain"
./install-wrappers.sh "$prefix" --host-clang=/usr/bin/clang-%{llvm_major}
./build-mingw-w64.sh "$prefix" --with-default-msvcrt=ucrt
# Catch target/sysroot mismatches before building the C and C++ runtimes.
for target in aarch64 arm64ec; do
    printf '#include <stdlib.h>\n#include <windows.h>\n' | \
        "$prefix/bin/$target-w64-mingw32-clang" -x c -fsyntax-only -
done
printf '#include <stdlib.h>\n' | \
    "$prefix/bin/aarch64-w64-mingw32-clang" -marm64x -x c -c - -o arm64x-header-check.o
./build-compiler-rt.sh "$prefix"
./build-libcxx.sh "$prefix" --disable-shared
./build-mingw-w64-libraries.sh "$prefix"

%install
mkdir -p %{buildroot}%{toolchain_dir}
cp -a toolchain/. %{buildroot}%{toolchain_dir}/
# The libtool archive records the temporary build prefix and is not used by
# Clang/LLD. Import archives are data, even if libtool installed them executable.
find %{buildroot}%{toolchain_dir} -type f -name '*.la' -delete
find %{buildroot}%{toolchain_dir} -type f -name '*.a' -exec chmod 644 {} +
%fdupes %{buildroot}%{toolchain_dir}
# SUSE's brp-15-strip-debug invokes GNU strip directly, ignoring __strip.
# Its archive handling cannot preserve ARM64EC/ARM64X members. Native wrappers
# are already stripped by install-wrappers.sh; keep the cross runtimes intact.
export NO_BRP_STRIP_DEBUG=true
# llvm-ar already writes deterministic archives. brp-75-ar uses GNU objcopy,
# which also cannot rewrite the mixed ARM64/ARM64EC import-library members.
export NO_BRP_AR=true

%check
# Exercise C++ containers, exceptions and Win32 imports, including relocation
# after SUSE's symlink policy rewrites /usr links to relative paths. Populate
# only the dependency paths in a disposable installation layout, not BUILDROOT.
checkroot="$PWD/check-root"
mkdir -p "$checkroot%{_libexecdir}"
cp -a %{buildroot}%{toolchain_dir} "$checkroot%{toolchain_dir}"
ln -s %{_bindir} "$checkroot%{_bindir}"
ln -s %{_libdir} "$checkroot%{_libdir}"
for target in aarch64 arm64ec; do
    "$checkroot%{toolchain_dir}/bin/$target-w64-mingw32-clang-scan-deps" --version
done
compiler="$checkroot%{toolchain_dir}/bin/arm64ec-w64-mingw32-clang++"
"$compiler" -std=c++23 -c %{SOURCE3} -o link-check.o
llvm-readobj-%{llvm_major} --file-headers link-check.o | tee object-header.txt
grep -q IMAGE_FILE_MACHINE_ARM64EC object-header.txt
"$compiler" -shared -static -static-libgcc -static-libstdc++ link-check.o -o link-check.dll
llvm-readobj-%{llvm_major} --file-headers --coff-imports link-check.dll
test -s link-check.dll
# Use LLVM's archive parser: GNU readelf does not understand ARM64X archives.
# Verify the three upstream compatibility placeholders really are empty.
python3 - "$checkroot%{toolchain_dir}" <<'PY'
from pathlib import Path
import subprocess
import sys
root = Path(sys.argv[1])
for archive in root.rglob('*.a'):
    subprocess.run(['llvm-ar-%{llvm_major}', 't', str(archive)],
                   check=True, stdout=subprocess.DEVNULL)
for name in ('libdelayimp.a', 'libssp.a', 'libssp_nonshared.a'):
    assert (root / 'aarch64-w64-mingw32/lib' / name).read_bytes() == b'!<arch>\n', name
PY

%files
%doc README.md
%license llvm-project/llvm/LICENSE.TXT
%dir %{toolchain_dir}
%{toolchain_dir}/bin/

%files devel
%license llvm-project/llvm/LICENSE.TXT
%dir %{toolchain_dir}
%{toolchain_dir}/aarch64-w64-mingw32/
%{toolchain_dir}/generic-w64-mingw32/
%{toolchain_dir}/lib64/
%{toolchain_dir}/share/

%changelog
