"""Generate metrics-stats.svg: joined year, longest streak, followers."""
import datetime as dt
import json
import os
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
    "query($u:String!){user(login:$u){createdAt followers{totalCount} repositories(ownerAffiliations:OWNER){totalCount}}}", u=USER
)
created = dt.datetime.fromisoformat(profile["createdAt"].replace("Z", "+00:00"))
now = dt.datetime.now(dt.timezone.utc)

# The calendar API is limited to 1 year per request, so walk year by year.
days = {}
for year in range(created.year, now.year + 1):
    start = max(created, dt.datetime(year, 1, 1, tzinfo=dt.timezone.utc))
    end = min(now, dt.datetime(year, 12, 31, 23, 59, 59, tzinfo=dt.timezone.utc))
    cal = gql(
        "query($u:String!,$f:DateTime!,$t:DateTime!){user(login:$u){"
        "contributionsCollection(from:$f,to:$t){contributionCalendar{weeks{"
        "contributionDays{date contributionCount}}}}}}",
        u=USER, f=start.isoformat(), t=end.isoformat(),
    )["contributionsCollection"]["contributionCalendar"]["weeks"]
    for week in cal:
        for d in week["contributionDays"]:
            days[d["date"]] = d["contributionCount"]

longest = run = 0
prev = None
for date in sorted(days):
    day = dt.date.fromisoformat(date)
    if days[date] > 0:
        run = run + 1 if prev and (day - prev).days == 1 else 1
        prev = day
        longest = max(longest, run)
    else:
        run, prev = 0, None

items = [
    (str(created.year), "joined"),
    (f"{longest}", "longest streak"),
    (f"{profile['followers']['totalCount']}", "followers"),
    (f"{profile['repositories']['totalCount']}", "repositories"),
]

cells = ""
for i, (value, label) in enumerate(items):
    x = 20 + i * 145
    cells += (
        f'<text x="{x}" y="42" class="v">{value}</text>'
        f'<text x="{x}" y="64" class="l">{label}</text>'
    )

svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="590" height="88" viewBox="0 0 590 88">
<style>
  .v {{ font: 700 26px 'Segoe UI', Ubuntu, sans-serif; fill: #1f2328 }}
  .l {{ font: 13px 'Segoe UI', Ubuntu, sans-serif; fill: #656d76 }}
  @media (prefers-color-scheme: dark) {{
    .v {{ fill: #e6edf3 }} .l {{ fill: #8b949e }}
  }}
</style>
{cells}
</svg>
"""
open("metrics-stats.svg", "w").write(svg)
