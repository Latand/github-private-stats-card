#!/usr/bin/env python3
from __future__ import annotations

import datetime as dt
import html
import json
import os
import urllib.parse
import urllib.request
from typing import Dict, List, Tuple

API_REST = "https://api.github.com"
API_GRAPHQL = "https://api.github.com/graphql"


# ---------- HTTP helpers ----------

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


# ---------- Data fetching ----------

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


def fetch_repo_languages(repos: List[dict], token: str) -> Dict[str, int]:
    by_lang: Dict[str, int] = {}
    for repo in repos:
        if repo.get("fork"):
            continue
        languages_url = str(repo.get("languages_url", "")).strip()
        if not languages_url:
            continue
        payload = gh_request(languages_url, token)
        if not isinstance(payload, dict):
            continue
        for lang, n in payload.items():
            by_lang[lang] = by_lang.get(lang, 0) + int(n)
    return by_lang


def fetch_viewer_basics(token: str) -> dict:
    query = """
    query {
      viewer {
        login
        name
        createdAt
        pullRequests { totalCount }
        issues { totalCount }
      }
    }
    """
    return gh_graphql(query, {}, token)["viewer"]


def fetch_contrib_window(token: str, date_from: dt.date, date_to: dt.date) -> dict:
    # GitHub limitation: contributionsCollection window must be <= 1 year.
    frm = f"{date_from.isoformat()}T00:00:00Z"
    to = f"{date_to.isoformat()}T23:59:59Z"
    query = """
    query($from: DateTime!, $to: DateTime!) {
      viewer {
        contributionsCollection(from: $from, to: $to) {
          totalCommitContributions
          totalRepositoriesWithContributedCommits
          contributionCalendar {
            totalContributions
            weeks {
              contributionDays {
                date
                contributionCount
              }
            }
          }
        }
      }
    }
    """
    return gh_graphql(query, {"from": frm, "to": to}, token)["viewer"]["contributionsCollection"]


def collect_daily_contributions(token: str, start_date: dt.date, end_date: dt.date) -> Dict[str, int]:
    daily: Dict[str, int] = {}
    cur = start_date
    while cur <= end_date:
        win_end = min(cur + dt.timedelta(days=364), end_date)
        block = fetch_contrib_window(token, cur, win_end)
        for week in block["contributionCalendar"]["weeks"]:
            for day in week["contributionDays"]:
                d = day["date"]
                c = int(day["contributionCount"])
                # Keep max in case of accidental overlap
                if c > daily.get(d, 0):
                    daily[d] = c
        cur = win_end + dt.timedelta(days=1)
    return daily


# ---------- Metrics ----------

def short(n: int) -> str:
    if n >= 1_000_000:
        return f"{n/1_000_000:.1f}m".rstrip("0").rstrip(".")
    if n >= 1_000:
        return f"{n/1_000:.1f}k".rstrip("0").rstrip(".")
    return str(n)


def parse_gh_datetime(s: str) -> dt.datetime:
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00"))


def compute_streaks(daily: Dict[str, int], today: dt.date) -> dict:
    if not daily:
        return {
            "current": 0,
            "current_start": None,
            "current_end": None,
            "longest": 0,
            "longest_start": None,
            "longest_end": None,
            "active_days": 0,
            "total_contributions": 0,
        }

    all_dates = sorted(dt.date.fromisoformat(d) for d in daily.keys())
    start = all_dates[0]
    end = today

    longest = 0
    longest_start = None
    longest_end = None
    run = 0
    run_start = None

    active_days = 0
    total_contribs = 0

    d = start
    while d <= end:
        c = daily.get(d.isoformat(), 0)
        total_contribs += c
        if c > 0:
            active_days += 1
            if run == 0:
                run_start = d
            run += 1
            if run > longest:
                longest = run
                longest_start = run_start
                longest_end = d
        else:
            run = 0
            run_start = None
        d += dt.timedelta(days=1)

    # Current streak: valid if latest active day is today or yesterday.
    positive_days = sorted((dt.date.fromisoformat(k) for k, v in daily.items() if v > 0))
    if not positive_days:
        current = 0
        current_start = None
        current_end = None
    else:
        last_active = positive_days[-1]
        if (today - last_active).days > 1:
            current = 0
            current_start = None
            current_end = None
        else:
            current_end = last_active
            cur = last_active
            while daily.get((cur - dt.timedelta(days=1)).isoformat(), 0) > 0:
                cur -= dt.timedelta(days=1)
            current_start = cur
            current = (current_end - current_start).days + 1

    return {
        "current": current,
        "current_start": current_start.isoformat() if current_start else None,
        "current_end": current_end.isoformat() if current_end else None,
        "longest": longest,
        "longest_start": longest_start.isoformat() if longest_start else None,
        "longest_end": longest_end.isoformat() if longest_end else None,
        "active_days": active_days,
        "total_contributions": total_contribs,
    }


# ---------- SVG renderers ----------

def svg_header(width: int, height: int, aria_label: str) -> str:
    return f"""<svg width=\"{width}\" height=\"{height}\" viewBox=\"0 0 {width} {height}\" xmlns=\"http://www.w3.org/2000/svg\" role=\"img\" aria-label=\"{html.escape(aria_label)}\">"""


def svg_styles() -> str:
    return """
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="#0b1220"/>
      <stop offset="100%" stop-color="#111827"/>
    </linearGradient>
  </defs>
  <style>
    .title { font: 700 28px 'Inter', 'Segoe UI', sans-serif; fill: #f8fafc; }
    .sub { font: 500 14px 'Inter', 'Segoe UI', sans-serif; fill: #94a3b8; }
    .label { font: 600 18px 'Inter', 'Segoe UI', sans-serif; fill: #dbe7ff; }
    .value { font: 700 20px 'Inter', 'Segoe UI', sans-serif; fill: #22d3ee; }
    .muted { font: 500 13px 'Inter', 'Segoe UI', sans-serif; fill: #94a3b8; }
    .chip { fill: #111a2d; stroke: #23324f; }
    .bar-bg { fill: #1f2937; }
    .bar-fg { fill: #22d3ee; }
  </style>
"""


def render_stats_svg(stats: dict, title: str, updated_human: str) -> str:
    width, height = 860, 330
    rows: List[Tuple[str, str]] = [
        ("⭐ Stars (owned repos)", short(stats["stars_earned"])),
        ("🧩 Commits (last 365d)", short(stats["commits_last_year"])),
        ("🔀 Pull Requests (all time)", short(stats["prs_total"])),
        ("🐞 Issues (all time)", short(stats["issues_total"])),
        ("📦 Contributed repos (last 365d)", short(stats["contributed_repos_last_year"])),
    ]

    lines = []
    y = 102
    for label, value in rows:
        lines.append(f'<rect x="34" y="{y - 24}" width="792" height="34" rx="8" class="chip"/>')
        lines.append(f'<text x="48" y="{y}" class="label">{html.escape(label)}</text>')
        lines.append(f'<text x="808" y="{y}" text-anchor="end" class="value">{html.escape(value)}</text>')
        y += 44

    return (
        svg_header(width, height, f"{title} stats")
        + svg_styles()
        + f'''<rect x="2" y="2" width="{width-4}" height="{height-4}" rx="18" fill="url(#bg)" stroke="#1f2937"/>
  <text x="34" y="45" class="title">{html.escape(title)} · Overview</text>
  <text x="34" y="68" class="sub">Private + public metrics from GitHub API</text>
  {"".join(lines)}
  <text x="34" y="314" class="muted">Updated: {html.escape(updated_human)}</text>
</svg>'''
    )


def render_top_langs_svg(stats: dict, title: str, updated_human: str) -> str:
    width, height = 860, 340
    langs = stats["languages_top"][:7]
    max_bytes = max((int(x["bytes"]) for x in langs), default=1)

    rows = []
    y = 98
    for item in langs:
        name = item["name"]
        value = int(item["bytes"])
        pct = float(item["percent"])
        bar_w = int((value / max_bytes) * 430)

        rows.append(f'<text x="48" y="{y}" class="label">{html.escape(name)}</text>')
        rows.append(f'<rect x="290" y="{y-16}" width="450" height="14" rx="7" class="bar-bg"/>')
        rows.append(f'<rect x="290" y="{y-16}" width="{bar_w}" height="14" rx="7" class="bar-fg"/>')
        rows.append(
            f'<text x="808" y="{y}" text-anchor="end" class="value">{html.escape(short(value))} · {pct:.1f}%</text>'
        )
        y += 34

    return (
        svg_header(width, height, f"{title} top languages")
        + svg_styles()
        + f'''<rect x="2" y="2" width="{width-4}" height="{height-4}" rx="18" fill="url(#bg)" stroke="#1f2937"/>
  <text x="34" y="45" class="title">{html.escape(title)} · Top Languages</text>
  <text x="34" y="68" class="sub">Aggregated bytes across owned non-fork repositories</text>
  {"".join(rows)}
  <text x="34" y="324" class="muted">Updated: {html.escape(updated_human)}</text>
</svg>'''
    )


def render_streak_svg(stats: dict, title: str, updated_human: str) -> str:
    width, height = 860, 260
    streak = stats["streak"]

    cards = [
        ("Current streak", str(streak["current"]), streak["current_start"] or "—"),
        ("Longest streak", str(streak["longest"]), streak["longest_start"] or "—"),
        ("Active days", str(streak["active_days"]), "all time"),
        ("Contributions", short(streak["total_contributions"]), "all time"),
    ]

    blocks = []
    x = 34
    for label, value, sub in cards:
        blocks.append(f'<rect x="{x}" y="88" width="188" height="120" rx="12" class="chip"/>')
        blocks.append(f'<text x="{x+12}" y="116" class="sub">{html.escape(label)}</text>')
        blocks.append(f'<text x="{x+12}" y="154" class="title" style="font-size:34px">{html.escape(value)}</text>')
        blocks.append(f'<text x="{x+12}" y="182" class="muted">{html.escape(sub)}</text>')
        x += 202

    return (
        svg_header(width, height, f"{title} streak stats")
        + svg_styles()
        + f'''<rect x="2" y="2" width="{width-4}" height="{height-4}" rx="18" fill="url(#bg)" stroke="#1f2937"/>
  <text x="34" y="45" class="title">{html.escape(title)} · Streak</text>
  <text x="34" y="68" class="sub">Calculated from daily contribution calendar (private + public)</text>
  {"".join(blocks)}
  <text x="34" y="244" class="muted">Updated: {html.escape(updated_human)}</text>
</svg>'''
    )


# ---------- Main ----------

def main() -> None:
    token = os.getenv("GITHUB_TOKEN", "").strip()
    if not token:
        raise SystemExit("GITHUB_TOKEN is required")

    expected_username = os.getenv("GITHUB_USERNAME", "").strip()

    viewer = fetch_viewer_basics(token)
    login = viewer["login"]
    if expected_username and expected_username.lower() != login.lower():
        raise SystemExit(
            f"Token belongs to '{login}', but GITHUB_USERNAME is set to '{expected_username}'."
        )

    display_name = viewer.get("name") or login

    repos = fetch_all_owned_repos(token)
    owned_non_fork = [r for r in repos if not r.get("fork")]
    stars = sum(int(r.get("stargazers_count", 0)) for r in owned_non_fork)

    # Last year window
    today = dt.datetime.now(dt.timezone.utc).date()
    last_year_from = today - dt.timedelta(days=364)
    contrib_1y = fetch_contrib_window(token, last_year_from, today)

    # All-time (chunked yearly)
    created_at = parse_gh_datetime(viewer["createdAt"]).date()
    daily = collect_daily_contributions(token, created_at, today)
    streak = compute_streaks(daily, today)

    lang_totals = fetch_repo_languages(owned_non_fork, token)
    lang_sorted = sorted(lang_totals.items(), key=lambda kv: kv[1], reverse=True)
    total_lang_bytes = sum(v for _, v in lang_sorted) or 1
    languages_top = [
        {
            "name": name,
            "bytes": int(value),
            "percent": round((value / total_lang_bytes) * 100, 2),
        }
        for name, value in lang_sorted[:12]
    ]

    now_utc = dt.datetime.now(dt.timezone.utc)
    updated_human = now_utc.strftime("%Y-%m-%d %H:%M UTC")

    stats = {
        "login": login,
        "name": display_name,
        "generated_at_utc": now_utc.isoformat(),
        "repos_owned_total": len(repos),
        "repos_owned_non_fork": len(owned_non_fork),
        "repos_private": sum(1 for r in repos if r.get("private")),
        "stars_earned": stars,
        "commits_last_year": int(contrib_1y["totalCommitContributions"]),
        "contributions_last_year": int(contrib_1y["contributionCalendar"]["totalContributions"]),
        "prs_total": int(viewer["pullRequests"]["totalCount"]),
        "issues_total": int(viewer["issues"]["totalCount"]),
        "contributed_repos_last_year": int(contrib_1y["totalRepositoriesWithContributedCommits"]),
        "streak": streak,
        "languages_top": languages_top,
    }

    os.makedirs("generated", exist_ok=True)
    with open("generated/stats.json", "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)
        f.write("\n")

    with open("generated/stats.svg", "w", encoding="utf-8") as f:
        f.write(render_stats_svg(stats, display_name, updated_human))

    with open("generated/top-langs.svg", "w", encoding="utf-8") as f:
        f.write(render_top_langs_svg(stats, display_name, updated_human))

    with open("generated/streak.svg", "w", encoding="utf-8") as f:
        f.write(render_streak_svg(stats, display_name, updated_human))

    print("Generated: generated/stats.json, generated/stats.svg, generated/top-langs.svg, generated/streak.svg")


if __name__ == "__main__":
    main()
