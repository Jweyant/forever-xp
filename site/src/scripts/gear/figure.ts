// The character in the middle of the BIS sheet, drawn for this site (no game art).
// A jointed figure proportioned per race and body type. Armour is drawn in its material (plate,
// mail, leather, cloth) and edged with the item's quality colour, the way gear reads in the game.
// Only numbers and this file's own constants go into the SVG: item data contributes a quality
// index, an armour/weapon type matched against fixed patterns, and a slot name.
import type { DollSlot } from "./model";

export interface FigItem { q: number; type?: string; slot?: string }
type Gear = Partial<Record<DollSlot, FigItem>>;
type Pt = [number, number];

const QCOLOR = ["#9d9d9d", "#ffffff", "#1eff00", "#0070dd", "#a335ee", "#ff8000", "#e6cc80"];
const CLOTH = ["#4d4d4d", "#7b7466", "#2f6a2c", "#204c88", "#55298a", "#8a4512", "#7d6a3a"];

interface Build { h: number; sw: number; hw: number; head: number; bulk: number; hunch: number; skin: string; eyes?: string;
  ears?: "long" | "big" | "troll"; tusks?: boolean; horns?: boolean; beard?: boolean; hooves?: boolean; hair: string }
const BUILDS: Record<string, Build> = {
  human: { h: 1, sw: 1, hw: 1, head: 1, bulk: 1, hunch: 0, skin: "#dcae88", hair: "#4a3322" },
  dwarf: { h: 0.74, sw: 1.24, hw: 1.22, head: 1.08, bulk: 1.35, hunch: 0, skin: "#d59f78", beard: true, hair: "#7a3d1c" },
  gnome: { h: 0.56, sw: 0.86, hw: 0.86, head: 1.3, bulk: 0.9, hunch: 0, skin: "#efc6a2", ears: "big", hair: "#d65aa0" },
  nightelf: { h: 1.1, sw: 0.98, hw: 0.92, head: 0.94, bulk: 0.9, hunch: 0, skin: "#9a84c8", ears: "long", eyes: "#d8fbff", hair: "#cfe3ef" },
  orc: { h: 0.98, sw: 1.3, hw: 1.08, head: 1, bulk: 1.3, hunch: 6, skin: "#6e8e3e", tusks: true, hair: "#1d1d1d" },
  undead: { h: 0.95, sw: 0.92, hw: 0.86, head: 0.94, bulk: 0.74, hunch: 3, skin: "#97a28a", eyes: "#ffe680", hair: "#2a2a2a" },
  tauren: { h: 1.12, sw: 1.46, hw: 1.26, head: 1.16, bulk: 1.5, hunch: 4, skin: "#7a5537", horns: true, hooves: true, hair: "#3b2618" },
  troll: { h: 1.08, sw: 1.12, hw: 0.94, head: 1, bulk: 1, hunch: 8, skin: "#4e8e9f", tusks: true, ears: "troll", hair: "#c4392f" },
  skyborne: { h: 1.02, sw: 0.96, hw: 0.94, head: 0.98, bulk: 0.92, hunch: 0, skin: "#d9c3a8", eyes: "#9fe7ff", hair: "#e9e2d0" },
};

const f = (x: number) => (Math.round(x * 10) / 10).toString();
const P = (p: Pt) => `${f(p[0])} ${f(p[1])}`;
const q = (it?: FigItem) => Math.min(6, Math.max(0, Math.trunc(Number(it?.q) || 0)));
const mat = (it?: FigItem) => {
  const t = String(it?.type || "");
  return t === "plate" || t === "mail" || t === "leather" ? t : "cloth";
};
const fill = (it: FigItem, forceCloth = false) => (forceCloth || mat(it) === "cloth" ? `url(#fx-cloth${q(it)})` : `url(#fx-${mat(it)})`);

/** A capsule from a (radius ra) to b (radius rb): the basic limb shape. */
function capsule(a: Pt, b: Pt, ra: number, rb: number) {
  const dx = b[0] - a[0], dy = b[1] - a[1], len = Math.hypot(dx, dy) || 1;
  const nx = -dy / len, ny = dx / len;
  const a1: Pt = [a[0] + nx * ra, a[1] + ny * ra], a2: Pt = [a[0] - nx * ra, a[1] - ny * ra];
  const b1: Pt = [b[0] + nx * rb, b[1] + ny * rb], b2: Pt = [b[0] - nx * rb, b[1] - ny * rb];
  return `M${P(a1)} L${P(b1)} A${f(rb)} ${f(rb)} 0 0 0 ${P(b2)} L${P(a2)} A${f(ra)} ${f(ra)} 0 0 0 ${P(a1)} Z`;
}
const lerp = (a: Pt, b: Pt, t: number): Pt => [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t];
const mirror = (p: Pt): Pt => [200 - p[0], p[1]];

function defs() {
  const cloth = CLOTH.map((c, i) => `<linearGradient id="fx-cloth${i}" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="${c}"/><stop offset="1" stop-color="#11131c"/></linearGradient>`).join("");
  return `<defs>
    <radialGradient id="fx-aura" cx="50%" cy="42%" r="58%"><stop offset="0" stop-color="var(--cls)" stop-opacity=".42"/><stop offset="1" stop-color="var(--cls)" stop-opacity="0"/></radialGradient>
    <linearGradient id="fx-plate" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#d3d8e1"/><stop offset=".45" stop-color="#828a9b"/><stop offset="1" stop-color="#343945"/></linearGradient>
    <linearGradient id="fx-mail" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#b9c0c8"/><stop offset="1" stop-color="#3c424c"/></linearGradient>
    <linearGradient id="fx-leather" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#9a6334"/><stop offset="1" stop-color="#3b2312"/></linearGradient>
    <linearGradient id="fx-metal" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#f4f6fa"/><stop offset=".5" stop-color="#aab2c0"/><stop offset="1" stop-color="#596070"/></linearGradient>
    <linearGradient id="fx-wood" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#8a5a32"/><stop offset="1" stop-color="#4a2e17"/></linearGradient>
    <linearGradient id="fx-under" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#3d4456"/><stop offset="1" stop-color="#232837"/></linearGradient>
    <pattern id="fx-rings" width="5" height="4" patternUnits="userSpaceOnUse"><path d="M0 2 a2.5 2 0 0 1 5 0" fill="none" stroke="#1d2129" stroke-width=".7" opacity=".55"/></pattern>
    ${cloth}
  </defs>`;
}

export function drawFigure(o: { race: string; body: "M" | "F"; gear: Gear }): string {
  const B = BUILDS[o.race] || BUILDS.human;
  const fem = o.body === "F";
  const g = o.gear;
  const G = 318;                                   // ground
  const H = 278 * B.h * (fem ? 0.96 : 1);          // height
  const bulk = B.bulk * (fem ? 0.86 : 1);
  const R = 17 * B.head * Math.sqrt(B.h) * (fem ? 0.95 : 1);
  const S = 31 * B.sw * (0.72 + 0.28 * B.h) * (fem ? 0.86 : 1);   // shoulder half-width
  const Wst = 19 * B.hw * (0.75 + 0.25 * B.h) * (fem ? 0.9 : 1);  // waist half-width
  const Hip = 22 * B.hw * (0.75 + 0.25 * B.h) * (fem ? 1.08 : 1); // hip half-width
  const headC: Pt = [100, G - H + R];
  const neckY = headC[1] + R * 0.85;
  const shY = neckY + 9 * B.h + B.hunch;
  const waistY = shY + H * 0.3;
  const hipY = waistY + H * 0.07;
  const kneeY = hipY + (G - hipY) * 0.5;
  const ankleY = G - 9 * B.h;
  // joints (character's right side is on the viewer's left)
  const shL: Pt = [100 - S, shY + 4], elL: Pt = [100 - S - 9 * B.sw, shY + H * 0.17], wrL: Pt = [100 - S - 14 * B.sw, shY + H * 0.32];
  const hpL: Pt = [100 - Hip * 0.55, hipY], knL: Pt = [100 - Hip * 0.6, kneeY], anL: Pt = [100 - Hip * 0.58, ankleY];
  const rU = 7.5 * bulk, rF = 6 * bulk, rH = 6.5 * bulk, rT = 10 * bulk * B.hw, rS = 7.5 * bulk;
  const both = (fn: (m: (p: Pt) => Pt) => string) => fn((p) => p) + fn(mirror);
  const tag = (d: DollSlot, it: FigItem | undefined, path: string, fillv: string, extra = "") =>
    `<path class="part${it ? " eq" : fillv === "transparent" ? " ghost" : ""}" data-part="${d}" d="${path}" fill="${fillv}"${it ? ` style="--c:${QCOLOR[q(it)]}"` : ""}${extra}/>`;
  const rings = (it: FigItem | undefined, path: string) => (it && mat(it) === "mail" ? `<path d="${path}" fill="url(#fx-rings)" pointer-events="none"/>` : "");

  // ---- shapes
  const torso = (pad: number) => `M${P([100 - S - pad, shY - 2 - pad])} Q100 ${f(shY - 9 - pad)} ${P([100 + S + pad, shY - 2 - pad])}
    L${P([100 + Wst + 4 + pad, waistY])} L${P([100 + Hip + pad, hipY + 4])} L${P([100 - Hip - pad, hipY + 4])} L${P([100 - Wst - 4 - pad, waistY])} Z`;
  const arm = (m: (p: Pt) => Pt) => capsule(m(shL), m(elL), rU, rF) + capsule(m(elL), m(wrL), rF, rF * 0.85);
  const leg = (m: (p: Pt) => Pt) => capsule(m(hpL), m(knL), rT, rS * 1.05) + capsule(m(knL), m(anL), rS * 1.05, rS * 0.8);
  const foot = (m: (p: Pt) => Pt, pad = 0) => {
    const a = m(anL), dir = m === mirror ? 1 : -1;
    return `M${P([a[0] - rS - pad, a[1] - 4])} L${P([a[0] + rS + pad, a[1] - 4])} L${P([a[0] + (rS + 4 + pad) * (dir > 0 ? 1.4 : 1), G])} L${P([a[0] - (rS + 4 + pad) * (dir < 0 ? 1.4 : 1), G])} Z`;
  };
  const cloth = (d: DollSlot) => g[d] && mat(g[d]) === "cloth";

  const out: string[] = [];
  out.push(`<ellipse cx="100" cy="${f(H * 0.55 + G - H)}" rx="96" ry="${f(H * 0.62)}" fill="url(#fx-aura)"/>`);
  out.push(`<ellipse cx="100" cy="${f(G + 1)}" rx="${f(40 + S)}" ry="8" fill="#000" opacity=".45"/>`);

  // cloak, behind everything
  const back = g.back;
  const capeBottom = Math.min(G - 6, kneeY + (G - kneeY) * 0.55);
  const capePath = `M${P([100 - S + 2, shY - 4])} L${P([100 + S - 2, shY - 4])} L${P([100 + S + 14, capeBottom])} Q${P([100 + S * 0.4, capeBottom + 6])} 100 ${f(capeBottom - 2)} Q${P([100 - S * 0.4, capeBottom + 6])} ${P([100 - S - 14, capeBottom])} Z`;
  if (back) out.push(tag("back", back, capePath, fill(back, true)));

  // ranged weapon slung on the back
  const rg = g.ranged;
  if (rg) {
    const t = String(rg.type || ""), c = QCOLOR[q(rg)];
    if (/gun|crossbow/.test(t)) out.push(`<path class="part eq wpn" data-part="ranged" style="--c:${c}" fill="url(#fx-wood)" d="${capsule([100 + S + 6, shY - 22], [100 - S - 4, waistY + 18], 4, 3.4)}"/>`);
    else if (/bow/.test(t)) out.push(`<path class="part eq wpn bowp" data-part="ranged" style="--c:${c}" d="M${P([100 + S + 10, shY - 26])} Q${P([100 + S + 40, waistY - 20])} ${P([100 + S - 4, waistY + 34])}"/><path class="string" d="M${P([100 + S + 10, shY - 26])} L${P([100 + S - 4, waistY + 34])}"/>`);
  }

  // long hair falls behind the shoulders
  const [hx, hy] = headC;
  if (fem) out.push(`<path d="M${P([hx - R * 1.02, hy - R * 0.35])} Q${P([hx - R * 1.45, hy + R * 1.4])} ${P([hx - R * 1.15, hy + R * 2.6])} L${P([hx + R * 1.15, hy + R * 2.6])} Q${P([hx + R * 1.45, hy + R * 1.4])} ${P([hx + R * 1.02, hy - R * 0.35])} Z" fill="${B.hair}"/>`);

  // body: skin limbs and plain underclothes, each clickable for its slot
  out.push(`<path class="skin" d="${capsule([100, neckY - 6], [100, shY], 7 * bulk, 8 * bulk)}" fill="${B.skin}"/>`);
  out.push(both((m) => `<path class="skin" d="${arm(m)}" fill="${B.skin}"/>`));
  out.push(tag("legs", undefined, leg((p) => p) + leg(mirror), "url(#fx-under)"));
  out.push(tag("chest", undefined, torso(0), "url(#fx-under)"));
  const feet = g.feet;
  if (B.hooves && !feet) out.push(both((m) => `<path d="${foot(m)}" fill="#2b2119"/>`));
  else if (!feet) out.push(tag("feet", undefined, foot((p) => p) + foot(mirror), B.skin));

  // legs armour
  const legs = g.legs;
  if (legs) {
    const lp = both((m) => capsule(m(hpL), m(knL), rT + 1.5, rS * 1.05 + 1.5) + capsule(m(knL), m(anL), rS * 1.05 + 1.5, rS * 0.8 + 1.5));
    out.push(tag("legs", legs, lp, fill(legs)) + rings(legs, lp));
    if (mat(legs) === "plate") out.push(both((m) => `<circle cx="${f(m(knL)[0])}" cy="${f(knL[1])}" r="${f(rS * 0.95)}" fill="url(#fx-plate)" stroke="${QCOLOR[q(legs)]}" stroke-width="1" pointer-events="none"/>`));
  }
  // boots
  if (feet) {
    const bp = both((m) => capsule(lerp(m(knL), m(anL), 0.45), m(anL), rS + 2, rS * 0.8 + 2) + foot(m, 2));
    out.push(tag("feet", feet, bp, fill(feet)) + rings(feet, bp));
  }
  // chest armour; a cloth chest piece is a robe down to the knees
  const chest = g.chest;
  if (chest) {
    let cp = torso(2.5);
    if (cloth("chest")) cp += `M${P([100 - Wst - 6, waistY])} L${P([100 + Wst + 6, waistY])} L${P([100 + Hip + 14, kneeY + 18])} Q100 ${f(kneeY + 26)} ${P([100 - Hip - 14, kneeY + 18])} Z`;
    out.push(tag("chest", chest, cp, fill(chest)) + rings(chest, cp));
    const c = QCOLOR[q(chest)];
    if (mat(chest) === "plate") out.push(`<path d="M100 ${f(shY - 4)} L100 ${f(waistY - 2)}" stroke="#ffffff" stroke-opacity=".35" stroke-width="2" pointer-events="none"/><path d="M${P([100 - S * 0.7, shY + 18])} Q100 ${f(shY + 30)} ${P([100 + S * 0.7, shY + 18])}" fill="none" stroke="${c}" stroke-width="1" opacity=".7" pointer-events="none"/>`);
    if (mat(chest) === "leather") out.push(`<path d="M${P([96, shY + 6])} L${P([104, shY + 12])} M${P([104, shY + 6])} L${P([96, shY + 12])} M${P([96, shY + 16])} L${P([104, shY + 22])} M${P([104, shY + 16])} L${P([96, shY + 22])}" stroke="#e2c08d" stroke-width="1.2" pointer-events="none"/>`);
  }
  if (chest) {
    const sl = both((m) => capsule(m(shL), lerp(m(shL), m(elL), 1.08), rU + 1.6, rF + 1.8));
    out.push(tag("chest", chest, sl, fill(chest)) + rings(chest, sl));
  }
  // belt
  const waist = g.waist;
  const beltP = `M${P([100 - Wst - 5.5, waistY - 4])} L${P([100 + Wst + 5.5, waistY - 4])} L${P([100 + Wst + 6.5, waistY + 6])} L${P([100 - Wst - 6.5, waistY + 6])} Z`;
  out.push(tag("waist", waist, beltP, waist ? fill(waist) : "#1c1f29"));
  if (waist) out.push(`<rect x="94.5" y="${f(waistY - 3.5)}" width="11" height="9" rx="2" fill="#7a6326" stroke="${QCOLOR[q(waist)]}" stroke-width="1" pointer-events="none"/>`);

  // arms on top: bracers, gloves or bare hands
  const wrist = g.wrist;
  if (wrist) out.push(tag("wrist", wrist, both((m) => capsule(lerp(m(elL), m(wrL), 0.4), m(wrL), rF + 1.8, rF * 0.85 + 1.8)), fill(wrist)));
  else out.push(tag("wrist", undefined, both((m) => capsule(lerp(m(elL), m(wrL), 0.55), m(wrL), rF + 0.5, rF * 0.85 + 0.5)), "transparent"));
  const hands = g.hands;
  const handP = both((m) => { const w = m(wrL); return `M${f(w[0])} ${f(w[1] + 3)} m-${f(rH)} 0 a${f(rH)} ${f(rH * 1.15)} 0 1 0 ${f(rH * 2)} 0 a${f(rH)} ${f(rH * 1.15)} 0 1 0 -${f(rH * 2)} 0 Z`; });
  out.push(tag("hands", hands, handP, hands ? fill(hands) : B.skin));

  // shoulders
  const sh = g.shoulder;
  const big = sh ? ({ plate: 1.45, mail: 1.25, leather: 1.05, cloth: 1 } as Record<string, number>)[mat(sh)] : 1;
  const shP = both((m) => {
    const c = m(shL), r = 11 * bulk * big, dir = m === mirror ? 1 : -1;
    return `M${P([c[0] - dir * r * 0.2, c[1] - r * 0.95])} Q${P([c[0] + dir * r * 1.25, c[1] - r * 0.9])} ${P([c[0] + dir * r * 1.15, c[1] + r * 0.55])} Q${P([c[0] + dir * r * 0.2, c[1] + r * 0.35])} ${P([c[0] - dir * r * 0.65, c[1] + r * 0.1])} Z`;
  });
  out.push(sh ? tag("shoulder", sh, shP, fill(sh)) + rings(sh, shP) : tag("shoulder", undefined, shP, "transparent"));
  if (sh && q(sh) >= 4 && mat(sh) === "plate") out.push(both((m) => { const c = m(shL), dir = m === mirror ? 1 : -1, r = 11 * bulk * big; return `<path d="M${P([c[0] + dir * r * 0.5, c[1] - r * 0.8])} L${P([c[0] + dir * r * 0.95, c[1] - r * 1.55])} L${P([c[0] + dir * r * 1.05, c[1] - r * 0.7])} Z" fill="url(#fx-metal)" stroke="${QCOLOR[q(sh)]}" stroke-width=".8" pointer-events="none"/>`; }));

  // head and race features
  if (B.horns) out.push(`<path d="M${P([hx - R * 0.7, hy - R * 0.55])} Q${P([hx - R * 2.1, hy - R * 0.9])} ${P([hx - R * 1.7, hy - R * 1.9])} Q${P([hx - R * 1.45, hy - R * 1.05])} ${P([hx - R * 0.45, hy - R * 0.9])} Z M${P([hx + R * 0.7, hy - R * 0.55])} Q${P([hx + R * 2.1, hy - R * 0.9])} ${P([hx + R * 1.7, hy - R * 1.9])} Q${P([hx + R * 1.45, hy - R * 1.05])} ${P([hx + R * 0.45, hy - R * 0.9])} Z" fill="#e8dcc0" stroke="#7d705a" stroke-width="1"/>`);
  const ear = B.ears === "long" ? [2.3, 0.75] : B.ears === "troll" ? [2.0, 0.55] : B.ears === "big" ? [1.25, 0.9] : [0.35, 0.4];
  out.push(`<path d="M${P([hx - R * 0.9, hy - R * 0.15])} L${P([hx - R * (0.9 + ear[0]), hy - R * (0.15 + ear[1])])} L${P([hx - R * 0.85, hy + R * 0.3])} Z M${P([hx + R * 0.9, hy - R * 0.15])} L${P([hx + R * (0.9 + ear[0]), hy - R * (0.15 + ear[1])])} L${P([hx + R * 0.85, hy + R * 0.3])} Z" fill="${B.skin}" stroke="#000" stroke-opacity=".25" stroke-width=".8"/>`);
  out.push(`<ellipse class="skin" cx="${f(hx)}" cy="${f(hy)}" rx="${f(R * (B.horns ? 1.05 : 0.92))}" ry="${f(R)}" fill="${B.skin}"/>`);
  if (B.horns) out.push(`<ellipse cx="${f(hx)}" cy="${f(hy + R * 0.55)}" rx="${f(R * 0.55)}" ry="${f(R * 0.38)}" fill="#5c3e28"/>`);
  const eye = B.eyes || "#1b1b1b";
  out.push(`<circle cx="${f(hx - R * 0.33)}" cy="${f(hy - R * 0.05)}" r="${f(R * 0.11)}" fill="${eye}"/><circle cx="${f(hx + R * 0.33)}" cy="${f(hy - R * 0.05)}" r="${f(R * 0.11)}" fill="${eye}"/>`);
  if (B.eyes) out.push(`<circle cx="${f(hx - R * 0.33)}" cy="${f(hy - R * 0.05)}" r="${f(R * 0.3)}" fill="${eye}" opacity=".25"/><circle cx="${f(hx + R * 0.33)}" cy="${f(hy - R * 0.05)}" r="${f(R * 0.3)}" fill="${eye}" opacity=".25"/>`);
  if (B.tusks) out.push(`<path d="M${P([hx - R * 0.42, hy + R * 0.48])} q-${f(R * 0.12)} -${f(R * 0.45)} ${f(R * 0.06)} -${f(R * 0.55)} M${P([hx + R * 0.42, hy + R * 0.48])} q${f(R * 0.12)} -${f(R * 0.45)} -${f(R * 0.06)} -${f(R * 0.55)}" stroke="#f3ead2" stroke-width="${f(R * 0.14)}" stroke-linecap="round" fill="none"/>`);
  if (B.beard && !fem) out.push(`<path d="M${P([hx - R * 0.85, hy + R * 0.1])} Q${P([hx - R * 0.9, hy + R * 1.9])} 100 ${f(hy + R * 2.3)} Q${P([hx + R * 0.9, hy + R * 1.9])} ${P([hx + R * 0.85, hy + R * 0.1])} Q100 ${f(hy + R * 0.7)} ${P([hx - R * 0.85, hy + R * 0.1])} Z" fill="${B.hair}"/>`);
  const head = g.head;
  if (head) {
    const m = mat(head), c = QCOLOR[q(head)];
    let hp: string;
    if (m === "cloth") hp = `M${P([hx - R * 1.12, hy + R * 0.5])} Q${P([hx - R * 1.2, hy - R * 1.35])} ${P([hx, hy - R * 1.3])} Q${P([hx + R * 1.2, hy - R * 1.35])} ${P([hx + R * 1.12, hy + R * 0.5])} L${P([hx + R * 0.75, hy + R * 0.2])} Q${P([hx + R * 0.7, hy - R * 0.62])} ${P([hx, hy - R * 0.68])} Q${P([hx - R * 0.7, hy - R * 0.62])} ${P([hx - R * 0.75, hy + R * 0.2])} Z`;
    else if (m === "plate") hp = `M${P([hx - R * 1.08, hy + R * 0.85])} L${P([hx - R * 1.1, hy - R * 0.3])} Q${P([hx - R * 1.05, hy - R * 1.3])} ${P([hx, hy - R * 1.32])} Q${P([hx + R * 1.05, hy - R * 1.3])} ${P([hx + R * 1.1, hy - R * 0.3])} L${P([hx + R * 1.08, hy + R * 0.85])} L${P([hx + R * 0.55, hy + R * 0.75])} L${P([hx + R * 0.55, hy - R * 0.2])} L${P([hx - R * 0.55, hy - R * 0.2])} L${P([hx - R * 0.55, hy + R * 0.75])} Z`;
    else hp = `M${P([hx - R * 1.04, hy - R * 0.05])} Q${P([hx - R * 1.02, hy - R * 1.25])} ${P([hx, hy - R * 1.24])} Q${P([hx + R * 1.02, hy - R * 1.25])} ${P([hx + R * 1.04, hy - R * 0.05])} L${P([hx + R * 0.8, hy - R * 0.3])} Q${P([hx, hy - R * 0.5])} ${P([hx - R * 0.8, hy - R * 0.3])} Z`;
    out.push(tag("head", head, hp, fill(head)) + rings(head, hp));
    if (m === "plate" && q(head) >= 4) out.push(`<path d="M${P([hx, hy - R * 1.32])} Q${P([hx + R * 0.15, hy - R * 1.9])} ${P([hx + R * 0.6, hy - R * 2.1])}" stroke="${c}" stroke-width="${f(R * 0.2)}" stroke-linecap="round" fill="none" pointer-events="none"/>`);
  }
  const neck = g.neck;
  if (neck) out.push(`<path class="part eq" data-part="neck" style="--c:${QCOLOR[q(neck)]}" fill="${QCOLOR[q(neck)]}" d="M100 ${f(shY + 8)} l4 5 -4 5 -4 -5 Z"/><path d="M${P([100 - 8 * bulk, shY - 4])} Q100 ${f(shY + 8)} ${P([100 + 8 * bulk, shY - 4])}" stroke="#c9a24a" stroke-width="1" fill="none" pointer-events="none"/>`);

  // weapons in the hands: main hand on the character's right (viewer's left)
  const weapon = (it: FigItem | undefined, d: DollSlot, hand: Pt, side: -1 | 1) => {
    if (!it) return "";
    const t = String(it.type || ""), slot = String(it.slot || ""), c = QCOLOR[q(it)];
    const at = (dx: number, dy: number): Pt => [hand[0] + dx * side, hand[1] + dy];
    const cls = `class="part eq wpn" data-part="${d}" style="--c:${c}"`;
    if (slot === "shield" || t === "shield") {
      const sc = 1 + 0.15 * (bulk - 1);
      return `<path ${cls} fill="url(#fx-metal)" d="M${P(at(-4 * sc, -26 * sc))} L${P(at(26 * sc, -20 * sc))} L${P(at(24 * sc, 10 * sc))} Q${P(at(14 * sc, 30 * sc))} ${P(at(4 * sc, 34 * sc))} Q${P(at(-8 * sc, 28 * sc))} ${P(at(-14 * sc, 10 * sc))} L${P(at(-14 * sc, -20 * sc))} Z"/><path d="M${P(at(5 * sc, -18 * sc))} L${P(at(5 * sc, 24 * sc))} M${P(at(-8 * sc, 0))} L${P(at(18 * sc, 0))}" stroke="${c}" stroke-width="2" opacity=".8" pointer-events="none"/>`;
    }
    if (slot === "holdable") return `<circle ${cls} cx="${f(at(6, -4)[0])}" cy="${f(hand[1] - 4)}" r="7" fill="${c}" fill-opacity=".55"/>`;
    if (/staff|polearm/.test(t)) {
      const top = at(-2, -H * 0.42), bot = at(4, H * 0.3);
      const headShape = t === "polearm" ? `<path ${cls} fill="url(#fx-metal)" d="M${P(top)} l${f(10 * side)} 10 l${f(-10 * side)} 18 l${f(-4 * side)} -14 Z"/>` : `<circle ${cls} cx="${f(top[0])}" cy="${f(top[1])}" r="6.5" fill="${c}" fill-opacity=".8"/>`;
      return `<path ${cls} fill="url(#fx-wood)" d="${capsule(top, bot, 2.4, 2.4)}"/>${headShape}`;
    }
    const grip = at(0, 0), tip = at(10, H * 0.27);
    if (/axe/.test(t)) {
      const two = /2/.test(t), blade = lerp(grip, tip, 0.85), sz = two ? 1.5 : 1;
      return `<path ${cls} fill="url(#fx-wood)" d="${capsule(at(0, -6), tip, 2.2, 2.2)}"/><path ${cls} fill="url(#fx-metal)" d="M${P(blade)} q${f(16 * sz * side)} -${f(12 * sz)} ${f(20 * sz * side)} ${f(6 * sz)} q-${f(4 * sz * side)} ${f(14 * sz)} -${f(20 * sz * side)} ${f(10 * sz)} Z"/>`;
    }
    if (/mace/.test(t)) {
      const end = lerp(grip, tip, 0.95), two = /2/.test(t);
      return `<path ${cls} fill="url(#fx-wood)" d="${capsule(at(0, -6), end, 2.2, 2.2)}"/><circle ${cls} cx="${f(end[0])}" cy="${f(end[1])}" r="${two ? 10 : 7.5}" fill="url(#fx-metal)"/>`;
    }
    if (/dagger|fist/.test(t)) return `<path ${cls} fill="url(#fx-metal)" d="M${P(at(-6, 2))} L${P(at(6, 2))} L${P(at(4, 6))} L${P(at(6, 34))} L${P(at(-1, 6))} Z"/>`;
    if (/wand/.test(t)) return `<path ${cls} fill="url(#fx-wood)" d="${capsule(at(0, -2), at(6, 30), 1.8, 1.4)}"/><circle cx="${f(at(6, 30)[0])}" cy="${f(hand[1] + 30)}" r="3" fill="${c}" pointer-events="none"/>`;
    // swords (and anything else with a blade)
    const two = /2/.test(t), len = two ? H * 0.36 : H * 0.27;
    const end = at(9, len);
    return `<path ${cls} fill="url(#fx-metal)" d="M${P(at(-1.8, 7))} L${P(at(3.2, 7))} L${P([end[0] + 1.5 * side, end[1] - 6])} L${P(end)} L${P([end[0] - 4 * side, end[1] - 7])} Z"/><path ${cls} fill="#7a6326" d="M${P(at(-9, 5))} L${P(at(11, 5))} L${P(at(11, 9))} L${P(at(-9, 9))} Z"/>`;
  };
  const mh = g.mainhand, oh = g.offhand && g.offhand.slot !== "twohand" ? g.offhand : undefined;
  out.push(weapon(mh, "mainhand", [wrL[0], wrL[1] + 3], -1));
  out.push(weapon(oh, "offhand", [200 - wrL[0], wrL[1] + 3], 1));
  if (rg && !/gun|crossbow|bow/.test(String(rg.type || ""))) out.push(`<path class="part eq wpn" data-part="ranged" style="--c:${QCOLOR[q(rg)]}" fill="url(#fx-wood)" d="${capsule([100 + Wst + 2, waistY + 2], [100 + Wst + 10, waistY + 26], 2, 1.6)}"/>`);

  return `<svg viewBox="0 0 200 340" class="figure-svg" role="img" aria-label="Your character, drawn with each equipped item">${defs()}${out.join("")}</svg>`;
}
