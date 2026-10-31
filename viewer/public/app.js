// Draws the character. Gear arrives as numbers only: from the URL hash (standalone use, e.g.
// /#r=8&g=0&i=1:30606,5:30990) or by postMessage from the BIS planner (gear_params.js checks
// both the sender and the values).
import { generateModels } from "./vendor/wow-model-viewer/index.js";
import { parseGear, parseHash, parentAllowed } from "./gear_params.js";

const model = document.getElementById("model");
const note = document.getElementById("note");
let current = ""; // what's on screen, to skip redraws of the same gear
let busy = null;  // the draw in flight; the next request waits for it

function say(text) {
  note.textContent = text || "";
  note.hidden = !text;
}

async function draw(gear) {
  if (!gear) return;
  const key = JSON.stringify(gear);
  if (key === current) return;
  while (busy) await busy; // one draw at a time; latest request wins
  if (key === current) return;
  current = key;
  busy = (async () => {
    say("");
    model.replaceChildren();
    const character = {
      race: gear.race, gender: gear.gender,
      skin: 1, face: 0, hairStyle: 1, hairColor: 1, facialStyle: 0,
      items: gear.items,
    };
    const aspect = model.clientHeight ? model.clientWidth / model.clientHeight : 1;
    try {
      try {
        await generateModels(aspect, "#model", character, "classic");
      } catch {
        // Some models have no customization meta; draw the plain model instead.
        await generateModels(aspect, "#model", { ...character, noCharCustomization: true }, "classic");
      }
    } catch (e) {
      console.error("viewer:", e);
      say("The 3D model couldn't load. The model files may be unreachable right now.");
      current = "";
    }
  })();
  await busy;
  busy = null;
}

window.addEventListener("message", (e) => {
  if (!parentAllowed(e.origin) || !e.data || e.data.t !== "fxp3d") return;
  draw(parseGear(e.data));
});
window.addEventListener("hashchange", () => draw(parseHash(location.hash)));

if (location.hash.length > 1) draw(parseHash(location.hash));
// Tell the embedding page it can send gear now. No data goes out, so any parent may hear it.
if (window.parent !== window) window.parent.postMessage({ t: "fxp3d:ready" }, "*");
