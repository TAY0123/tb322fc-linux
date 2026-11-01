from pathlib import Path
import subprocess, sys
subprocess.run([sys.executable,str(Path(__file__).resolve().parents[1]/'vendor-dependencies.py'),'cargo',sys.argv[1],'sources/steamos-manager/Cargo.toml'],check=True)
