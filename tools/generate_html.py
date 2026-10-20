# -*- coding: utf-8 -*-
"""
生化狂潮：瘟疫王朝 单位图鉴生成器

扫描 mod/ 下全部 .ini，按"玩家能否在游戏里见到"分类后生成自包含的 units.html。

分类规则（从开局单位出发追踪单位之间的引用关系）：
  玩家单位  从开局的「选择阵营」出发，经 canBuild / builtFrom / convertTo 能到达的单位，
            以及战斗中由 spawnUnits / unitsSpawnedOnDeath 衍生出来、可以选中的单位
  形态      某个单位的瘫痪 / 降落 / 遁形 / 狂暴等变形，合并到本体的详情里展示
  辅助      特效、标记、残骸等：不可选中（isUnselectable）且不能建造，或在 HELPER_NAMES 中
  未接入    没有被任何单位引用，游戏中无法通过建造或转化获得（只能由地图或编辑器放置）

用法（在项目根目录运行）：
    python tools/generate_html.py
"""

import base64
import io
import json
import re
import time
from collections import defaultdict
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
MOD_DIR = ROOT / "mod"
TOOLS_DIR = ROOT / "tools"
OUT_FILE = ROOT / "units.html"
VERSION = "v1.0"

# overrideAndReplace 之后，地图开局会生成这两个原版单位的替代品
START_UNITS = ("commandCenter", "builder")

# 可以选中、但只是特效 / 残骸 / 弹体 / 开局选择器的单位
HELPER_NAMES = {"choose", "尸块", "尸块2", "bleed", "手臂", "孵化者炮弹", "爬行者3"}

# 模组引用的游戏原生建筑/单位（不单独作为模组卡片列出，但在建造关系中予以识别与展示）
KNOWN_VANILLA = {
    "bugNest": {"displayName": "虫巢 (原版)", "tier": 3, "isBuilding": True},
    "repairbay": {"displayName": "维修站 (原版)", "tier": 2, "isBuilding": True},
}

FACTIONS = {"人类": "人类", "僵尸": "僵尸", "阵营选择": "系统"}


def parse_ini(path):
    """解析 ini 为 {section: {key: value}}；同一段内重复的键以后出现的为准。"""
    sections = {}
    cur = None
    for line in path.read_text(encoding="utf-8-sig", errors="replace").splitlines():
        s = line.strip()
        if not s or s.startswith(("#", "//")):
            continue
        if s.startswith("[") and s.endswith("]"):
            cur = s[1:-1].strip()
            sections.setdefault(cur, {})
        elif cur and ":" in s:
            k, v = s.split(":", 1)
            sections[cur][k.strip()] = v.split("#")[0].strip()
    return sections


def load_unit_sections(path):
    """读取单位 ini；[core] 里的 copyFrom 指向另一个 ini 时，先继承它的内容。"""
    sections = parse_ini(path)
    base_name = sections.get("core", {}).get("copyFrom", "")
    if base_name.lower().endswith(".ini"):
        base_path = path.parent / base_name
        if base_path.is_file():
            merged = {sec: dict(kv) for sec, kv in parse_ini(base_path).items()}
            for sec, kv in sections.items():
                merged.setdefault(sec, {}).update(kv)
            return merged
    return sections


def split_names(value):
    """把 "a, b*3, setRally" 这样的列表拆成单位名（去掉数量和非单位指令）。"""
    out = []
    for item in value.split(","):
        name = item.strip().split("*")[0].strip()
        if name and name not in ("setRally", "reclaim", "none", "NONE"):
            out.append(name)
    return out


def lock_requirement(cond):
    """从 "if not numberOfUnitsInTeam(withTag='血肉祭坛', greaterThan=0)" 中取出需要的 tag。"""
    m = re.fullmatch(r"if\s+not\s+numberOfUnitsInTeam\(\s*withTag\s*=\s*'([^']+)'\s*,\s*greaterThan\s*=\s*0\s*\)", cond.strip())
    return m.group(1) if m else ""


def action_seconds(speed):
    """动作的 buildSpeed 换算成秒：写成 "30s" 的直接取值，写成小数的是每帧进度。"""
    speed = speed.strip()
    if not speed:
        return None
    if speed.endswith("s"):
        return to_float(speed[:-1]) or 0
    v = to_float(speed)
    return round(1.0 / (v * 60.0), 1) if v > 0 else None


def to_float(v, default=0.0):
    m = re.search(r"[-+]?\d*\.?\d+", str(v))
    return float(m.group(0)) if m else default


def to_int(v, default=0):
    m = re.search(r"[-+]?\d+", str(v))
    return int(m.group(0)) if m else default


def is_true(v):
    return str(v).strip().lower() == "true"


# ---------------------------------------------------------------- 贴图

def image_data(ini_path, image_name, total_frames, cache):
    """返回 (base64, 相对路径)；多帧贴图只取第一帧。"""
    if not image_name or image_name.upper() == "NONE" or image_name.upper().startswith(("SHARED:", "ROOT:")):
        return "", ""
    candidates = [ini_path.parent / image_name, MOD_DIR / image_name, ini_path.parent.parent / image_name]
    actual = next((p for p in candidates if p.is_file()), None)
    if actual is None:
        return "", image_name
    rel = actual.relative_to(ROOT).as_posix()
    key = (actual, total_frames)
    if key not in cache:
        try:
            with Image.open(actual) as im:
                w, h = im.size
                if total_frames > 1 and w > h:
                    frame = im.crop((0, 0, w // total_frames, h))
                elif total_frames > 1 and h > w:
                    frame = im.crop((0, 0, w, h // total_frames))
                else:
                    frame = im
                buf = io.BytesIO()
                frame.save(buf, format="PNG", optimize=True)
            cache[key] = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")
        except Exception as e:
            print(f"读取贴图失败 {actual}: {e}")
            cache[key] = ""
    return cache[key], rel


# ---------------------------------------------------------------- 单个单位

def unit_type_of(core, movement_type, is_building):
    if is_building:
        return "建筑"
    if movement_type == "AIR":
        return "空中"
    if movement_type in ("OVER_CLIFF", "OVER_CLIFF_WATER", "HOVER"):
        return "越崖 / 两栖"
    return "地面 · 生物" if is_true(core.get("isBio", "")) else "地面 · 机械"


def extract_unit(path, img_cache):
    sections = load_unit_sections(path)
    core = sections.get("core", {})
    graphics = sections.get("graphics", {})
    attack = sections.get("attack", {})
    movement = sections.get("movement", {})

    rel_parts = path.relative_to(MOD_DIR).parts
    name = core.get("name", "") or path.stem
    display_name = core.get("displayText_zh", "") or core.get("displayText", "") or name
    desc = (core.get("displayDescription_zh", "") or core.get("displayDescription", "")).replace("\\n", "\n").strip()

    movement_type = movement.get("movementType", "LAND").upper()
    is_building = is_true(core.get("isBuilding", "")) or movement_type == "BUILDING"

    total_frames = max(to_int(graphics.get("total_frames", 1), 1), 1)
    img_b64, img_rel = image_data(path, graphics.get("image", "").strip(), total_frames, img_cache)
    turret_b64, _ = image_data(path, graphics.get("image_turret", "").strip(), 1, img_cache)
    wreak_b64, _ = image_data(path, graphics.get("image_wreak", "").strip(), 1, img_cache)

    price = to_int(core.get("price", 0))
    max_hp = to_int(core.get("maxHp", 0))
    max_shield = to_int(core.get("maxShield", 0))
    self_regen = to_float(core.get("selfRegenRate", 0))
    build_speed = to_float(core.get("buildSpeed", 0))
    build_time = round(1.0 / (build_speed * 60.0), 1) if build_speed > 0 else 0
    credits_gen = to_int(core.get("generation_credits", 0))
    max_transport = to_int(core.get("maxTransportingUnits", 0))
    nuke_on_death = is_true(core.get("nukeOnDeath", ""))
    spawn_on_death = core.get("unitsSpawnedOnDeath", "").strip()
    tech_level = max(to_int(core.get("techLevel", 1)), 1)

    can_attack = attack.get("canAttack", "true").lower() == "true"
    can_attack_air = is_true(attack.get("canAttackFlyingUnits", ""))
    is_melee = is_true(attack.get("isMelee", ""))
    max_range = to_int(attack.get("maxAttackRange", 0))
    shoot_delay = to_float(attack.get("shootDelay", 0))
    fire_rate = round(60.0 / shoot_delay, 2) if shoot_delay > 0 else 0

    direct_dmg = area_dmg = area_radius = 0
    for sec, kv in sections.items():
        if sec.startswith("projectile_"):
            direct_dmg = max(direct_dmg, to_int(kv.get("directDamage", 0)))
            area_dmg = max(area_dmg, to_int(kv.get("areaDamage", 0)))
            area_radius = max(area_radius, to_int(kv.get("areaRadius", 0)))
    single_damage = direct_dmg + area_dmg
    dps = round(single_damage * fire_rate, 1) if single_damage and fire_rate else 0

    # 引用关系：canBuild / builtFrom / convertTo / spawnUnits / unitsSpawnedOnDeath
    can_build, built_from, convert_to, spawns, actions = [], [], [], [], []
    for k, v in core.items():
        if re.fullmatch(r"canBuild_\w+_name", k):
            can_build += split_names(v)
        elif re.fullmatch(r"builtFrom_\w+_name", k):
            built_from += split_names(v)
    for sec, kv in sections.items():
        for k, v in kv.items():
            if re.fullmatch(r"(action_\w+_)?convertTo", k):
                convert_to += split_names(v)
            elif re.fullmatch(r"(action_\w+_)?spawnUnits?", k):
                spawns += split_names(v)
        if sec.startswith("action_") and kv.get("isVisible", "").lower() != "false":
            text = kv.get("text_zh", "") or kv.get("text", "")
            if text:
                detail = kv.get("description_zh", "") or kv.get("description", "")
                actions.append(text + (f"（{detail}）" if detail else ""))
    for k, v in core.items():
        m = re.fullmatch(r"action_(\w+)_text", k)
        if m:
            actions.append(v)

    # 升级 / 转换动作的花费与耗时：{目标单位: {"price": 文本, "time": 秒}}
    convert_info = {}
    action_defs = [(core.get(m.group(1) + "_convertTo", ""), core.get(m.group(1) + "_price", ""),
                    core.get(m.group(1) + "_buildSpeed", ""))
                   for k in core if (m := re.fullmatch(r"(action_\w+)_convertTo", k))]
    action_defs += [(kv.get("convertTo", ""), kv.get("price", ""), kv.get("buildSpeed", ""))
                    for sec, kv in sections.items() if sec.startswith("action_") and kv.get("convertTo")]
    for target, action_price, action_speed in action_defs:
        for t in split_names(target):
            convert_info[t] = {"price": action_price.strip(), "time": action_seconds(action_speed)}

    # 带解锁条件的建造 / 转换：{目标单位: 需要场上已有的单位 tag}
    gated = {}
    for k, v in core.items():
        m = re.fullmatch(r"(canBuild_\w+|action_\w+)_(name|convertTo)", k)
        req = lock_requirement(core.get(m.group(1) + "_isLocked", "")) if m else ""
        for t in split_names(v) if req else ():
            gated[t] = req
    for sec, kv in sections.items():
        req = lock_requirement(kv.get("isLocked", "")) if sec.startswith("action_") else ""
        for t in split_names(kv.get("convertTo", "")) + split_names(kv.get("spawnUnits", "")) if req else ():
            gated[t] = req

    traits = []
    if max_shield > 0:
        traits.append({"label": f"护盾 {max_shield}", "type": "shield"})
    if self_regen > 0:
        traits.append({"label": f"自愈 {self_regen}", "type": "regen"})
    if spawn_on_death:
        traits.append({"label": "死亡生成单位", "type": "infection"})
    if nuke_on_death:
        traits.append({"label": "死亡爆炸", "type": "nuke"})
    if credits_gen:
        traits.append({"label": f"产资 {credits_gen:+d}", "type": "credits"})
    if max_transport > 0:
        traits.append({"label": f"运载 {max_transport}", "type": "transport"})
    if can_attack and can_attack_air:
        traits.append({"label": "可对空", "type": "air"})
    if area_dmg > 0:
        traits.append({"label": f"溅射 R{area_radius}", "type": "area"})
    if can_attack and is_melee:
        traits.append({"label": "近战", "type": "melee"})

    return {
        "name": name,
        "displayName": display_name,
        "filename": path.name,
        "filePath": path.relative_to(ROOT).as_posix(),
        "faction": FACTIONS.get(rel_parts[0], "系统"),
        "subCategory": rel_parts[1] if len(rel_parts) > 2 else rel_parts[0],
        "unitType": unit_type_of(core, movement_type, is_building),
        "isBuilding": is_building,
        "techLevel": tech_level,
        "description": desc,
        "tags": core.get("tags", ""),
        "_gated": gated,
        "_unselectable": is_true(core.get("isUnselectable", "")),
        "_replaces": core.get("overrideAndReplace", "").strip(),
        "image": {"base64": img_b64, "relPath": img_rel, "turretBase64": turret_b64, "wreakBase64": wreak_b64},
        "stats": {
            "hp": max_hp, "shield": max_shield, "selfRegen": self_regen, "price": price,
            "buildTime": build_time, "mass": to_int(core.get("mass", 0)), "radius": to_int(core.get("radius", 0)),
            "creditsGen": credits_gen, "transport": max_transport,
        },
        "combat": {
            "canAttack": can_attack, "canAttackAir": can_attack_air, "isMelee": is_melee, "range": max_range,
            "shootDelay": shoot_delay, "fireRate": fire_rate, "singleDamage": single_damage, "dps": dps,
            "areaRadius": area_radius,
        },
        "movement": {"type": movement_type, "speed": to_float(movement.get("moveSpeed", 0))},
        "relations": {
            "canBuild": can_build, "builtFrom": built_from, "convertTo": convert_to, "spawns": spawns,
            "spawnOnDeath": spawn_on_death, "actions": list(dict.fromkeys(actions)),
            "convertInfo": convert_info,
        },
        "traits": traits,
    }


# ---------------------------------------------------------------- 分类

def classify(units):
    """给每个单位标上 scope（player / form / helper / unused）和获得方式。"""
    by_name = {u["name"]: u for u in units}
    replaced = {u["_replaces"]: u["name"] for u in units if u["_replaces"]}
    resolve = lambda n: replaced.get(n, n)

    build, convert, spawn = defaultdict(set), defaultdict(set), defaultdict(set)
    for u in units:
        n = u["name"]
        rel = u["relations"]
        for t in rel["canBuild"]:
            build[n].add(resolve(t))
        for src in rel["builtFrom"]:
            build[resolve(src)].add(n)
        for t in rel["convertTo"]:
            convert[n].add(resolve(t))
        for t in rel["spawns"] + split_names(rel["spawnOnDeath"]):
            spawn[n].add(resolve(t))

    def reach(seeds, edge_sets):
        seen, queue = set(seeds), list(seeds)
        while queue:
            cur = queue.pop()
            for edges in edge_sets:
                for nxt in edges.get(cur, ()):
                    if nxt in by_name and nxt not in seen:
                        seen.add(nxt)
                        queue.append(nxt)
        return seen

    starts = [replaced[s] for s in START_UNITS if s in replaced]
    buildable = reach(starts, [build, convert])
    reachable = reach(buildable, [build, convert, spawn])

    built_by = defaultdict(set)
    for src, targets in build.items():
        for t in targets:
            built_by[t].add(src)

    # 形态：与本体互相转换（瘫痪、降落、遁形、阵地等），或由本体转换得到且显示名相同。
    # 换武器这类单向转换、且本身能被建造的单位仍算独立单位。
    form_of = {}
    for u in units:
        n = u["name"]
        for src, targets in convert.items():
            if n not in targets or src == n or src not in by_name:
                continue
            two_way = src in convert.get(n, ())
            same_display = by_name[src]["displayName"] == u["displayName"] and not built_by.get(n)
            if (two_way or same_display) and not built_by.get(n):
                form_of[n] = form_of.get(n) or src
    # 两个单位互为形态时，能被建造的（或名字更短的）作为本体
    for n, src in list(form_of.items()):
        if form_of.get(src) == n:
            if bool(built_by.get(n)) != bool(built_by.get(src)):
                base = n if built_by.get(n) else src
            else:
                base = n if len(n) < len(src) else src
            form_of.pop(base, None)

    spawned_by = defaultdict(list)
    for src, targets in spawn.items():
        for t in targets:
            spawned_by[t].append(src)

    gates = {(u["name"], resolve(t)): req for u in units for t, req in u["_gated"].items()}
    tiers, gate_units = compute_tiers(units, starts, [build, convert, spawn], gates)

    for u in units:
        n = u["name"]
        if n not in reachable:
            scope, obtain = "unused", "未接入"
        elif n in HELPER_NAMES or (u["_unselectable"] and not built_by.get(n)):
            scope, obtain = "helper", "辅助"
        elif n in form_of:
            scope, obtain = "form", "形态"
        elif built_by.get(n):
            scope, obtain = "player", "可建造"
        elif n in buildable:
            scope, obtain = "player", "转换获得"
        else:
            scope, obtain = "player", "战斗衍生"
        u["scope"], u["obtain"] = scope, obtain
        u["formOf"] = form_of.get(n, "")
        u["forms"] = sorted(f for f, b in form_of.items() if b == n)
        u["relations"]["builtFrom"] = sorted(built_by.get(n, set()))
        u["relations"]["canBuild"] = sorted(t for t in build.get(n, set()) if t in by_name or t in KNOWN_VANILLA)
        u["relations"]["convertTo"] = sorted(t for t in convert.get(n, set()) if t in by_name)
        u["relations"]["spawnedBy"] = sorted(set(spawned_by.get(n, [])))
        u["relations"]["spawns"] = sorted(t for t in spawn.get(n, set()) if t in by_name)
        u["tier"] = tiers.get(n, 0) if scope != "unused" else 0
        # 只有真正的科技门槛才写进"解锁"：tags 标了 T2/T3 的基地或卵，以及被解锁条件引用的建筑
        marker = tag_tier(u)
        if marker and marker > 1:
            u["unlocksTier"] = marker
        elif n in gate_units and n in tiers:
            u["unlocksTier"] = tiers[n] + 1
        else:
            u["unlocksTier"] = 0
        u["_builds_buildings"] = any(
            by_name[t]["isBuilding"] if t in by_name else KNOWN_VANILLA[t].get("isBuilding", False)
            for t in u["relations"]["canBuild"]
        )
        u["category"], u["role"] = category_of(u)
        if u["_replaces"] and u["_replaces"] not in START_UNITS:
            u["traits"].append({"label": f"替换 {u['_replaces']}", "type": "replace"})
        del u["_unselectable"], u["_replaces"], u["_gated"], u["_builds_buildings"]
    return units


def tag_tier(u):
    """tags 里带 T2 / 红卵T2 这类后缀的单位是科技门槛（人类阵营T2、红巨卵），返回它代表的等级。"""
    levels = [int(m.group(1)) for t in u["tags"].split(",") if (m := re.search(r"T(\d)$", t.strip()))]
    return max(levels) if levels else None


def tier_marker(u):
    """单位至少处于的科技等级：tags 门槛，或 ini 里明确写的 techLevel >= 2。

    名字后缀（熔炉T2~T4、补给站T2~T4）只是建筑升级等级，不代表科技阶段，不计入。
    """
    levels = [lv for lv in (tag_tier(u), u.get("techLevel", 1)) if lv and lv >= 2]
    return max(levels) if levels else None


def compute_tiers(units, starts, edge_sets, gates):
    """推算每个单位最早在第几本科技能拿到。

    - 开局单位为 T1；建造 / 转换 / 生成出来的单位继承来源的等级
    - tags 带 Tn 的单位（人类阵营T2、红巨卵 = 红卵T2）至少是 Tn
    - 有解锁条件的建造项（"需要建造血肉祭坛"）：条件建筑没有 Tn 标记时，等级 = 条件建筑等级 + 1，
      而这个条件建筑自己生产的单位也同样算高一级（血肉祭坛在 T1 就能造，它解锁的是 T2）
    - 多条路线取最低等级
    """
    by_name = {u["name"]: u for u in units}
    by_tag = defaultdict(list)
    for u in units:
        for t in u["tags"].split(","):
            if t.strip():
                by_tag[t.strip()].append(u["name"])
    markers = {n: tier_marker(u) for n, u in by_name.items()}
    gate_units = {n for req in gates.values() for n in by_tag.get(req, [])}

    tiers = {s: 1 for s in starts}

    def output_tier(src):
        bump = src in gate_units and markers[src] is None
        return tiers[src] + (1 if bump else 0)

    changed = True
    while changed:
        changed = False
        for edges in edge_sets:
            for src, targets in edges.items():
                if src not in tiers:
                    continue
                for dst in targets:
                    if dst not in by_name:
                        continue
                    cand = output_tier(src)
                    req = gates.get((src, dst))
                    if req:
                        req_tiers = [output_tier(r) for r in by_tag.get(req, []) if r in tiers]
                        if not req_tiers:
                            continue
                        cand = max(cand, min(req_tiers))
                    if markers[dst]:
                        cand = max(cand, markers[dst])
                    if cand < tiers.get(dst, 99):
                        tiers[dst] = cand
                        changed = True
    return tiers, gate_units


def category_of(u):
    """返回 (大类, 补充说明)：建筑 / 防御 / 单位 / 其他。"""
    if u["isBuilding"]:
        if "围墙" in u["name"]:
            return "防御", "围墙"
        if u["combat"]["canAttack"] and not u["relations"]["canBuild"]:
            return "防御", "炮台 / 工事"
        return "建筑", ""
    if u["name"] == "地雷":
        return "防御", "地雷"
    if u["subCategory"] in ("小队", "尸群"):
        return "其他", "编队（死亡后展开成多个单位）"
    if u["_builds_buildings"]:
        return "其他", "建造者"
    return "单位", ""


def count(units, **cond):
    return sum(1 for u in units if all(u[k] == v for k, v in cond.items()))


# ---------------------------------------------------------------- 输出

def render_html(units, css, js):
    player = [u for u in units if u["scope"] == "player"]
    n_player = len(player)
    n_human = count(player, faction="人类")
    n_zombie = count(player, faction="僵尸")
    n_form, n_unused, n_helper = (count(units, scope=s) for s in ("form", "unused", "helper"))
    data_json = json.dumps(units, ensure_ascii=False).replace("</", "<\\/")

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>生化狂潮：瘟疫王朝 {VERSION} 单位图鉴</title>
  <style>
{css}
  </style>
</head>
<body>

  <header>
    <div class="header-inner">
      <div class="brand-wrap">
        <div class="brand-icon">☣️</div>
        <div class="brand-text">
          <h1>生化狂潮：瘟疫王朝 <span class="badge-ver">{VERSION}</span></h1>
          <p>单位图鉴 · 玩家可见单位 {n_player} 个（另有形态 {n_form}、未接入 {n_unused}、辅助 {n_helper}）</p>
        </div>
      </div>
      <div class="header-actions">
        <button class="btn-action" id="btn-export-csv">📥 导出 CSV</button>
        <button class="btn-action" id="btn-export-json">💾 导出 JSON</button>
      </div>
    </div>
  </header>

  <div class="container">
    <nav class="faction-switch">
      <button class="faction-big human active" data-faction="人类">🛡️ 人类阵营 <span>{n_human}</span></button>
      <button class="faction-big zombie" data-faction="僵尸">☣️ 僵尸阵营 <span>{n_zombie}</span></button>
      <button class="faction-big system" data-faction="系统" hidden>⚙️ 系统</button>
    </nav>

    <section class="roadmap" id="roadmap"></section>

    <div class="control-panel">
      <div class="category-row">
        <div class="seg" id="category-tabs">
          <button class="seg-btn active" data-category="all">全部</button>
          <button class="seg-btn" data-category="建筑">🏛️ 建筑</button>
          <button class="seg-btn" data-category="防御">🧱 防御</button>
          <button class="seg-btn" data-category="单位">⚔️ 单位</button>
          <button class="seg-btn" data-category="其他">🧩 其他</button>
        </div>
        <div class="seg" id="tier-tabs">
          <button class="seg-btn active" data-tier="all">全部等级</button>
          <button class="seg-btn tier-1" data-tier="1">T1</button>
          <button class="seg-btn tier-2" data-tier="2">T2</button>
          <button class="seg-btn tier-3" data-tier="3">T3</button>
        </div>
      </div>

      <div class="search-row">
        <div class="search-box">
          <span class="search-icon">🔍</span>
          <input type="text" id="search-input" placeholder="搜索名称、单位代码（如 tanke、zb5）、描述、文件名…" autocomplete="off">
          <button class="clear-search" id="clear-search">✕</button>
        </div>
      </div>

      <div class="filter-row">
        <div class="filter-selects">
          <div class="select-wrap">
            <label>收录范围</label>
            <select id="filter-scope">
              <option value="player">玩家可见单位（{n_player}）</option>
              <option value="form">形态变体（{n_form}）</option>
              <option value="unused">未接入（{n_unused}）</option>
              <option value="helper">辅助 / 特效（{n_helper}）</option>
              <option value="all">全部 ini（{len(units)}）</option>
            </select>
          </div>

          <div class="select-wrap">
            <label>作战属性</label>
            <select id="filter-combat">
              <option value="all">全部</option>
              <option value="attacker">可攻击</option>
              <option value="melee">近战</option>
              <option value="ranged">远程</option>
              <option value="air_atk">可对空</option>
              <option value="air_unit">空中单位</option>
            </select>
          </div>

          <div class="select-wrap">
            <label>特殊机制</label>
            <select id="filter-trait">
              <option value="all">全部机制</option>
              <option value="infection">死亡生成单位</option>
              <option value="shield">护盾</option>
              <option value="regen">自愈</option>
              <option value="credits">产出资源</option>
              <option value="transport">运载</option>
              <option value="nuke">死亡爆炸</option>
            </select>
          </div>

          <div class="select-wrap">
            <label>排序方式</label>
            <select id="sort-select">
              <option value="default">按等级分组</option>
              <option value="hp_desc">生命值 高 → 低</option>
              <option value="price_desc">造价 高 → 低</option>
              <option value="price_asc">造价 低 → 高</option>
              <option value="dmg_desc">单发伤害 高 → 低</option>
              <option value="dps_desc">估算 DPS 高 → 低</option>
              <option value="range_desc">射程 远 → 近</option>
              <option value="speed_desc">移速 快 → 慢</option>
            </select>
          </div>
        </div>

        <div class="view-toggles">
          <button class="view-btn active" data-view="card">🗂️ 卡片</button>
          <button class="view-btn" data-view="table">📊 表格</button>
          <button class="view-btn" data-view="compact">📑 紧凑</button>
        </div>
      </div>
    </div>

    <div class="status-bar">
      <div class="status-count">
        当前显示 <strong id="filter-count">0</strong> / <span id="scope-total">0</span> 个
      </div>
      <button class="btn-reset-filter" id="btn-reset-filter">↺ 重置筛选</button>
    </div>

    <main id="units-container"></main>
  </div>

  <div class="modal-backdrop" id="unit-modal">
    <div class="modal-content">
      <div class="modal-header">
        <div class="modal-nav-btns">
          <button class="btn-nav-modal" id="modal-prev" title="快捷键: ←">‹</button>
          <button class="btn-nav-modal" id="modal-next" title="快捷键: →">›</button>
        </div>
        <button class="modal-close" id="modal-close" title="快捷键: Esc">✕</button>
      </div>
      <div class="modal-body" id="modal-body"></div>
      <div class="modal-footer">
        <div class="filepath-box" id="modal-filepath">mod/...</div>
        <div style="display:flex;gap:8px;">
          <button class="copy-btn" id="btn-copy-id">📋 复制单位代码</button>
          <button class="copy-btn" id="btn-copy-path">📂 复制文件路径</button>
        </div>
      </div>
    </div>
  </div>

  <div class="toast" id="toast">已复制到剪贴板</div>

  <script id="mod-units-data" type="application/json">
{data_json}
  </script>

  <script>
{js}
  </script>
</body>
</html>
"""


def main():
    t0 = time.time()
    ini_files = sorted(MOD_DIR.rglob("*.ini"))
    print(f"扫描到 {len(ini_files)} 个 ini，开始解析…")
    img_cache = {}
    units = classify([extract_unit(p, img_cache) for p in ini_files])

    for scope, label in (("player", "玩家可见"), ("form", "形态"), ("helper", "辅助"), ("unused", "未接入")):
        print(f"  {label}: {count(units, scope=scope)}")

    css = (TOOLS_DIR / "style.css").read_text(encoding="utf-8")
    js = (TOOLS_DIR / "app.js").read_text(encoding="utf-8")
    OUT_FILE.write_text(render_html(units, css, js), encoding="utf-8")
    size_mb = OUT_FILE.stat().st_size / 1024 / 1024
    print(f"已生成 {OUT_FILE}（{size_mb:.2f} MB，用时 {time.time() - t0:.1f} 秒）")


if __name__ == "__main__":
    main()
