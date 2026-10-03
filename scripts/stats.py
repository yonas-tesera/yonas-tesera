"""Generate metrics-stats.svg: joined year, total contribs, followers, repos.
Also patches metrics-calendar.svg, swapping its "Best streak" field for the
all-time total PR count."""
import datetime as dt
import json
import os
import re
import urllib.request

USER = os.environ["GH_USER"]
TOKEN = os.environ["GH_TOKEN"]


def gql(query, **variables):
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": query, "variables": variables}).encode(),
        headers={"Authorization": f"bearer {TOKEN}"},
    )
    with urllib.request.urlopen(req) as res:
        data = json.load(res)
    if "errors" in data:
        raise SystemExit(data["errors"])
    return data["data"]["user"]


profile = gql(
    "query($u:String!){user(login:$u){createdAt followers{totalCount} "
    "repositories(ownerAffiliations:OWNER){totalCount} pullRequests{totalCount}}}",
    u=USER,
)
created = dt.datetime.fromisoformat(profile["createdAt"].replace("Z", "+00:00"))
now = dt.datetime.now(dt.timezone.utc)

# The calendar API is limited to 1 year per request, so walk year by year.
days = {}
total_commits = 0
for year in range(created.year, now.year + 1):
    start = max(created, dt.datetime(year, 1, 1, tzinfo=dt.timezone.utc))
    end = min(now, dt.datetime(year, 12, 31, 23, 59, 59, tzinfo=dt.timezone.utc))
    collection = gql(
        "query($u:String!,$f:DateTime!,$t:DateTime!){user(login:$u){"
        "contributionsCollection(from:$f,to:$t){totalCommitContributions contributionCalendar{weeks{"
        "contributionDays{date contributionCount}}}}}}",
        u=USER, f=start.isoformat(), t=end.isoformat(),
    )["contributionsCollection"]
    total_commits += collection["totalCommitContributions"]
    for week in collection["contributionCalendar"]["weeks"]:
        for d in week["contributionDays"]:
            days[d["date"]] = d["contributionCount"]

total_contribs = sum(days.values())

items = [
    (str(created.year), "joined"),
    (str(total_contribs), "contribs"),
    (str(profile["followers"]["totalCount"]), "followers"),
    (str(profile["repositories"]["totalCount"]), "repos"),
]

CHAR, PAD, GAP, H = 7.2, 10, 6, 22  # monospace 12px, pill padding, gap, height
pills, x = "", 0
for value, label in items:
    w = round((len(value) + 1 + len(label)) * CHAR + PAD * 2)
    pills += (
        f'<rect x="{x}" y="1" width="{w}" height="{H}" rx="{H // 2}" class="p"/>'
        f'<text x="{x + PAD}" y="16"><tspan class="v">{value}</tspan>'
        f'<tspan class="l"> {label}</tspan></text>'
    )
    x += w + GAP
total = x - GAP

svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="{total}" height="{H + 2}" viewBox="0 0 {total} {H + 2}">
<style>
  text {{ font: 12px 'Fira Code', ui-monospace, SFMono-Regular, Menlo, monospace; white-space: pre }}
  .p {{ fill: none; stroke: #d0d7de }}
  .v {{ fill: #1f2328; font-weight: 700 }}
  .l {{ fill: #656d76 }}
  @media (prefers-color-scheme: dark) {{
    .p {{ stroke: #30363d }} .v {{ fill: #e6edf3 }} .l {{ fill: #8b949e }}
  }}
</style>
{pills}
</svg>
"""
open("metrics-stats.svg", "w").write(svg)

# Swap the calendar block's "Best streak" field for the all-time total PR
# count, keeping it in the same position, then add a "Total commits" field
# right below it.
calendar_path = "metrics-calendar.svg"
if os.path.exists(calendar_path):
    calendar = open(calendar_path).read()
    calendar = re.sub(
        r"Best streak \d+ days?",
        f'Total PRs {profile["pullRequests"]["totalCount"]}',
        calendar,
    )
    commits_field = (
        '<div class="field">'
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16" width="16" height="16">'
        '<path fill-rule="evenodd" d="M10.5 7.75a2.5 2.5 0 11-5 0 2.5 2.5 0 015 0zm1.43.75a4.002 4.002 0 01-7.86 0H.75a.75.75 0 110-1.5h3.32a4.001 4.001 0 017.86 0h3.32a.75.75 0 110 1.5h-3.32z"/>'
        "</svg>"
        f"Total commits {total_commits}"
        "</div>"
    )
    calendar = re.sub(
        r"(Total PRs \d+\s*)(</div>)",
        lambda m: m.group(1) + m.group(2) + commits_field,
        calendar,
    )
    open(calendar_path, "w").write(calendar)
