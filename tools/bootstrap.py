# -*- coding: utf-8 -*-
"""跨平台一键重建：本仓库 wheels/（web-launcher-apps 不含内嵌 runtime）。

替代原 bootstrap.bat（仅 Windows）。等价于运行 make_wheels.py。
runtime 属于 web-launcher 仓库，请到那边重建（那边有自己的 tools/bootstrap.py）。

前置：联网 + 命令行里有 python。
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent   # tools/ 上一级 = 仓库根


def main():
    print("=" * 44)
    print("重建本仓库应用依赖 wheels (wheels/<平台>)")
    print("=" * 44)
    r = subprocess.run([sys.executable, str(ROOT / "tools" / "make_wheels.py")], cwd=str(ROOT))
    if r.returncode != 0:
        print("\n[ERROR] wheels 下载失败，请检查网络与依赖 wheel 可用性。")
        return 1
    print("\n完成！本仓库 wheels/ 已重建。（runtime 属于 web-launcher，请到它那边重建）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
