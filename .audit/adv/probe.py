import sys, tomllib, tempfile, traceback
from pathlib import Path
sys.path.insert(0, "/Users/madne5/Documents/elite-hud")
from elite_hud.config import (Config, ensure_config_file, set_config_value,
    set_config_list, add_missing_sections, _toml_value)

def tmp():
    return Path(tempfile.mkdtemp()) / "config.toml"

def report(name, fn):
    print("="*70); print("CASE:", name)
    try:
        fn()
    except Exception:
        traceback.print_exc()

# ---- 1: missing key appended at tail
def c1():
    p = tmp(); ensure_config_file(p)
    txt = p.read_text(); txt2 = txt.replace('name = ""\n','',1)
    print("removed line:", txt != txt2)
    p.write_text(txt2)
    print("load before:", repr(Config.load(p).faction.name))
    ok = set_config_value(p, "faction", "name", "Traders & Explorers")
    print("set_config_value returned", ok)
    print("--- file tail ---"); print("\n".join(p.read_text().splitlines()[-6:]))
    try:
        raw = tomllib.loads(p.read_text()); print("parses; exobiology.values =", raw.get("exobiology",{}).get("values"))
    except Exception as e: print("PARSE FAIL", e)
    print("load after: faction.name =", repr(Config.load(p).faction.name))
report("1 set_config_value missing key -> tail", c1)

# ---- 1b: monitor
def c1b():
    p = tmp(); ensure_config_file(p)
    txt = p.read_text().replace('monitor = "primary"\n','',1)
    p.write_text(txt)
    print("persisted:", set_config_value(p, "overlay", "monitor", "1"))
    print("tail:", p.read_text().splitlines()[-2:])
    print("loaded monitor:", Config.load(p).overlay.monitor)
report("1b monitor", c1b)

# ---- 2: multiline list
def c2():
    p = tmp()
    p.write_text('''[overlay]
font_size = 15
status_segments = [
  "mode",
  "empire",
  "ship",
]
[alerts]
min_value = 12345678
''')
    print("before parses:", tomllib.loads(p.read_text())["overlay"]["status_segments"])
    print("persisted:", set_config_list(p, "overlay", "status_segments", ["mode","ship"]))
    print("--- file ---"); print(p.read_text())
    try:
        tomllib.loads(p.read_text()); print("parses OK")
    except Exception as e: print("PARSE FAIL:", type(e).__name__, e)
    c = Config.load(p)
    print("font_size", c.overlay.font_size, "min_value", c.alerts.min_value, "status", c.overlay.status_segments[:3])
report("2 multiline list", c2)

# ---- 3: dotted keys
def c3():
    p = tmp()
    p.write_text('journal.path = "D:/ED/Saved Games"\noverlay.monitor = "1"\n')
    c = Config.load(p)
    print("first load ok:", c.journal.path, c.overlay.monitor)
    added = add_missing_sections(p)
    print("added:", added[:6], "...")
    try:
        tomllib.loads(p.read_text()); print("parses OK")
    except Exception as e: print("PARSE FAIL:", type(e).__name__, e)
    c2 = Config.load(p)
    print("second load: journal.path=%r monitor=%r font=%d" % (c2.journal.path, c2.overlay.monitor, c2.overlay.font_size))
    print("second add_missing_sections ->", add_missing_sections(p))
report("3 dotted keys", c3)

# ---- 3b: header with trailing comment
def c3b():
    p = tmp()
    p.write_text('[journal] # journal folder\npath = "D:/ED"\n')
    print("first load:", Config.load(p).journal.path)
    print("added:", add_missing_sections(p))
    try:
        tomllib.loads(p.read_text()); print("parses OK")
    except Exception as e: print("PARSE FAIL:", type(e).__name__, e)
    print("second load:", repr(Config.load(p).journal.path))
report("3b header trailing comment", c3b)

# ---- 4: empty segments
def c4():
    p = tmp(); ensure_config_file(p)
    c = Config.load(p)
    c.overlay.segments = []
    c.validate()
    print("after validate, segments =", c.overlay.segments)
    set_config_list(p, "overlay", "segments", list(c.overlay.segments))
    print("reloaded:", Config.load(p).overlay.segments)
    c2 = Config.load(p); c2.overlay.status_segments = []; c2.validate()
    print("status empty -> ", c2.overlay.status_segments)
report("4 empty segments", c4)

# ---- 5: scalar section
def c5():
    for text in ['overlay = false\n', 'exobiology = 3\n', 'overlay = "top-center"\n']:
        p = tmp(); p.write_text(text)
        try:
            Config.load(p); print(repr(text), "-> no error")
        except Exception as e:
            print(repr(text), "->", type(e).__name__, e)
report("5 scalar section name", c5)

# ---- 6: newline in value
def c6():
    print("_toml_value:", repr(_toml_value("a\nb")))
    p = tmp(); ensure_config_file(p)
    print("persisted:", set_config_value(p, "faction", "name", "Traders\nExplorers"))
    try:
        tomllib.loads(p.read_text()); print("parses OK")
    except Exception as e: print("PARSE FAIL:", type(e).__name__, e)
    print("load:", repr(Config.load(p).faction.name), Config.load(p).overlay.font_size)
    for ch in ["\r", "\x00", "\t"]:
        try:
            tomllib.loads("x = " + _toml_value("a"+ch+"b")); print(repr(ch), "ok")
        except Exception as e: print(repr(ch), "FAIL", e)
report("6 control char in value", c6)

# ---- 7: round trip overrides
def c7():
    c = Config(); c.exobiology_overrides = {"$Codex_Ent_Stratum_07_Name;": 20_000_000}
    p = tmp(); p.write_text(c.to_toml())
    print("reloaded overrides:", Config.load(p).exobiology_overrides)
    print("defaults equal:", Config.load(p) == Config())
report("7 to_toml drops overrides", c7)

# ---- 8: bool via set_config_value
def c8():
    p = tmp(); ensure_config_file(p)
    print("persisted:", set_config_value(p, "overlay", "click_through", "false"))
    print(p.read_text().splitlines().__getitem__(18) if False else [l for l in p.read_text().splitlines() if "click_through" in l])
    print("loaded click_through:", Config.load(p).overlay.click_through)
report("8 bool", c8)

# ---- 9: example vs defaults
def c9():
    ex = Path("/Users/madne5/Documents/elite-hud/config.example.toml")
    import json
    a = tomllib.loads(ex.read_text())
    b = tomllib.loads(Config().to_toml())
    def flat(d, pre=""):
        out={}
        for k,v in d.items():
            if isinstance(v, dict): out.update(flat(v, pre+k+"."))
            else: out[pre+k]=v
        return out
    fa, fb = flat(a), flat(b)
    missing = sorted(set(fb) - set(fa))
    diff = {k:(fa[k],fb[k]) for k in set(fa)&set(fb) if fa[k]!=fb[k]}
    print("keys in defaults missing from example:", len(missing)); print(missing)
    print("differing values:", diff)
    print("sections in defaults missing from example:", sorted({k.split('.')[0] for k in missing}))
report("9 example stale", c9)
