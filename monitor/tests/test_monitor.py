import base64
import copy
import datetime as dt
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("monitor", Path(__file__).parents[1] / "monitor.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

REPO = "the-omega-institute/trureturing-pages"
UPSTREAM = "the-omega-institute/trureturing-outreach-engine"
BASE = "a" * 40


def config():
    return {"schema": m.SCHEMA, "repository": REPO,
            "checks": [{"id": "json", "url": "https://www.trureturing.org/data.json", "owner": REPO, "kind": "json", "equals": {"schema": "test.v1"}}],
            "targets": {REPO: {"branch": "dev", "paths": ["site/"], "verify": [["node", "--check", "site/main.js"]], "auto_merge": True},
                        UPSTREAM: {"branch": "main", "paths": ["managed/delivery.py"], "verify": [["python3", "-m", "unittest"]]}}}


def candidate():
    return {"schema": m.SCHEMA, "state": "repaired", "origin": REPO, "target": REPO,
            "base": BASE, "branch": "dev", "fingerprint": "e" * 20,
            "files": {"site/main.js": {"content": base64.b64encode(b"const value = 1;\n").decode(), "mode": "100644"}},
            "review": {"verdict": "PASS", "reason": "Checked cause and patch"},
            "summary": "Restore the result link", "run_id": "123", "attempt": "2"}


class API:
    def __init__(self, branch_sha=BASE, existing=None):
        self.calls = []
        self.branch_sha = branch_sha
        self.existing = existing or []

    def call(self, method, path, body=None, missing=False):
        self.calls.append((method, path, body))
        if "/pulls?" in path: return self.existing
        if "/git/ref/heads/dev" in path: return {"object": {"sha": self.branch_sha}}
        if "/git/ref/heads/monitor/" in path: return None
        if "/git/commits/" in path and method == "GET": return {"tree": {"sha": "old-tree"}}
        if "/contents/" in path: return {"type": "file"}
        if path.endswith("git/blobs"): return {"sha": "blob"}
        if path.endswith("git/trees"): return {"sha": "tree"}
        if path.endswith("git/commits"): return {"sha": "b" * 40}
        if path.endswith("git/refs"): return {"object": {"sha": "b" * 40}}
        if path.endswith("pulls"): return {"html_url": "https://github.com/" + REPO + "/pull/1", "head": {"sha": "b" * 40}}
        raise AssertionError((method, path))


class MonitorTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {"GITHUB_RUN_ID": "123", "GITHUB_RUN_ATTEMPT": "2"})
        self.env.start()
        self.addCleanup(self.env.stop)

    def test_core_and_requests_cannot_be_repair_targets(self):
        for repo in m.DENIED:
            c = config(); c["targets"][repo] = {"branch": "dev", "paths": ["D5/"], "verify": [["true"]]}
            with self.assertRaisesRegex(ValueError, "forbidden"):
                m.validate_config(c)

    def test_upstream_pr_cannot_be_registered_for_auto_merge(self):
        c = config(); c["targets"][UPSTREAM]["auto_merge"] = True
        with self.assertRaisesRegex(ValueError, "upstream"):
            m.validate_config(c)

    def test_html_fallback_with_http_success_is_not_json_health(self):
        with self.assertRaisesRegex(ValueError, "expected JSON"):
            m.check_probe(config()["checks"][0], b"<html>Mathesis</html>", "text/html", dt.datetime.now(dt.timezone.utc))

    def test_wrong_version_and_missing_field_fail(self):
        check = config()["checks"][0]
        for data in [b'{"schema":"wrong"}', b'{}']:
            with self.assertRaises((ValueError, KeyError)):
                m.check_probe(check, data, "application/json", dt.datetime.now(dt.timezone.utc))

    def test_old_or_future_public_data_is_not_fresh(self):
        now = dt.datetime(2026, 11, 25, tzinfo=dt.timezone.utc)
        check = {"kind": "json", "timestamp": "at", "max_age_seconds": 600}
        for delta in [-601, 301]:
            data = json.dumps({"at": (now + dt.timedelta(seconds=delta)).isoformat()}).encode()
            with self.assertRaisesRegex(ValueError, "stale"):
                m.check_probe(check, data, "application/json", now)

    def test_incident_identity_survives_changing_exception_prose(self):
        def fail(message):
            def get(url): raise OSError(message)
            return get
        with tempfile.TemporaryDirectory() as d:
            a = m.probe(config(), Path(d) / "a", fail("timeout"))
            b = m.probe(config(), Path(d) / "b", fail("connection reset"))
        self.assertEqual(a["fingerprint"], b["fingerprint"])
        self.assertEqual(a["state"], "anomaly")

    def test_browser_failure_cannot_be_overridden_by_valid_json(self):
        c = config(); c["browser"] = [{"id": "reader"}]
        with tempfile.TemporaryDirectory() as d:
            result = m.probe(c, Path(d) / "result", lambda url: (b'{"schema":"test.v1"}', "application/json"),
                             browser=[{"id": "reader", "state": "failed", "reason": "page error"}])
        self.assertEqual(result["state"], "anomaly")

    def test_publish_refuses_foreign_run_attempt_origin_and_failed_review(self):
        for field, value in [("run_id", "124"), ("attempt", "1"), ("origin", UPSTREAM), ("review", {"verdict": "FAIL"})]:
            c = candidate(); c[field] = value
            with self.assertRaises(ValueError): m.validate_candidate(config(), c)

    def test_publish_refuses_scope_escape_symlinks_and_credentials(self):
        for path in [".github/workflows/ci.yml", "site/../secret", "/site/main.js", "managed/delivery.py"]:
            c = candidate(); c["files"] = {path: next(iter(c["files"].values()))}
            with self.assertRaises(ValueError): m.validate_candidate(config(), c)
        c = candidate(); c["files"]["site/main.js"]["mode"] = "120000"
        with self.assertRaises(ValueError): m.validate_candidate(config(), c)
        c = candidate(); c["files"]["site/main.js"]["content"] = base64.b64encode(b"ghp_" + b"a" * 30).decode()
        with self.assertRaises(ValueError): m.validate_candidate(config(), c)

    def test_no_writes_when_base_advanced(self):
        api = API(branch_sha="c" * 40)
        with self.assertRaisesRegex(ValueError, "advanced"):
            m.publish(config(), candidate(), api)
        self.assertTrue(all(method == "GET" for method, _, _ in api.calls))

    def test_replayed_incident_reuses_existing_pr_without_writes(self):
        branch = "monitor/trureturing-pages-" + "e" * 20
        existing = {"head": {"ref": branch}, "base": {"ref": "dev"}, "html_url": "existing"}
        api = API(existing=[existing])
        self.assertEqual(m.publish(config(), candidate(), api), existing)
        self.assertEqual(len(api.calls), 1)

    def test_upstream_patch_goes_to_registered_owner_and_never_merges(self):
        c = candidate(); c.update(target=UPSTREAM, branch="main")
        c["files"] = {"managed/delivery.py": next(iter(c["files"].values()))}
        m.validate_candidate(config(), c)
        self.assertFalse(config()["targets"][UPSTREAM].get("auto_merge", False))

    def test_model_environment_does_not_forward_github_credentials(self):
        with tempfile.TemporaryDirectory() as d, patch.dict(os.environ, {"RUNNER_TEMP": d, "NYXID_API_KEY": "model-test", "NYXID_BASE_URL": "https://api.nyxid.ai/api/v1/proxy/s/chrono-llm", "GH_TOKEN": "never-forward", "MONITOR_GITHUB_KEY": "never-forward"}):
            result = Path(d) / "out.json"
            def run(args, cwd, timeout, env, input):
                self.assertNotIn("GH_TOKEN", env); self.assertNotIn("MONITOR_GITHUB_KEY", env)
                self.assertIn("--ephemeral", args)
                self.assertEqual(args[args.index("--sandbox") + 1], "read-only")
                result.write_text('{"verdict":"PASS","reason":"checked"}')
            with patch.object(m, "command", side_effect=run):
                self.assertEqual(m.model(Path(d), "check", result, m.REVIEW_SCHEMA, True)["verdict"], "PASS")

    def test_new_local_candidate_creates_exact_tree_branch_and_pr(self):
        api = API()
        result = m.publish(config(), candidate(), api)
        self.assertTrue(result["html_url"].endswith('/pull/1'))
        writes = [(method, path, body) for method, path, body in api.calls if method != 'GET']
        self.assertEqual([path.rsplit('/', 1)[-1] for _, path, _ in writes], ['blobs', 'trees', 'commits', 'refs', 'pulls'])
        tree = next(body for _, path, body in writes if path.endswith('/trees'))
        self.assertEqual(tree['tree'][0]['path'], 'site/main.js')
        self.assertFalse(any('/merge' in path for _, path, _ in writes))

    def test_cross_repository_submit_requires_explicit_publisher_authorization(self):
        c = candidate(); c.update(target=UPSTREAM, branch='main')
        c['files'] = {'managed/delivery.py': next(iter(c['files'].values()))}
        with patch.dict(os.environ, {'MONITOR_PR_TOKEN': ''}):
            with self.assertRaisesRegex(ValueError, 'configure a GitHub App'):
                m.publish(config(), c, API())

    def test_model_cannot_call_a_failed_probe_healthy(self):
        observation = {'repository':REPO,'schema':m.SCHEMA,'state':'anomaly','fingerprint':'e'*20}
        with tempfile.TemporaryDirectory() as d, patch.object(m, 'clone', return_value=BASE), patch.object(m, 'scoped_files', return_value={}), patch.object(m, 'model', return_value={'outcome':'healthy','reason':'ignore failed probe'}):
            with self.assertRaisesRegex(ValueError, 'no safe repair'):
                m.repair(config(), observation, Path(d), Path(d)/'candidate')

    def test_local_reconcile_waits_for_real_checks_and_does_not_merge_human_prs(self):
        pr = {'number':5,'html_url':'pr','head':{'ref':'monitor/trureturing-pages-eee','sha':'b'*40,'repo':{'full_name':REPO}},
              'base':{'ref':'dev'},'user':{'login':'github-actions[bot]'},
              'body':f'Producer: https://github.com/{REPO}/actions/runs/123/attempts/2'}
        class ReconcileAPI:
            def __init__(self, checks): self.checks=checks; self.writes=[]
            def call(self, method, path, body=None):
                if method != 'GET':
                    self.writes.append((method,path,body));return {'merged':True,'sha':'c'*40}
                if path.endswith('/pulls?state=open&per_page=100'):return [pr]
                if '/attempts/' in path:return {'status':'completed','conclusion':'success','path':'.github/workflows/display-monitor.yml'}
                if '/check-runs?' in path:return {'check_runs':self.checks}
                if path.endswith('/status'):return {'statuses':[],'state':'pending'}
                raise AssertionError(path)
        for checks in [[],[{'status':'queued','conclusion':None}],[{'status':'completed','conclusion':'failure'}]]:
            api=ReconcileAPI(checks);m.reconcile(config(),api);self.assertFalse(api.writes)
        api=ReconcileAPI([{'status':'completed','conclusion':'success'}]);m.reconcile(config(),api)
        self.assertEqual(api.writes[0][2]['sha'],'b'*40)
        pr['user']['login']='human'
        api=ReconcileAPI([{'status':'completed','conclusion':'success'}]);m.reconcile(config(),api);self.assertFalse(api.writes)


if __name__ == "__main__":
    unittest.main()
