# Research notes

These are the source notes behind several design decisions in this project.
They are **working research**, not polished documentation: they were compiled
from the official Frontier player-journal manual, the Elite Dangerous wiki,
Canonn Research, the EDMC-BioScan and ArtemisScannerTracker datasets, the
Microsoft Learn documentation, and the GitHub and Inno Setup references.

Each document marks anything it could **not** confirm, so treat the flagged
items as leads to verify rather than settled facts.

| Document | What it covers |
|---|---|
| `journal_format_reference.md` | Elite Dangerous player-journal schema: every event this project reads, with real field names and sample JSON |
| `EXOBIOLOGY_RU.md` | Exobiology payouts: genus/species values, the base+4x "first logged" bonus, and where the sources disagree |
| `INNO_SETUP_RU.md` | Inno Setup: silent-install flags, `CloseApplications`/`RestartApplications`, `AppMutex`, uninstall registry keys |
| `WINDOWS_RELEASE_UPDATE_RU.md` | PyInstaller onefile vs onedir, GitHub Releases API, release workflows, Windows self-update, code signing |

`data/` holds intermediate datasets used while building
`elite_hud/data/exobiology.json`. The canonical generator is
`tools/build_exobiology_data.py`, which reads the EDMC-BioScan ruleset catalogs
directly; these files are kept as the evidence trail for the values that ended
up in the table — in particular `Concha Biconcavis`, where the upstream dataset
still carries a pre-Update-14 `2²⁴−1` placeholder.

To rebuild the table:

```bash
git clone --depth 1 https://github.com/Silarn/EDMC-BioScan research/EDMC-BioScan
python tools/build_exobiology_data.py
```
