"""把打包好的 .rwmod 装进铁锈战争的 mods/units，可选顺带启动游戏。

替换前会把游戏里原来的模组备份到 _backup/游戏内上一版.rwmod（只保留一代，校验后才算备份成功）。

用法（在项目根目录运行）：
    python tools/install_to_game.py              # 替换游戏里的模组
    python tools/install_to_game.py --launch     # 替换后通过 Steam 启动游戏
    python tools/install_to_game.py --launch-only
    python tools/install_to_game.py --restore    # 用 _backup/游戏内上一版.rwmod 恢复
"""
import argparse
import hashlib
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MOD_NAME = "[生化狂潮-瘟疫王朝].rwmod"
SRC = ROOT / "dist" / MOD_NAME
GAME_DIR = Path(r"D:\Steam\steamapps\common\Rusted Warfare")
UNITS_DIR = GAME_DIR / "mods" / "units"
TARGET = UNITS_DIR / MOD_NAME
SAME_MOD_PREFIX = "[生化狂潮-瘟疫王朝]"
PREV_BACKUP = ROOT / "_backup" / "游戏内上一版.rwmod"
STEAM_APP_ID = "647960"


def md5(path):
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def game_running():
    out = subprocess.run(["tasklist", "/FO", "CSV", "/NH"], capture_output=True, text=True,
                         encoding="gbk", errors="replace").stdout.lower()
    return "rusted warfare" in out


def verified_copy(src, dst):
    """先复制到临时文件，md5 一致后再原子替换到 dst；失败时清理临时文件并退出。"""
    tmp = dst.with_name(dst.name + ".tmp")
    try:
        shutil.copy2(src, tmp)
        if md5(tmp) != md5(src):
            sys.exit(f"复制到 {dst} 后校验不一致，已放弃，原文件未改动")
        os.replace(tmp, dst)
    finally:
        if tmp.exists():
            tmp.unlink()


def check_ready():
    if not UNITS_DIR.is_dir():
        sys.exit(f"找不到游戏模组目录 {UNITS_DIR}")
    others = [p.name for p in UNITS_DIR.iterdir()
              if p.is_file() and p.name.startswith(SAME_MOD_PREFIX) and p.name.endswith(".rwmod") and p.name != MOD_NAME]
    if others:
        sys.exit(f"mods/units 里还有其他生化狂潮模组 {others}，会和本模组重复加载，请先处理")
    if game_running():
        sys.exit("游戏正在运行，请先退出游戏再替换")


def install():
    if not SRC.is_file():
        sys.exit(f"找不到打包产物 {SRC}，先运行 python tools/pack.py")
    import zipfile
    with zipfile.ZipFile(SRC) as z:
        bad = z.testzip()
        if bad or "mod-info.txt" not in z.namelist():
            sys.exit(f"打包产物损坏或缺少 mod-info.txt（{bad}），不替换")
    check_ready()
    if TARGET.is_file():
        if md5(TARGET) == md5(SRC):
            print("游戏里已经是最新版本，无需替换")
            return
        PREV_BACKUP.parent.mkdir(exist_ok=True)
        verified_copy(TARGET, PREV_BACKUP)
        print(f"上一版备份 -> {PREV_BACKUP}")
    verified_copy(SRC, TARGET)
    print(f"已替换 -> {TARGET}")


def restore():
    if not PREV_BACKUP.is_file():
        sys.exit(f"没有可恢复的备份 {PREV_BACKUP}")
    check_ready()
    verified_copy(PREV_BACKUP, TARGET)
    print(f"已用上一版恢复 -> {TARGET}")


def launch():
    if game_running():
        print("游戏已经在运行")
        return
    os.startfile(f"steam://rungameid/{STEAM_APP_ID}")
    print("已通过 Steam 启动铁锈战争")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--launch", action="store_true", help="替换后启动游戏")
    g.add_argument("--launch-only", action="store_true", help="不替换，只启动游戏")
    g.add_argument("--restore", action="store_true", help="用上一版备份恢复游戏里的模组")
    args = ap.parse_args()
    if args.restore:
        restore()
    elif not args.launch_only:
        install()
    if args.launch or args.launch_only:
        launch()


if __name__ == "__main__":
    main()
