from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
from collections import OrderedDict
from dataclasses import dataclass
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PYPROJECT_PATH = ROOT / "pyproject.toml"
CHANGELOG_PATH = ROOT / "CHANGELOG.md"
RELEASE_NOTES_PATH = ROOT / ".github" / "tmp" / "release-notes.md"

VERSION_PATTERN = re.compile(r'^(version\s*=\s*")(?P<version>\d+\.\d+\.\d+)(")$', re.MULTILINE)
CONVENTIONAL_PATTERN = re.compile(r"^(?P<type>[a-z]+)(?:\([^)]+\))?(?P<breaking>!)?: (?P<description>.+)$")
BREAKING_PATTERN = re.compile(r"(^|[\r\n])BREAKING CHANGE:", re.MULTILINE)

SECTION_TITLES = OrderedDict(
    [
        ("feat", "Features"),
        ("fix", "Bug Fixes"),
        ("perf", "Performance"),
        ("refactor", "Refactoring"),
        ("docs", "Documentation"),
        ("test", "Tests"),
        ("build", "Build System"),
        ("ci", "CI"),
        ("style", "Style"),
        ("chore", "Chores"),
        ("revert", "Reverts"),
    ]
)

PATCH_TYPES = set(SECTION_TITLES) - {"feat"}


@dataclass(frozen=True)
class ReleaseCommit:
    sha: str
    subject: str
    message: str
    type: str
    breaking: bool
    valid: bool


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--commits-file", required=True)
    args = parser.parse_args()

    payload = json.loads(Path(args.commits_file).read_text(encoding="utf-8"))
    commits = [parse_commit(item["sha"], item["message"]) for item in payload["commits"]]
    invalid_commits = [commit for commit in commits if not commit.valid]
    if invalid_commits:
        formatted = "\n".join(f"- {commit.sha[:7]}: {commit.subject}" for commit in invalid_commits)
        raise RuntimeError(f"Release aborted: non-conventional commit messages detected.\n{formatted}")

    current_version = read_current_version()
    next_version = bump_version(current_version, commits)
    previous_tag = read_previous_tag()
    pull_request = payload.get("pull_request")

    update_pyproject_version(next_version)
    release_section = build_release_section(
        version=next_version,
        previous_tag=previous_tag,
        commits=commits,
        pull_request=pull_request,
    )
    prepend_changelog(release_section)

    RELEASE_NOTES_PATH.parent.mkdir(parents=True, exist_ok=True)
    RELEASE_NOTES_PATH.write_text(release_section, encoding="utf-8")

    github_output = os.environ.get("GITHUB_OUTPUT")
    if github_output:
        with Path(github_output).open("a", encoding="utf-8") as handle:
            handle.write(f"version={next_version}\n")


def parse_commit(sha: str, message: str) -> ReleaseCommit:
    subject = message.strip().splitlines()[0]
    match = CONVENTIONAL_PATTERN.match(subject)
    commit_type = match.group("type") if match else "chore"
    breaking = bool(match and match.group("breaking")) or bool(BREAKING_PATTERN.search(message))
    return ReleaseCommit(
        sha=sha,
        subject=subject,
        message=message,
        type=commit_type,
        breaking=breaking,
        valid=match is not None,
    )


def read_current_version() -> str:
    content = PYPROJECT_PATH.read_text(encoding="utf-8")
    match = VERSION_PATTERN.search(content)
    if match is None:
        raise RuntimeError("Unable to locate project version in pyproject.toml")
    return match.group("version")


def bump_version(current_version: str, commits: list[ReleaseCommit]) -> str:
    major, minor, patch = (int(part) for part in current_version.split("."))

    if any(commit.breaking for commit in commits):
        return f"{major + 1}.0.0"
    if any(commit.type == "feat" for commit in commits):
        return f"{major}.{minor + 1}.0"
    if any(commit.type in PATCH_TYPES for commit in commits):
        return f"{major}.{minor}.{patch + 1}"
    return f"{major}.{minor}.{patch + 1}"


def read_previous_tag() -> str | None:
    result = subprocess.run(
        ["git", "describe", "--tags", "--match", "v[0-9]*.[0-9]*.[0-9]*", "--abbrev=0"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


def update_pyproject_version(next_version: str) -> None:
    content = PYPROJECT_PATH.read_text(encoding="utf-8")
    updated = VERSION_PATTERN.sub(rf"\g<1>{next_version}\3", content, count=1)
    PYPROJECT_PATH.write_text(updated, encoding="utf-8")


def build_release_section(
    *,
    version: str,
    previous_tag: str | None,
    commits: list[ReleaseCommit],
    pull_request: dict[str, object] | None,
) -> str:
    release_date = date.today().isoformat()
    compare_url = compare_link(previous_tag, version)
    title = f"## [{version}]({compare_url}) ({release_date})" if compare_url else f"## [{version}] ({release_date})"

    lines = [title, ""]
    if pull_request:
        lines.append(
            f"_Automated release from [#{pull_request['number']}]({pull_request['url']}) {pull_request['title']}_"
        )
        lines.append("")

    grouped = group_commits(commits)
    for commit_type, section_title in SECTION_TITLES.items():
        section_commits = grouped.get(commit_type, [])
        if not section_commits:
            continue
        lines.append(f"### {section_title}")
        lines.append("")
        for commit in section_commits:
            short_sha = commit.sha[:7]
            lines.append(f"- {commit.subject} ({short_sha})")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def compare_link(previous_tag: str | None, version: str) -> str | None:
    repository = os.environ.get("GITHUB_REPOSITORY")
    if repository is None or previous_tag is None:
        return None
    return f"https://github.com/{repository}/compare/{previous_tag}...v{version}"


def group_commits(commits: list[ReleaseCommit]) -> dict[str, list[ReleaseCommit]]:
    grouped: dict[str, list[ReleaseCommit]] = {}
    for commit in commits:
        section_key = commit.type if commit.type in SECTION_TITLES else "chore"
        grouped.setdefault(section_key, []).append(commit)
    return grouped


def prepend_changelog(release_notes: str) -> None:
    existing = CHANGELOG_PATH.read_text(encoding="utf-8")
    if existing.startswith("# Changelog\n"):
        remainder = existing[len("# Changelog\n") :].lstrip("\n")
        updated = f"# Changelog\n\n{release_notes.rstrip()}\n\n{remainder}"
    else:
        updated = f"# Changelog\n\n{release_notes.rstrip()}\n\n{existing.lstrip()}"
    CHANGELOG_PATH.write_text(updated.rstrip() + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
