"""Offline tests for tools/indexnow.py: which pages get submitted after a deploy."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import indexnow  # noqa: E402

PAGE = '<html><head><script type="module" src="/_astro/site.AbC123.js"></script></head><body><h1>{}</h1></body></html>'


def build(root, pages):
    """A fake dist/ with a sitemap listing `pages` (path -> heading)."""
    d = Path(root)
    for path, heading in pages.items():
        f = d / path.lstrip("/") / "index.html"
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(PAGE.format(heading))
    locs = "".join(f"<url><loc>https://forever-xp.com{p}</loc></url>" for p in pages)
    (d / "sitemap-0.xml").write_text(f'<?xml version="1.0"?><urlset>{locs}</urlset>')
    (d / "sitemap-index.xml").write_text("<sitemapindex><sitemap><loc>https://forever-xp.com/sitemap-0.xml</loc></sitemap></sitemapindex>")
    (d / f"{indexnow.KEY}.txt").write_text(indexnow.KEY)
    return d


class Fingerprints(unittest.TestCase):
    def test_renamed_bundles_and_inline_scripts_do_not_count_as_changes(self):
        a = PAGE.format("Changes")
        b = a.replace("site.AbC123.js", "site.ZzZ999.js").replace("</head>", "<script>console.log(1)</script></head>")
        self.assertEqual(indexnow.fingerprint(a), indexnow.fingerprint(b))

    def test_content_changes_count(self):
        self.assertNotEqual(indexnow.fingerprint(PAGE.format("A")), indexnow.fingerprint(PAGE.format("B")))


class Changed(unittest.TestCase):
    def test_first_deploy_submits_every_page(self):
        with tempfile.TemporaryDirectory() as t:
            d = build(t, {"/": "Home", "/changes/": "Changes"})
            self.assertEqual(indexnow.changed(None, indexnow.manifest(d)), ["https://forever-xp.com/", "https://forever-xp.com/changes/"])

    def test_only_new_changed_and_removed_pages(self):
        with tempfile.TemporaryDirectory() as t1, tempfile.TemporaryDirectory() as t2:
            prev = indexnow.manifest(build(t1, {"/": "Home", "/changes/": "Old", "/gone/": "Gone"}))
            cur = indexnow.manifest(build(t2, {"/": "Home", "/changes/": "New", "/bis/": "BIS"}))
            self.assertEqual(indexnow.changed(prev, cur), ["https://forever-xp.com/bis/", "https://forever-xp.com/changes/", "https://forever-xp.com/gone/"])

    def test_a_mass_removal_is_not_submitted(self):
        prev = {f"/q/{i}/": "0" * 64 for i in range(indexnow.MAX_REMOVED + 1)}
        self.assertEqual(indexnow.changed(prev, {"/": "1" * 64}), ["https://forever-xp.com/"])

    def test_pages_outside_the_sitemap_are_ignored(self):
        with tempfile.TemporaryDirectory() as t:
            d = build(t, {"/": "Home"})
            (Path(d) / "account").mkdir()
            (Path(d) / "account" / "index.html").write_text(PAGE.format("Account"))
            self.assertEqual(set(indexnow.manifest(d)), {"/"})


class Previous(unittest.TestCase):
    def load(self, value):
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            f.write(value if isinstance(value, str) else json.dumps(value))
        return indexnow.load_previous(f.name)

    def test_missing_or_broken_files_mean_no_previous(self):
        self.assertIsNone(indexnow.load_previous("/nonexistent/prev.json"))
        self.assertIsNone(self.load("not json"))
        self.assertIsNone(self.load([1, 2]))

    def test_anything_but_site_paths_and_digests_is_rejected(self):
        good = "a" * 64
        self.assertEqual(self.load({"/": good}), {"/": good})
        for bad in ({"https://evil.example/": good}, {"/x/": "nothex"}, {"/x/": 5}, {"/a b/": good}, {"/<script>/": good}):
            self.assertIsNone(self.load(bad), bad)


class Submit(unittest.TestCase):
    def test_batches_and_body(self):
        sent = []
        urls = [f"https://forever-xp.com/q/{i}/" for i in range(indexnow.BATCH + 5)]
        self.assertEqual(indexnow.submit(urls, send=lambda b: sent.append(b) or 200), [200, 200])
        self.assertEqual([len(b["urlList"]) for b in sent], [indexnow.BATCH, 5])
        self.assertEqual(sent[0]["host"], "forever-xp.com")
        self.assertEqual(sent[0]["keyLocation"], f"https://forever-xp.com/{indexnow.KEY}.txt")

    def test_prepare_refuses_without_the_key_file(self):
        with tempfile.TemporaryDirectory() as t:
            d = build(t, {"/": "Home"})
            (Path(d) / f"{indexnow.KEY}.txt").unlink()
            with self.assertRaises(SystemExit):
                indexnow.main(["prepare", "--dist", str(d), "--previous", "/nonexistent", "--manifest", f"{t}/m.json", "--out", f"{t}/o.txt"])


if __name__ == "__main__":
    unittest.main(verbosity=1)
