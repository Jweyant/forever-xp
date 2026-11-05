// The /send/ page: a pasted /fscout export (or the ForeverScout.lua file) goes to the upload server.
// Plain text body and no custom headers, so the browser sends it without a preflight; the server only
// accepts this site's origin. Everything shown back goes in with textContent.
const UPLOAD = "https://upload.forever-xp.com/v1/send";
const MAX_BYTES = 4 * 1024 * 1024;
const KEY = "fxp-scout-install";

const root = document.getElementById("send-page")!;
const box = root.querySelector<HTMLTextAreaElement>("textarea")!;
const button = root.querySelector<HTMLButtonElement>("[data-send]")!;
const file = root.querySelector<HTMLInputElement>("[data-file]")!;
const status = root.querySelector<HTMLElement>("[data-status]")!;

const hex = (bytes: number) =>
  Array.from(crypto.getRandomValues(new Uint8Array(bytes)), (b) => b.toString(16).padStart(2, "0")).join("");

// One random id per browser, so a player's characters and sends count as one scout on the leaderboard.
function installId(): string {
  try {
    const saved = localStorage.getItem(KEY);
    if (saved && /^[0-9a-f]{32}$/.test(saved)) return saved;
    const id = hex(16);
    localStorage.setItem(KEY, id);
    return id;
  } catch {
    return hex(16);
  }
}

function looksRight(text: string) {
  return /^\s*FSCOUT1:\{/.test(text) || /^\s*ForeverScoutDB\s*=\s*\{/.test(text);
}

function count(text: string) {
  return (text.match(/(?:\bstart=|\["start"\]\s*=)/g) || []).length;
}

function say(msg: string, bad = false) {
  status.textContent = msg;
  status.classList.toggle("bad", bad);
}

function check() {
  const text = box.value.trim();
  button.disabled = !text;
  if (!text) return say("");
  if (!looksRight(text)) return say("That doesn't look like a ForeverScout export. It starts with FSCOUT1:", true);
  if (new Blob([text]).size > MAX_BYTES) return say("That's too big to send in one go. Send the ForeverScout.lua file from the uploader instead, or export more often.", true);
  const n = count(text);
  say(`Ready: ${n} session${n === 1 ? "" : "s"}.`);
}

async function send() {
  const text = box.value.trim();
  if (!text || !looksRight(text)) return check();
  button.disabled = true;
  say("Sending…");
  try {
    const url = `${UPLOAD}?install=${installId()}&slot=${hex(8)}`;
    const res = await fetch(url, { method: "POST", body: text, credentials: "omit" });
    if (res.ok) {
      const n = count(text);
      box.value = "";
      say(`Thanks! ${n} session${n === 1 ? "" : "s"} sent. Your quest times and drops show up on the site within the hour.`);
      return;
    }
    const why: Record<number, string> = {
      413: "That's too big to send in one go.",
      422: "That doesn't look like a ForeverScout export.",
      429: "Too many sends from your network today. Try again tomorrow.",
    };
    say(why[res.status] || `Couldn't send (error ${res.status}). Try again in a minute.`, true);
  } catch {
    say("Couldn't reach forever-xp.com. Check your connection and try again.", true);
  }
  button.disabled = !box.value.trim();
}

box.addEventListener("input", check);
button.addEventListener("click", send);
file.addEventListener("change", async () => {
  const f = file.files?.[0];
  if (!f) return;
  if (f.size > MAX_BYTES) return say("That file is too big to send here. The optional uploader app can send it.", true);
  box.value = await f.text();
  check();
});
