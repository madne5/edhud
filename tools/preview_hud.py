"""Render the HUD to PNG files so it can be reviewed without the game.

    QT_QPA_PLATFORM=offscreen python tools/preview_hud.py [outdir]

Produces one image per scenario in ``tools/preview/``.  Each shot composites
the translucent HUD over a mock "space" backdrop so the alpha is obvious.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from PySide6.QtCore import QPoint, QPointF, Qt  # noqa: E402
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPixmap  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from elite_hud.config import Config  # noqa: E402
from elite_hud.exobiology import ExobiologyTable  # noqa: E402
from elite_hud.overlay.hud import HudWindow  # noqa: E402
from elite_hud.state import Alert, Confidence, GameState  # noqa: E402

FIXTURE = REPO_ROOT / "tests" / "fixtures" / "Journal.2026-03-14T200000.01.log"
OUT_DIR = REPO_ROOT / "tools" / "preview"


def load_fixture_events() -> list[dict]:
    with open(FIXTURE, encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def play_fixture(state: GameState) -> list[Alert]:
    alerts: list[Alert] = []
    with open(FIXTURE, encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                alerts.extend(state.apply(json.loads(line)))
    return alerts


def backdrop(width: int, height: int, title: str) -> QPixmap:
    """A stand-in for the game frame behind the HUD."""
    pixmap = QPixmap(width, height)
    gradient = QLinearGradient(0, 0, 0, height)
    gradient.setColorAt(0.0, QColor("#050810"))
    gradient.setColorAt(0.55, QColor("#101a2e"))
    gradient.setColorAt(1.0, QColor("#2a1c12"))

    painter = QPainter(pixmap)
    painter.fillRect(0, 0, width, height, gradient)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

    # A few stars so the transparency blending is visible.
    import random

    rng = random.Random(7)
    painter.setPen(Qt.PenStyle.NoPen)
    for _ in range(220):
        alpha = rng.randint(40, 220)
        painter.setBrush(QColor(255, 255, 255, alpha))
        x, y = rng.randrange(width), rng.randrange(height)
        painter.drawEllipse(QPointF(x, y), 0.8, 0.8)

    painter.setBrush(QColor("#3a4a66"))
    painter.drawEllipse(QPointF(width * 0.78, height * 0.74), height * 0.16, height * 0.16)

    painter.setPen(QColor(255, 255, 255, 110))
    painter.setFont(QFont("Helvetica", 15))
    painter.drawText(24, height - 24, title)
    painter.end()
    return pixmap


def shoot(
    app: QApplication,
    name: str,
    config: Config,
    state: GameState,
    alert: Alert | None,
    screen_width: int = 2560,
) -> Path:
    hud = HudWindow(config, state)
    # The offscreen platform reports a tiny screen, which would elide every
    # preview; pin a realistic width unless the scenario is about elision.
    hud._available_width = lambda: float(screen_width)  # type: ignore[method-assign]
    if alert is not None:
        hud.push_alert(alert)
    hud.rebuild()

    width = max(hud.width() + 120, 900)
    height = 190
    canvas = backdrop(width, height, name)

    painter = QPainter(canvas)
    hud.render(painter, QPoint(int((width - hud.width()) / 2.0), config.overlay.offset_y + 12))
    painter.end()
    hud.close()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUT_DIR / f"{name}.png"
    canvas.save(str(path))

    painted, colours = pixel_counts(canvas)
    print(f"{name}: {hud.width()}x{hud.height()} px bar, {painted} opaque px, {colours} colours")
    print(f"    {hud.bar_text()}")
    return path


def pixel_counts(image) -> tuple[int, int]:
    from collections import Counter

    from PySide6.QtGui import QImage

    if hasattr(image, "toImage"):
        image = image.toImage()
    image = image.convertToFormat(QImage.Format.Format_ARGB32)
    counts: Counter = Counter()
    for y in range(0, image.height(), 2):
        for x in range(0, image.width(), 2):
            argb = image.pixel(x, y)
            if ((argb >> 24) & 0xFF) > 40:
                counts[argb & 0xFFFFFF] += 1
    return sum(counts.values()), len(counts)


def main() -> int:
    app = QApplication(sys.argv[:1])

    config = Config()
    config.overlay.font_size = 14

    written: list[Path] = []

    # 1. Idle mid-scan: carrier counting down, FSS in progress, bio present.
    state = GameState(ExobiologyTable(), value_threshold=config.alerts.min_value)
    with open(FIXTURE, encoding="utf-8") as handle:
        for line in handle:
            event = json.loads(line)
            if event.get("event") in {"CarrierJumpCancelled", "FSDJump"} and event.get("StarSystem") == "Synuefe GX-K c24-11":
                break
            state.apply(event)
    # Freeze the countdown so the screenshot is deterministic.
    from datetime import datetime, timezone

    state.carrier.departure = datetime(2026, 3, 14, 20, 30, tzinfo=timezone.utc)
    import elite_hud.state as state_module

    original = state_module.utcnow
    state_module.utcnow = lambda: datetime(2026, 3, 14, 20, 17, 26, tzinfo=timezone.utc)
    written.append(shoot(app, "01-scanning", config, state, None))
    state_module.utcnow = original

    # 2. Confirmed high-value species with the first-logged bonus.
    confirmed = Alert(
        key="demo-confirmed",
        title="Stratum Tectonicas",
        detail="confirmed",
        value=19_010_800,
        confidence=Confidence.CONFIRMED,
        system="Synuefe PK-V b48-0",
        body="Synuefe PK-V b48-0 5",
        genus="Stratum",
        species="Stratum Tectonicas",
        bonus_applies=True,
        payout=95_054_000,
    )
    state_module.utcnow = lambda: datetime(2026, 3, 14, 20, 17, 26, tzinfo=timezone.utc)
    written.append(shoot(app, "02-alert-confirmed", config, state, confirmed))
    state_module.utcnow = original

    # 3. Genus-only sighting: worth a look, not a promise.
    possible = Alert(
        key="demo-possible",
        title="Cactoida",
        detail="possible",
        value=16_202_800,
        confidence=Confidence.POSSIBLE,
        system="Synuefe PK-V b48-0",
        body="Synuefe PK-V b48-0 7",
        genus="Cactoida",
    )
    written.append(shoot(app, "03-alert-possible", config, state, possible))

    # 4. Carrier recharging: the post-jump cooldown, no jump scheduled.
    state_module.utcnow = lambda: datetime(2026, 3, 14, 20, 17, 26, tzinfo=timezone.utc)
    cooldown_state = GameState(ExobiologyTable(), value_threshold=config.alerts.min_value)
    for event in load_fixture_events():
        if event.get("event") in {"CarrierJumpCancelled"}:
            continue
        cooldown_state.apply(event)
    cooldown_state.carrier.cancel()
    cooldown_state.carrier.last_jump = datetime(2026, 3, 14, 20, 14, 0, tzinfo=timezone.utc)
    written.append(shoot(app, "04-carrier-cooldown", config, cooldown_state, None))
    state_module.utcnow = original

    # 5. Narrow screen: elastic names are elided, then whole segments drop.
    state_module.utcnow = lambda: datetime(2026, 3, 14, 20, 17, 26, tzinfo=timezone.utc)
    written.append(shoot(app, "05-narrow-screen", config, state, None, screen_width=760))
    state_module.utcnow = original

    # 5. Empty state: no journal data at all.
    empty = GameState(ExobiologyTable(), value_threshold=config.alerts.min_value)
    written.append(shoot(app, "06-no-data", config, empty, None))

    for path in written:
        print(f"wrote {path.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
