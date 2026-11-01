from pathlib import Path
import subprocess, sys
subprocess.run([sys.executable,str(Path(__file__).resolve().parents[1]/'vendor-dependencies.py'),'npm',sys.argv[1],'local/decky'],check=True)
