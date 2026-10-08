"""Generate metrics-stats.svg and metrics-languages.svg.
Also patches metrics-calendar.svg, swapping its "Best streak" field for the
all-time total PR count and adding total commits."""
import datetime as dt
import json
import os
import re
import urllib.request

USER = os.environ["GH_USER"]
TOKEN = os.environ["GH_TOKEN"]


def format_count(n):
    """1234 -> '1.2K', 999 -> '999' (truncates, doesn't round)."""
    if n < 1000:
        return str(n)
    value = f"{n // 100 / 10:.1f}".rstrip("0").rstrip(".")
    return f"{value}K"


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
        f"Total commits {format_count(total_commits)}"
        "</div>"
    )
    calendar = re.sub(
        r"(Total PRs \d+\s*)(</div>)",
        lambda m: m.group(1) + m.group(2) + commits_field,
        calendar,
    )
    open(calendar_path, "w").write(calendar)

# Generate metrics-languages.svg: top languages across all owned non-fork repositories
repos_query = """query($u:String!,$after:String){user(login:$u){
    repositories(ownerAffiliations:OWNER, first:100, isFork:false, after:$after){
        pageInfo{hasNextPage endCursor}
        nodes{
            languages(first:10, orderBy:{field:SIZE, direction:DESC}){
                edges{
                    size
                    node{name color}
                }
            }
        }
    }
}}"""

cursor = None
lang_sizes = {}
lang_colors = {}
while True:
    repo_conn = gql(repos_query, u=USER, after=cursor)["repositories"]
    for repo in repo_conn["nodes"]:
        for edge in repo["languages"]["edges"]:
            name = edge["node"]["name"]
            color = edge["node"]["color"]
            size = edge["size"]
            lang_sizes[name] = lang_sizes.get(name, 0) + size
            if color and name not in lang_colors:
                lang_colors[name] = color
    if not repo_conn["pageInfo"]["hasNextPage"]:
        break
    cursor = repo_conn["pageInfo"]["endCursor"]

if lang_sizes:
    total_unique = len(lang_sizes)
    top_langs = sorted(lang_sizes.items(), key=lambda x: x[1], reverse=True)[:5]
    top_total = sum(size for _, size in top_langs)

    if top_total > 0:
        bar_width = 460
        current_x = 0
        bar_rects = []
        for name, size in top_langs:
            w = (size / top_total) * bar_width
            color = lang_colors.get(name, "#959DA5")
            bar_rects.append(
                f'                    <rect mask="url(#languages-bar)" x="{current_x}" y="0" width="{w}" height="8" fill="{color}"/>'
            )
            current_x += w

        col1_items = []
        col2_items = []
        for i, (name, size) in enumerate(top_langs):
            pct = f"{(size / top_total) * 100:.2f}%"
            color = lang_colors.get(name, "#959DA5")
            item_html = (
                '                        <div class="field language details">\n'
                '                            <div class="field">\n'
                '                                <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16" width="16" height="16">\n'
                f'                                    <path fill="{color}" fill-rule="evenodd" d="M8 4a4 4 0 100 8 4 4 0 000-8z"/>\n'
                '                                </svg>\n'
                f'                                {name}\n'
                '                            </div>\n'
                '                            <small>\n'
                f'                                <div>{pct}</div>\n'
                '                            </small>\n'
                '                        </div>'
            )
            if i % 2 == 0:
                col1_items.append(item_html)
            else:
                col2_items.append(item_html)

        LANG_TEMPLATE = """<svg xmlns="http://www.w3.org/2000/svg" width="480" height="124" class="">
    <defs>
        <style/>
    </defs>
    <style>@keyframes animation-gauge{0%{stroke-dasharray:0 329}}@keyframes animation-rainbow{0%,to{color:#7f00ff;fill:#7f00ff}14%{color:#a933ff;fill:#a933ff}29%{color:#007fff;fill:#007fff}43%{color:#00ff7f;fill:#00ff7f}57%{color:#ff0;fill:#ff0}71%{color:#ff7f00;fill:#ff7f00}86%{color:red;fill:red}}svg{font-family:-apple-system,BlinkMacSystemFont,Segoe UI,Helvetica,Arial,sans-serif,Apple Color Emoji,Segoe UI Emoji;color:#777}h2,h3{margin:8px 0 2px;padding:0;color:#0366d6;font-weight:400}h2 svg,h3 svg{fill:currentColor}h2{font-size:16px}h3,svg{font-size:14px}section&gt;.field{margin-left:5px;margin-right:5px}.field{display:flex;align-items:center;margin-bottom:2px;white-space:nowrap}.field svg{margin:0 8px;fill:#959da5;flex-shrink:0}.row{display:flex;flex-wrap:wrap}.row section{flex:1 1 0}.column{display:flex;flex-direction:column;align-items:center}#metrics-end,.fill-width{width:100%}svg.bar{margin:4px 0}.field.language{margin:0 8px;flex-grow:0}.field.language.details,.field.language.details small{display:flex;justify-content:space-between}.field.language.details small{color:#666;text-align:right}.field.language.details small&gt;*,.field.language.details&gt;*{flex:1 1 0}.field.language.details small&gt;:not(:last-child){margin-right:6px}:root{--color-calendar-graph-day-bg:#ebedf0;--color-calendar-graph-day-border:rgba(27,31,35,0.06);--color-calendar-graph-day-L1-bg:#9be9a8;--color-calendar-graph-day-L2-bg:#40c463;--color-calendar-graph-day-L3-bg:#30a14e;--color-calendar-graph-day-L4-bg:#216e39;--color-calendar-halloween-graph-day-L1-bg:#ffee4a;--color-calendar-halloween-graph-day-L2-bg:#ffc501;--color-calendar-halloween-graph-day-L3-bg:#fe9600;--color-calendar-halloween-graph-day-L4-bg:#03001c;--color-calendar-winter-graph-day-L1-bg:#0a3069;--color-calendar-winter-graph-day-L2-bg:#0969da;--color-calendar-winter-graph-day-L3-bg:#54aeff;--color-calendar-winter-graph-day-L4-bg:#b6e3ff;--color-calendar-graph-day-L4-border:rgba(27,31,35,0.06);--color-calendar-graph-day-L3-border:rgba(27,31,35,0.06);--color-calendar-graph-day-L2-border:rgba(27,31,35,0.06);--color-calendar-graph-day-L1-border:rgba(27,31,35,0.06)}</style>
    <style/>
    <foreignObject x="0" y="0" width="100%" height="100%">
        <div xmlns="http://www.w3.org/1999/xhtml" xmlns:xlink="http://www.w3.org/1999/xlink" class="items-wrapper">
            <section>
                <h2 class="field">
                    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16" width="16" height="16">
                        <path fill-rule="evenodd" d="M1.5 2.75a.25.25 0 01.25-.25h12.5a.25.25 0 01.25.25v8.5a.25.25 0 01-.25.25h-6.5a.75.75 0 00-.53.22L4.5 14.44v-2.19a.75.75 0 00-.75-.75h-2a.25.25 0 01-.25-.25v-8.5zM1.75 1A1.75 1.75 0 000 2.75v8.5C0 12.216.784 13 1.75 13H3v1.543a1.457 1.457 0 002.487 1.03L8.061 13h6.189A1.75 1.75 0 0016 11.25v-8.5A1.75 1.75 0 0014.25 1H1.75zm5.03 3.47a.75.75 0 010 1.06L5.31 7l1.47 1.47a.75.75 0 01-1.06 1.06l-2-2a.75.75 0 010-1.06l2-2a.75.75 0 011.06 0zm2.44 0a.75.75 0 000 1.06L10.69 7 9.22 8.47a.75.75 0 001.06 1.06l2-2a.75.75 0 000-1.06l-2-2a.75.75 0 00-1.06 0z"/>
                    </svg>
                    __TOTAL_LANGS__ Languages
                </h2>
            </section>
            <section class="column">
                <h3 class="field">Most used languages</h3>
                <svg class="bar" xmlns="http://www.w3.org/2000/svg" width="460" height="8">
                    <mask id="languages-bar">
                        <rect x="0" y="0" width="460" height="8" fill="white" rx="5"/>
                    </mask>
                    <rect mask="url(#languages-bar)" x="0" y="0" width="0" height="8" fill="#d1d5da"/>
__BAR_RECTS__
                </svg>
                <div class="row fill-width">
                    <section>
__COL1_ITEMS__
                    </section>
                    <section>
__COL2_ITEMS__
                    </section>
                </div>
            </section>
        </div>
        <div xmlns="http://www.w3.org/1999/xhtml" id="metrics-end"></div>
    </foreignObject>
</svg>
"""
        languages_svg = (
            LANG_TEMPLATE
            .replace("__TOTAL_LANGS__", str(total_unique))
            .replace("__BAR_RECTS__", "\n".join(bar_rects))
            .replace("__COL1_ITEMS__", "\n".join(col1_items))
            .replace("__COL2_ITEMS__", "\n".join(col2_items))
        )
        open("metrics-languages.svg", "w").write(languages_svg)


