// The 3D view on the BIS planner: an iframe of viewer.forever-xp.com (viewer/ in this repo),
// which draws the character with Wowhead's model viewer on its own isolated origin. The iframe
// sits over the drawn figure in the character sheet — it lives outside #g-doll because the doll
// re-renders wholesale (and moving an iframe in the DOM reloads it), so this module keeps it
// aligned with the figure cell instead. Only numbers cross the boundary — race and body as the
// viewer's model ids, gear as [slot, displayId] pairs — and the viewer checks the sender and
// every value again on its side.
import { SITE } from "../../config";
import type { DollSlot, Item } from "./model";

const ORIGIN = new URL(SITE.viewer3d).origin;

// Model-viewer race ids (model = race * 2 - 1 + gender). Skyborne is Forever's own race with no
// public model yet; it borrows the human one and the note under the sheet says so.
const RACE_ID: Record<string, number> = {
  human: 1, orc: 2, dwarf: 3, nightelf: 4, undead: 5, tauren: 6, gnome: 7, troll: 8, skyborne: 1,
};
// Our doll slots -> model-viewer item slots. Rings, trinkets and necks don't display.
const ZAM_SLOT: Partial<Record<DollSlot, number>> = {
  head: 1, shoulder: 3, chest: 5, waist: 6, legs: 7, feet: 8, wrist: 9, hands: 10,
  back: 16, mainhand: 21, offhand: 22, ranged: 15,
};

let on = false;
let ready = false;
let queued: object | null = null;
let answered = false; // the viewer has pinged at least once (so the worker is deployed)
const $ = (id: string) => document.getElementById(id);
const frame = () => $("g-3d-frame") as HTMLIFrameElement | null;

/** Keep the iframe over the paperdoll's figure cell (called after renders and on resize). */
function place(): void {
  const f = frame(), wrap = document.querySelector(".doll-wrap"), fig = document.querySelector("#g-doll .figure");
  if (!f || !wrap || !fig) return;
  const w = wrap.getBoundingClientRect(), r = fig.getBoundingClientRect();
  f.style.left = `${r.left - w.left}px`;
  f.style.top = `${r.top - w.top}px`;
  f.style.width = `${r.width}px`;
  f.style.height = `${r.height}px`;
}

function payload(race: string, body: "M" | "F", gear: Partial<Record<DollSlot, number>>,
  byId: Map<number, Item>): { msg: object; missing: string[] } {
  const items: [number, number][] = [];
  const missing: string[] = [];
  for (const [doll, slot] of Object.entries(ZAM_SLOT) as [DollSlot, number][]) {
    const id = gear[doll];
    const it = id ? byId.get(Number(id)) : undefined;
    if (!it) continue;
    const did = Math.trunc(Number(it.did) || 0);
    if (!did) { missing.push(it.name); continue; }
    // Guns and wands hang on the other hip; shields and held items sit in the off hand.
    const s = doll === "ranged" && Number(it.inv) === 26 ? 26 : slot;
    items.push([s, did]);
  }
  const msg = { t: "fxp3d", race: RACE_ID[race] || 1, gender: body === "F" ? 1 : 0, items };
  return { msg, missing };
}

function note(race: string, missing: string[]): void {
  const el = $("g-3d-note");
  if (!el) return;
  const parts = [];
  if (on && !answered) parts.push("If the model stays blank, the 3D viewer isn't reachable right now.");
  if (race === "skyborne") parts.push("Skyborne has no public 3D model yet, so a human stands in.");
  if (missing.length) parts.push(`No 3D art yet for ${missing.length} item${missing.length === 1 ? "" : "s"}: ${missing.join(", ")}.`);
  if (on && !parts.length) parts.push("Drag to turn the character. Rings, trinkets and necks don't display.");
  el.textContent = parts.join(" ");
  el.hidden = !on || !parts.length;
}

/** Send the current character to the viewer (no-op while the 3D view is off). */
export function send3d(race: string, body: "M" | "F", gear: Partial<Record<DollSlot, number>>,
  byId: Map<number, Item>): void {
  const f = frame();
  if (!on || !f) return;
  place();
  const { msg, missing } = payload(race, body, gear, byId);
  note(race, missing);
  if (ready && f.contentWindow) f.contentWindow.postMessage(msg, ORIGIN);
  else queued = msg;
}

/** Flip the 3D view; the iframe only loads (and zam code only runs) on first use. */
export function toggle3d(resend: () => void): boolean {
  const f = frame();
  if (!f) return false;
  on = !on;
  if (on && !f.src) {
    // The viewer pings when it can take gear; nothing else is accepted from it.
    window.addEventListener("message", (e) => {
      if (e.origin !== ORIGIN || e.source !== frame()?.contentWindow) return;
      if ((e.data as { t?: string } | null)?.t !== "fxp3d:ready") return;
      ready = true;
      answered = true;
      const w = frame()?.contentWindow;
      if (queued && w) { w.postMessage(queued, ORIGIN); queued = null; }
    });
    window.addEventListener("resize", place);
    f.src = SITE.viewer3d;
  }
  f.hidden = !on;
  document.querySelector(".doll-wrap")?.classList.toggle("mode3d", on);
  $("g-3d-open")?.setAttribute("aria-pressed", String(on));
  if (!on) { const el = $("g-3d-note"); if (el) el.hidden = true; }
  resend();
  return on;
}
