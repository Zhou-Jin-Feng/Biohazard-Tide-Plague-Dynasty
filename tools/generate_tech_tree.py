# -*- coding: utf-8 -*-
"""
生化狂潮：瘟疫王朝 真实树状科技树生成器
根据 mod/ 单位数据读取 tools/tech_tree_template.html，注入 JSON 并输出 tech_tree.html。
"""
import sys
import json
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tools.generate_html import extract_unit, classify, MOD_DIR, ROOT

OUT_FILE = ROOT / "tech_tree.html"
TEMPLATE_FILE = ROOT / "tools" / "tech_tree_template.html"

def main():
    t0 = time.time()
    ini_files = sorted(MOD_DIR.rglob("*.ini"))
    print(f"正在扫描并解析 {len(ini_files)} 个单位 ini…")
    img_cache = {}
    units = classify([extract_unit(p, img_cache) for p in ini_files])

    template = TEMPLATE_FILE.read_text(encoding="utf-8")
    data_json = json.dumps(units, ensure_ascii=False).replace("</", "<\\/")
    rendered = template.replace("__DATA_JSON__", data_json)

    OUT_FILE.write_text(rendered, encoding="utf-8")
    mb = OUT_FILE.stat().st_size / 1024 / 1024
    print(f"真实树状科技树页面已生成: {OUT_FILE} ({mb:.2f} MB, 耗时 {time.time() - t0:.1f}s)")

if __name__ == "__main__":
    main()
