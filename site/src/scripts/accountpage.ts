// The /account/ page: saved plans, sign out, delete account. All server text goes in with
// textContent; plan links are rebuilt by planHref() from checked parts.
import {
  accountsOn, me, listPlans, deletePlan, signOut, deleteAccount, planHref, type Plan,
  listScouts, claimScout, updateScout, unlinkScout, pendingClaim, forgetClaim, scoutHandle, type ScoutClaim,
} from "./account";

const root = document.getElementById("acct-page")!;
const $ = <T extends HTMLElement>(s: string) => root.querySelector<T>(s)!;
const state = $("[data-state]");
const toast = (m: string) => (window as unknown as { fxpToast?: (m: string) => void }).fxpToast?.(m);

function row(p: Plan) {
  const tr = document.createElement("tr");
  const name = document.createElement("td");
  const href = planHref(p);
  if (href) { const a = document.createElement("a"); a.href = href; a.textContent = p.name; name.append(a); }
  else name.textContent = p.name;
  const kind = document.createElement("td"); kind.className = "kind"; kind.textContent = p.kind === "bis" ? "BIS plan" : "Talent build";
  const when = document.createElement("td"); when.className = "when";
  const t = Number(p.updated);
  when.textContent = Number.isFinite(t) ? new Date(t * 1000).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" }) : "";
  const del = document.createElement("td");
  const b = document.createElement("button"); b.type = "button"; b.className = "link"; b.textContent = "Delete";
  b.addEventListener("click", async () => {
    b.disabled = true;
    try { await deletePlan(p.id); tr.remove(); toast("Deleted."); showEmpty(); } catch { b.disabled = false; toast("Couldn't delete that. Try again."); }
  });
  del.append(b);
  tr.append(name, kind, when, del);
  return tr;
}

const ERRORS: Record<string, string> = {
  "already-claimed": "That install is already linked to another account.",
  "too-many-claims": "You can link up to 3 installs. Unlink one first.",
  "bad-name": "Names are 3-20 letters, numbers, spaces, _ ' or -.",
};
const why = (e: unknown, fallback: string) => ERRORS[(e as Error)?.message] ?? fallback;

function scoutRow(c: ScoutClaim) {
  const tr = document.createElement("tr");
  const cell = (el?: Node) => { const td = document.createElement("td"); if (el) td.append(el); tr.append(td); return td; };
  cell().textContent = c.handle;
  const shown = cell(); shown.textContent = c.shown;
  const input = document.createElement("input");
  input.type = "text"; input.maxLength = 20; input.autocomplete = "off"; input.spellcheck = false;
  input.placeholder = "Use my Discord name"; input.value = c.name ?? "";
  const save = document.createElement("button"); save.type = "button"; save.className = "link"; save.textContent = "Save";
  save.addEventListener("click", async () => {
    save.disabled = true;
    try { await updateScout(c.id, { name: input.value.trim() || null }); toast("Saved."); await loadScouts(); }
    catch (e) { save.disabled = false; toast(why(e, "Couldn't save that. Try again.")); }
  });
  const nameCell = cell(input); nameCell.append(" ", save);
  const vis = document.createElement("input"); vis.type = "checkbox"; vis.checked = c.visible; vis.setAttribute("aria-label", `Show ${c.handle} on the leaderboard`);
  vis.addEventListener("change", async () => {
    try { await updateScout(c.id, { visible: vis.checked }); toast(vis.checked ? "Shown on the board." : "Hidden from the board."); }
    catch { vis.checked = !vis.checked; toast("Couldn't change that. Try again."); }
  });
  cell(vis);
  const un = document.createElement("button"); un.type = "button"; un.className = "link"; un.textContent = "Unlink";
  un.addEventListener("click", async () => {
    un.disabled = true;
    try { await unlinkScout(c.id); toast("Unlinked. Your logs stay, but you're off the board."); await loadScouts(); }
    catch { un.disabled = false; toast("Couldn't unlink that. Try again."); }
  });
  cell(un);
  return tr;
}

async function loadScouts() {
  let list: ScoutClaim[] = [];
  try { list = await listScouts(); } catch { toast("Couldn't load your scouting."); }
  $("[data-scouts]").replaceChildren(...list.map(scoutRow));
  $("[data-scout-table]").hidden = list.length === 0;
  $("[data-scout-empty]").hidden = list.length > 0 || !$("[data-pending]").hidden;
}

async function offerClaim(code: string) {
  const box = $("[data-pending]");
  $("[data-pending-handle]").textContent = await scoutHandle(code);
  box.hidden = false;
  $("[data-scout-empty]").hidden = true;
  const done = () => { forgetClaim(); box.hidden = true; return loadScouts(); };
  $("[data-link]").addEventListener("click", async () => {
    const name = $<HTMLInputElement>("[data-pending-name]").value.trim();
    try { await claimScout(code, name || undefined); toast("Linked. The board updates within six hours."); await done(); }
    catch (e) { toast(why(e, "Couldn't link that. Try again.")); if ((e as Error)?.message === "already-claimed") await done(); }
  });
  $("[data-skip]").addEventListener("click", () => { void done(); });
}

function showEmpty() {
  const n = $("[data-plans]").children.length;
  $("[data-empty]").hidden = n > 0;
  $("[data-table]").hidden = n === 0;
}

async function load() {
  const who = accountsOn() ? await me() : "off";
  if (who === "off") { state.textContent = "Accounts aren't switched on yet. Everything on the site still works without one."; return; }
  state.hidden = true;
  const code = pendingClaim();
  if (!who) { $("[data-signed-out]").hidden = false; $("[data-claim-note]").hidden = !code; return; }
  $("[data-signed-in]").hidden = false;
  $("[data-name]").textContent = who.name;
  try {
    const plans = await listPlans();
    $("[data-plans]").replaceChildren(...plans.map(row));
  } catch { toast("Couldn't load your plans."); }
  showEmpty();
  await loadScouts();
  if (code) await offerClaim(code);
}

$("[data-signout]").addEventListener("click", async () => {
  try { await signOut(); } catch { /* already signed out */ }
  location.assign("/");
});
let armed = false;
const delBtn = $<HTMLButtonElement>("[data-delete]");
delBtn.addEventListener("click", async () => {
  if (!armed) { armed = true; delBtn.textContent = "Delete everything"; $("[data-delete-note]").hidden = false; return; }
  delBtn.disabled = true;
  try { await deleteAccount(); location.assign("/?account=deleted"); }
  catch { delBtn.disabled = false; toast("Couldn't delete your account. Try again."); }
});

load();
