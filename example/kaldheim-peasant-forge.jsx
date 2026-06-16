import React, { useState, useMemo, useEffect } from "react";
import {
  Snowflake, Swords, Download, X, Search, Check, AlertTriangle,
  BarChart3, Copy, Plus, Minus, Hammer, Layers, Trees, Skull, Sparkles
} from "lucide-react";

/* ------------------------------------------------------------------ *
 *  KALDHEIM — PEASANT FORGE
 *  Peasant format = 60 cards, exactly 5 uncommons + 55 commons.
 *  Basic (snow) lands count as commons. Max 4 of any non-basic card.
 *  Card pool below is a curated KHM (Kaldheim) common/uncommon set,
 *  tagged with archetypes + mechanics drawn from the original Limited
 *  archetype guides. Extend the POOL array to add more cards.
 * ------------------------------------------------------------------ */

// helper: c(id, name, colors[], rarity, type, cmc, tags[])
const c = (id, name, colors, rarity, type, cmc, tags) =>
  ({ id, name, colors, rarity, type, cmc, tags });

const POOL = [
  // ---------- WHITE ----------
  c("battlefield-raptor", "Battlefield Raptor", ["W"], "C", "Creature — Bird Soldier", 1, ["Aggro", "Flyers"]),
  c("iron-verdict", "Iron Verdict", ["W"], "C", "Instant", 2, ["Removal"]),
  c("bound-in-gold", "Bound in Gold", ["W"], "C", "Enchantment — Aura", 2, ["Removal"]),
  c("usher-of-the-fallen", "Usher of the Fallen", ["W"], "U", "Creature — Human Soldier", 1, ["Aggro", "Boast", "Tokens"]),
  c("stalwart-valkyrie", "Stalwart Valkyrie", ["W"], "U", "Creature — Angel Warrior", 3, ["Angels", "Flyers"]),
  c("battle-for-bretagard", "Battle for Bretagard", ["W"], "U", "Enchantment — Saga", 3, ["Tokens", "Aggro"]),
  c("rally-the-ranks", "Rally the Ranks", ["W"], "U", "Enchantment", 2, ["Aggro", "Tokens"]),

  // ---------- BLUE ----------
  c("mistwalker", "Mistwalker", ["U"], "C", "Creature — Spirit Illusion", 1, ["Foretell", "Flyers", "Aggro"]),
  c("ravenform", "Ravenform", ["U"], "C", "Sorcery", 2, ["Removal", "Foretell"]),
  c("run-ashore", "Run Ashore", ["U"], "C", "Instant", 2, ["Tempo"]),
  c("augury-raven", "Augury Raven", ["U"], "C", "Creature — Bird", 3, ["Foretell", "Flyers"]),
  c("berg-strider", "Berg Strider", ["U"], "C", "Creature — Giant Wizard", 4, ["Snow", "Giants", "Tempo"]),
  c("saw-it-coming", "Saw It Coming", ["U"], "U", "Instant", 3, ["Control", "Foretell"]),
  c("behold-the-multiverse", "Behold the Multiverse", ["U"], "U", "Instant", 4, ["Card Advantage", "Foretell", "Control"]),

  // ---------- BLACK ----------
  c("weakening-blow", "Weakening Blow", ["B"], "C", "Instant", 2, ["Removal"]),
  c("withercrown", "Withercrown", ["B"], "C", "Enchantment — Aura", 2, ["Removal"]),
  c("elderfang-disciple", "Elderfang Disciple", ["B"], "C", "Creature — Elf Cleric", 2, ["Elves", "Sacrifice", "Foretell"]),
  c("deathknell-berserker", "Deathknell Berserker", ["B"], "C", "Creature — Zombie Berserker", 2, ["Berserkers", "Boast", "Aggro"]),
  c("grim-draugr", "Grim Draugr", ["B"], "C", "Creature — Zombie Berserker", 3, ["Berserkers", "Aggro"]),
  c("bloodsky-berserker", "Bloodsky Berserker", ["B"], "U", "Creature — Human Berserker", 2, ["Berserkers", "Aggro"]),
  c("poison-the-cup", "Poison the Cup", ["B"], "U", "Instant", 4, ["Removal", "Foretell"]),
  c("feed-the-serpent", "Feed the Serpent", ["B"], "U", "Instant", 4, ["Removal"]),
  c("skemfar-shadowsage", "Skemfar Shadowsage", ["B"], "U", "Creature — Elf Cleric", 5, ["Elves", "Drain"]),
  c("skemfar-avenger", "Skemfar Avenger", ["B"], "U", "Creature — Elf Berserker", 3, ["Elves", "Berserkers", "Card Advantage"]),

  // ---------- RED ----------
  c("frost-bite", "Frost Bite", ["R"], "C", "Instant — Snow", 1, ["Snow", "Removal", "Aggro"]),
  c("demon-bolt", "Demon Bolt", ["R"], "C", "Instant", 2, ["Removal", "Foretell"]),
  c("fearless-pup", "Fearless Pup", ["R"], "C", "Creature — Dog", 1, ["Aggro", "Boast"]),
  c("run-amok", "Run Amok", ["R"], "C", "Instant", 2, ["Aggro"]),
  c("craven-hulk", "Craven Hulk", ["R"], "C", "Creature — Giant Warrior", 4, ["Giants", "Aggro"]),
  c("dwarven-reinforcements", "Dwarven Reinforcements", ["R"], "C", "Sorcery", 4, ["Tokens", "Dwarves", "Foretell"]),
  c("cinderheart-giant", "Cinderheart Giant", ["R"], "C", "Creature — Giant Warrior", 6, ["Giants"]),
  c("dragonkin-berserker", "Dragonkin Berserker", ["R"], "U", "Creature — Dwarf Berserker", 2, ["Berserkers", "Dragons", "Boast", "Aggro"]),
  c("crush-the-weak", "Crush the Weak", ["R"], "U", "Sorcery", 2, ["Removal", "Foretell"]),
  c("squash", "Squash", ["R"], "U", "Sorcery", 5, ["Giants", "Removal"]),

  // ---------- GREEN ----------
  c("jaspera-sentinel", "Jaspera Sentinel", ["G"], "C", "Creature — Elf Shaman", 1, ["Elves", "Ramp"]),
  c("snakeskin-veil", "Snakeskin Veil", ["G"], "C", "Instant", 1, ["Protection"]),
  c("elven-bow", "Elven Bow", ["G"], "C", "Artifact — Equipment", 1, ["Elves", "Aggro"]),
  c("broken-wings", "Broken Wings", ["G"], "C", "Instant", 2, ["Removal"]),
  c("mammoth-growth", "Mammoth Growth", ["G"], "C", "Instant", 2, ["Aggro"]),
  c("sarulfs-packmate", "Sarulf's Packmate", ["G"], "C", "Creature — Beast", 4, ["Card Advantage", "Foretell"]),
  c("ravenous-lindwurm", "Ravenous Lindwurm", ["G"], "C", "Creature — Wurm", 6, ["Ramp"]),
  c("sculptor-of-winter", "Sculptor of Winter", ["G"], "U", "Creature — Elf Berserker", 2, ["Snow", "Elves", "Ramp"]),
  c("boreal-outrider", "Boreal Outrider", ["G"], "U", "Creature — Elf Warrior", 3, ["Snow", "Elves"]),
  c("masked-vandal", "Masked Vandal", ["G"], "U", "Creature — Shapeshifter", 2, ["Removal", "Changeling"]),
  c("struggle-for-skemfar", "Struggle // Survive", ["G"], "U", "Sorcery", 3, ["Removal", "Foretell"]),
  c("path-to-the-world-tree", "Path to the World Tree", ["G"], "U", "Enchantment — Saga", 3, ["Ramp"]),

  // ---------- MULTICOLOR ----------
  c("harald-king-of-skemfar", "Harald, King of Skemfar", ["B", "G"], "U", "Legendary Creature — Elf Warrior", 3, ["Elves", "Card Advantage"]),
  c("vega-the-watcher", "Vega, the Watcher", ["W", "U"], "U", "Legendary Creature — God Bird", 2, ["Foretell", "Card Advantage", "Flyers"]),

  // ---------- ARTIFACT / COLORLESS ----------
  c("icehide-golem", "Icehide Golem", [], "C", "Artifact Creature — Golem", 2, ["Snow", "Aggro"]),
  c("scorn-effigy", "Scorn Effigy", [], "C", "Artifact Creature — Construct", 3, ["Foretell"]),
  c("tormentors-helm", "Tormentor's Helm", [], "C", "Artifact — Equipment", 2, ["Aggro", "Foretell"]),
  c("mind-carver", "Mind Carver", [], "U", "Artifact — Equipment", 2, ["Aggro", "Foretell"]),
  c("replicating-ring", "Replicating Ring", [], "U", "Artifact — Snow", 5, ["Snow", "Ramp"]),

  // ---------- LANDS: snow taplands (two-color, common) ----------
  c("alpine-meadow", "Alpine Meadow", ["R", "W"], "C", "Snow Land", 0, ["Land", "Dual"]),
  c("arctic-treeline", "Arctic Treeline", ["G", "W"], "C", "Snow Land", 0, ["Land", "Dual"]),
  c("glacial-floodplain", "Glacial Floodplain", ["W", "U"], "C", "Snow Land", 0, ["Land", "Dual"]),
  c("highland-forest", "Highland Forest", ["R", "G"], "C", "Snow Land", 0, ["Land", "Dual"]),
  c("ice-tunnel", "Ice Tunnel", ["U", "B"], "C", "Snow Land", 0, ["Land", "Dual"]),
  c("rimewood-falls", "Rimewood Falls", ["G", "U"], "C", "Snow Land", 0, ["Land", "Dual"]),
  c("snowfield-sinkhole", "Snowfield Sinkhole", ["W", "B"], "C", "Snow Land", 0, ["Land", "Dual"]),
  c("sulfurous-mire", "Sulfurous Mire", ["B", "R"], "C", "Snow Land", 0, ["Land", "Dual"]),
  c("volatile-fjord", "Volatile Fjord", ["U", "R"], "C", "Snow Land", 0, ["Land", "Dual"]),
  c("woodland-chasm", "Woodland Chasm", ["B", "G"], "C", "Snow Land", 0, ["Land", "Dual"]),

  // ---------- LANDS: snow basics (common, unlimited) ----------
  c("snow-plains", "Snow-Covered Plains", ["W"], "C", "Basic Snow Land — Plains", 0, ["Land", "Basic", "Snow"]),
  c("snow-island", "Snow-Covered Island", ["U"], "C", "Basic Snow Land — Island", 0, ["Land", "Basic", "Snow"]),
  c("snow-swamp", "Snow-Covered Swamp", ["B"], "C", "Basic Snow Land — Swamp", 0, ["Land", "Basic", "Snow"]),
  c("snow-mountain", "Snow-Covered Mountain", ["R"], "C", "Basic Snow Land — Mountain", 0, ["Land", "Basic", "Snow"]),
  c("snow-forest", "Snow-Covered Forest", ["G"], "C", "Basic Snow Land — Forest", 0, ["Land", "Basic", "Snow"]),
];

const ARCHETYPES = ["Snow", "Elves", "Giants", "Berserkers", "Foretell", "Aggro", "Removal", "Ramp", "Tokens", "Flyers"];

const COLOR_META = {
  W: { name: "White", hex: "#f4efda", glyph: "☀" },
  U: { name: "Blue",  hex: "#2f7fc4", glyph: "💧" },
  B: { name: "Black", hex: "#6b6b78", glyph: "☠" },
  R: { name: "Red",   hex: "#cf5440", glyph: "🔥" },
  G: { name: "Green", hex: "#4a9c62", glyph: "🌿" },
};
const COLOR_ORDER = ["W", "U", "B", "R", "G"];
const SNOW_BASIC = { W: "snow-plains", U: "snow-island", B: "snow-swamp", R: "snow-mountain", G: "snow-forest" };

// theme
const T = {
  bg: "#0a0e16",
  bg2: "#0e141f",
  panel: "#121b29",
  panel2: "#0f1622",
  line: "#243246",
  lineSoft: "#1a2434",
  frost: "#9fdcef",
  frostDim: "#5a8ea3",
  gold: "#d8b974",
  goldDim: "#8a754a",
  text: "#e3ebf3",
  mut: "#8295ab",
  mut2: "#5d6e83",
  good: "#7fd6a0",
  bad: "#e2796b",
};

const STYLE = `
@import url('https://fonts.googleapis.com/css2?family=Cinzel:wght@500;600;700&family=Spectral:ital,wght@0,300;0,400;0,500;0,600;1,400&display=swap');
* { box-sizing: border-box; }
.kf-root { font-family: 'Spectral', Georgia, serif; color: ${T.text}; }
.kf-display { font-family: 'Cinzel', serif; letter-spacing: .04em; }
.kf-scroll::-webkit-scrollbar { width: 9px; height: 9px; }
.kf-scroll::-webkit-scrollbar-track { background: ${T.panel2}; }
.kf-scroll::-webkit-scrollbar-thumb { background: ${T.line}; border-radius: 8px; }
.kf-scroll::-webkit-scrollbar-thumb:hover { background: ${T.frostDim}; }
@keyframes kfRise { from { opacity:0; transform: translateY(8px);} to {opacity:1; transform:none;} }
@keyframes kfShimmer { 0%{background-position:-200% 0;} 100%{background-position:200% 0;} }
.kf-card { animation: kfRise .35s ease both; }
.kf-titlebar { background: linear-gradient(100deg, ${T.frost}11, ${T.gold}11, ${T.frost}11); background-size:200% 100%; animation: kfShimmer 9s linear infinite; }
.kf-btn { transition: all .15s ease; cursor:pointer; }
.kf-btn:hover { filter: brightness(1.12); }
.kf-btn:active { transform: scale(.97); }
.kf-row:hover { background:${T.panel}; }
input, textarea, button { font-family: inherit; }
`;

function Pip({ color, size = 16 }) {
  const m = COLOR_META[color];
  if (!m) return (
    <span style={{ width: size, height: size, borderRadius: "50%", background: "#3a4456",
      display: "inline-flex", alignItems: "center", justifyContent: "center",
      fontSize: size * 0.6, border: `1px solid ${T.line}`, color: T.mut }}>◇</span>
  );
  const dark = color === "U" || color === "B" || color === "R" || color === "G";
  return (
    <span title={m.name} style={{
      width: size, height: size, borderRadius: "50%", background: m.hex,
      display: "inline-flex", alignItems: "center", justifyContent: "center",
      fontSize: size * 0.62, color: dark ? "#0b0f17" : "#3a3320",
      border: `1px solid rgba(0,0,0,.35)`, boxShadow: "inset 0 1px 1px rgba(255,255,255,.25)",
      flex: "0 0 auto",
    }}>{m.glyph}</span>
  );
}

function Tag({ children, tone = "frost" }) {
  const c = tone === "gold"
    ? { bg: `${T.gold}1a`, bd: `${T.goldDim}`, tx: T.gold }
    : { bg: `${T.frost}14`, bd: T.frostDim, tx: T.frost };
  return (
    <span style={{
      fontSize: 10.5, padding: "2px 7px", borderRadius: 4, background: c.bg,
      border: `1px solid ${c.bd}55`, color: c.tx, whiteSpace: "nowrap",
      letterSpacing: ".03em", textTransform: "uppercase", fontWeight: 600,
    }}>{children}</span>
  );
}

export default function App() {
  const [deck, setDeck] = useState({});
  const [colors, setColors] = useState([]);          // active color toggles
  const [arch, setArch] = useState("All");
  const [rarity, setRarity] = useState("All");
  const [q, setQ] = useState("");
  const [toast, setToast] = useState("");
  const [landTarget, setLandTarget] = useState(17);
  const [exportOpen, setExportOpen] = useState(false);
  const [exportTab, setExportTab] = useState("moxfield");
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (!toast) return;
    const t = setTimeout(() => setToast(""), 2200);
    return () => clearTimeout(t);
  }, [toast]);

  const byId = useMemo(() => Object.fromEntries(POOL.map((x) => [x.id, x])), []);

  // ---- deck stats ----
  const stats = useMemo(() => {
    let total = 0, common = 0, uncommon = 0, lands = 0, nonland = 0;
    const curve = { 0: 0, 1: 0, 2: 0, 3: 0, 4: 0, 5: 0, "6+": 0 };
    const pips = { W: 0, U: 0, B: 0, R: 0, G: 0 };
    const tagCount = {};
    for (const [id, n] of Object.entries(deck)) {
      const card = byId[id]; if (!card || n <= 0) continue;
      total += n;
      if (card.rarity === "U") uncommon += n; else common += n;
      const isLand = card.tags.includes("Land");
      if (isLand) lands += n; else nonland += n;
      if (!isLand) {
        const key = card.cmc >= 6 ? "6+" : String(card.cmc);
        curve[key] += n;
        for (const col of card.colors) pips[col] += n;
      }
      for (const tg of card.tags) tagCount[tg] = (tagCount[tg] || 0) + n;
    }
    const valid = uncommon === 5 && common === 55;
    return { total, common, uncommon, lands, nonland, curve, pips, tagCount, valid };
  }, [deck, byId]);

  // ---- detected archetype + suggested manabase ----
  const insight = useMemo(() => {
    const tags = Object.entries(stats.tagCount)
      .filter(([k]) => !["Land", "Basic", "Dual", "Snow"].includes(k) || k === "Snow")
      .sort((a, b) => b[1] - a[1]);
    const topArch = tags.find(([k]) => ARCHETYPES.includes(k));
    const usedColors = COLOR_ORDER.filter((c) => stats.pips[c] > 0);
    const sortedColors = [...usedColors].sort((a, b) => stats.pips[b] - stats.pips[a]);

    let manabase = null;
    const totalPips = COLOR_ORDER.reduce((s, c) => s + stats.pips[c], 0);
    if (sortedColors.length === 1 && totalPips > 0) {
      const a = sortedColors[0];
      manabase = { kind: "mono", lines: [{ id: SNOW_BASIC[a], n: landTarget }] };
    } else if (sortedColors.length === 2 && totalPips > 0) {
      const [a, b] = sortedColors;
      const dual = POOL.find((p) => p.tags.includes("Dual") &&
        p.colors.includes(a) && p.colors.includes(b));
      const dualN = dual ? Math.min(4, Math.max(0, landTarget - 8)) : 0;
      const remaining = landTarget - dualN;
      const shareA = stats.pips[a] / totalPips;
      let nA = Math.round(remaining * shareA);
      let nB = remaining - nA;
      const lines = [];
      if (dual && dualN > 0) lines.push({ id: dual.id, n: dualN });
      if (nA > 0) lines.push({ id: SNOW_BASIC[a], n: nA });
      if (nB > 0) lines.push({ id: SNOW_BASIC[b], n: nB });
      manabase = { kind: "two", colors: [a, b], lines };
    } else if (sortedColors.length >= 3) {
      manabase = { kind: "many" };
    }
    return { topArch: topArch ? topArch[0] : null, sortedColors, manabase, totalPips, tags };
  }, [stats, landTarget]);

  // ---- filtering ----
  const filtered = useMemo(() => {
    const qq = q.trim().toLowerCase();
    return POOL.filter((card) => {
      if (rarity !== "All" && card.rarity !== rarity) return false;
      if (arch !== "All" && !card.tags.includes(arch)) return false;
      if (colors.length) {
        if (card.colors.length === 0) {
          if (!colors.includes("C")) return false;
        } else if (!card.colors.some((c) => colors.includes(c))) return false;
      }
      if (qq && !(card.name.toLowerCase().includes(qq) || card.type.toLowerCase().includes(qq)
        || card.tags.some((t) => t.toLowerCase().includes(qq)))) return false;
      return true;
    }).sort((a, b) => {
      const al = a.tags.includes("Land"), bl = b.tags.includes("Land");
      if (al !== bl) return al ? 1 : -1;
      if (a.cmc !== b.cmc) return a.cmc - b.cmc;
      return a.name.localeCompare(b.name);
    });
  }, [colors, arch, rarity, q]);

  // ---- mutations with format enforcement ----
  const add = (card) => {
    const n = deck[card.id] || 0;
    const isBasic = card.tags.includes("Basic");
    if (!isBasic && n >= 4) return setToast("Max 4 copies of a non-basic card.");
    if (card.rarity === "U" && stats.uncommon >= 5)
      return setToast("Peasant cap reached — exactly 5 uncommons allowed.");
    if (card.rarity === "C" && stats.common >= 55)
      return setToast("Peasant cap reached — exactly 55 commons allowed.");
    setDeck((d) => ({ ...d, [card.id]: n + 1 }));
  };
  const sub = (card) => setDeck((d) => {
    const n = (d[card.id] || 0) - 1;
    const next = { ...d };
    if (n <= 0) delete next[card.id]; else next[card.id] = n;
    return next;
  });
  const applyManabase = () => {
    if (!insight.manabase || !insight.manabase.lines) return;
    setDeck((d) => {
      const next = { ...d };
      // clear existing basics first, keep duals as part of suggestion
      for (const k of Object.keys(SNOW_BASIC)) delete next[SNOW_BASIC[k]];
      for (const ln of insight.manabase.lines) next[ln.id] = ln.n;
      return next;
    });
    setToast("Suggested mana base applied.");
  };
  const clearDeck = () => setDeck({});

  // ---- export ----
  const deckEntries = useMemo(() => {
    const arr = Object.entries(deck).map(([id, n]) => ({ card: byId[id], n }))
      .filter((e) => e.card && e.n > 0);
    const spells = arr.filter((e) => !e.card.tags.includes("Land"))
      .sort((a, b) => a.card.cmc - b.card.cmc || a.card.name.localeCompare(b.card.name));
    const lands = arr.filter((e) => e.card.tags.includes("Land"))
      .sort((a, b) => a.card.name.localeCompare(b.card.name));
    return [...spells, ...lands];
  }, [deck, byId]);

  const exportText = useMemo(() => {
    const lines = deckEntries.map((e) => `${e.n} ${e.card.name}`);
    if (exportTab === "arena") {
      return "Deck\n" + lines.join("\n");
    }
    return lines.join("\n"); // moxfield / plain
  }, [deckEntries, exportTab]);

  const copyExport = async () => {
    try { await navigator.clipboard.writeText(exportText); setCopied(true); setTimeout(() => setCopied(false), 1500); }
    catch { setToast("Copy failed — select the text manually."); }
  };

  const maxCurve = Math.max(1, ...Object.values(stats.curve));

  return (
    <div className="kf-root kf-scroll" style={{ background: T.bg, minHeight: "100vh", padding: "0 0 40px" }}>
      <style>{STYLE}</style>

      {/* atmospheric top band */}
      <div className="kf-titlebar" style={{ borderBottom: `1px solid ${T.line}` }}>
        <div style={{ maxWidth: 1280, margin: "0 auto", padding: "22px 22px 18px",
          display: "flex", alignItems: "flex-end", justifyContent: "space-between", flexWrap: "wrap", gap: 14 }}>
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: 11 }}>
              <Snowflake size={26} color={T.frost} strokeWidth={1.4} />
              <h1 className="kf-display" style={{ margin: 0, fontSize: 30, fontWeight: 700,
                color: T.text, textShadow: `0 0 22px ${T.frost}33` }}>
                KALDHEIM <span style={{ color: T.gold }}>·</span> PEASANT FORGE
              </h1>
            </div>
            <p style={{ margin: "6px 0 0 37px", color: T.mut, fontSize: 13.5, fontStyle: "italic" }}>
              60 cards of the Cosmos — exactly 5 uncommons &amp; 55 commons. Build your saga.
            </p>
          </div>
          <ValidatorBadge stats={stats} />
        </div>
      </div>

      <div style={{ maxWidth: 1280, margin: "0 auto", padding: "18px 22px",
        display: "grid", gridTemplateColumns: "minmax(0,1.55fr) minmax(320px,1fr)", gap: 18 }}>

        {/* ============ LEFT: pool + filters ============ */}
        <section style={{ minWidth: 0 }}>
          <Panel>
            {/* search */}
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 12 }}>
              <div style={{ position: "relative", flex: 1 }}>
                <Search size={15} color={T.mut2} style={{ position: "absolute", left: 10, top: 10 }} />
                <input value={q} onChange={(e) => setQ(e.target.value)}
                  placeholder="Search name, type, or tag…"
                  style={{ width: "100%", padding: "8px 10px 8px 32px", background: T.panel2,
                    border: `1px solid ${T.line}`, borderRadius: 7, color: T.text, fontSize: 13.5, outline: "none" }} />
              </div>
              <span style={{ color: T.mut2, fontSize: 12.5, whiteSpace: "nowrap" }}>{filtered.length} cards</span>
            </div>

            {/* color toggles */}
            <div style={{ display: "flex", alignItems: "center", gap: 7, marginBottom: 10, flexWrap: "wrap" }}>
              <span style={{ color: T.mut2, fontSize: 11.5, textTransform: "uppercase", letterSpacing: ".08em", marginRight: 2 }}>Color</span>
              {[...COLOR_ORDER, "C"].map((col) => {
                const on = colors.includes(col);
                return (
                  <button key={col} className="kf-btn"
                    onClick={() => setColors((cs) => on ? cs.filter((x) => x !== col) : [...cs, col])}
                    style={{ background: on ? `${T.frost}18` : "transparent",
                      border: `1px solid ${on ? T.frostDim : T.line}`, borderRadius: 999,
                      padding: 3, display: "inline-flex", alignItems: "center", opacity: on ? 1 : 0.7 }}>
                    <Pip color={col === "C" ? null : col} size={18} />
                  </button>
                );
              })}
              {(colors.length > 0) && (
                <button className="kf-btn" onClick={() => setColors([])}
                  style={{ background: "transparent", border: "none", color: T.mut2, fontSize: 12, textDecoration: "underline" }}>clear</button>
              )}
            </div>

            {/* archetype + rarity */}
            <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 4 }}>
              {["All", ...ARCHETYPES].map((a) => (
                <Chip key={a} active={arch === a} onClick={() => setArch(a)}>{a}</Chip>
              ))}
            </div>
            <div style={{ display: "flex", gap: 6, marginTop: 8 }}>
              {[["All", "All Rarities"], ["C", "Common"], ["U", "Uncommon"]].map(([v, label]) => (
                <Chip key={v} tone="gold" active={rarity === v} onClick={() => setRarity(v)}>{label}</Chip>
              ))}
            </div>
          </Panel>

          {/* card grid */}
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(218px,1fr))", gap: 10, marginTop: 14 }}>
            {filtered.map((card, i) => (
              <CardTile key={card.id} card={card} count={deck[card.id] || 0}
                onAdd={() => add(card)} onSub={() => sub(card)} index={i} />
            ))}
            {filtered.length === 0 && (
              <div style={{ color: T.mut, gridColumn: "1/-1", padding: 30, textAlign: "center", fontStyle: "italic" }}>
                No cards match these filters.
              </div>
            )}
          </div>
        </section>

        {/* ============ RIGHT: deck + analysis ============ */}
        <aside style={{ minWidth: 0, display: "flex", flexDirection: "column", gap: 14 }}>

          {/* validator */}
          <Panel>
            <PanelTitle icon={<Check size={15} />}>Format Validator</PanelTitle>
            <Counter label="Commons" value={stats.common} target={55} />
            <Counter label="Uncommons" value={stats.uncommon} target={5} />
            <div style={{ height: 1, background: T.lineSoft, margin: "8px 0" }} />
            <Counter label="Total deck" value={stats.total} target={60} bold />
            <div style={{ display: "flex", gap: 8, marginTop: 12 }}>
              <button className="kf-btn" disabled={!stats.valid} onClick={() => setExportOpen(true)}
                style={{ flex: 1, padding: "9px 0", borderRadius: 7, fontWeight: 600, fontSize: 13,
                  border: `1px solid ${stats.valid ? T.gold : T.line}`,
                  background: stats.valid ? `${T.gold}1c` : T.panel2,
                  color: stats.valid ? T.gold : T.mut2, cursor: stats.valid ? "pointer" : "not-allowed",
                  display: "inline-flex", alignItems: "center", justifyContent: "center", gap: 7 }}>
                <Download size={14} /> Export Deck
              </button>
              <button className="kf-btn" onClick={clearDeck}
                style={{ padding: "9px 12px", borderRadius: 7, fontSize: 13, border: `1px solid ${T.line}`,
                  background: T.panel2, color: T.mut }}>Clear</button>
            </div>
            {!stats.valid && stats.total > 0 && (
              <p style={{ margin: "9px 0 0", fontSize: 12, color: T.mut, display: "flex", gap: 6, alignItems: "flex-start" }}>
                <AlertTriangle size={13} color={T.gold} style={{ marginTop: 1, flex: "0 0 auto" }} />
                {hintFor(stats)}
              </p>
            )}
          </Panel>

          {/* mana curve */}
          <Panel>
            <PanelTitle icon={<BarChart3 size={15} />}>Mana Curve <span style={{ color: T.mut2, fontWeight: 400, fontSize: 11.5, marginLeft: 6 }}>(non-land · {stats.nonland})</span></PanelTitle>
            <div style={{ display: "flex", alignItems: "flex-end", gap: 6, height: 116, marginTop: 6 }}>
              {Object.entries(stats.curve).map(([k, v]) => (
                <div key={k} style={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center", gap: 4, height: "100%", justifyContent: "flex-end" }}>
                  <span style={{ fontSize: 11, color: v ? T.frost : T.mut2, fontWeight: 600 }}>{v || ""}</span>
                  <div style={{ width: "100%", height: `${(v / maxCurve) * 84}%`, minHeight: v ? 4 : 0,
                    background: `linear-gradient(${T.frost}, ${T.frostDim})`, borderRadius: "3px 3px 0 0",
                    boxShadow: v ? `0 0 10px ${T.frost}44` : "none", transition: "height .3s ease" }} />
                  <span style={{ fontSize: 11, color: T.mut2 }}>{k}</span>
                </div>
              ))}
            </div>
          </Panel>

          {/* archetype + synergy */}
          <Panel>
            <PanelTitle icon={<Sparkles size={15} />}>Archetype &amp; Synergy</PanelTitle>
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 10 }}>
              <span style={{ fontSize: 12.5, color: T.mut }}>Identity:</span>
              <span style={{ display: "inline-flex", gap: 3 }}>
                {insight.sortedColors.length
                  ? insight.sortedColors.map((c) => <Pip key={c} color={c} size={16} />)
                  : <span style={{ color: T.mut2, fontSize: 12.5 }}>—</span>}
              </span>
              {insight.topArch && (
                <span style={{ marginLeft: 4, color: T.gold, fontWeight: 600, fontSize: 13 }} className="kf-display">
                  {insight.topArch}
                </span>
              )}
            </div>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
              {insight.tags.length === 0 && <span style={{ color: T.mut2, fontSize: 12.5, fontStyle: "italic" }}>Add cards to reveal synergies.</span>}
              {insight.tags.slice(0, 12).map(([t, n]) => (
                <span key={t} style={{ fontSize: 11, padding: "3px 8px", borderRadius: 5,
                  background: T.panel2, border: `1px solid ${T.lineSoft}`, color: T.text }}>
                  {t} <span style={{ color: T.frost, fontWeight: 700 }}>{n}</span>
                </span>
              ))}
            </div>
          </Panel>

          {/* land suggestion */}
          <Panel>
            <PanelTitle icon={<Trees size={15} />}>Suggested Mana Base</PanelTitle>
            <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 10 }}>
              <span style={{ fontSize: 12.5, color: T.mut }}>Land target</span>
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <Step onClick={() => setLandTarget((n) => Math.max(14, n - 1))}><Minus size={12} /></Step>
                <span style={{ minWidth: 22, textAlign: "center", fontWeight: 700, color: T.frost }}>{landTarget}</span>
                <Step onClick={() => setLandTarget((n) => Math.min(24, n + 1))}><Plus size={12} /></Step>
              </div>
            </div>
            <ManabaseSuggestion insight={insight} byId={byId} onApply={applyManabase} />
          </Panel>

          {/* decklist */}
          <Panel>
            <PanelTitle icon={<Layers size={15} />}>Decklist <span style={{ color: T.mut2, fontWeight: 400, fontSize: 11.5, marginLeft: 6 }}>{stats.total} cards</span></PanelTitle>
            <DeckList entries={deckEntries} onAdd={add} onSub={sub} />
          </Panel>
        </aside>
      </div>

      {/* toast */}
      {toast && (
        <div style={{ position: "fixed", bottom: 22, left: "50%", transform: "translateX(-50%)",
          background: T.panel, border: `1px solid ${T.gold}66`, color: T.text, padding: "10px 16px",
          borderRadius: 9, fontSize: 13, boxShadow: "0 10px 30px rgba(0,0,0,.5)", zIndex: 60,
          display: "flex", gap: 8, alignItems: "center" }}>
          <AlertTriangle size={15} color={T.gold} /> {toast}
        </div>
      )}

      {/* export modal */}
      {exportOpen && (
        <div onClick={() => setExportOpen(false)} style={{ position: "fixed", inset: 0, background: "rgba(4,7,12,.78)",
          zIndex: 70, display: "flex", alignItems: "center", justifyContent: "center", padding: 20 }}>
          <div onClick={(e) => e.stopPropagation()} className="kf-scroll" style={{ width: "min(620px,100%)", maxHeight: "86vh",
            overflow: "auto", background: T.bg2, border: `1px solid ${T.line}`, borderRadius: 12, padding: 20,
            boxShadow: "0 24px 70px rgba(0,0,0,.6)" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 14 }}>
              <h2 className="kf-display" style={{ margin: 0, fontSize: 19, color: T.gold }}>Export Deck</h2>
              <button className="kf-btn" onClick={() => setExportOpen(false)}
                style={{ background: "none", border: "none", color: T.mut, cursor: "pointer" }}><X size={20} /></button>
            </div>
            <div style={{ display: "flex", gap: 8, marginBottom: 12 }}>
              {[["moxfield", "Moxfield / Plain"], ["arena", "MTG Arena"]].map(([v, l]) => (
                <Chip key={v} active={exportTab === v} onClick={() => setExportTab(v)}>{l}</Chip>
              ))}
            </div>
            <textarea readOnly value={exportText} className="kf-scroll"
              style={{ width: "100%", height: 300, background: T.panel2, color: T.text, border: `1px solid ${T.line}`,
                borderRadius: 8, padding: 12, fontFamily: "ui-monospace, monospace", fontSize: 12.5, resize: "vertical", lineHeight: 1.55 }} />
            <p style={{ fontSize: 11.5, color: T.mut2, margin: "8px 0 12px" }}>
              {exportTab === "arena"
                ? "Paste into MTG Arena → Decks → Import. Names resolve to Kaldheim (KHM); snow basics import as “Snow-Covered …”."
                : "Paste into Moxfield’s bulk-import box, or any tool that reads “quantity + name” lists."}
            </p>
            <button className="kf-btn" onClick={copyExport}
              style={{ width: "100%", padding: "10px 0", borderRadius: 8, border: `1px solid ${T.gold}`,
                background: `${T.gold}1f`, color: T.gold, fontWeight: 600, fontSize: 13.5,
                display: "inline-flex", alignItems: "center", justifyContent: "center", gap: 8 }}>
              {copied ? <Check size={15} /> : <Copy size={15} />} {copied ? "Copied!" : "Copy to clipboard"}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

/* ---------------- small components ---------------- */

function Panel({ children }) {
  return (
    <div style={{ background: T.panel, border: `1px solid ${T.line}`, borderRadius: 11,
      padding: 15, boxShadow: "inset 0 1px 0 rgba(255,255,255,.02)" }}>{children}</div>
  );
}
function PanelTitle({ icon, children }) {
  return (
    <h3 className="kf-display" style={{ margin: "0 0 11px", fontSize: 13.5, fontWeight: 600, color: T.frost,
      letterSpacing: ".07em", textTransform: "uppercase", display: "flex", alignItems: "center", gap: 8 }}>
      <span style={{ color: T.gold, display: "inline-flex" }}>{icon}</span>{children}
    </h3>
  );
}
function Chip({ children, active, onClick, tone = "frost" }) {
  const ac = tone === "gold" ? T.gold : T.frost;
  const acd = tone === "gold" ? T.goldDim : T.frostDim;
  return (
    <button className="kf-btn" onClick={onClick}
      style={{ fontSize: 12, padding: "4px 10px", borderRadius: 6, cursor: "pointer",
        border: `1px solid ${active ? acd : T.line}`,
        background: active ? `${ac}1c` : "transparent", color: active ? ac : T.mut,
        fontWeight: active ? 600 : 400 }}>{children}</button>
  );
}
function Step({ children, onClick }) {
  return (
    <button className="kf-btn" onClick={onClick}
      style={{ width: 24, height: 24, borderRadius: 6, border: `1px solid ${T.line}`, background: T.panel2,
        color: T.frost, display: "inline-flex", alignItems: "center", justifyContent: "center", cursor: "pointer" }}>{children}</button>
  );
}

function ValidatorBadge({ stats }) {
  const ok = stats.valid;
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 10, background: T.panel,
      border: `1px solid ${ok ? `${T.good}66` : T.line}`, borderRadius: 10, padding: "8px 14px" }}>
      <div style={{ width: 30, height: 30, borderRadius: "50%", display: "flex", alignItems: "center", justifyContent: "center",
        background: ok ? `${T.good}22` : `${T.gold}1a`, border: `1px solid ${ok ? T.good : T.goldDim}` }}>
        {ok ? <Check size={17} color={T.good} /> : <Hammer size={16} color={T.gold} />}
      </div>
      <div style={{ lineHeight: 1.2 }}>
        <div style={{ fontSize: 12.5, fontWeight: 700, color: ok ? T.good : T.text }}>
          {ok ? "Legal Peasant Deck" : "Forging…"}
        </div>
        <div style={{ fontSize: 11.5, color: T.mut }}>
          {stats.common}/55 C · {stats.uncommon}/5 U · {stats.total}/60
        </div>
      </div>
    </div>
  );
}

function Counter({ label, value, target, bold }) {
  const ok = value === target;
  const over = value > target;
  const color = ok ? T.good : over ? T.bad : T.text;
  return (
    <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "5px 0" }}>
      <span style={{ fontSize: 13, color: T.mut, fontWeight: bold ? 600 : 400 }}>{label}</span>
      <div style={{ display: "flex", alignItems: "center", gap: 10, minWidth: 130 }}>
        <div style={{ flex: 1, height: 5, background: T.panel2, borderRadius: 3, overflow: "hidden" }}>
          <div style={{ width: `${Math.min(100, (value / target) * 100)}%`, height: "100%",
            background: ok ? T.good : over ? T.bad : T.frostDim, transition: "width .25s ease" }} />
        </div>
        <span style={{ fontSize: 13, fontWeight: 700, color, minWidth: 48, textAlign: "right",
          fontVariantNumeric: "tabular-nums" }}>{value}/{target}</span>
      </div>
    </div>
  );
}

function CardTile({ card, count, onAdd, onSub, index }) {
  const isLand = card.tags.includes("Land");
  const rar = card.rarity === "U"
    ? { tx: T.gold, bd: T.goldDim, lbl: "Uncommon" }
    : { tx: T.frostDim, bd: T.line, lbl: "Common" };
  return (
    <div className="kf-card" style={{ animationDelay: `${Math.min(index, 18) * 18}ms`,
      background: count ? `${T.frost}0a` : T.panel2, border: `1px solid ${count ? T.frostDim : T.line}`,
      borderRadius: 9, padding: 11, display: "flex", flexDirection: "column", gap: 8, minHeight: 132,
      position: "relative", overflow: "hidden" }}>
      {count > 0 && (
        <span style={{ position: "absolute", top: 0, right: 0, background: T.frost, color: "#06202b",
          fontWeight: 800, fontSize: 12, padding: "1px 8px", borderBottomLeftRadius: 8 }}>×{count}</span>
      )}
      <div style={{ display: "flex", alignItems: "flex-start", gap: 6 }}>
        <div style={{ display: "flex", gap: 2, flexShrink: 0, marginTop: 1 }}>
          {card.colors.length ? card.colors.map((c) => <Pip key={c} color={c} size={15} />) : <Pip size={15} />}
        </div>
        <div style={{ fontSize: 13.5, fontWeight: 600, lineHeight: 1.25, color: T.text }}>{card.name}</div>
      </div>
      <div style={{ fontSize: 11, color: T.mut, fontStyle: "italic", lineHeight: 1.25 }}>{card.type}</div>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
        {!isLand && card.tags.slice(0, 3).map((t) => <Tag key={t}>{t}</Tag>)}
        {isLand && card.tags.filter(t=>t!=="Land").slice(0,2).map((t) => <Tag key={t} tone="gold">{t}</Tag>)}
      </div>
      <div style={{ marginTop: "auto", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <span style={{ fontSize: 10.5, color: rar.tx, fontWeight: 600, textTransform: "uppercase", letterSpacing: ".05em" }}>
          {rar.lbl}{!isLand ? ` · ${card.cmc} CMC` : ""}
        </span>
        <div style={{ display: "flex", gap: 5 }}>
          <button className="kf-btn" onClick={onSub} disabled={!count}
            style={{ width: 26, height: 26, borderRadius: 6, border: `1px solid ${T.line}`,
              background: T.panel, color: count ? T.text : T.mut2, cursor: count ? "pointer" : "default",
              display: "inline-flex", alignItems: "center", justifyContent: "center" }}><Minus size={13} /></button>
          <button className="kf-btn" onClick={onAdd}
            style={{ width: 26, height: 26, borderRadius: 6, border: `1px solid ${T.frostDim}`,
              background: `${T.frost}14`, color: T.frost, display: "inline-flex", alignItems: "center", justifyContent: "center" }}><Plus size={13} /></button>
        </div>
      </div>
    </div>
  );
}

function ManabaseSuggestion({ insight, byId, onApply }) {
  const mb = insight.manabase;
  if (!mb) return <p style={{ color: T.mut2, fontSize: 12.5, fontStyle: "italic", margin: 0 }}>
    Add some colored spells and I’ll compute a mana base from your color pips.</p>;
  if (mb.kind === "many") return (
    <p style={{ color: T.mut, fontSize: 12.5, margin: 0, lineHeight: 1.5 }}>
      This deck runs <b style={{ color: T.text }}>3+ colors</b>. Peasant Kaldheim is happiest in two colors —
      trim a color, or lean on snow basics plus the {insight.sortedColors.length} matching snow taplands.
    </p>
  );
  return (
    <div>
      {mb.kind === "two" && (
        <p style={{ margin: "0 0 9px", fontSize: 12.5, color: T.mut, lineHeight: 1.5 }}>
          Two-color base split by your pip ratio
          (<span style={{ color: T.text }}>{insight.colorsLabel || insight.sortedColors.join("/")}</span>):
        </p>
      )}
      <div style={{ display: "flex", flexDirection: "column", gap: 5, marginBottom: 11 }}>
        {mb.lines.map((ln) => {
          const card = byId[ln.id];
          return (
            <div key={ln.id} style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 13 }}>
              <span style={{ color: T.frost, fontWeight: 700, minWidth: 22 }}>{ln.n}</span>
              <span style={{ display: "flex", gap: 2 }}>{card.colors.map((c) => <Pip key={c} color={c} size={13} />)}</span>
              <span style={{ color: T.text }}>{card.name}</span>
            </div>
          );
        })}
      </div>
      <button className="kf-btn" onClick={onApply}
        style={{ width: "100%", padding: "8px 0", borderRadius: 7, border: `1px solid ${T.frostDim}`,
          background: `${T.frost}14`, color: T.frost, fontWeight: 600, fontSize: 12.5 }}>
        Apply mana base to deck
      </button>
    </div>
  );
}

function DeckList({ entries, onAdd, onSub }) {
  if (entries.length === 0) return (
    <p style={{ color: T.mut2, fontSize: 12.5, fontStyle: "italic", margin: 0 }}>Empty. Click + on cards to build.</p>
  );
  const spells = entries.filter((e) => !e.card.tags.includes("Land"));
  const lands = entries.filter((e) => e.card.tags.includes("Land"));
  const Section = ({ title, list }) => list.length ? (
    <div style={{ marginBottom: 8 }}>
      <div style={{ fontSize: 10.5, color: T.mut2, textTransform: "uppercase", letterSpacing: ".08em", margin: "4px 0 4px" }}>
        {title} ({list.reduce((s, e) => s + e.n, 0)})
      </div>
      {list.map((e) => (
        <div key={e.card.id} className="kf-row" style={{ display: "flex", alignItems: "center", gap: 7, padding: "3px 4px", borderRadius: 5 }}>
          <span style={{ color: e.card.rarity === "U" ? T.gold : T.frost, fontWeight: 700, minWidth: 20, fontSize: 13 }}>{e.n}</span>
          <span style={{ display: "flex", gap: 2 }}>
            {e.card.colors.length ? e.card.colors.map((c) => <Pip key={c} color={c} size={12} />) : <Pip size={12} />}
          </span>
          <span style={{ flex: 1, fontSize: 12.5, color: T.text, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{e.card.name}</span>
          <button className="kf-btn" onClick={() => onSub(e.card)} style={miniBtn}><Minus size={11} /></button>
          <button className="kf-btn" onClick={() => onAdd(e.card)} style={{ ...miniBtn, color: T.frost, borderColor: T.frostDim }}><Plus size={11} /></button>
        </div>
      ))}
    </div>
  ) : null;
  return (
    <div className="kf-scroll" style={{ maxHeight: 360, overflowY: "auto", paddingRight: 4 }}>
      <Section title="Spells & Creatures" list={spells} />
      <Section title="Lands" list={lands} />
    </div>
  );
}
const miniBtn = { width: 21, height: 21, borderRadius: 5, border: `1px solid ${T.line}`,
  background: T.panel2, color: T.mut, display: "inline-flex", alignItems: "center", justifyContent: "center", cursor: "pointer", flex: "0 0 auto" };

function hintFor(s) {
  const parts = [];
  if (s.uncommon < 5) parts.push(`add ${5 - s.uncommon} more uncommon${5 - s.uncommon > 1 ? "s" : ""}`);
  if (s.uncommon > 5) parts.push(`cut ${s.uncommon - 5} uncommon${s.uncommon - 5 > 1 ? "s" : ""}`);
  if (s.common < 55) parts.push(`add ${55 - s.common} more common${55 - s.common > 1 ? "s" : ""}`);
  if (s.common > 55) parts.push(`cut ${s.common - 55} common${s.common - 55 > 1 ? "s" : ""}`);
  return "To make it legal: " + parts.join(", ") + ".";
}
