# -*- coding: utf-8 -*-
"""
根据 ini 数值自动生成单位描述里的属性行（生命、造价、建造/升级耗时、武器伤害等）。

描述 displayDescription 的结构：
    简介（手写，可多行）
    【生命】……              ← 以「【」开头的行由本脚本生成，每次运行都会重新计算
    【武器】……
    原作者：蚟醛钯烨          ← 原样保留在最后一行

同时给可见的升级 / 动作按钮的描述补上「【耗时】X 秒」。
改了数值后重新运行即可同步描述：
    python tools/gen_descriptions.py           # 写回 ini
    python tools/gen_descriptions.py --check   # 只打印，不写文件

计时口径（反编译 game-lib.jar 核实）：
  生产队列每帧进度 = 目标 buildSpeed × 生产者 nanoFactorySpeed（默认 1），每秒 60 帧；
  buildSpeed 写成 "10s" 即 10 秒；升级动作同样乘以单位自身的 nanoFactorySpeed。
  建筑由工人建造时按工人的 nanoBuildSpeed（默认 1）计算，多名工人同时建造会更快。
  selfRegenRate 为每帧回血量；generation_credits 每 generation_delay 帧发放一次。
"""

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import generate_html as g  # noqa: E402

MOD_DIR = g.MOD_DIR
FPS = 60
AUTO_PREFIX = "【"
MELEE_RANGE = 60
# 旧描述里手写的产资说明，由【产资】行代替
OLD_CREDIT_LINE = re.compile(r"^每秒\s*[加+＋]\s*\d+\s*[＄$]$")
OLD_TIME_PHRASE = re.compile(r"(\\n)?\s*耗时\s*\d+(\.\d+)?\s*秒")
# 沙盒调试单位，不参与建造时间统计，也不改写描述
SANDBOX = {"zuobi", "敌军投放器"}


# ---------------------------------------------------------------- 解析

def read_sections(path):
    """解析 ini（保留同名段的合并），处理文件级 copyFrom 与段级 copyFrom。"""
    sections = g.load_unit_sections(path)
    for sec, kv in list(sections.items()):
        src = kv.get("copyFrom", "").strip()
        if sec == "core" or not src or src.lower().endswith(".ini"):
            continue
        prefix = sec.split("_")[0]
        base = sections.get(f"{prefix}_{src}")
        if base:
            sections[sec] = {**base, **{k: v for k, v in kv.items() if k != "copyFrom"}}
    return sections


def seconds_from_speed(value):
    """buildSpeed 换算为秒；返回 None 表示未设置或不可用。"""
    value = str(value).strip()
    if not value:
        return None
    if value.endswith("ms"):
        return g.to_float(value[:-2]) / 1000
    if value.endswith("s"):
        return g.to_float(value[:-1])
    v = g.to_float(value)
    if v <= 0:
        return None
    return 0.0 if v >= 1 else 1.0 / (v * FPS)


def parse_price(value):
    """"800,setFlag=3" → 800；"credits=500" → 500；只有其他资源时返回 0。"""
    for part in str(value).split(","):
        part = part.strip()
        if "=" in part:
            k, v = part.split("=", 1)
            if k.strip() == "credits":
                return g.to_int(v)
        elif re.fullmatch(r"[-+]?\d+(\.\d+)?", part):
            return int(float(part))
    return 0


def fmt_num(v, digits=1):
    s = f"{v:.{digits}f}"
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    return s or "0"


def fmt_seconds(v):
    if v < 0.05:
        return "瞬间"
    return f"{fmt_num(v, 1 if v >= 1 else 2)} 秒"


def is_condition(v):
    return str(v).strip().lower().startswith("if ")


def condition_label(cond):
    if "transportingCount" in cond:
        return "载员时"
    if "hasFlag" in cond:
        return "特定形态"
    return "条件触发"


# ---------------------------------------------------------------- 单位数据

class Unit:
    def __init__(self, path):
        self.path = path
        self.sec = read_sections(path)
        core = self.core = self.sec.get("core", {})
        self.name = core.get("name", "") or path.stem
        self.display = core.get("displayText_zh", "") or core.get("displayText", "") or self.name
        movement = self.sec.get("movement", {})
        self.is_building = g.is_true(core.get("isBuilding", "")) or movement.get("movementType", "").upper() == "BUILDING"
        self.factory_speed = g.to_float(core.get("nanoFactorySpeed", 1), 1.0) or 1.0
        self.nano_build_speed = g.to_float(core.get("nanoBuildSpeed", 1), 1.0) or 1.0
        self.build_seconds = seconds_from_speed(core.get("buildSpeed", "1"))
        self.can_build = []  # (目标名, 是否按建造者模式)
        for k, v in core.items():
            m = re.fullmatch(r"canBuild_(\w+)_name", k)
            if m:
                force = g.is_true(core.get(f"canBuild_{m.group(1)}_forceNano", ""))
                self.can_build += [(n, force) for n in g.split_names(v)]
        rel = path.relative_to(MOD_DIR).parts
        # 编队（尸群 / 小队）一出生就展开成多个单位，自身武器没有实际意义
        self.is_squad = any(p in ("小队", "尸群") for p in rel[:-1])
        self.selectable = not g.is_true(core.get("isUnselectable", ""))
        self.built_from = []
        for k, v in core.items():
            if re.fullmatch(r"builtFrom_\w+_name", k):
                self.built_from += g.split_names(v)

    # ---------- 动作

    def actions(self):
        """返回可见动作列表：dict(key 前缀, convertTo, price, seconds, 来源)。"""
        out = []
        core = self.core
        for k in core:
            m = re.fullmatch(r"(action_\w+?)_text", k)
            if m:
                p = m.group(1)
                out.append({"id": p, "style": "core", "convertTo": core.get(p + "_convertTo", ""),
                            "price": core.get(p + "_price", ""), "speed": core.get(p + "_buildSpeed", ""),
                            "visible": core.get(p + "_isVisible", "true"), "auto": core.get(p + "_autoTrigger", ""),
                            "text": core.get(k, "")})
        for sec, kv in self.sec.items():
            if sec.startswith("action_"):
                out.append({"id": sec, "style": "section", "convertTo": kv.get("convertTo", ""),
                            "price": kv.get("price", ""), "speed": kv.get("buildSpeed", ""),
                            "visible": kv.get("isVisible", "true"), "auto": kv.get("autoTrigger", ""),
                            "text": kv.get("text", "")})
        result = []
        for a in out:
            if a["visible"].strip().lower() == "false" or a["auto"].strip() or not a["text"].strip():
                continue
            secs = seconds_from_speed(a["speed"])
            if secs is not None:
                secs = secs / self.factory_speed
            a["seconds"] = secs
            result.append(a)
        return result

    # ---------- 武器

    def weapons(self):
        attack = self.sec.get("attack", {})
        if attack.get("canAttack", "true").strip().lower() != "true":
            return []
        base_delay = g.to_float(attack.get("shootDelay", 0))
        unit_land = attack.get("canAttackLandUnits", "true")
        unit_air = attack.get("canAttackFlyingUnits", "false")
        turrets = [(s, kv) for s, kv in self.sec.items() if s.startswith("turret_")]
        if not turrets:
            turrets = [("turret_1", {})]
        groups = {}
        for sec, kv in turrets:
            if kv.get("canShoot", "true").strip().lower() == "false":
                continue
            proj_id = kv.get("projectile", "1").strip() or "1"
            proj = self.sec.get(f"projectile_{proj_id}")
            if proj is None:
                continue
            direct = g.to_float(proj.get("directDamage", 0))
            area = g.to_float(proj.get("areaDamage", 0))
            spawn = proj.get("spawnUnit", "").strip()
            if direct <= 0 and area <= 0 and not spawn:
                continue
            delay = g.to_float(kv.get("delay", "")) if kv.get("delay", "").strip() else base_delay
            land = kv.get("canAttackLandUnits", unit_land)
            air = kv.get("canAttackFlyingUnits", unit_air)
            cond = kv.get("canAttackCondition", "").strip()
            for v in (land, air):
                if is_condition(v):
                    cond = cond or v
            targets = []
            if is_condition(land) or g.is_true(land):
                targets.append("对地")
            if is_condition(air) or g.is_true(air):
                targets.append("对空")
            if not targets:
                continue
            energy = g.to_float(kv.get("energyUsage", 0))
            key = (proj_id, delay, condition_label(cond) if cond else "", tuple(targets), energy)
            if key not in groups:
                groups[key] = {
                    "count": 0, "direct": direct, "area": area,
                    "radius": g.to_float(proj.get("areaRadius", 0)), "delay": delay,
                    "cond": cond, "targets": targets, "spawn": spawn,
                    "building_mult": g.to_float(proj.get("buildingDamageMultiplier", 1), 1.0),
                    "pierce": g.to_float(proj.get("armourIgnoreAmount", 0)),
                    "energy": energy,
                }
            groups[key]["count"] += 1
        return list(groups.values())


def load_units():
    units = {}
    for p in sorted(MOD_DIR.rglob("*.ini")):
        u = Unit(p)
        units.setdefault(u.name, u)
    return units


def build_times(units):
    """{目标名: [各生产者下的建造秒数]}，按生产者倍率换算。"""
    times = {}

    def add(producer, target_name, force_nano):
        target = units.get(target_name)
        if target is None or producer.name in SANDBOX or target.build_seconds is None:
            return
        nano = force_nano or target.is_building
        speed = producer.nano_build_speed if nano else producer.factory_speed
        times.setdefault(target_name, []).append(target.build_seconds / speed)

    for u in units.values():
        for target_name, force in u.can_build:
            add(u, target_name, force)
        for src in u.built_from:
            if src in units:
                add(units[src], u.name, False)
    return times


# ---------------------------------------------------------------- 描述

def fire_rate(delay_frames):
    per_sec = FPS / delay_frames
    if per_sec >= 2:
        return f"每秒 {fmt_num(per_sec)} 发"
    return f"每 {fmt_num(delay_frames / FPS, 1)} 秒一发"


def unit_list(value, units):
    """"a, a, b*2" → "a×2、b×2"，使用显示名。"""
    counts = {}
    for item in value.split(","):
        n, _, cnt = item.strip().partition("*")
        n = n.strip()
        if not n:
            continue
        du = units.get(n)
        if n in g.HELPER_NAMES - {"尸块"} or (du is not None and not du.selectable):
            continue
        label = du.display if du else n
        counts[label] = counts.get(label, 0) + (g.to_int(cnt, 1) if cnt.strip() else 1)
    return "、".join(f"{k}×{v}" if v > 1 else k for k, v in counts.items())


def weapon_lines(u, units):
    lines = []
    attack = u.sec.get("attack", {})
    energy_max = g.to_float(u.core.get("energyMax", 0))
    energy_regen = g.to_float(u.core.get("energyRegen", 0))
    rng = g.to_float(attack.get("maxAttackRange", 0))
    # 不少远程单位也写了 isMelee（只影响走位），按射程区分近战
    melee = g.is_true(attack.get("isMelee", "")) and rng <= MELEE_RANGE
    merged = {}  # 去掉数量后文字相同的武器合并计数
    for w in u.weapons():
        head, tail = [], []
        if w["direct"] > 0:
            head.append(f"伤害 {fmt_num(w['direct'])}")
        if w["area"] > 0:
            head.append(f"溅射 {fmt_num(w['area'])}/半径 {fmt_num(w['radius'])}")
        spawned = unit_list(w["spawn"], units) if w["spawn"] else ""
        if spawned:
            head.append(f"命中生成 {spawned}")
        if w["delay"] > 0:
            head.append(fire_rate(w["delay"]))
        if w["energy"] > 0 and energy_max > 0:
            shots = max(int(round(energy_max / w["energy"], 3)), 1)
            regen = energy_regen * FPS / w["energy"]
            # 回复比射速快时弹药不构成限制
            if w["delay"] <= 0 or regen < FPS / w["delay"]:
                tail.append(f"弹药 {shots} 发（每秒回复 {fmt_num(regen)} 发）")
        if w["building_mult"] != 1:
            tail.append(f"对建筑 ×{fmt_num(w['building_mult'], 2)}")
        if w["pierce"] > 0:
            tail.append(f"无视护甲 {fmt_num(w['pierce'])}")
        tail.append("/".join(w["targets"]))
        tag = "近战" if melee else "武器"
        if w["cond"]:
            tag += "·" + condition_label(w["cond"])
        key = (tag, tuple(head), tuple(tail))
        merged[key] = merged.get(key, 0) + w["count"]
    for (tag, head, tail), count in merged.items():
        parts = list(head)
        if count > 1:
            parts.append(f"{count} 门" + ("（视载员数）" if "载员" in tag else ""))
        lines.append(f"【{tag}】" + "，".join(parts + list(tail)))
    if lines and rng > 0 and not melee:
        lines.append(f"【射程】{fmt_num(rng)}")
    return lines


def auto_lines(u, units, times):
    core = u.core
    lines = []

    hp = g.to_float(core.get("maxHp", 0))
    first = [f"【生命】{fmt_num(hp)}"] if hp > 0 else []
    shield = g.to_float(core.get("maxShield", 0))
    if shield > 0:
        first.append(f"【护盾】{fmt_num(shield)}")
    armour = g.to_float(core.get("armour", 0))
    if armour > 0:
        first.append(f"【护甲】{fmt_num(armour)}")
    regen = g.to_float(core.get("selfRegenRate", 0)) * FPS
    if regen >= 0.05 and not u.is_squad:
        first.append(f"【回血】{fmt_num(regen)}/秒")
    if first:
        lines.append("  ".join(first))

    second = []
    t = times.get(u.name)
    price = parse_price(core.get("price", 0))
    # 只能由升级 / 转化得到的单位，price 不是玩家实际付的钱，不显示
    if price > 0 and t:
        second.append(f"【造价】＄{price}")
    if t:
        lo, hi = min(t), max(t)
        value = fmt_seconds(lo) if abs(hi - lo) < 0.05 else f"{fmt_num(lo)}~{fmt_seconds(hi)}"
        second.append("【建造】" + value + ("（单个工人）" if u.is_building else ""))
    if second:
        lines.append("  ".join(second))

    if not u.is_squad:
        lines += weapon_lines(u, units)

    extra = []
    credits = g.to_int(core.get("generation_credits", 0))
    delay = g.to_int(core.get("generation_delay", 40)) or 40
    if credits > 0:
        extra.append(f"【产资】+{fmt_num(credits * FPS / delay)}＄/秒")
    elif credits < 0:
        extra.append(f"【维持费】{fmt_num(-credits * FPS / delay)}＄/秒")
    transport = g.to_int(core.get("maxTransportingUnits", 0))
    if transport > 0:
        extra.append(f"【运载】{transport} 人")
    if extra:
        lines.append("  ".join(extra))

    seen = set()
    for a in u.actions():
        for target in g.split_names(a["convertTo"]):
            if target in seen:
                continue
            seen.add(target)
            tu = units.get(target)
            name = tu.display if tu else target
            info = []
            p = parse_price(a["price"])
            if p > 0:
                info.append(f"＄{p}")
            if a["seconds"] is not None:
                info.append(fmt_seconds(a["seconds"]))
            lines.append(f"【升级】→ {name}" + (f"（{'，'.join(info)}）" if info else ""))

    death = []
    spawn_on_death = core.get("unitsSpawnedOnDeath", "").strip()
    if spawn_on_death and u.is_squad:
        lines.append("【包含】" + unit_list(spawn_on_death, units))
    elif spawn_on_death and unit_list(spawn_on_death, units):
        death.append("生成 " + unit_list(spawn_on_death, units))
    if g.is_true(core.get("nukeOnDeath", "")):
        death.append("发生爆炸")
    if death:
        lines.append("【死亡】" + "，".join(death))
    return lines


def compose(old_desc, new_auto):
    parts = old_desc.split("\\n")
    author = [p for p in parts if p.strip().startswith("原作者")]
    flavor = [p for p in parts
              if p.strip() and not p.strip().startswith(AUTO_PREFIX) and not p.strip().startswith("原作者")
              and not OLD_CREDIT_LINE.match(p.strip())]
    return "\\n".join(flavor + new_auto + author[-1:])


# ---------------------------------------------------------------- 写回

KEY_RE = r"^(\s*{key}\s*:)(.*?)(\r?)$"


def rewrite_file(path, edits, check):
    """edits: [(正则, 替换函数)]；保持编码、BOM 与换行风格不变。"""
    raw = path.read_bytes()
    bom = raw.startswith(b"\xef\xbb\xbf")
    text = raw.decode("utf-8-sig")
    new = text
    for pattern, fn in edits:
        new = re.sub(pattern, fn, new, count=1, flags=re.M)
    if new != text and not check:
        path.write_bytes((b"\xef\xbb\xbf" if bom else b"") + new.encode("utf-8"))
    return new != text


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="只打印结果，不写文件")
    ap.add_argument("--show", help="打印指定单位的新描述")
    args = ap.parse_args()

    units = load_units()
    times = build_times(units)
    scope = {u["name"]: u for u in g.classify([g.extract_unit(p, {}) for p in sorted(MOD_DIR.rglob("*.ini"))])}

    changed = 0
    for u in units.values():
        info = scope.get(u.name)
        if u.name in SANDBOX or not info or info["scope"] not in ("player", "form") or info["faction"] == "系统":
            continue
        edits = []

        def new_desc(m, u=u):
            return m.group(1) + " " + compose(m.group(2).strip(), auto_lines(u, units, times)) + m.group(3)
        edits.append((KEY_RE.format(key="displayDescription"), new_desc))

        # 动作按钮：描述里补「【耗时】X 秒」
        for a in u.actions():
            if a["seconds"] is None or a["seconds"] < 0.05:
                continue
            line = f"【耗时】{fmt_seconds(a['seconds'])}"
            if a["style"] == "core":
                key, text_key = a["id"] + "_description", a["id"] + "_text"
                if key in u.core:
                    edits.append((KEY_RE.format(key=re.escape(key)),
                                  lambda m, line=line: m.group(1) + " " + merge_action_desc(m.group(2), line) + m.group(3)))
                else:
                    edits.append((KEY_RE.format(key=re.escape(text_key)),
                                  lambda m, key=key, line=line: m.group(0) + "\n" + key + ": " + line + m.group(3)
                                  if not m.group(3) else m.group(1) + m.group(2) + "\r\n" + key + ": " + line + "\r"))
            else:
                sec_body = rf"(^\[{re.escape(a['id'])}\]\r?\n(?:(?!\[).*\r?\n?)*?)"
                if "description" in u.sec.get(a["id"], {}):
                    edits.append((sec_body + r"(\s*description\s*:)(.*?)(\r?)$",
                                  lambda m, line=line: m.group(1) + m.group(2) + " " + merge_action_desc(m.group(3), line) + m.group(4)))
                else:
                    edits.append((rf"^(\[{re.escape(a['id'])}\])(\r?)$",
                                  lambda m, line=line: m.group(1) + m.group(2) + "\n" + "description: " + line + m.group(2)))

        if args.show and u.name == args.show:
            print(compose(u.core.get("displayDescription", ""), auto_lines(u, units, times)).replace("\\n", "\n"))
        if rewrite_file(u.path, edits, args.check or bool(args.show)):
            changed += 1
    print(f"{'需要更新' if args.check else '已更新'} {changed} 个文件")


def merge_action_desc(old, line):
    old = OLD_TIME_PHRASE.sub("", old.strip())
    parts = [p for p in old.split("\\n") if p.strip() and not p.strip().startswith(AUTO_PREFIX)]
    return "\\n".join(parts + [line])


if __name__ == "__main__":
    main()
