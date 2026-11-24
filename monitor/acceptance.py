#!/usr/bin/env python3
"""Exercise real model repair and independent review on a disposable broken reader.

Only a manual verify_model run invokes this fixture. It never publishes a PR or
changes a production checkout; the normal repair and validation code is reused.
"""
import os
from pathlib import Path
import sys
import tempfile

import monitor as m


def main():
    repo = "display-monitor/acceptance-reader"
    with tempfile.TemporaryDirectory(prefix="monitor-acceptance-", dir=os.environ["RUNNER_TEMP"]) as temp:
        root = Path(temp).resolve()
        source = root / "source"
        source.mkdir()
        (source / "index.html").write_text('<html><body><h1>Paper materials</h1><a href="missing.html">Read the explanation</a></body></html>\n')
        (source / "reader.html").write_text('<html><body>A preserved readable explanation.</body></html>\n')
        (source / "verify.py").write_text(
            'from html.parser import HTMLParser\nfrom pathlib import Path\n'
            'class Links(HTMLParser):\n'
            ' def __init__(self):\n  super().__init__(); self.links=[]\n'
            ' def handle_starttag(self, tag, attrs):\n'
            '  if tag == "a": self.links.append(dict(attrs)["href"])\n'
            'p=Links(); p.feed(Path("index.html").read_text())\n'
            'assert len(p.links)==1 and all(Path(x).is_file() for x in p.links), "broken reader link"\n')
        m.command(["git", "init", "-qb", "main"], source)
        m.command(["git", "add", "."], source)
        m.command(["git", "-c", "user.name=Display Monitor Acceptance", "-c",
                   "user.email=acceptance@example.invalid", "commit", "-qm", "Broken reader fixture"], source)
        config = m.validate_config({"schema": m.SCHEMA, "repository": repo,
            "checks": [{"id": "reader", "url": "https://example.invalid/missing.html", "owner": repo, "kind": "html"}],
            "targets": {repo: {"branch": "main", "paths": ["index.html"],
                                "verify": [[sys.executable, "verify.py"]], "auto_merge": False}}})
        observation = {"schema": m.SCHEMA, "repository": repo, "state": "anomaly", "fingerprint": "e" * 20,
            "observations": [{"id": "reader", "url": "https://example.invalid/missing.html", "owner": repo,
                              "state": "failed", "reason": "Disposable acceptance fixture: index.html links to missing.html (404). Inspect the preserved local reader."}]}
        original_clone = m.clone
        def clone(registered, branch, target):
            m.require(registered == repo and branch == "main", "foreign acceptance target")
            m.command(["git", "clone", "--quiet", "--no-hardlinks", str(source), str(target)])
            return m.command(["git", "rev-parse", "HEAD"], target).strip()
        try:
            m.clone = clone
            output = root / "candidate.json"
            m.repair(config, observation, root / "workspace", output)
            candidate = m.read(output)
            m.validate_candidate(config, candidate)
            m.require(list(candidate["files"]) == ["index.html"], "unexpected acceptance patch")
        finally:
            m.clone = original_clone
    print("Acceptance fixture passed: real model repair, registered verification, independent review and candidate validation. No PR publication.")


if __name__ == "__main__":
    main()
