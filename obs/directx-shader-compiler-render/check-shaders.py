#!/usr/bin/env python3
"""Exercise DXC's DXIL destructor path and its SPIR-V backend before packaging."""
from pathlib import Path
import subprocess
import sys
import tempfile

compiler = Path(sys.argv[1]).resolve()
shader = """
RWStructuredBuffer<float4> output : register(u0);
[numthreads(1, 1, 1)]
void main(uint3 id : SV_DispatchThreadID) {
#ifdef USE_HALF
    half4 value = half4(id.x, 2, 3, 4);
#else
    float4 value = float4(id.x, 2, 3, 4);
#endif
    output[id.x] = float4(value);
}
"""
with tempfile.TemporaryDirectory(prefix="dxc-check-") as temporary:
    root = Path(temporary)
    source = root / "shader.hlsl"
    source.write_text(shader)
    for name, flags, magic in (
        ("dxil", [], b"DXBC"),
        ("dxil-fp16", ["-DUSE_HALF=1", "-enable-16bit-types"], b"DXBC"),
        ("spirv", ["-spirv"], bytes.fromhex("03022307")),
    ):
        output = root / name
        subprocess.run(
            [str(compiler), "-E", "main", "-T", "cs_6_2", *flags,
             str(source), "-Fo", str(output)],
            check=True, timeout=120,
        )
        data = output.read_bytes()
        assert len(data) > 32 and data.startswith(magic), name
        print(f"{name}: compiled and exited normally ({len(data)} bytes)", flush=True)
