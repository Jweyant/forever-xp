// Hostile-input tests for the viewer: the /zam/ proxy path allow-list and the gear parameters.
import { test } from "node:test";
import assert from "node:assert/strict";
import { zamPath } from "../src/index.js";
import { parseGear, parseHash, parentAllowed } from "../public/gear_params.js";

const zam = (path) => zamPath(new URL(`https://viewer.example${path}`));

test("the proxy serves only the model viewer's files", () => {
  assert.equal(zam("/zam/modelviewer/classic/viewer/viewer.min.js?3ee7ec5121"),
    "/modelviewer/classic/viewer/viewer.min.js?3ee7ec5121");
  assert.equal(zam("/zam/modelviewer/classic/meta/charactercustomization/15.json"),
    "/modelviewer/classic/meta/charactercustomization/15.json");
  assert.equal(zam("/zam/modelviewer/classic/mo3/character/troll/male.mo3"),
    "/modelviewer/classic/mo3/character/troll/male.mo3");
});

test("everything else on the host is refused", () => {
  for (const p of [
    "/zam/images/logo.png",                       // outside /modelviewer/
    "/zam/modelviewer/classic/../../js/x.js",     // traversal
    "/zam/modelviewer/classic//etc/passwd",       // double slash
    "/zam/modelviewer/classic/viewer/viewer.php", // extension not on the list
    "/zam/modelviewer/classic/meta/a.json?q=<script>", // hostile query
    "/zam/modelviewer/future/viewer/viewer.min.js",    // env not on the list
    "/zam/modelviewer/classic/a%2F..%2Fb.js",          // encoded traversal (no % allowed)
  ]) assert.equal(zam(p), null, p);
});

test("gear parameters only pass as clean numbers", () => {
  assert.deepEqual(parseGear({ race: 8, gender: 0, items: [[1, 30606], [5, "30990"]] }),
    { race: 8, gender: 0, items: [[1, 30606], [5, 30990]] });
  assert.deepEqual(parseGear({ race: "8", gender: 9, items: "x" }), { race: 8, gender: 0, items: [] });
  assert.equal(parseGear({ race: 0 }), null);
  assert.equal(parseGear({ race: "__proto__" }), null);
  assert.equal(parseGear(null), null);
  const g = parseGear({ race: 1, gender: 1, items: [[2, 5], [1, -4], [99, 5], [1, 1e9], ["a", "b"], [1, 7], [1, 8]] });
  assert.deepEqual(g.items, [[1, 7]]); // bad slots, bad ids and duplicates dropped
});

test("the hash form parses the same way", () => {
  assert.deepEqual(parseHash("#r=8&g=0&i=1:30606,5:30990"),
    { race: 8, gender: 0, items: [[1, 30606], [5, 30990]] });
  assert.equal(parseHash("#r=<img onerror=x>&g=0"), null);
});

test("only the site (and its previews) may send gear", () => {
  assert.equal(parentAllowed("https://forever-xp.com"), true);
  assert.equal(parentAllowed("https://www.forever-xp.com"), true);
  assert.equal(parentAllowed("https://abc123.forever-xp.pages.dev"), true);
  for (const o of ["https://evil.com", "http://forever-xp.com", "https://forever-xp.com.evil.com",
    "https://xforever-xp.pages.dev", "null", ""]) assert.equal(parentAllowed(o), false, o);
});
