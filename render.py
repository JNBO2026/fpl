#!/usr/bin/env python3
"""Inline data.json into template.html to produce a self-contained index.html."""
import json, os

HERE = os.path.dirname(os.path.abspath(__file__))
data = json.load(open(os.path.join(HERE, "data.json")))
tpl = open(os.path.join(HERE, "template.html")).read()

payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
# keep the JSON from terminating the script block
payload = payload.replace("</", "<\\/")

out = tpl.replace("__DATA__", payload)
path = os.path.join(HERE, "index.html")
open(path, "w").write(out)
print(f"wrote {path}  ({os.path.getsize(path)/1024:.0f} KB)")
