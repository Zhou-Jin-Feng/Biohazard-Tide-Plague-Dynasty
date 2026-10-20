// 生化狂潮：瘟疫王朝 图鉴交互逻辑
const ALL_UNITS = JSON.parse(document.getElementById("mod-units-data").textContent);
const nameMap = {};
ALL_UNITS.forEach((u, i) => { nameMap[u.name] = i; });

const CATEGORIES = ["建筑", "防御", "单位", "其他"];
const CATEGORY_ICON = { "建筑": "🏛️", "防御": "🧱", "单位": "⚔️", "其他": "🧩" };
const SCOPE_BADGE = { form: "形态", unused: "未接入", helper: "辅助" };
const OBTAIN_BADGE = { "转换获得": "转换", "战斗衍生": "衍生" };

let currentFiltered = [];
let currentModalIndex = -1;
let currentZoom = 1;

const DEFAULT_STATE = {
  faction: "人类",
  scope: "player",
  category: "all",
  tier: "all",
  keyword: "",
  combatRole: "all",
  specialTrait: "all",
  sortBy: "default",
  viewMode: "card",
  onlyNew: false
};
const state = { ...DEFAULT_STATE };

function init() {
  setupEvents();
  setupTreeEvents();
  refresh();
}

function refresh() {
  syncControls();
  renderRoadmap();
  applyFilter();
}

// ---------------------------------------------------------------- 事件

function setupEvents() {
  const searchInput = document.getElementById("search-input");
  let debounceTimer;
  searchInput.addEventListener("input", (e) => {
    clearTimeout(debounceTimer);
    debounceTimer = setTimeout(() => {
      state.keyword = e.target.value.trim().toLowerCase();
      document.getElementById("clear-search").classList.toggle("show", state.keyword.length > 0);
      applyFilter();
    }, 180);
  });
  document.getElementById("clear-search").addEventListener("click", () => {
    state.keyword = "";
    refresh();
  });

  document.querySelectorAll(".faction-big").forEach(btn => {
    btn.addEventListener("click", () => {
      state.faction = btn.dataset.faction;
      refresh();
    });
  });
  document.querySelectorAll("#category-tabs .seg-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      state.category = btn.dataset.category;
      refresh();
    });
  });
  document.querySelectorAll("#tier-tabs .seg-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      state.tier = btn.dataset.tier;
      refresh();
    });
  });

  const selects = { "filter-scope": "scope", "filter-combat": "combatRole", "filter-trait": "specialTrait", "sort-select": "sortBy" };
  Object.entries(selects).forEach(([id, key]) => {
    document.getElementById(id).addEventListener("change", (e) => {
      state[key] = e.target.value;
      refresh();
    });
  });

  document.querySelectorAll(".view-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      state.viewMode = btn.dataset.view;
      syncControls();
      renderUnits();
    });
  });

  document.getElementById("btn-reset-filter").addEventListener("click", () => {
    Object.assign(state, DEFAULT_STATE, { faction: state.faction, viewMode: state.viewMode });
    refresh();
  });

  // 发育总览、卡片列表、详情里的单位都通过 data-jump 打开
  document.body.addEventListener("click", (e) => {
    const jump = e.target.closest("[data-jump]");
    if (jump) jumpToUnit(jump.dataset.jump);
  });
  document.body.addEventListener("keydown", (e) => {
    const jump = e.target.closest && e.target.closest("[data-jump]");
    if (jump && (e.key === "Enter" || e.key === " ")) {
      e.preventDefault();
      jumpToUnit(jump.dataset.jump);
    }
  });

  document.getElementById("modal-close").addEventListener("click", closeModal);
  document.getElementById("unit-modal").addEventListener("click", (e) => {
    if (e.target.id === "unit-modal") closeModal();
  });
  document.getElementById("modal-prev").addEventListener("click", () => navigateModal(-1));
  document.getElementById("modal-next").addEventListener("click", () => navigateModal(1));
  window.addEventListener("keydown", (e) => {
    if (!document.getElementById("unit-modal").classList.contains("show")) return;
    if (e.key === "Escape") closeModal();
    else if (e.key === "ArrowLeft") navigateModal(-1);
    else if (e.key === "ArrowRight") navigateModal(1);
  });

  document.getElementById("btn-copy-id").addEventListener("click", () => {
    const u = currentFiltered[currentModalIndex];
    if (u) copyToClipboard(u.name, "单位代码已复制");
  });
  document.getElementById("btn-copy-path").addEventListener("click", () => {
    const u = currentFiltered[currentModalIndex];
    if (u) copyToClipboard(u.filePath, "文件路径已复制");
  });
  document.getElementById("btn-export-json").addEventListener("click", exportJSON);
  document.getElementById("btn-export-csv").addEventListener("click", exportCSV);
}

function syncControls() {
  const needSystem = state.scope !== "player" || state.faction === "系统";
  document.querySelector('.faction-big[data-faction="系统"]').hidden = !needSystem;
  if (!needSystem && state.faction === "系统") state.faction = "人类";

  document.querySelectorAll(".faction-big").forEach(b => b.classList.toggle("active", b.dataset.faction === state.faction));
  document.querySelectorAll("#category-tabs .seg-btn").forEach(b => b.classList.toggle("active", b.dataset.category === state.category));
  document.querySelectorAll("#tier-tabs .seg-btn").forEach(b => b.classList.toggle("active", b.dataset.tier === state.tier));
  document.querySelectorAll(".view-btn").forEach(b => b.classList.toggle("active", b.dataset.view === state.viewMode));
  document.getElementById("search-input").value = state.keyword;
  document.getElementById("clear-search").classList.toggle("show", state.keyword.length > 0);
  document.getElementById("filter-scope").value = state.scope;
  document.getElementById("filter-combat").value = state.combatRole;
  document.getElementById("filter-trait").value = state.specialTrait;
  document.getElementById("sort-select").value = state.sortBy;
}

// ---------------------------------------------------------------- 发育总览

function tierLabel(t) {
  return t > 0 ? `T${t}` : "—";
}

function tierGates(faction, tier) {
  return ALL_UNITS.filter(u => u.faction === faction && u.unlocksTier === tier && u.scope !== "unused");
}

// 科技树（参考 ATD 模组的科技树页）：左侧竖轨是各级总部和升级条件，右侧每一本一棵从总部出发的横向树。
// 每棵树列出这一本能拿到的全部内容：前一本已有的标"旧"，同一棵树里重复出现的标"见上"且不再展开。
const GROUP_ORDER = ["建造单位", "建筑", "防御", "部队", "编队", "升级", "生成"];

function startUnitOf(faction) {
  const chooser = ALL_UNITS.find(u => u.name === "choose");
  const targets = chooser ? chooser.relations.convertTo : [];
  return ALL_UNITS.find(u => targets.includes(u.name) && u.faction === faction);
}

function edgesFrom(u) {
  const out = [];
  u.relations.canBuild.forEach(n => out.push([n, "build"]));
  u.relations.convertTo.forEach(n => out.push([n, "upgrade"]));
  u.relations.spawns.forEach(n => out.push([n, "spawn"]));
  return out.filter(([n]) => n !== u.name);
}

function groupOf(target, kind) {
  if (kind === "upgrade") return "升级";
  if (kind === "spawn") return "生成";
  if (!target) return "建筑";                       // 原版单位（bugNest、repairbay）都是建筑
  if (target.category === "其他") return target.role.startsWith("编队") ? "编队" : "建造单位";
  return target.category === "单位" ? "部队" : target.category;
}

function kindClass(target, kind) {
  if (kind === "upgrade") return "k-upgrade";
  if (!target) return "k-building";
  if (target.category === "建筑") return "k-building";
  if (target.category === "防御") return "k-defense";
  if (target.movement.type === "AIR") return "k-air";
  if (target.unitType === "地面 · 机械") return "k-vehicle";
  return "k-infantry";
}

function fmtTime(sec) {
  return sec ? `${sec >= 10 ? Math.round(sec) : sec}s` : "";
}

function costHtml(price, time) {
  const p = price !== "" && price !== undefined && price !== null && String(price) !== "0"
    ? `<i class="r credits">${escapeHtml(String(price))}</i>` : "";
  const t = time ? `<i class="tm">${fmtTime(time)}</i>` : "";
  return p || t ? `<span class="cs">${p}${t}</span>` : "";
}

// 每一本的总部：人类是 ahx → 人类阵营T2 → 人类阵营T3；僵尸没有总部升级，各本都从僵尸阵营出发
function tierHeads(faction, tiers) {
  const start = startUnitOf(faction);
  return tiers.map(t => {
    if (t === 1) return { tier: t, hq: start, gates: [] };
    const gates = ALL_UNITS.filter(u => u.faction === faction && u.unlocksTier === t && u.scope === "player");
    const own = gates.filter(g => g.tier === t && g.isBuilding);
    if (own.length === 1 && gates.length === 1) return { tier: t, hq: own[0], gates };
    return { tier: t, hq: start, gates, sharedHq: true };
  });
}

function renderTierTree(root, tier, pool, rendered) {
  const seen = new Set();
  const usable = n => { const t = ALL_UNITS[nameMap[n]]; return t && pool.has(n) && t.tier <= tier; };
  const depth = new Map([[root.name, 0]]);
  const queue = [root.name];
  while (queue.length) {
    const cur = queue.shift();
    edgesFrom(pool.get(cur)).forEach(([n]) => {
      if (usable(n) && !depth.has(n)) { depth.set(n, depth.get(cur) + 1); queue.push(n); }
    });
  }

  function card(u, kind, opts) {
    const target = u;
    const cls = kindClass(target, kind);
    const isNew = target && target.tier === tier && tier > 1;
    const isOld = target && target.tier < tier;
    const tags = [
      isNew ? `<b class="new">新</b>` : "",
      opts.ref ? `<b class="tag" title="在离总部更近的位置展开">另见</b>` : "",
      opts.vanilla ? `<b class="tag">原版</b>` : "",
      target && target.forms.length ? `<b class="tag">${target.forms.length} 种形态</b>` : ""
    ].join("");
    const name = target ? target.displayName : opts.vanilla;
    const img = target ? (target.image.base64 || target.image.relPath) : "";
    const price = target ? opts.price ?? target.stats.price : "";
    const time = target ? opts.time ?? target.stats.buildTime : 0;
    const toggle = opts.count ? `<button class="tg" type="button" aria-label="展开 ${opts.count} 项">${opts.count}<span></span></button>` : "";
    const jump = target ? ` data-jump="${escapeHtml(target.name)}"` : "";
    return {
      old: isOld,
      html: `<div class="node ${cls}" tabindex="0"${jump} title="${escapeHtml(target ? target.name : opts.vanilla)}">
        ${img ? `<span class="th" style="background-image:url('${img}')"></span>` : `<span class="th"></span>`}
        <span class="bd"><span class="nm">${escapeHtml(name)}${tags}</span>${costHtml(price, time)}</span>${toggle}
      </div>`
    };
  }

  // 子项按类别分组；升级显示升级动作本身的花费和耗时。
  // 返回 { html, count, hasNew }：count 为子项总数，hasNew 表示子树里有本级新增内容
  function expand(u, level = 0) {
    seen.add(u.name);
    const groups = new Map();
    edgesFrom(u).forEach(([n, kind]) => {
      const t = ALL_UNITS[nameMap[n]];
      if (t && (!pool.has(n) || t.tier > tier)) return;
      const g = groupOf(t, kind);
      if (!groups.has(g)) groups.set(g, []);
      groups.get(g).push([n, kind, t]);
      rendered.add(`${kind}|${n}|${u.name}`);
    });
    const order = [...groups.keys()].sort((a, b) => GROUP_ORDER.indexOf(a) - GROUP_ORDER.indexOf(b));
    let html = "", count = 0, hasNew = false;
    order.forEach(g => {
      const items = groups.get(g).sort((a, b) =>
        (a[2] ? a[2].stats.price : 0) - (b[2] ? b[2].stats.price : 0)
        || (a[2] ? a[2].displayName : a[0]).localeCompare(b[2] ? b[2].displayName : b[0], "zh"));
      let groupNew = false;
      const lis = items.map(([n, kind, t]) => {
        const info = kind === "upgrade" ? (u.relations.convertInfo || {})[n] : null;
        const extra = info ? { price: info.price, time: info.time } : {};
        if (!t) {
          groupNew = groupNew || (n === "bugNest" && tier === 3);
          return `<li>${card(null, kind, { vanilla: n }).html}</li>`;
        }
        const selfNew = t.tier === tier;
        if (seen.has(n) || depth.get(n) < level + 1) {
          groupNew = groupNew || selfNew;
          return `<li class="${selfNew ? "" : "old"}">${card(t, kind, { ref: true, ...extra }).html}</li>`;
        }
        const sub = expand(t, level + 1);
        const c = card(t, kind, { count: sub.count, ...extra });
        const keep = selfNew || sub.hasNew;
        groupNew = groupNew || keep;
        return `<li class="${keep ? "" : "old"}">${c.html}${sub.count ? `<ul>${sub.html}</ul>` : ""}</li>`;
      }).join("");
      hasNew = hasNew || groupNew;
      count += items.length;
      html += `<li class="${level === 0 ? "open " : ""}grp${groupNew ? "" : " old"}"><div class="gnode" tabindex="0">${g}<button class="tg" type="button" aria-label="展开 ${items.length} 项">${items.length}<span></span></button></div><ul>${lis}</ul></li>`;
    });
    return { html, count, hasNew };
  }

  const top = expand(root);
  // 只展开第一层分组，其余默认折叠
  return `<ul class="tree">${top.html}</ul>`;
}

function renderRoadmap() {
  const box = document.getElementById("roadmap");
  if (state.scope !== "player" || state.faction === "系统") {
    box.hidden = true;
    return;
  }
  box.hidden = false;
  const faction = state.faction;
  const pool = new Map(ALL_UNITS.filter(u => u.faction === faction && u.scope === "player" && u.tier > 0).map(u => [u.name, u]));
  const tiers = [...new Set([...pool.values()].map(u => u.tier))].sort();
  const heads = tierHeads(faction, tiers);
  const rendered = new Set();
  const reached = new Set();

  const sections = heads.map((h, i) => {
    const next = heads[i + 1];
    const hq = h.hq;
    const treeHtml = renderTierTree(hq, h.tier, pool, rendered);
    [...treeHtml.matchAll(/data-jump="([^"]+)"/g)].forEach(m => reached.add(m[1].replace(/&amp;/g, "&").replace(/&quot;/g, '"').replace(/&#39;/g, "'").replace(/&lt;/g, "<").replace(/&gt;/g, ">")));
    reached.add(hq.name);
    const meta = [`生命 ${hq.stats.hp}`, hq.stats.shield ? `护盾 ${hq.stats.shield}` : ""].filter(Boolean).join("，");
    const note = h.sharedHq
      ? `满足任一条件进入 T${h.tier}：${h.gates.map(g => `<span class="gate-link" data-jump="${escapeHtml(g.name)}">${escapeHtml(g.displayName)}</span>`).join("、")}`
      : (h.tier === 1 ? "开局选择阵营后获得" : "");
    let upgrade = "";
    if (next && !next.sharedHq && next.hq !== hq) {
      const info = (hq.relations.convertInfo || {})[next.hq.name];
      rendered.add(`upgrade|${next.hq.name}|${hq.name}`);
      upgrade = `<div class="up-arrow"><span class="lbl">升级到 T${next.tier}</span>${info ? costHtml(info.price, info.time) : ""}</div>`;
    } else if (next) {
      upgrade = `<div class="up-arrow"><span class="lbl">进入 T${next.tier}</span><span class="note">满足下一段列出的任一条件</span></div>`;
    }
    return `
      <section class="tier t${h.tier}">
        <div class="rail">
          <div class="tier-tag">T${h.tier}</div>
          <div class="hq node k-building" tabindex="0" data-jump="${escapeHtml(hq.name)}">
            <span class="th big" style="background-image:url('${hq.image.base64 || hq.image.relPath}')"></span>
            <span class="bd"><span class="nm">${escapeHtml(hq.displayName)}</span><span class="meta">${meta}</span>${note ? `<span class="note">${note}</span>` : ""}</span>
          </div>
          <div class="row-tools"><button type="button" data-act="open">展开本级</button><button type="button" data-act="close">收起</button></div>
          ${upgrade}
        </div>
        <div class="canvas">${treeHtml}</div>
      </section>`;
  }).join("");

  const orphans = [...pool.values()].filter(u => !reached.has(u.name));
  const orphanHtml = orphans.length
    ? `<p class="tt-orphans">不在任何总部的生产链上（只能由辅助单位或战斗中获得）：${orphans.map(u => `<span class="gate-link" data-jump="${escapeHtml(u.name)}">${escapeHtml(u.displayName)}</span>`).join("、")}</p>`
    : "";

  box.innerHTML = `
    <div class="tt-head">
      <div>
        <h2>${faction}阵营科技树</h2>
        <p class="sub">左侧是各级总部和升级条件，右侧从总部出发逐层展开：总部 → 单位 → 建筑 → 生产与升级。点卡片看详情，点右侧数字展开。</p>
      </div>
      <div class="tools">
        <button type="button" data-all="open">全部展开</button>
        <button type="button" data-all="close">全部收起</button>
        <button type="button" data-onlynew aria-pressed="${state.onlyNew ? "true" : "false"}">只看本级新增</button>
      </div>
    </div>
    <div class="legend">
      <span><i class="dot" style="background:var(--tt-t1)"></i>T1</span>
      <span><i class="dot" style="background:var(--tt-t2)"></i>T2</span>
      <span><i class="dot" style="background:var(--tt-t3)"></i>T3</span>
      <span>卡片左边色条：<i class="dot" style="background:var(--k-infantry)"></i>步兵 <i class="dot" style="background:var(--k-vehicle)"></i>载具 <i class="dot" style="background:var(--k-air)"></i>飞行 <i class="dot" style="background:var(--k-building)"></i>建筑 <i class="dot" style="background:var(--k-defense)"></i>防御 <i class="dot" style="background:var(--k-upgrade)"></i>升级</span>
    </div>
    <div class="tt-body${state.onlyNew ? " only-new" : ""}">${sections}</div>
    ${orphanHtml}`;

  if (location.hash === "#open-all") box.querySelectorAll(".tree li").forEach(li => li.classList.add("open"));
  const missing = checkTreeCoverage(pool, rendered, reached);
  box.dataset.missingEdges = String(missing.length);
  box.dataset.missingList = missing.join("; ");
  if (missing.length) console.warn("科技树缺少的关系：", missing);
}

// 自检：阵营内每条建造 / 升级 / 生成关系都应出现在某一本的树里（来源单位不在任何生产链上的除外）
function checkTreeCoverage(pool, rendered, reached) {
  const missing = [];
  pool.forEach((u, name) => {
    if (!reached.has(name)) return;
    edgesFrom(u).forEach(([n, kind]) => {
      const t = ALL_UNITS[nameMap[n]];
      if (t && !pool.has(n)) return;
      if (!rendered.has(`${kind}|${n}|${name}`)) missing.push(`${name} -${kind}-> ${n}`);
    });
  });
  return missing;
}

function setupTreeEvents() {
  const box = document.getElementById("roadmap");
  box.addEventListener("click", (e) => {
    const tg = e.target.closest(".tg");
    if (tg) {
      e.stopPropagation();
      tg.closest("li").classList.toggle("open");
      return;
    }
    const gnode = e.target.closest(".gnode");
    if (gnode) {
      gnode.closest("li").classList.toggle("open");
      return;
    }
    const all = e.target.closest("[data-all]");
    if (all) {
      box.querySelectorAll(".tree li").forEach(li => li.classList.toggle("open", all.dataset.all === "open"));
      return;
    }
    const act = e.target.closest("[data-act]");
    if (act) {
      act.closest(".tier").querySelectorAll(".tree li").forEach(li => li.classList.toggle("open", act.dataset.act === "open"));
      return;
    }
    if (e.target.closest("[data-onlynew]")) {
      state.onlyNew = !state.onlyNew;
      box.querySelector(".tt-body").classList.toggle("only-new", state.onlyNew);
      e.target.closest("[data-onlynew]").setAttribute("aria-pressed", String(state.onlyNew));
    }
  }, true);
  box.addEventListener("keydown", (e) => {
    const gnode = e.target.closest && e.target.closest(".gnode");
    if (gnode && (e.key === "Enter" || e.key === " ")) {
      e.preventDefault();
      gnode.closest("li").classList.toggle("open");
    }
  });
}

// ---------------------------------------------------------------- 筛选

function byDefaultOrder(a, b) {
  return (a.tier || 9) - (b.tier || 9)
    || CATEGORIES.indexOf(a.category) - CATEGORIES.indexOf(b.category)
    || a.stats.price - b.stats.price
    || a.displayName.localeCompare(b.displayName, "zh");
}

function applyFilter() {
  const scoped = ALL_UNITS.filter(u => (state.scope === "all" || u.scope === state.scope) && u.faction === state.faction);
  document.getElementById("scope-total").textContent = scoped.length;

  currentFiltered = scoped.filter(u => {
    if (state.category !== "all" && u.category !== state.category) return false;
    if (state.tier !== "all" && String(u.tier) !== state.tier) return false;

    const c = u.combat;
    if (state.combatRole === "attacker" && !c.canAttack) return false;
    if (state.combatRole === "melee" && !(c.canAttack && c.isMelee)) return false;
    if (state.combatRole === "ranged" && !(c.canAttack && !c.isMelee)) return false;
    if (state.combatRole === "air_atk" && !(c.canAttack && c.canAttackAir)) return false;
    if (state.combatRole === "air_unit" && u.movement.type !== "AIR") return false;

    const s = u.stats;
    if (state.specialTrait === "infection" && !u.relations.spawnOnDeath) return false;
    if (state.specialTrait === "shield" && s.shield <= 0) return false;
    if (state.specialTrait === "regen" && s.selfRegen <= 0) return false;
    if (state.specialTrait === "credits" && s.creditsGen === 0) return false;
    if (state.specialTrait === "transport" && s.transport <= 0) return false;
    if (state.specialTrait === "nuke" && !u.traits.some(t => t.type === "nuke")) return false;

    if (state.keyword) {
      const hay = [u.displayName, u.name, u.description, u.filename, u.tags].join(" ").toLowerCase();
      if (!hay.includes(state.keyword)) return false;
    }
    return true;
  });

  const sorters = {
    default: byDefaultOrder,
    hp_desc: (a, b) => b.stats.hp - a.stats.hp,
    price_desc: (a, b) => b.stats.price - a.stats.price,
    price_asc: (a, b) => a.stats.price - b.stats.price,
    dmg_desc: (a, b) => b.combat.singleDamage - a.combat.singleDamage,
    dps_desc: (a, b) => b.combat.dps - a.combat.dps,
    range_desc: (a, b) => b.combat.range - a.combat.range,
    speed_desc: (a, b) => b.movement.speed - a.movement.speed
  };
  currentFiltered.sort(sorters[state.sortBy] || byDefaultOrder);

  document.getElementById("filter-count").textContent = currentFiltered.length;
  renderUnits();
}

// ---------------------------------------------------------------- 列表

function renderUnits() {
  const container = document.getElementById("units-container");
  if (currentFiltered.length === 0) {
    container.innerHTML = `
      <div class="empty-state">
        <div class="empty-icon">🔍</div>
        <h3>没有符合条件的单位</h3>
        <p style="margin-top:6px;font-size:13px;">换个关键词，或点“重置筛选”。</p>
      </div>`;
    return;
  }
  if (state.viewMode === "table") renderTableView(container);
  else if (state.viewMode === "compact") renderGrouped(container, "compact-grid", compactItem);
  else renderGrouped(container, "units-grid", cardItem);
}

// 默认排序时按等级分段，方便看发育顺序；其他排序直接平铺
function renderGrouped(container, gridClass, itemFn) {
  if (state.sortBy !== "default") {
    container.innerHTML = `<div class="${gridClass}">${currentFiltered.map(itemFn).join("")}</div>`;
    return;
  }
  let html = "";
  let lastTier = null;
  let buffer = [];
  const flush = () => {
    if (!buffer.length) return;
    const gates = tierGates(state.faction, lastTier);
    const gateText = lastTier === 1 ? "开局可用" : (gates.length ? "解锁：" + gates.map(g => escapeHtml(g.displayName)).join(" / ") : "");
    html += `
      <div class="tier-section-head">
        <span class="tier-badge tier-${lastTier}">${tierLabel(lastTier)}</span>
        <span class="tier-section-gate">${lastTier > 0 ? gateText : "无法获得"}</span>
        <span class="tier-section-count">${buffer.length} 个</span>
      </div>
      <div class="${gridClass}">${buffer.join("")}</div>`;
    buffer = [];
  };
  currentFiltered.forEach((u, idx) => {
    if (u.tier !== lastTier) {
      flush();
      lastTier = u.tier;
    }
    buffer.push(itemFn(u, idx));
  });
  flush();
  container.innerHTML = html;
}

function badgesFor(u) {
  const obtainLabel = SCOPE_BADGE[u.scope] || OBTAIN_BADGE[u.obtain];
  return `
    <span class="tier-badge sm tier-${u.tier}">${tierLabel(u.tier)}</span>
    <span class="badge badge-cat cat-${u.category}">${u.category}</span>
    ${obtainLabel ? `<span class="badge badge-obtain">${obtainLabel}</span>` : ""}`;
}

function cardItem(u, idx) {
  const facClass = u.faction === "人类" ? "human" : (u.faction === "僵尸" ? "zombie" : "system");
  let statsHtml = `
    <div class="card-stat-item"><span class="stat-lbl">生命</span><span class="stat-val hp">${u.stats.hp}</span></div>
    <div class="card-stat-item"><span class="stat-lbl">造价</span><span class="stat-val price">${u.stats.price}</span></div>`;
  statsHtml += u.combat.canAttack
    ? `<div class="card-stat-item"><span class="stat-lbl">伤害 / 射程</span><span class="stat-val dmg">${u.combat.singleDamage || "-"} / ${u.combat.range}</span></div>`
    : `<div class="card-stat-item"><span class="stat-lbl">移速</span><span class="stat-val">${u.isBuilding ? "建筑" : u.movement.speed}</span></div>`;

  const pills = [];
  if (u.role) pills.push(`<span class="trait-pill form">${escapeHtml(u.role)}</span>`);
  if (u.forms.length) pills.push(`<span class="trait-pill form">${u.forms.length} 种形态</span>`);
  u.traits.slice(0, 3).forEach(t => pills.push(`<span class="trait-pill ${t.type}">${escapeHtml(t.label)}</span>`));

  return `
    <div class="unit-card ${facClass}" onclick="openDetail(${idx})">
      <div class="card-topbar">
        <div class="card-subcat">${escapeHtml(u.subCategory)}</div>
        <div class="card-badges">${badgesFor(u)}</div>
      </div>
      <div class="card-body">
        <div class="card-thumb-wrap">
          <img class="card-thumb" src="${u.image.base64 || u.image.relPath}" alt="" loading="lazy">
        </div>
        <div class="card-main-info">
          <div class="card-title-row"><h3 class="card-title">${escapeHtml(u.displayName)}</h3></div>
          <div class="card-code">${escapeHtml(u.name)}</div>
          <div class="card-desc">${u.description ? escapeHtml(u.description) : "（无描述）"}</div>
        </div>
      </div>
      <div class="card-stats">${statsHtml}</div>
      <div class="card-traits">${pills.join("")}</div>
    </div>`;
}

function compactItem(u, idx) {
  return `
    <div class="compact-item" onclick="openDetail(${idx})">
      <img class="compact-thumb" src="${u.image.base64 || u.image.relPath}" alt="" loading="lazy">
      <div style="flex:1;min-width:0;">
        <div style="font-weight:700;font-size:13px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">${escapeHtml(u.displayName)}</div>
        <div style="font-size:11px;color:var(--text-dim);display:flex;gap:6px;align-items:center;">
          <span class="tier-badge xs tier-${u.tier}">${tierLabel(u.tier)}</span>
          <span>${u.category}</span>
          <span>$ ${u.stats.price}</span>
        </div>
      </div>
    </div>`;
}

function renderTableView(container) {
  const rows = currentFiltered.map((u, idx) => `
    <tr onclick="openDetail(${idx})">
      <td>
        <img class="table-thumb" src="${u.image.base64 || u.image.relPath}" alt="">
        <strong>${escapeHtml(u.displayName)}</strong>
        <span style="color:var(--text-dim);font-size:11px;margin-left:4px;">(${escapeHtml(u.name)})</span>
      </td>
      <td><span class="tier-badge xs tier-${u.tier}">${tierLabel(u.tier)}</span></td>
      <td>${u.category}${u.role ? ` · <span style="color:var(--text-dim)">${escapeHtml(u.role)}</span>` : ""}</td>
      <td>${u.obtain}</td>
      <td style="color:#f87171;font-weight:700;">${u.stats.hp}</td>
      <td style="color:#facc15;font-weight:700;">${u.stats.price}</td>
      <td style="color:#fb923c;">${u.combat.canAttack ? u.combat.singleDamage : "-"}</td>
      <td style="color:#fb923c;font-weight:700;">${u.combat.canAttack ? u.combat.dps : "-"}</td>
      <td>${u.combat.canAttack ? u.combat.range : "-"}</td>
      <td>${u.isBuilding ? "建筑" : u.movement.speed}</td>
    </tr>`).join("");
  container.innerHTML = `
    <div class="table-view-wrap">
      <table class="data-table">
        <thead><tr>
          <th>单位</th><th>等级</th><th>大类</th><th>获得方式</th><th>生命</th><th>造价</th>
          <th>单发伤害</th><th>估算 DPS</th><th>射程</th><th>移速</th>
        </tr></thead>
        <tbody>${rows}</tbody>
      </table>
    </div>`;
}

// ---------------------------------------------------------------- 详情

function openDetail(idx) {
  currentModalIndex = idx;
  const u = currentFiltered[idx];
  if (!u) return;

  currentZoom = 1;
  document.getElementById("modal-filepath").textContent = u.filePath;

  const relationsHtml = [
    relationBlock("🔁 本体", u.formOf ? [u.formOf] : []),
    relationBlock("🔁 形态 / 切换", u.forms),
    relationBlock("🏭 由谁建造", u.relations.builtFrom),
    relationBlock("🛠️ 可建造", u.relations.canBuild),
    relationBlock("🔀 可转换为", u.relations.convertTo.filter(n => n !== u.formOf && !u.forms.includes(n))),
    relationBlock("☣️ 会生成", u.relations.spawns),
    relationBlock("🧬 由谁生成", u.relations.spawnedBy),
    u.relations.actions.length ? `
      <div class="relation-block">
        <div class="relation-title">⚡ 技能 / 指令</div>
        <div style="font-size:12px;color:#cbd5e1;line-height:1.5;">
          ${u.relations.actions.map(act => `<div>• ${escapeHtml(act)}</div>`).join("")}
        </div>
      </div>` : ""
  ].join("");

  let extraImgHtml = "";
  if (u.image.turretBase64) extraImgHtml += `<div class="extra-img-box"><img src="${u.image.turretBase64}"><span>炮塔贴图</span></div>`;
  if (u.image.wreakBase64) extraImgHtml += `<div class="extra-img-box"><img src="${u.image.wreakBase64}"><span>残骸贴图</span></div>`;

  const unlockNote = u.unlocksTier ? `<div class="unlock-note">升级 / 建造它可以进入 ${tierLabel(u.unlocksTier)}</div>` : "";

  document.getElementById("modal-body").innerHTML = `
    <div class="modal-left">
      <div class="modal-image-showcase">
        <img id="modal-main-img" class="modal-img-main" src="${u.image.base64 || u.image.relPath}" alt="">
        <div class="zoom-ctrls">
          <button class="zoom-btn active" onclick="setZoom(1)">1x</button>
          <button class="zoom-btn" onclick="setZoom(2)">2x</button>
          <button class="zoom-btn" onclick="setZoom(3)">3x</button>
        </div>
      </div>
      ${extraImgHtml ? `<div class="extra-images">${extraImgHtml}</div>` : ""}
      <div style="background:rgba(0,0,0,0.25);border:1px solid rgba(255,255,255,0.05);border-radius:6px;padding:12px;">
        <div style="font-size:11px;color:var(--text-dim);margin-bottom:4px;">阵营 · 目录</div>
        <div style="font-weight:700;font-size:14px;color:var(--text-main);">${u.faction} · ${escapeHtml(u.subCategory)}</div>
        <div style="font-size:12px;color:var(--text-muted);margin-top:2px;">${u.unitType}</div>
      </div>
    </div>

    <div class="modal-right">
      <div class="modal-title-area">
        <h2>${escapeHtml(u.displayName)}</h2>
        <div class="modal-subtitle">
          <span class="code-tag">ID: ${escapeHtml(u.name)}</span>
          <span class="tier-badge xs tier-${u.tier}">${tierLabel(u.tier)}</span>
          <span>${u.category}${u.role ? " · " + escapeHtml(u.role) : ""}</span>
          <span>·</span>
          <span>${u.obtain}</span>
        </div>
        ${unlockNote}
      </div>

      <div class="modal-desc-box">${u.description ? escapeHtml(u.description) : "（无描述）"}</div>

      <div>
        <div class="detail-section-title">🛡️ 生存</div>
        <div class="detail-grid">
          <div class="detail-item"><div class="detail-lbl">生命值</div><div class="detail-val" style="color:#f87171">${u.stats.hp}</div></div>
          <div class="detail-item"><div class="detail-lbl">护盾</div><div class="detail-val" style="color:#38bdf8">${u.stats.shield || "无"}</div></div>
          <div class="detail-item"><div class="detail-lbl">自愈</div><div class="detail-val" style="color:#86efac">${u.stats.selfRegen > 0 ? u.stats.selfRegen : "无"}</div></div>
          <div class="detail-item"><div class="detail-lbl">质量</div><div class="detail-val">${u.stats.mass}</div></div>
          <div class="detail-item"><div class="detail-lbl">碰撞半径</div><div class="detail-val">${u.stats.radius}</div></div>
        </div>
      </div>

      <div>
        <div class="detail-section-title">⚔️ 火力</div>
        <div class="detail-grid">
          <div class="detail-item"><div class="detail-lbl">可攻击</div><div class="detail-val">${u.combat.canAttack ? "是" : "否"}</div></div>
          <div class="detail-item"><div class="detail-lbl">单发伤害</div><div class="detail-val" style="color:#fb923c">${u.combat.canAttack ? u.combat.singleDamage : "-"}</div></div>
          <div class="detail-item"><div class="detail-lbl">估算 DPS</div><div class="detail-val" style="color:#fb923c">${u.combat.canAttack ? u.combat.dps : "-"}</div></div>
          <div class="detail-item"><div class="detail-lbl">射程</div><div class="detail-val">${u.combat.canAttack ? u.combat.range : "-"}</div></div>
          <div class="detail-item"><div class="detail-lbl">攻击间隔</div><div class="detail-val">${u.combat.canAttack ? (u.combat.shootDelay / 60).toFixed(2) + " 秒" : "-"}</div></div>
          <div class="detail-item"><div class="detail-lbl">对空</div><div class="detail-val">${u.combat.canAttackAir ? "可以" : "不可以"}</div></div>
          <div class="detail-item"><div class="detail-lbl">溅射半径</div><div class="detail-val">${u.combat.areaRadius > 0 ? u.combat.areaRadius : "单体"}</div></div>
        </div>
      </div>

      <div>
        <div class="detail-section-title">🚀 机动与造价</div>
        <div class="detail-grid">
          <div class="detail-item"><div class="detail-lbl">移动类型</div><div class="detail-val">${u.movement.type}</div></div>
          <div class="detail-item"><div class="detail-lbl">移速</div><div class="detail-val">${u.isBuilding ? "建筑" : u.movement.speed}</div></div>
          <div class="detail-item"><div class="detail-lbl">造价</div><div class="detail-val" style="color:#facc15">${u.stats.price}</div></div>
          <div class="detail-item"><div class="detail-lbl">建造耗时</div><div class="detail-val">${u.stats.buildTime > 0 ? u.stats.buildTime + " 秒" : "-"}</div></div>
          <div class="detail-item"><div class="detail-lbl">产资</div><div class="detail-val" style="color:#fde047">${u.stats.creditsGen || "无"}</div></div>
          <div class="detail-item"><div class="detail-lbl">运载</div><div class="detail-val">${u.stats.transport || "无"}</div></div>
        </div>
      </div>

      <div style="display:flex;flex-direction:column;gap:10px;">
        <div class="detail-section-title">🔗 关联单位</div>
        ${relationsHtml || '<div style="font-size:12px;color:var(--text-dim);">无</div>'}
      </div>
    </div>`;

  document.getElementById("unit-modal").classList.add("show");
}

const VANILLA_UNITS = {
  "bugNest": { displayName: "虫巢 (原版)", tier: 3 },
  "repairbay": { displayName: "维修站 (原版)", tier: 2 },
};

function relationBlock(title, names) {
  if (!names || names.length === 0) return "";
  const pills = names.map(n => {
    const target = ALL_UNITS[nameMap[n]];
    const vanilla = VANILLA_UNITS[n];
    const disp = target ? target.displayName : (vanilla ? vanilla.displayName : n);
    const tierNum = target && target.tier ? target.tier : (vanilla ? vanilla.tier : 0);
    const tier = tierNum ? ` <span class="tier-badge xs tier-${tierNum}">${tierLabel(tierNum)}</span>` : "";
    const tag = target && SCOPE_BADGE[target.scope] ? `<span style="opacity:.6;">·${SCOPE_BADGE[target.scope]}</span>` : (vanilla ? `<span style="opacity:.6;">·原版</span>` : "");
    const jumpAttr = target ? `data-jump="${escapeHtml(n)}"` : `style="cursor:default;opacity:0.85;" title="游戏原版内置单位"`;
    return `<span class="relation-pill" ${jumpAttr}>${escapeHtml(disp)}${tier}${tag}</span>`;
  }).join("");
  return `
    <div class="relation-block">
      <div class="relation-title">${escapeHtml(title)}</div>
      <div class="relation-pills">${pills}</div>
    </div>`;
}

function closeModal() {
  document.getElementById("unit-modal").classList.remove("show");
  currentModalIndex = -1;
}

function navigateModal(direction) {
  if (currentFiltered.length === 0) return;
  const n = currentFiltered.length;
  openDetail((currentModalIndex + direction + n) % n);
}

// 跳到指定单位：当前列表里没有时，切到它所在的阵营和收录范围
function jumpToUnit(unitName) {
  let idx = currentFiltered.findIndex(u => u.name === unitName);
  if (idx < 0) {
    const target = ALL_UNITS[nameMap[unitName]];
    if (!target) return;
    Object.assign(state, DEFAULT_STATE, { faction: target.faction, scope: target.scope, viewMode: state.viewMode });
    refresh();
    idx = currentFiltered.findIndex(u => u.name === unitName);
  }
  if (idx >= 0) openDetail(idx);
}

function setZoom(scale) {
  currentZoom = scale;
  const img = document.getElementById("modal-main-img");
  if (img) img.style.transform = `scale(${scale})`;
  document.querySelectorAll(".zoom-btn").forEach((btn, i) => btn.classList.toggle("active", i + 1 === scale));
}

// ---------------------------------------------------------------- 工具

function escapeHtml(text) {
  return String(text).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "\"": "&quot;", "'": "&#39;" }[c]));
}

function copyToClipboard(text, successMsg) {
  navigator.clipboard.writeText(text).then(() => showToast(successMsg)).catch(() => {
    const ta = document.createElement("textarea");
    ta.value = text;
    document.body.appendChild(ta);
    ta.select();
    document.execCommand("copy");
    document.body.removeChild(ta);
    showToast(successMsg);
  });
}

function showToast(msg) {
  const toast = document.getElementById("toast");
  toast.textContent = msg;
  toast.classList.add("show");
  setTimeout(() => toast.classList.remove("show"), 2000);
}

function download(content, type, filename) {
  const url = URL.createObjectURL(new Blob([content], { type }));
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

function exportJSON() {
  download(JSON.stringify(currentFiltered, null, 2), "application/json;charset=utf-8",
           `生化狂潮_单位图鉴_${new Date().toISOString().slice(0, 10)}.json`);
  showToast("已导出 JSON");
}

function exportCSV() {
  const q = v => `"${String(v).replace(/"/g, '""')}"`;
  const headers = ["名称", "代码", "阵营", "等级", "大类", "说明", "获得方式", "目录", "生命", "护盾", "造价", "单发伤害", "估算DPS", "射程", "移速", "死亡生成", "文件路径"];
  const rows = currentFiltered.map(u => [
    q(u.displayName), q(u.name), q(u.faction), q(tierLabel(u.tier)), q(u.category), q(u.role), q(u.obtain), q(u.subCategory),
    u.stats.hp, u.stats.shield, u.stats.price, u.combat.singleDamage, u.combat.dps, u.combat.range,
    u.isBuilding ? q("建筑") : u.movement.speed, q(u.relations.spawnOnDeath || ""), q(u.filePath)
  ].join(","));
  download("﻿" + [headers.join(","), ...rows].join("\r\n"), "text/csv;charset=utf-8",
           `生化狂潮_单位清单_${new Date().toISOString().slice(0, 10)}.csv`);
  showToast("已导出 CSV");
}

window.addEventListener("DOMContentLoaded", init);
