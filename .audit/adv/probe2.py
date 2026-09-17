import sys, tomllib, tempfile, traceback
from pathlib import Path
sys.path.insert(0, "/Users/madne5/Documents/elite-hud")
from elite_hud.config import Config, add_missing_sections, ensure_config_file

def tmp():
    return Path(tempfile.mkdtemp()) / "config.toml"

# 3c: exactly the claim's "one overlay.enabled = false line in dotted form"
p = tmp(); p.write_text("overlay.enabled = false\n")
c = Config.load(p); print("first load overlay.enabled:", c.overlay.enabled)
print("added:", add_missing_sections(p, c)[:4], "...")
try:
    tomllib.loads(p.read_text()); print("parses OK")
except Exception as e:
    print("PARSE FAIL:", e)
print("after:", Config.load(p).overlay.enabled)
print("second add:", add_missing_sections(p))
print("tail of file:"); print("\n".join(p.read_text().splitlines()[-6:]))

# 3d: does the appended section copy the user's own values? (app passes the loaded config)
p2 = tmp(); p2.write_text('journal.path = "D:/ED/Saved Games"\n')
c2 = Config.load(p2)
add_missing_sections(p2, c2)
print("appended [journal] body:", [l for l in p2.read_text().splitlines() if "D:/ED" in l])

# 7b: what actually writes to_toml()?
print("ensure_config_file defaults only:", "exobiology" in Config().to_toml())
