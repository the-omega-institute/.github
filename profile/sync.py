"""Refresh the organization profile from existing, public Pages publications.

This worker has no model client or upstream writer. It preserves the introduction
and contact text outside its markers, and only commits changed profile bytes.
"""
from __future__ import annotations

import argparse
import base64
from collections import Counter
from datetime import date
import html
import json
import os
from pathlib import Path
import re
import subprocess
import time
from urllib.parse import quote, urljoin, urlsplit
from urllib.request import Request, urlopen

REPOSITORY = "the-omega-institute/.github"
SOURCE_REPOSITORY = "the-omega-institute/trureturing"
SITE = "https://www.trureturing.org/"
BEGIN = "<!-- BEGIN AUTOMATIC RESEARCH -->"
END = "<!-- END AUTOMATIC RESEARCH -->"
README = Path(__file__).with_name("README.md")
SHA = re.compile(r"[a-f0-9]{40}")
DIGEST = re.compile(r"sha256:[a-f0-9]{64}")
SLUG = re.compile(r"[a-z0-9][a-z0-9-]*")
MAX_BYTES = 16 * 1024 * 1024


def require(condition, message):
    if not condition:
        raise ValueError(message)


def text(value):
    require(isinstance(value, str) and len(value) <= 16000, "Invalid published text")
    return html.escape(" ".join(value.split()), quote=False)


def label(value):
    return re.sub(r"([\\`*\[\]_])", r"\\\1", text(value))


def url(value):
    require(isinstance(value, str), "Invalid published link")
    parsed = urlsplit(value)
    require(parsed.scheme == "https" and parsed.hostname and not parsed.username
            and not parsed.password and not any(c.isspace() for c in value), "Invalid published link")
    return quote(value, safe="/:#?=&%+@,~.-_")


def publication_date(value):
    require(isinstance(value, str) and re.fullmatch(r"\d{4}-\d{2}(?:-\d{2})?", value),
            "Invalid publication date")
    # The existing feed permits month precision for workshop announcements.
    date.fromisoformat(value + "-01" if len(value) == 7 else value)
    return value


def read_json(path, observation):
    request = Request(SITE + path + "?profile=" + observation,
                      headers={"User-Agent": "trureturing-organization-profile/1.0", "Cache-Control": "no-cache"})
    with urlopen(request, timeout=30) as response:
        raw = response.read(MAX_BYTES + 1)
    require(len(raw) <= MAX_BYTES, "Published input exceeds the profile limit")
    return json.loads(raw)


def load_publication(fetch=read_json):
    observation = str(time.time_ns())
    before = fetch("deployment-manifest.v1.json", observation)
    catalog = fetch("assets/research-catalog.json", observation)
    milestones = fetch("assets/research-milestones.json", observation)
    papers = fetch("assets/publication-index.json", observation)
    after = fetch("deployment-manifest.v1.json", observation)
    require(before == after, "Publication changed during profile synchronization; keep the existing profile")
    validate(before, catalog, milestones, papers)
    return before, catalog, milestones, papers


def validate(manifest, catalog, milestones, papers):
    require(manifest.get("schema") == "pages-deployment-manifest.v1"
            and SHA.fullmatch(manifest.get("source_commit", ""))
            and SHA.fullmatch(manifest.get("pages_commit", ""))
            and DIGEST.fullmatch(manifest.get("release_digest", "")), "Invalid publication identity")
    commit, release = manifest["source_commit"], manifest["release_digest"]
    require(catalog.get("schema_version") == "pages-research-catalog.v1"
            and catalog.get("source_repo") == SOURCE_REPOSITORY
            and catalog.get("source_commit") == commit and catalog.get("revision") == release,
            "Research catalog belongs to a different publication")
    require(milestones.get("schema_version") == "research-milestones.v1"
            and milestones.get("source_commit") == commit
            and milestones.get("truth_release_digest") == release,
            "Research milestones belong to a different publication")
    require(papers.get("schema_version") == "publication-index.v1", "Invalid public publication index")
    families, results, publications = catalog.get("families"), milestones.get("results"), papers.get("publications")
    require(isinstance(families, list) and 0 < len(families) <= 50000
            and isinstance(results, list) and len(results) <= len(families)
            and isinstance(publications, list) and len(publications) <= 5000, "Invalid publication inventory")
    by_id = {}
    for row in families:
        require(SLUG.fullmatch(row["id"]) and row["id"] not in by_id
                and row["kind"] in {"proved", "refuted"} and row["source_commit"] == commit
                and isinstance(row.get("kernel_verified"), dict) and row["kernel_verified"],
                "Invalid released resolution record")
        by_id[row["id"]] = row
    seen = set()
    for row in results:
        family = by_id.get(row["id"])
        require(family and row["id"] not in seen and row["kind"] == family["kind"],
                "Featured result is not in the released catalog")
        seen.add(row["id"])
        require(isinstance(row.get("story"), dict) and row["story"].get("finding"),
                "Featured result has no published finding")
        destination = urljoin(SITE, row["url"])
        require(destination.startswith(SITE), "Featured result points outside the published site")
        # A declaration points into the exact released Lean source, never dev.
        require(re.fullmatch(r"[A-Za-z0-9_/'.-]+", family["declaration_gid"])
                and ".." not in family["declaration_gid"], "Invalid Lean source coordinate")
        url(family["source_url"])
    seen = set()
    for row in publications:
        require(row["id"] not in seen, "Duplicate publication identity")
        seen.add(row["id"])
        publication_date(row["date"])
        text(row["title"])
        url(row["url"])


def render(manifest, catalog, milestones, papers):
    validate(manifest, catalog, milestones, papers)
    counts = Counter(row["kind"] for row in catalog["families"])
    source = "https://github.com/" + SOURCE_REPOSITORY + "/blob/" + manifest["source_commit"] + "/"
    lines = [BEGIN, "<!-- source_commit=" + manifest["source_commit"]
             + " release_digest=" + manifest["release_digest"] + " -->", "", "## Recent publications", ""]
    publications = sorted(papers["publications"], key=lambda row: (row["date"], row["id"]), reverse=True)
    for row in publications:
        lines.append(f'- **{row["date"][:7]}** · [{label(row["title"])}]({url(row["url"])})')
    if not publications:
        lines.append("Browse the [research page](" + SITE + "research.html) for public research updates.")
    lines += ["", "[All publications](" + SITE + "research.html#publications)", "", "## Selected results", ""]
    families = {row["id"]: row for row in catalog["families"]}
    # Milestones already carry Pages' automatic contribution order and admission.
    # No local list of favored results or new scientific assessment is introduced.
    for row in milestones["results"][:3]:
        family, story = families[row["id"]], row["story"]
        proof = source + quote(family["declaration_gid"].split(".", 1)[0] + ".lean", safe="/")
        lines += ["### " + text(row["title"]), "", text(story["finding"])]
        if story.get("impact") and story["impact"] != story["finding"]:
            lines += ["", text(story["impact"])]
        if story.get("boundary"):
            lines += ["", text(story["boundary"])]
        lines += ["", "[Read the result](" + url(urljoin(SITE, row["url"])) + ") · "
                  + "[Lean source](" + url(proof) + ") · "
                  + "[Original question](" + url(family["source_url"]) + ")", ""]
    if not milestones["results"]:
        lines += ["Browse the [released results](" + SITE + "conjectures.html#results).", ""]
    lines += ["[Explore all results](" + SITE + "conjectures.html#results)", "", "## Published research snapshot", "",
              f'**{len(families):,} resolution records** in the current verified release: '
              + f'**{counts["proved"]:,} proved** and **{counts["refuted"]:,} refuted**. '
              + f'**{len(papers["publications"]):,} publication records** in the public research catalog.', "",
              "Each result links its exact statement, assumptions and proof source. "
              + "Explore the [research library](" + SITE + ") to find a question to work on.", "", END]
    value = "\n".join(lines)
    require(len(value.encode()) <= 128 * 1024, "Generated profile is too large")
    return value


def update(document, publication):
    require(document.count(BEGIN) == document.count(END) == 1, "Profile requires exactly one managed research block")
    start, end = document.index(BEGIN), document.index(END) + len(END)
    require(start < end - len(END), "Invalid profile block order")
    return document[:start] + render(*publication) + document[end:]


def github(path, body=None):
    command = ["gh", "api", "repos/" + REPOSITORY + "/" + path]
    if body is not None:
        command += ["--method", "PUT", "--input", "-"]
    result = subprocess.run(command, input=json.dumps(body) if body is not None else None,
                            capture_output=True, text=True, timeout=60)
    require(result.returncode == 0, "Profile publication failed; no retry or force update was attempted")
    return json.loads(result.stdout)


def publish(old, new, api=github):
    if old == new:
        return False
    require(os.environ.get("GITHUB_REPOSITORY") == REPOSITORY
            and os.environ.get("GITHUB_REF") == "refs/heads/main", "Profile writes require the registered main workflow")
    current = api("contents/profile/README.md?ref=main")
    require(base64.b64decode(current["content"]).decode() == old,
            "Profile changed after checkout; preserve the newer edit and try on the next wake-up")
    api("contents/profile/README.md", {"branch": "main", "sha": current["sha"],
        "message": "Sync organization profile from published research",
        "content": base64.b64encode(new.encode()).decode()})
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--publish", action="store_true", help="Update only this repository's main profile through GitHub")
    args = parser.parse_args()
    old = README.read_text()
    publication = load_publication()
    new = update(old, publication)
    changed = publish(old, new) if args.publish else old != new
    if not args.publish and changed:
        README.write_text(new)
    summary = json.dumps({"changed": changed, "resolutions": len(publication[1]["families"]),
                          "publications": len(publication[3]["publications"]), "model_calls": 0})
    print(summary)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as stream:
            stream.write("Organization profile synchronization\n\n```json\n" + summary + "\n```\n")


if __name__ == "__main__":
    main()
