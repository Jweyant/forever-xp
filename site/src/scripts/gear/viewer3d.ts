// The "View in 3D" dialog on the BIS planner: an iframe of viewer.forever-xp.com (viewer/ in
// this repo), which draws the character with Wowhead's model viewer on its own isolated origin.
// Only numbers cross the boundary — race and body as the viewer's model ids, gear as
// [slot, displayId] pairs — and the viewer checks the sender and every value again on its side.
import { SITE } from "../../config";
import type { DollSlot, Item } from "./model";

const ORIGIN = new URL(SITE.viewer3d).origin;

// Model-viewer race ids (model = race * 2 - 1 + gender). Skyborne is Forever's own race with no
// public model yet; it borrows the human one and the dialog says so.
const RACE_ID: Record<string, number> = {
  human: 1, orc: 2, dwarf: 3, nightelf: 4, undead: 5, tauren: 6, gnome: 7, troll: 8, skyborne: 1,
};
// Our doll slots -> model-viewer item slots. Rings, trinkets and necks don't display.
const ZAM_SLOT: Partial<Record<DollSlot, number>> = {
  head: 1, shoulder: 3, chest: 5, waist: 6, legs: 7, feet: 8, wrist: 9, hands: 10,
  back: 16, mainhand: 21, offhand: 22, ranged: 15,
};

let frame: HTMLIFrameElement | null = null;
let ready = false;
let queued: object | null = null;

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

/** Send the current character to the viewer (queued until its ready ping). */
export function send3d(race: string, body: "M" | "F", gear: Partial<Record<DollSlot, number>>,
  byId: Map<number, Item>): void {
  const dlg = document.getElementById("g-3d") as HTMLDialogElement | null;
  if (!dlg || !dlg.open || !frame) return;
  const { msg, missing } = payload(race, body, gear, byId);
  const note = document.getElementById("g-3d-note");
  if (note) {
    const parts = [];
    if (race === "skyborne") parts.push("Skyborne has no public 3D model yet, so a human stands in.");
    if (missing.length) parts.push(`No 3D art yet for ${missing.length} item${missing.length === 1 ? "" : "s"}: ${missing.join(", ")}.`);
    note.textContent = parts.join(" ");
    note.hidden = !parts.length;
  }
  if (ready && frame.contentWindow) frame.contentWindow.postMessage(msg, ORIGIN);
  else queued = msg;
}

/** Open the dialog; the iframe only loads (and zam code only runs) on first use. */
export function open3d(resend: () => void): void {
  const dlg = document.getElementById("g-3d") as HTMLDialogElement | null;
  if (!dlg) return;
  if (!frame) {
    frame = document.getElementById("g-3d-frame") as HTMLIFrameElement | null;
    if (!frame) return;
    // The viewer pings when it can take gear; nothing else is accepted from it.
    window.addEventListener("message", (e) => {
      if (e.origin !== ORIGIN || !frame || e.source !== frame.contentWindow) return;
      if ((e.data as { t?: string } | null)?.t !== "fxp3d:ready") return;
      ready = true;
      if (queued && frame.contentWindow) { frame.contentWindow.postMessage(queued, ORIGIN); queued = null; }
    });
    frame.src = SITE.viewer3d;
  }
  dlg.showModal();
  resend();
}
