# PyInstaller spec for htTamer on Windows (one folder). Build from the repo root:
#   pyinstaller deploy/windows/httamer.spec --noconfirm
# Needs tools/minidsp/minidsp.exe (the release workflow downloads it) and a VERSION file.
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

root = Path(SPECPATH).parents[1]
datas = [(str(root / "subtune" / "web"), "subtune/web"), (str(root / "subtune" / "hwdb_seed.json"), "subtune"),
         (str(root / "tools" / "minidsp" / "minidsp.exe"), "tools/minidsp"),
         (str(root / "LICENSE.md"), "."), (str(root / "README.md"), "."), (str(root / "VERSION"), ".")]
datas += collect_data_files("_sounddevice_data")

a = Analysis([str(root / "deploy" / "windows" / "httamer_launcher.py")], pathex=[str(root)], datas=datas,
             hiddenimports=collect_submodules("subtune") + collect_submodules("numpy._core") + ["scipy.signal", "scipy.optimize", "scipy.ndimage"],
             excludes=["tkinter", "matplotlib", "IPython", "pytest"])
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="htTamer", console=True,
          icon=str(root / "deploy" / "windows" / "httamer.ico") if (root / "deploy" / "windows" / "httamer.ico").exists() else None)
coll = COLLECT(exe, a.binaries, a.datas, name="htTamer")
