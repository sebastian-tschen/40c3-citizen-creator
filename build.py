#!/usr/bin/env python3
"""Build the self-contained citizen_creator.html.

Reads the styleguide assets (creator parts, icons, fonts, deco) and inlines
them into src/citizen_creator.html -> citizen_creator.html (one file, no
network, no server).

    python3 build.py
"""
import base64
import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src" / "citizen_creator.html"
OUT = ROOT / "citizen_creator.html"

# asset directory -> slot name used in the app / the JSON format
CATEGORIES = [
    (ROOT / "Citizen_Creator_Assets" / "Bodies", "body"),
    (ROOT / "Citizen_Creator_Assets" / "Heads", "head"),
    (ROOT / "Citizen_Creator_Assets" / "Hair", "hair"),
    (ROOT / "Citizen_Creator_Assets" / "Eyes", "eyes"),
    (ROOT / "Citizen_Creator_Assets" / "Noses", "nose"),
    (ROOT / "Citizen_Creator_Assets" / "Mouths", "mouth"),
    (ROOT / "Citizen_Creator_Assets" / "Deco", "deco"),
    (ROOT / "Assets" / "Icons_Deco", "extra"),
]

# The three colour roles every part is drawn in. Source files use slightly
# different hex values for the same role, so normalise them to tokens that the
# app swaps for the chosen palette: @M main, @L light, @D dark.
ROLE = {
    "#6ab143": "@M", "#75b44b": "@M",
    "#fffbff": "@L", "#ebedf0": "@L", "#fff": "@L", "#ffffff": "@L",
    "#12110f": "@D", "#001300": "@D", "#000": "@D", "#000000": "@D",
}
PAINT_PROPS = {"fill", "stroke"}
SKIP_TAGS = {"defs", "style", "title", "desc", "metadata"}
DROP_ATTRS = {"id", "class", "data-name"}
unmapped = {}


def local(tag):
    return tag.rsplit("}", 1)[-1]


def paint(value, where):
    v = value.strip().lower()
    if v in ROLE:
        return ROLE[v]
    if v.startswith("#"):
        unmapped.setdefault(v, set()).add(where)
    return value.strip()


def class_rules(root):
    rules = {}
    for el in root.iter():
        if local(el.tag) != "style" or not el.text:
            continue
        for sel, body in re.findall(r"([^{}]+)\{([^}]*)\}", el.text):
            decls = {}
            for d in body.split(";"):
                if ":" in d:
                    k, v = d.split(":", 1)
                    decls[k.strip()] = v.strip()
            for s in sel.split(","):
                s = s.strip()
                if s.startswith("."):
                    rules.setdefault(s[1:], {}).update(decls)
    return rules


def esc(v):
    return v.replace("&", "&amp;").replace('"', "&quot;").replace("<", "&lt;")


def serialize(el, rules, where):
    tag = local(el.tag)
    if tag in SKIP_TAGS:
        return ""
    attrs = {}
    for cls in (el.get("class") or "").split():
        attrs.update(rules.get(cls, {}))
    for k, v in el.attrib.items():
        k = local(k)
        if k not in DROP_ATTRS:
            attrs[k] = v
    for k in list(attrs):
        if k in PAINT_PROPS:
            attrs[k] = paint(attrs[k], where)
    kids = "".join(serialize(c, rules, where) for c in el)
    if tag == "g" and not attrs:
        return kids  # plain grouping, nothing to keep
    a = "".join(f' {k}="{esc(v)}"' for k, v in attrs.items())
    return f"<{tag}{a}>{kids}</{tag}>" if kids else f"<{tag}{a}/>"


def natural_key(p):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", p.stem)]


def load_part(path, slot):
    root = ET.parse(path).getroot()
    vb = [float(x) for x in root.get("viewBox").split()]
    assert vb[0] == 0 and vb[1] == 0, f"{path}: viewBox origin not 0,0"
    rules = class_rules(root)
    markup = "".join(serialize(c, rules, path.stem) for c in root)
    return {"c": slot, "w": vb[2], "h": vb[3], "m": markup}


def data_uri(path, mime):
    return f"data:{mime};base64," + base64.b64encode(path.read_bytes()).decode()


def main():
    parts = {}
    for folder, slot in CATEGORIES:
        for path in sorted(folder.glob("*.svg"), key=natural_key):
            parts[path.stem] = load_part(path, slot)

    logo = load_part(ROOT / "Assets" / "Logos" / "40C3_Logo_0.svg", "logo")

    html = SRC.read_text(encoding="utf-8")
    html = html.replace("/*__PARTS__*/{}", json.dumps(parts, separators=(",", ":")))
    html = html.replace("/*__LOGO__*/{}", json.dumps(logo, separators=(",", ":")))

    fonts = {
        "__FONT_JERSEY__": "jersey-10-latin-400-normal.woff2",
        "__FONT_HACK__": "Hack-Regular.woff2",
        "__FONT_HACK_BOLD__": "Hack-Bold.woff2",
    }
    for token, name in fonts.items():
        html = html.replace(token, data_uri(ROOT / "fonts" / name, "font/woff2"))

    def image(m):
        hits = list((ROOT / "Assets").glob(f"*/{m.group(1)}.svg"))
        if not hits:
            sys.exit(f"missing asset for {m.group(0)}")
        return data_uri(hits[0], "image/svg+xml")

    html = re.sub(r"__IMG_([A-Za-z0-9_]+?)__", image, html)

    # The embedded fonts must travel with their licence texts (MIT / OFL).
    notices = "\n\n".join(
        f"===== {title} =====\n\n" + (ROOT / "fonts" / name).read_text(encoding="utf-8").strip()
        for title, name in [
            ("Hack (https://github.com/source-foundry/Hack)", "Hack-License.txt"),
            ("Jersey 10 (https://github.com/scfried/soft-type-jersey) - "
             "Copyright 2023 The Soft Type Project Authors", "jersey-10_License.txt"),
        ]
    )
    assert "</script" not in notices.lower()
    html = html.replace("__FONT_LICENSES__", notices.replace("&", "&amp;").replace("<", "&lt;"))

    left = re.findall(r"__[A-Z][A-Z0-9_]+__", html)
    if left:
        sys.exit(f"unreplaced placeholders: {sorted(set(left))}")

    OUT.write_text(html, encoding="utf-8")
    by_slot = {}
    for p in parts.values():
        by_slot[p["c"]] = by_slot.get(p["c"], 0) + 1
    print(f"wrote {OUT.relative_to(ROOT)}  {OUT.stat().st_size / 1024:.0f} KB")
    print("parts:", ", ".join(f"{k} {v}" for k, v in by_slot.items()))
    if unmapped:
        print("colours kept as-is (not one of the three roles):")
        for colour, where in sorted(unmapped.items()):
            print(f"  {colour}: {', '.join(sorted(where))}")


if __name__ == "__main__":
    main()
