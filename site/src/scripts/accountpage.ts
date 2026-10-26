// The /account/ page: saved plans, sign out, delete account. All server text goes in with
// textContent; plan links are rebuilt by planHref() from checked parts.
import { me, listPlans, deletePlan, signOut, deleteAccount, planHref, type Plan } from "./account";

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

function showEmpty() {
  const n = $("[data-plans]").children.length;
  $("[data-empty]").hidden = n > 0;
  $("[data-table]").hidden = n === 0;
}

async function load() {
  const who = await me();
  if (who === "off") { state.textContent = "Accounts aren't switched on yet. Everything on the site still works without one."; return; }
  state.hidden = true;
  if (!who) { $("[data-signed-out]").hidden = false; return; }
  $("[data-signed-in]").hidden = false;
  $("[data-name]").textContent = who.name;
  try {
    const plans = await listPlans();
    $("[data-plans]").replaceChildren(...plans.map(row));
  } catch { toast("Couldn't load your plans."); }
  showEmpty();
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
