import base64
import copy
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("profile_sync", Path(__file__).parents[1] / "sync.py")
sync = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sync)


def publication():
    commit, release = "a" * 40, "sha256:" + "b" * 64
    manifest = {"schema": "pages-deployment-manifest.v1", "source_commit": commit,
                "release_digest": release, "pages_commit": "c" * 40}
    catalog = {"schema_version": "pages-research-catalog.v1", "source_repo": sync.SOURCE_REPOSITORY,
               "source_commit": commit, "revision": release, "families": []}
    milestones = {"schema_version": "research-milestones.v1", "source_commit": commit,
                  "truth_release_digest": release, "results": []}
    for n in range(4):
        catalog["families"].append({"id": "result-" + str(n), "kind": "proved", "source_commit": commit,
            "kernel_verified": {"freeze_status": "frozen"}, "declaration_gid": "D5/S3/Example" + str(n) + ".result",
            "source_url": "https://arxiv.org/abs/2601.00001"})
        milestones["results"].append({"id": "result-" + str(n), "kind": "proved",
            "title": "Result " + str(n), "url": "results/result-" + str(n) + "/",
            "story": {"finding": "An exact bound for all admissible parameters.",
                      "impact": "This resolves the stated source question.",
                      "boundary": "The infinite-dimensional extension remains open."}})
    papers = {"schema_version": "publication-index.v1", "updated_at": "2026-11-26T00:00:00Z",
              "publications": [{"id": "paper-old", "date": "2026-10-01", "title": "Earlier paper",
                  "authors": "A. Author, B. Author", "status": "Preprint", "summary": "A precise published result.",
                  "qualification": "Official results are pending.", "url": "https://arxiv.org/abs/2610.00001"}]}
    return manifest, catalog, milestones, papers


DOCUMENT = "Introduction stays.\n\n" + sync.BEGIN + "\nOld snapshot\n" + sync.END + "\n\nContact stays.\n"


class ProfileTests(unittest.TestCase):
    def test_new_publication_is_added_and_removed_publication_disappears(self):
        values = publication()
        old = sync.update(DOCUMENT, values)
        values[3]["publications"] = [{**values[3]["publications"][0], "id": "new-paper",
                                     "date": "2026-11-11", "title": "New research"}]
        updated = sync.update(old, values)
        self.assertIn("New research", updated)
        self.assertNotIn("Earlier paper", updated)
        self.assertTrue(updated.startswith("Introduction stays.\n\n"))
        self.assertTrue(updated.endswith("\n\nContact stays.\n"))
        self.assertIn("Official results are pending.", updated)

    def test_featured_results_follow_published_order_and_retain_scope(self):
        values = publication()
        values[2]["results"].reverse()
        updated = sync.update(DOCUMENT, values)
        self.assertLess(updated.index("### Result 3"), updated.index("### Result 2"))
        self.assertNotIn("### Result 0", updated)
        self.assertEqual(updated.count("The infinite-dimensional extension remains open."), 3)
        self.assertIn("/blob/" + "a" * 40 + "/D5/S3/Example3.lean", updated)
        self.assertNotIn("/blob/dev/", updated)

    def test_withdrawn_result_is_removed_and_counts_use_current_catalog(self):
        values = publication()
        old = sync.update(DOCUMENT, values)
        values[1]["families"] = values[1]["families"][1:]
        values[2]["results"] = values[2]["results"][1:]
        values[1]["families"][0]["kind"] = "refuted"
        values[2]["results"][0]["kind"] = "refuted"
        updated = sync.update(old, values)
        self.assertNotIn("### Result 0", updated)
        self.assertIn("**3 resolution records**", updated)
        self.assertIn("**2 proved** and **1 refuted**", updated)

    def test_newest_publications_are_selected_without_a_fixed_list(self):
        values = publication()
        template = values[3]["publications"][0]
        values[3]["publications"] = [{**template, "id": "paper-" + str(n), "date": "2026-11-" + str(n).zfill(2),
                                      "title": "Publication " + str(n)} for n in range(1, 10)]
        updated = sync.update(DOCUMENT, values)
        self.assertLess(updated.index("Publication 9"), updated.index("Publication 8"))
        self.assertIn("Publication 4", updated)
        self.assertNotIn("Publication 3", updated)
        self.assertIn("**9 publication records**", updated)

    def test_month_precision_is_preserved_and_invalid_dates_are_rejected(self):
        values = publication()
        values[3]["publications"][0]["date"] = "2026-09"
        self.assertIn("**2026-09 · Preprint**", sync.update(DOCUMENT, values))
        for invalid in ["2026-13", "2026-02-30", "2026-9", "2026-09 trailing"]:
            values[3]["publications"][0]["date"] = invalid
            with self.subTest(date=invalid), self.assertRaises(ValueError):
                sync.update(DOCUMENT, values)

    def test_identical_content_and_poll_timestamp_changes_do_not_publish(self):
        values = publication()
        updated = sync.update(DOCUMENT, values)
        values[3]["updated_at"] = "2026-11-27T00:00:00Z"
        values[0]["pages_commit"] = "d" * 40
        again = sync.update(updated, values)
        self.assertEqual(again, updated)
        calls = []
        self.assertFalse(sync.publish(updated, again, lambda *args: calls.append(args)))
        self.assertEqual(calls, [])

    def test_mixed_or_invalid_publications_are_rejected(self):
        for position, key, value in [(0, "source_commit", "invalid"), (1, "revision", "sha256:" + "c" * 64),
                                     (1, "source_repo", "other/source"), (2, "source_commit", "d" * 40),
                                     (3, "schema_version", "unrelated.v1")]:
            values = list(copy.deepcopy(publication()))
            values[position][key] = value
            with self.subTest(position=position, key=key), self.assertRaises(ValueError):
                sync.update(DOCUMENT, values)

    def test_unreleased_duplicate_or_misclassified_feature_cannot_be_published(self):
        for change in ["unreleased", "duplicate", "kind", "external", "source"]:
            values = publication()
            if change == "unreleased": values[2]["results"][0]["id"] = "missing"
            if change == "duplicate": values[2]["results"][1] = copy.deepcopy(values[2]["results"][0])
            if change == "kind": values[2]["results"][0]["kind"] = "refuted"
            if change == "external": values[2]["results"][0]["url"] = "https://example.org/"
            if change == "source": values[1]["families"][0]["source_url"] = "javascript:alert(1)"
            with self.subTest(change=change), self.assertRaises(ValueError): sync.update(DOCUMENT, values)

    def test_managed_markers_and_text_cannot_overwrite_the_introduction(self):
        for document in ["No markers", DOCUMENT + sync.BEGIN, sync.END + sync.BEGIN]:
            with self.subTest(document=document), self.assertRaises(ValueError):
                sync.update(document, publication())
        values = publication()
        values[3]["publications"][0]["title"] = "[fake](javascript:alert(1)) <script>bad</script>"
        values[2]["results"][0]["story"]["finding"] = sync.END
        updated = sync.update(DOCUMENT, values)
        self.assertEqual(updated.count(sync.END), 1)
        self.assertIn("&lt;script&gt;", updated)
        self.assertNotIn("[fake](", updated)

    def test_publication_changing_during_fetch_does_not_touch_the_profile(self):
        values = publication()
        fetched = [values[0], values[1], values[2], values[3], {**values[0], "pages_commit": "d" * 40}]
        with self.assertRaisesRegex(ValueError, "changed during"):
            sync.load_publication(lambda *_: fetched.pop(0))
        self.assertEqual(fetched, [])

    def test_network_error_does_not_write_or_publish(self):
        with tempfile.TemporaryDirectory() as directory:
            readme = Path(directory) / "README.md"
            readme.write_text(DOCUMENT)
            with patch.object(sync, "README", readme), patch("sys.argv", ["sync.py", "--publish"]), \
                 patch.object(sync, "load_publication", side_effect=OSError("network unavailable")), \
                 patch.object(sync, "publish") as publish:
                with self.assertRaises(OSError): sync.main()
                publish.assert_not_called()
            self.assertEqual(readme.read_text(), DOCUMENT)

    def test_publisher_only_updates_exact_profile_with_observed_sha(self):
        calls = []
        def api(path, body=None):
            calls.append((path, body))
            return {"sha": "observed-file-sha", "content": base64.b64encode(DOCUMENT.encode()).decode()}
        env = {"GITHUB_REPOSITORY": sync.REPOSITORY, "GITHUB_REF": "refs/heads/main"}
        with patch.dict(os.environ, env):
            self.assertTrue(sync.publish(DOCUMENT, "Updated profile", api))
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[1][0], "contents/profile/README.md")
        self.assertEqual(calls[1][1]["sha"], "observed-file-sha")
        self.assertEqual(calls[1][1]["branch"], "main")
        self.assertEqual(base64.b64decode(calls[1][1]["content"]).decode(), "Updated profile")

    def test_newer_human_edit_and_foreign_runner_are_never_overwritten(self):
        calls = []
        def api(path, body=None):
            calls.append((path, body))
            return {"sha": "newer", "content": base64.b64encode(b"New human introduction").decode()}
        with patch.dict(os.environ, {"GITHUB_REPOSITORY": sync.REPOSITORY, "GITHUB_REF": "refs/heads/main"}):
            with self.assertRaisesRegex(ValueError, "changed after checkout"):
                sync.publish(DOCUMENT, "Updated profile", api)
        self.assertEqual(len(calls), 1)
        with patch.dict(os.environ, {"GITHUB_REPOSITORY": "another/repo", "GITHUB_REF": "refs/heads/main"}):
            with self.assertRaisesRegex(ValueError, "registered main"):
                sync.publish(DOCUMENT, "Updated profile", api)
        self.assertEqual(len(calls), 1)


if __name__ == "__main__":
    unittest.main()
