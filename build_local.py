#!/usr/bin/env python3
"""Turn the rendered page into the locally served out/index.html.

The live design is D (out/cockpit-d.html, from proposals.py --live). If that file is missing or older
than out/cockpit-v2.html (the D step failed this run), it falls back to the v2 page.

Adds the Dock icon links and a small script that reloads the page when a
newer snapshot lands (it polls out/summary.json, only while the window is visible).
"""
from pathlib import Path

OUT = Path(__file__).resolve().parent / "out"
v2, d = OUT / "cockpit-v2.html", OUT / "cockpit-d.html"
src = d if d.exists() and d.stat().st_mtime >= v2.stat().st_mtime else v2
page = src.read_text()
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
page = page.replace("<title>Work Cockpit v2</title>", "<title>Work Cockpit</title>" + head, 1) + script
tmp = OUT / "index.html.tmp"
tmp.write_text(page)
tmp.replace(OUT / "index.html")
print(f"wrote out/index.html from {src.name}")
