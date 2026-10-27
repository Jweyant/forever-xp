// "Save to my account" on the BIS planner and talent calculator (only when accounts are on).
// What gets saved is exactly the page's own shareable state from the address bar.
import { accountsOn, me, savePlan, startSignIn } from "./account";

const BIS = /^[A-Za-z0-9=&._,:%-]{1,2048}$/;
const POINTS = /^[0-9-]{0,200}$/;

export function mountSave() {
  const box = document.querySelector<HTMLElement>("[data-save-plan]");
  if (!box || !accountsOn()) return;
  const kind = box.dataset.savePlan === "talents" ? "talents" : "bis";
  const form = box.querySelector<HTMLFormElement>("form")!;
  const input = box.querySelector<HTMLInputElement>("input")!;
  const signin = box.querySelector<HTMLAnchorElement>("[data-save-signin]")!;
  const toast = (m: string) => (window as unknown as { fxpToast?: (m: string) => void }).fxpToast?.(m);

  const data = () => {
    const h = location.hash.slice(1);
    if (kind === "bis") return BIS.test(h) ? h : null;
    const slug = location.pathname.split("/").filter(Boolean)[1] || "";
    return /^[a-z]+$/.test(slug) && POINTS.test(h) ? `${slug}#${h}` : null;
  };

  me().then((who) => {
    if (who === "off") return;
    box.hidden = false;
    if (!who) {
      form.hidden = true; signin.hidden = false;
      signin.href = "/account/";
      signin.addEventListener("click", startSignIn);
    }
  });

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const d = data();
    const name = input.value.trim();
    if (!d) { toast(kind === "bis" ? "Pick some gear first." : "Spend some points first."); return; }
    if (!name) { input.focus(); toast("Give it a name first."); return; }
    const btn = form.querySelector("button")!;
    btn.disabled = true;
    try { await savePlan(kind, name.slice(0, 60), d); input.value = ""; toast("Saved to your account."); }
    catch (err) {
      const code = err instanceof Error ? err.message : "";
      toast(code === "too-many-plans" ? "You have 50 saved plans. Delete some on your account page first." : code === "signed-out" ? "You've been signed out. Sign in again to save." : "Couldn't save that. Try again.");
    } finally { btn.disabled = false; }
  });
}
