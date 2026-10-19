"""把 mod/ 目录打包成铁锈战争可加载的 .rwmod 文件。

用法：
    python tools/pack.py                      # 输出到 dist/[生化狂潮-瘟疫王朝].rwmod
    python tools/pack.py -o dist/xxx.rwmod    # 指定输出路径
"""
import argparse
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "mod"
DEFAULT_OUT = ROOT / "dist" / "[生化狂潮-瘟疫王朝].rwmod"

# 系统自动生成的垃圾文件，不打进模组
SKIP_NAMES = {"Thumbs.db", "desktop.ini", ".DS_Store"}


def collect_files(src):
    files = [p for p in src.rglob("*") if p.is_file() and p.name not in SKIP_NAMES]
    # mod-info.txt 放在最前面，其余按路径排序，保证每次打包顺序一致
    return sorted(files, key=lambda p: (p.name != "mod-info.txt" or p.parent != src, p.relative_to(src).as_posix()))


def pack(src, out):
    if not (src / "mod-info.txt").is_file():
        sys.exit(f"找不到 {src / 'mod-info.txt'}，请确认 mod/ 目录完整")
    out.parent.mkdir(parents=True, exist_ok=True)
    files = collect_files(src)
    tmp = out.with_suffix(out.suffix + ".tmp")
    # 中文文件名由 zipfile 自动写成 UTF-8 并设置对应标志位，游戏可以正确读取
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for p in files:
            z.write(p, p.relative_to(src).as_posix())
    tmp.replace(out)
    print(f"已打包 {len(files)} 个文件 -> {out}")


def main():
    parser = argparse.ArgumentParser(description="打包 mod/ 为 .rwmod")
    parser.add_argument("-o", "--output", type=Path, default=DEFAULT_OUT, help="输出文件路径")
    args = parser.parse_args()
    pack(SRC, args.output.resolve())


if __name__ == "__main__":
    main()
