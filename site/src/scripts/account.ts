// Optional Forever XP accounts (docs/accounts.md): talks to /api/* on this same site.
// Everything that comes back is shown with textContent; links to saved plans are rebuilt from
// allow-listed parts, never taken as given.

export interface Plan { id: string; kind: "bis" | "talents"; name: string; data: string; updated: number }
export type Me = { name: string } | null;
/** A ForeverScout install linked to the account (shown on the leaderboard under `shown`). */
export interface ScoutClaim { id: string; handle: string; name: string | null; shown: string; visible: boolean }

const CLASSES = new Set(["warrior", "paladin", "hunter", "rogue", "priest", "shaman", "mage", "warlock", "druid"]);
const BIS = /^[A-Za-z0-9=&._,:%-]{1,2048}$/;
const TALENTS = /^([a-z]+)#([0-9-]{0,200})$/;
const PLAN_ID = /^[A-Za-z0-9_-]{16}$/;
export const CLAIM_CODE = /^[0-9a-f]{32}$/;
const CLAIM_ID = /^[0-9a-f]{64}$/;
const HANDLE = /^Scout [0-9a-f]{6}$/;
const BOARD_NAME = /^[A-Za-z0-9 _'-]{2,20}$/;
const CLAIM_KEY = "fxp-claim";

export const accountsOn = () => document.documentElement.dataset.accounts === "on";

let mePromise: Promise<Me | "off"> | null = null;
/** The signed-in player, null when signed out, "off" when accounts aren't available. */
export function me(): Promise<Me | "off"> {
  mePromise ??= fetch("/api/me", { credentials: "same-origin", headers: { Accept: "application/json" } })
    .then(async (r) => {
      if (r.status === 401) return null;
      if (!r.ok) return "off" as const;
      const j = await r.json();
      return typeof j?.name === "string" ? { name: j.name.slice(0, 60) } : "off";
    })
    .catch(() => "off" as const);
  return mePromise;
}

async function send(method: string, path: string, body?: unknown) {
  const r = await fetch(path, {
    method, credentials: "same-origin",
    headers: body === undefined ? { Accept: "application/json" } : { "Content-Type": "application/json", Accept: "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(typeof j?.error === "string" ? j.error : `http-${r.status}`);
  return j;
}

export async function listPlans(): Promise<Plan[]> {
  const j = await send("GET", "/api/plans");
  return Array.isArray(j?.plans) ? j.plans.filter((p: Plan) => PLAN_ID.test(String(p?.id)) && (p.kind === "bis" || p.kind === "talents")) : [];
}
export const savePlan = (kind: Plan["kind"], name: string, data: string) => send("POST", "/api/plans", { kind, name, data });
export const deletePlan = (id: string) => (PLAN_ID.test(id) ? send("DELETE", `/api/plans/${id}`) : Promise.reject(new Error("bad-id")));
export const signOut = () => send("POST", "/api/auth/logout", {});
export const deleteAccount = () => send("DELETE", "/api/me");

export async function listScouts(): Promise<ScoutClaim[]> {
  const j = await send("GET", "/api/scouts");
  const rows: ScoutClaim[] = Array.isArray(j?.scouts) ? j.scouts : [];
  return rows.filter((c) => CLAIM_ID.test(String(c?.id)) && HANDLE.test(String(c?.handle)) && BOARD_NAME.test(String(c?.shown)))
    .map((c) => ({ id: c.id, handle: c.handle, name: typeof c.name === "string" ? c.name.slice(0, 20) : null, shown: c.shown, visible: c.visible === true }));
}
export const claimScout = (code: string, name?: string) =>
  CLAIM_CODE.test(code) ? send("POST", "/api/scouts/claim", name ? { code, name } : { code }) : Promise.reject(new Error("bad-code"));
export const updateScout = (id: string, patch: { name?: string | null; visible?: boolean }) =>
  CLAIM_ID.test(id) ? send("PATCH", `/api/scouts/claim/${id}`, patch) : Promise.reject(new Error("bad-id"));
export const unlinkScout = (id: string) => (CLAIM_ID.test(id) ? send("DELETE", `/api/scouts/claim/${id}`) : Promise.reject(new Error("bad-id")));

/** The uploader opens /account/?claim=<install id>. The value is untrusted: exactly 32 lowercase hex
 * characters or it is ignored. It is moved out of the address bar into sessionStorage (it has to
 * survive the Discord sign-in round trip) and never shown or sent anywhere except the claim call. */
export function pendingClaim(): string | null {
  const fromUrl = new URLSearchParams(location.search).get("claim");
  if (fromUrl !== null) {
    const params = new URLSearchParams(location.search);
    params.delete("claim");
    const rest = params.toString();
    history.replaceState(null, "", location.pathname + (rest ? `?${rest}` : "") + location.hash);
    if (CLAIM_CODE.test(fromUrl)) { try { sessionStorage.setItem(CLAIM_KEY, fromUrl); } catch { /* storage blocked */ } return fromUrl; }
  }
  try {
    const saved = sessionStorage.getItem(CLAIM_KEY);
    return saved && CLAIM_CODE.test(saved) ? saved : null;
  } catch { return null; }
}
export function forgetClaim() { try { sessionStorage.removeItem(CLAIM_KEY); } catch { /* storage blocked */ } }

/** "Scout a1b2c3": the same one-way name the uploader shows (first 6 hex of sha256("forever-xp scout|" + id)). */
export async function scoutHandle(code: string): Promise<string> {
  const d = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(`forever-xp scout|${code}`));
  return "Scout " + [...new Uint8Array(d)].slice(0, 3).map((b) => b.toString(16).padStart(2, "0")).join("");
}

/** Where a saved plan opens, rebuilt from checked parts. */
export function planHref(p: Plan): string | null {
  if (p.kind === "bis" && BIS.test(p.data)) return `/bis/#${p.data}`;
  const m = p.kind === "talents" ? TALENTS.exec(p.data) : null;
  if (m && CLASSES.has(m[1])) return `/talents/${m[1]}/${m[2] ? `#${m[2]}` : ""}`;
  return null;
}

/** Start Discord sign-in and come back to this page (the server checks the path). It's a form POST,
 * so the sign-in address is never a plain link. Use as a click handler on a link to /account/. */
export function startSignIn(e?: Event) {
  e?.preventDefault();
  rememberHash();
  const form = document.createElement("form");
  form.method = "post";
  form.action = "/api/auth/login";
  form.hidden = true;
  const back = document.createElement("input");
  back.type = "hidden";
  back.name = "return";
  back.value = location.pathname;
  form.append(back);
  document.body.append(form);
  form.submit();
}

/** The talent calculator keeps its build in the hash, which a sign-in round trip drops. */
function rememberHash() {
  try { sessionStorage.setItem("fxp-signin", JSON.stringify({ path: location.pathname, hash: location.hash })); } catch { /* storage blocked */ }
}

/** After coming back from sign-in: put the hash back and tidy the address. Returns the outcome
 * (the same answer to every caller on the page). */
let outcome: "ok" | "failed" | "cancelled" | null | undefined;
export function afterSignIn(): "ok" | "failed" | "cancelled" | null {
  if (outcome !== undefined) return outcome;
  const flag = new URLSearchParams(location.search).get("signin");
  if (flag !== "ok" && flag !== "failed" && flag !== "cancelled") return (outcome = null);
  outcome = flag;
  let hash = location.hash;
  try {
    const saved = JSON.parse(sessionStorage.getItem("fxp-signin") || "null");
    sessionStorage.removeItem("fxp-signin");
    if (!hash && saved && saved.path === location.pathname && typeof saved.hash === "string" && /^#[A-Za-z0-9=&._,:%-]*$/.test(saved.hash)) hash = saved.hash;
  } catch { /* storage blocked */ }
  history.replaceState(null, "", location.pathname + hash);
  return flag;
}
