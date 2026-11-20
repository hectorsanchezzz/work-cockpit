#!/usr/bin/env python3
"""Turn the rendered page into the locally served out/index.html.

The live design is D (out/cockpit-d.html, from proposals.py --live). If that file is missing or older
than out/cockpit-v2.html (the D step failed this run), it falls back to the v2 page.

Adds the Dock icon links and a small script that reloads the page when a
newer snapshot lands (it polls out/summary.json, only while the window is visible).
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "out"
v2, d = OUT / "cockpit-v2.html", OUT / "cockpit-d.html"
src = d if d.exists() and d.stat().st_mtime >= v2.stat().st_mtime else v2
page = src.read_text(encoding="utf-8")


def lane_colors():
    """CSS for the lane colours from config.json: lanes[].color = [light, dark] (hex). Lanes that share a
    colour (all the university subjects, say) read as one group on the page."""
    try:
        lanes = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))["lanes"]
    except (OSError, ValueError, KeyError):
        return ""
    light, dark = [], []
    for l in lanes:
        c = l.get("color")
        if isinstance(c, list) and len(c) == 2 and all(isinstance(x, str) and x.startswith("#") for x in c):
            light.append(f".l-{l['key']}{{--lc:{c[0]}}}")
            dark.append(f".l-{l['key']}{{--lc:{c[1]}}}")
    if not light:
        return ""
    dk = "".join(f':root:not([data-theme="light"]) {r}' for r in dark)
    forced = "".join(f':root[data-theme="dark"] {r}' for r in dark)
    tint = ".ev,.ag-i{background:color-mix(in srgb,var(--lc) 16%,var(--panel))!important}"  # whole block takes the colour
    return ("<style>" + tint + "".join(light) + "@media (prefers-color-scheme:dark){" + dk + "}" + forced + "</style>")
head = ('<link rel="icon" href="icon.png"><link rel="apple-touch-icon" href="icon.png">'
        '<meta name="apple-mobile-web-app-title" content="Work Cockpit">')
script = """<script>
(function(){
  var seen=null;
  function check(){
    if(document.hidden) return;
    fetch('summary.json',{cache:'no-store'}).then(function(r){return r.json()}).then(function(s){
      var v=s.generated+'|'+s.linear_generated+'|'+(s.edited||'');
      if(seen===null){seen=v;return}
      if(v!==seen && !document.querySelector('details[open]:not([data-lf])') && !window.cockpitBusy) location.reload();
    }).catch(function(){});
  }
  check(); setInterval(check,60000);
  document.addEventListener('visibilitychange',check);
})();
</script>"""
page = page.replace("<title>Work Cockpit v2</title>", "<title>Work Cockpit</title>" + head, 1)
colors = lane_colors()
page = (page.replace("</head>", colors + "</head>", 1) if "</head>" in page else colors + page) + script
tmp = OUT / "index.html.tmp"
tmp.write_text(page, encoding="utf-8")
tmp.replace(OUT / "index.html")
print(f"wrote out/index.html from {src.name}")
