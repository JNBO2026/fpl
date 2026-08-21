#!/usr/bin/env python3
"""
Inline data.json into template.html.

Produces two files from one template:
  index.html     a complete standalone document (what Vercel serves)
  artifact.html  body content only, for hosts that supply their own <head>
"""
import json, os

HERE = os.path.dirname(os.path.abspath(__file__))

FONT_LINK = 'https://fonts.googleapis.com/css2?family=League+Spartan:wght@500;600;700;800&family=Source+Sans+3:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500;600&display=swap'

HEAD = f"""  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
  <meta name="theme-color" content="#0B0E13">
  <meta name="color-scheme" content="dark">
  <meta name="description" content="Fantasy Premier League squad and the underlying data behind every selection.">
  <title>AI FC Control Room</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link rel="stylesheet" href="{FONT_LINK}">
"""

# Artifact hosts inject their own head; only the title and font link belong here.
ARTIFACT_HEAD = f"""<title>AI FC Control Room</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="{FONT_LINK}">
"""

data = json.load(open(os.path.join(HERE, "data.json")))
body = open(os.path.join(HERE, "template.html")).read()

payload = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
body = body.replace("__DATA__", payload)

full = f"""<!doctype html>
<html lang="en">
<head>
{HEAD}</head>
<body>
{body}</body>
</html>
"""

for name, content in (("index.html", full), ("artifact.html", ARTIFACT_HEAD + "\n" + body)):
    path = os.path.join(HERE, name)
    open(path, "w").write(content)
    print(f"wrote {name}  ({os.path.getsize(path)/1024:.0f} KB)")
