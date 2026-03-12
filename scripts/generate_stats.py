#!/usr/bin/env python3
from __future__ import annotations

import datetime as dt
import json
import os
import textwrap
import urllib.parse
import urllib.request
from typing import Dict, List, Tuple

API_REST = "https://api.github.com"
API_GRAPHQL = "https://api.github.com/graphql"


def gh_request(url: str, token: str) -> dict | list:
    req = urllib.request.Request(url)
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Accept", "application/vnd.github+json")
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def gh_graphql(query: str, variables: dict, token: str) -> dict:
    payload = json.dumps({"query": query, "variables": variables}).encode("utf-8")
    req = urllib.request.Request(API_GRAPHQL, data=payload, method="POST")
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=30) as resp:
        out = json.loads(resp.read().decode("utf-8"))
    if out.get("errors"):
        raise RuntimeError(f"GraphQL error: {out['errors']}")
    return out["data"]


def fetch_all_owned_repos(token: str) -> List[dict]:
    repos: List[dict] = []
    page = 1
    while True:
        q = urllib.parse.urlencode(
            {
                "affiliation": "owner",
                "sort": "updated",
                "per_page": 100,
                "page": page,
            }
        )
        chunk = gh_request(f"{API_REST}/user/repos?{q}", token)
        if not chunk:
            break
        repos.extend(chunk)
        if len(chunk) < 100:
            break
        page += 1
    return repos


def short(n: int) -> str:
    if n >= 1_000_000:
        return f"{n/1_000_000:.1f}m".rstrip("0").rstrip(".")
    if n >= 1_000:
        return f"{n/1_000:.1f}k".rstrip("0").rstrip(".")
    return str(n)


def render_svg(stats: Dict[str, int], title: str) -> str:
    rows: List[Tuple[str, str]] = [
        ("⭐ Stars (all owned repos)", short(stats["stars_earned"])),
        ("🧩 Commits (last year)", short(stats["commits_last_year"])),
        ("🔀 PRs (all time)", short(stats["prs_total"])),
        ("🐞 Issues (all time)", short(stats["issues_total"])),
        ("📦 Contributed repos (last year)", short(stats["contributed_repos_last_year"])),
    ]

    line_h = 34
    card_w = 760
    top = 76
    card_h = top + line_h * len(rows) + 22

    text_rows = []
    for idx, (label, value) in enumerate(rows):
        y = top + idx * line_h
        text_rows.append(
            f'''<text x="38" y="{y}" class="label">{label}</text>\n'''
            f'''<text x="722" y="{y}" text-anchor="end" class="value">{value}</text>'''
        )

    updated = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    return f"""<svg width=\"{card_w}\" height=\"{card_h}\" viewBox=\"0 0 {card_w} {card_h}\" xmlns=\"http://www.w3.org/2000/svg\" role=\"img\" aria-label=\"{title}\">
  <defs>
    <linearGradient id=\"bg\" x1=\"0\" y1=\"0\" x2=\"1\" y2=\"1\">
      <stop offset=\"0%\" stop-color=\"#0f172a\"/>
      <stop offset=\"100%\" stop-color=\"#111827\"/>
    </linearGradient>
  </defs>
  <style>
    .title {{ font: 700 28px 'Inter', 'Segoe UI', sans-serif; fill: #f8fafc; }}
    .sub {{ font: 500 14px 'Inter', 'Segoe UI', sans-serif; fill: #94a3b8; }}
    .label {{ font: 600 20px 'Inter', 'Segoe UI', sans-serif; fill: #cbd5e1; }}
    .value {{ font: 700 22px 'Inter', 'Segoe UI', sans-serif; fill: #22d3ee; }}
    .line {{ stroke: #1e293b; stroke-width: 1; }}
  </style>

  <rect x=\"2\" y=\"2\" width=\"{card_w - 4}\" height=\"{card_h - 4}\" rx=\"18\" fill=\"url(#bg)\" stroke=\"#1f2937\"/>
  <text x=\"34\" y=\"42\" class=\"title\">{title}</text>
  <text x=\"34\" y=\"62\" class=\"sub\">Private + public data via GitHub API token</text>

  {''.join(text_rows)}

  <text x=\"34\" y=\"{card_h - 16}\" class=\"sub\">Updated: {updated}</text>
</svg>
"""


def main() -> None:
    token = os.getenv("GITHUB_TOKEN", "").strip()
    if not token:
        raise SystemExit("GITHUB_TOKEN is required")

    username = os.getenv("GITHUB_USERNAME", "").strip()

    repos = fetch_all_owned_repos(token)
    stars = sum(int(r.get("stargazers_count", 0)) for r in repos if not r.get("fork", False))

    now = dt.datetime.now(dt.timezone.utc)
    frm = (now - dt.timedelta(days=365)).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    to = now.replace(microsecond=0).isoformat().replace("+00:00", "Z")

    query = textwrap.dedent(
        """
        query($from: DateTime!, $to: DateTime!) {
          viewer {
            login
            name
            pullRequests { totalCount }
            issues { totalCount }
            contributionsCollection(from: $from, to: $to) {
              totalCommitContributions
              totalRepositoriesWithContributedCommits
            }
          }
        }
        """
    )
    data = gh_graphql(query, {"from": frm, "to": to}, token)["viewer"]

    login = data["login"]
    if username and username.lower() != login.lower():
        raise SystemExit(
            f"Token belongs to '{login}', but GITHUB_USERNAME is set to '{username}'. Use matching account/token."
        )

    title_name = data.get("name") or login

    stats = {
        "login": login,
        "name": title_name,
        "stars_earned": stars,
        "commits_last_year": int(data["contributionsCollection"]["totalCommitContributions"]),
        "prs_total": int(data["pullRequests"]["totalCount"]),
        "issues_total": int(data["issues"]["totalCount"]),
        "contributed_repos_last_year": int(
            data["contributionsCollection"]["totalRepositoriesWithContributedCommits"]
        ),
        "generated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
    }

    os.makedirs("generated", exist_ok=True)
    with open("generated/stats.json", "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)
        f.write("\n")

    svg = render_svg(stats, f"{title_name}'s GitHub Private Stats")
    with open("generated/stats.svg", "w", encoding="utf-8") as f:
        f.write(svg)

    print("Generated generated/stats.svg + generated/stats.json")


if __name__ == "__main__":
    main()
