#!/usr/bin/env python3
"""Build the self-contained citizen_creator.html and pattern_creator.html.

Reads the styleguide assets (creator parts, pattern objects, icons, fonts,
deco) and inlines them into the templates in src/ -> one HTML file each (no
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
PATTERN_SRC = ROOT / "src" / "pattern_creator.html"
PATTERN_OUT = ROOT / "pattern_creator.html"
PATTERN_DIR = ROOT / "Assets" / "Patterns"
ASSETS_SRC = ROOT / "src" / "assets.html"
ASSETS_OUT = ROOT / "assets.html"
# The assets page: section -> files. Logos come in one file per colour; one is
# enough, the page recolours it.
ASSET_GROUPS = [
    ("Logos", [ROOT / "Assets" / "Logos" / "40C3_Logo_0.svg", ROOT / "Assets" / "Logos" / "40C3_LogoText_0.svg"]),
    ("Icons / Deco", ROOT / "Assets" / "Icons_Deco"),
    ("Boxes", ROOT / "Assets" / "Boxes"),
    ("Citizens", ROOT / "Assets" / "Citizens"),
    ("Patterns", ROOT / "Assets" / "Patterns"),
    ("Citizen creator parts", ROOT / "Citizen_Creator_Assets"),
]

# The four pattern strips of the styleguide are flat lists of shapes. This
# table cuts them into their objects ("tiles"): name -> indices of the shapes
# (document order) that make up the object. Every shape must be used once.
def _r(a, b):
    return list(range(a, b + 1))


PATTERN_OBJECTS = {
    "Pattern0": {
        "submarine": [*_r(0, 12), *_r(53, 57)],  # with the tree it grows out of
        "fan": _r(13, 24),
        "bag": [*_r(25, 28), 33], "usb": _r(29, 32), "phone": _r(34, 45), "bar": [46, 47],
        "crossbox": _r(48, 50), "corner": [51, 52], "dash": [58], "dashes": [59, 60],
        "longdash": [61], "step": [62, 63], "shortdash": [64],
    },
    "Pattern1": {
        "datenklo": [*_r(0, 15), *_r(20, 23)], "screwdriver": _r(16, 19), "door": _r(24, 35),
        "key": _r(36, 43), "desk": _r(44, 55), "face": _r(56, 61), "tower": _r(62, 67),
        "folder": [68, 69], "lime": _r(70, 74), "wedge": [75, 76], "star": [77],
        "dash": [78], "square": [79],
    },
    "Pattern2": {
        "pipes": [0, 1, 2, 3, 5, 15, 23, 24, 27], "ruler": [4, *_r(11, 14)],
        "paper": [6, 7, 8, 9, 25, 26], "plate": [10, *_r(16, 22)], "saw": [28, 29],
        "wedge": [30, 31], "lines": [32, 33, 34], "dash": [35], "mouse": _r(36, 40),
        "rabbit": [*_r(41, 46), 58], "bottle": [*_r(47, 57), 59], "dashr": [60], "dashl": [61],
    },
    "Pattern3": {
        "creature": _r(0, 26), "robot": _r(27, 36), "flower": [37, 38], "cactus": _r(39, 54),
        "crossbox": _r(55, 57), "web": _r(58, 61), "gun": [62, 63], "dial": _r(64, 66),
    },
}
# Stand-alone pattern pieces, drawn with a 3 unit line instead of 1.79: file -> scale.
PATTERN_SINGLES = {
    "Pattern_Boxes": .597, "Pattern_Datenklo1": .597, "Pattern_Datenklo2": .597,
    "Pattern_Lime": .597, "Pattern_Mouse": .597, "Pattern_Oscilloscope": .597,
}
# Strip 3 is drawn with a 1.89 unit line; bring it to the 1.79 of the others.
PATTERN_SCALE = {"Pattern3": .947}
# Outline (cell mask) and connection points of each object, made with the
# object editor of the pattern creator ("download object data").
PATTERN_DATA = ROOT / "src" / "pattern_tiles.json"
SHAPES = {"path", "rect", "polygon", "circle", "ellipse", "line", "polyline"}

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
    "#e7edea": "@L",
    "#12110f": "@D", "#001300": "@D", "#000": "@D", "#000000": "@D", "#000d00": "@D", "#020308": "@D",
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
    if not kids and attrs.get("fill") == "none" and "stroke" not in attrs:
        return ""  # invisible leftovers from the Illustrator export
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


def load_tiles():
    """Pattern objects as single-colour markup; the app measures their boxes."""
    tiles = []

    def shapes(name):
        root = ET.parse(PATTERN_DIR / f"{name}.svg").getroot()
        rules = class_rules(root)
        out = []
        for el in root.iter():
            if local(el.tag) in SHAPES:
                m = serialize(el, rules, name)
                out.append(re.sub(r' fill="[^"]*"', "", m))
        return out

    for name, objects in PATTERN_OBJECTS.items():
        sh = shapes(name)
        used = sorted(i for ids in objects.values() for i in ids)
        assert used == list(range(len(sh))), f"{name}: object table does not cover each shape once"
        for obj, ids in objects.items():
            m = "".join(sh[i] for i in ids)
            if name in PATTERN_SCALE:
                m = f'<g transform="scale({PATTERN_SCALE[name]})">{m}</g>'
            tiles.append({"id": f"{name[7:]}.{obj}", "set": name, "m": m})
    for name, k in PATTERN_SINGLES.items():
        tiles.append({"id": name[8:].lower(), "set": "Singles",
                      "m": f'<g transform="scale({k})">{"".join(shapes(name))}</g>'})
    return tiles


def load_assets():
    assets = []
    for group, src in ASSET_GROUPS:
        files = src if isinstance(src, list) else sorted(src.rglob("*.svg"), key=lambda p: (p.parent.name, natural_key(p)))
        for path in files:
            a = load_part(path, group)
            name = path.stem.replace("_0", "") if group == "Logos" else path.stem
            if group == "Patterns":      # single-colour line art, whatever colour the file happens to use
                a["m"] = '<g fill="@M">' + re.sub(r' fill="[^"]*"', "", a["m"]) + "</g>"
            assets.append({"g": group, "n": name, "w": a["w"], "h": a["h"], "m": a["m"]})
    return assets


def finish(html, out):
    """Inline fonts, images and licence texts, then write the file."""
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
        sys.exit(f"{out.name}: unreplaced placeholders: {sorted(set(left))}")
    out.write_text(html, encoding="utf-8")
    print(f"wrote {out.relative_to(ROOT)}  {out.stat().st_size / 1024:.0f} KB")


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

    finish(html, OUT)

    known = dict(unmapped)
    tiles = load_tiles()          # single-colour: their source colours do not matter
    unmapped.clear()
    unmapped.update(known)
    html = PATTERN_SRC.read_text(encoding="utf-8")
    html = html.replace("/*__TILES__*/[]", json.dumps(tiles, separators=(",", ":")))
    data = json.loads(PATTERN_DATA.read_text(encoding="utf-8"))["tiles"] if PATTERN_DATA.exists() else {}
    stale = sorted(set(data) - {t["id"] for t in tiles})
    if stale:
        sys.exit(f"{PATTERN_DATA.name}: unknown objects {stale}")
    html = html.replace("/*__TILE_DATA__*/{}", json.dumps(data, separators=(",", ":")))
    finish(html, PATTERN_OUT)
    print(f"pattern tiles: {len(tiles)}")

    assets = load_assets()
    unmapped.clear()
    unmapped.update(known)
    html = ASSETS_SRC.read_text(encoding="utf-8")
    html = html.replace("/*__ASSETS__*/[]", json.dumps(assets, separators=(",", ":")))
    finish(html, ASSETS_OUT)
    print(f"assets: {len(assets)}")

    by_slot = {}
    for p in parts.values():
        by_slot[p["c"]] = by_slot.get(p["c"], 0) + 1
    print("parts:", ", ".join(f"{k} {v}" for k, v in by_slot.items()))
    if unmapped:
        print("colours kept as-is (not one of the three roles):")
        for colour, where in sorted(unmapped.items()):
            print(f"  {colour}: {', '.join(sorted(where))}")


if __name__ == "__main__":
    main()
