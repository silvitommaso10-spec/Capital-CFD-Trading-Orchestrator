"""J.A.R.V.I.S.-style HUD dashboard.

Renders a shadow run into a single self-contained HTML page with a futuristic
heads-up-display aesthetic (dark background, cyan/amber glow, an animated arc
reactor, per-symbol HUD cards, a risk panel, the AI Director briefing and an
audit ticker). No server and no external dependencies — open the file in any
browser. A web font is pulled from Google Fonts when online and falls back to a
monospace system font offline.

``render_dashboard`` is pure (dict -> HTML); ``report_to_data`` extracts the
dict from a shadow run; ``write_dashboard`` does both and writes the file.
"""

from __future__ import annotations

from datetime import datetime, timezone
from html import escape
from pathlib import Path
from typing import Any

# State -> (css class, glow colour, label)
_STATE_STYLE = {
    "EXECUTED": ("ok", "#38ffb0", "EXECUTED"),
    "RISK_REJECTED": ("bad", "#ff4d5e", "RISK REJECTED"),
    "WAIT": ("warn", "#ffb84d", "WAIT"),
    "WATCHLIST": ("info", "#25d0ff", "WATCHLIST"),
    "READONLY_SKIPPED": ("warn", "#ffb84d", "READ-ONLY"),
    "NO_TRADE": ("dim", "#5a7184", "NO TRADE"),
}


def _state_style(state: str) -> tuple[str, str, str]:
    return _STATE_STYLE.get(state, ("dim", "#5a7184", state))


def report_to_data(run: Any) -> dict[str, Any]:
    """Extract a render-ready dict from a ShadowRunReport (duck-typed)."""

    report = run.report
    account = getattr(report, "account", None) or {}

    symbols: list[dict[str, Any]] = []
    for r in run.results:
        ta = r.technical
        scores = (r.audit or {}).get("scores", {})
        direction = ta.direction.value if ta.direction is not None else None
        reasons = (
            [reason.value for reason in r.risk.reasons]
            if getattr(r, "risk", None) is not None
            else []
        )
        symbols.append(
            {
                "symbol": r.symbol,
                "state": r.state.value,
                "outcome": r.decision.outcome.value,
                "final_score": float(r.decision.final_score),
                "direction": direction,
                "trend": ta.trend.value,
                "scores": {
                    "technical": float(scores.get("technical", ta.technical_score)),
                    "trend": float(scores.get("trend", ta.trend_score)),
                    "volume": float(scores.get("volume", ta.volume_score)),
                    "news": float(scores.get("news", 0.5)),
                    "sentiment": float(scores.get("sentiment", 0.5)),
                },
                "stop_loss": ta.stop_loss,
                "take_profit": ta.take_profit,
                "entry": ta.entry_price,
                "reasons": reasons,
            }
        )

    return {
        "mode": "SHADOW",
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ"),
        "date": getattr(report, "date", ""),
        "equity": float(account.get("equity", 0.0)),
        "by_state": dict(getattr(report, "by_state", {})),
        "executed": list(getattr(report, "executed", [])),
        "symbols": symbols,
        "briefing": getattr(run, "briefing", None),
        "audit": list(getattr(run, "_orchestrator", None).audit_log)  # type: ignore[union-attr]
        if getattr(run, "_orchestrator", None) is not None
        else [],
    }


# --------------------------------------------------------------------------
# Rendering
# --------------------------------------------------------------------------


def _meter(label: str, value: float, color: str = "#25d0ff") -> str:
    pct = max(0.0, min(1.0, value)) * 100.0
    return (
        f'<div class="meter"><span class="meter-label">{escape(label)}</span>'
        f'<span class="meter-track"><span class="meter-fill" '
        f'style="width:{pct:.0f}%;background:{color};box-shadow:0 0 8px {color}">'
        f"</span></span>"
        f'<span class="meter-val">{value:.2f}</span></div>'
    )


def _arrow(direction: str | None) -> str:
    if direction == "LONG":
        return '<span class="dir long">&#9650; LONG</span>'
    if direction == "SHORT":
        return '<span class="dir short">&#9660; SHORT</span>'
    return '<span class="dir flat">&#9675; --</span>'


def _symbol_card(sym: dict[str, Any]) -> str:
    cls, color, label = _state_style(sym["state"])
    sc = sym["scores"]
    reasons = "".join(
        f"<span class='tag'>{escape(r)}</span>" for r in sym["reasons"]
    )
    levels = ""
    if sym.get("entry") is not None and sym.get("stop_loss") is not None:
        levels = (
            f"<div class='levels'>entry {sym['entry']:.2f} &middot; "
            f"stop {sym['stop_loss']:.2f} &middot; "
            f"tgt {sym['take_profit']:.2f}</div>"
        )
    return f"""
    <div class="card {cls}">
      <div class="corner tl"></div><div class="corner tr"></div>
      <div class="corner bl"></div><div class="corner br"></div>
      <div class="card-head">
        <span class="sym">{escape(sym['symbol'])}</span>
        <span class="badge" style="color:{color};border-color:{color};
              box-shadow:0 0 10px {color}33,inset 0 0 10px {color}22">{label}</span>
      </div>
      <div class="card-row">{_arrow(sym['direction'])}
        <span class="trend">trend {escape(sym['trend'])}</span>
        <span class="score">{sym['final_score']:.3f}</span></div>
      {_meter('FINAL', sym['final_score'], color)}
      <div class="subscores">
        {_meter('tech', sc['technical'])}
        {_meter('trend', sc['trend'])}
        {_meter('vol', sc['volume'])}
        {_meter('news', sc['news'], '#ffb84d')}
        {_meter('sent', sc['sentiment'], '#b07dff')}
      </div>
      {levels}
      <div class="reasons">{reasons}</div>
    </div>"""


def _stat(label: str, value: str, color: str = "#25d0ff") -> str:
    return (
        f'<div class="stat"><div class="stat-val" style="color:{color};'
        f'text-shadow:0 0 14px {color}">{escape(value)}</div>'
        f'<div class="stat-label">{escape(label)}</div></div>'
    )


def render_dashboard(
    data: dict[str, Any],
    title: str = "J.A.R.V.I.S.",
    *,
    refresh_seconds: int | None = None,
) -> str:
    by_state = data["by_state"]
    executed = by_state.get("EXECUTED", 0)
    rejected = by_state.get("RISK_REJECTED", 0)
    open_pos = len(data["executed"])

    cards = "".join(_symbol_card(s) for s in data["symbols"])

    briefing = data.get("briefing")
    briefing_html = ""
    if briefing:
        briefing_html = f"""
      <section class="panel director">
        <div class="panel-title">// AI DIRECTOR &mdash; ADVISORY</div>
        <pre class="console">{escape(briefing)}</pre>
      </section>"""

    audit_rows = ""
    for entry in data.get("audit", [])[-14:]:
        sym = escape(str(entry.get("symbol", "")))
        stage = escape(str(entry.get("stage", entry.get("decision", ""))))
        audit_rows += f'<span class="tick"><b>{sym}</b> {stage}</span>'

    refresh_meta = ""
    refresh_note = ""
    if refresh_seconds:
        refresh_meta = f"<meta http-equiv='refresh' content='{int(refresh_seconds)}'>"
        refresh_note = (
            f"<span class='auto'>&#8635; AUTO&#8209;REFRESH {int(refresh_seconds)}s</span>"
        )

    return (
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        f"{refresh_meta}"
        f"<title>{escape(title)} &middot; Orchestrator HUD</title>"
        f"<style>{_CSS}</style></head><body>"
        "<div class='scan'></div><div class='grid-bg'></div>"
        "<div class='wrap'>"
        f"""
        <header class="topbar">
          <div class="reactor">
            <div class="ring r1"></div><div class="ring r2"></div>
            <div class="ring r3"></div><div class="core"></div>
          </div>
          <div class="titles">
            <h1 class="glitch" data-text="{escape(title)}">{escape(title)}</h1>
            <div class="subtitle">Capital CFD Trading Orchestrator
              &middot; <span class="mode">{escape(data['mode'])}</span>
              <span class="ro">READ&#8209;ONLY</span></div>
          </div>
          <div class="clock">
            <div class="online">&#9679; SYSTEMS ONLINE</div>
            <div class="ts">{escape(data['generated_at'])}</div>
            {refresh_note}
          </div>
        </header>

        <section class="stats">
          {_stat('EQUITY', f"{data['equity']:,.2f}", '#38ffb0')}
          {_stat('OPEN POSITIONS', str(open_pos))}
          {_stat('EXECUTED', str(executed), '#38ffb0')}
          {_stat('REJECTED', str(rejected), '#ff4d5e')}
          {_stat('SYMBOLS', str(len(data['symbols'])))}
        </section>

        <section class="grid">{cards}</section>

        {briefing_html}

        <section class="ticker"><div class="ticker-track">{audit_rows or '<span class="tick">no audit entries</span>'}</div></section>

        <footer class="foot">
          Advisory &amp; simulation only &middot; no orders are sent to any broker
          &middot; generated {escape(data['generated_at'])}
        </footer>
        """
        "</div></body></html>"
    )


def write_dashboard(
    run: Any,
    path: str | Path,
    title: str = "J.A.R.V.I.S.",
    *,
    refresh_seconds: int | None = None,
) -> Path:
    """Render a shadow run to an HTML HUD file and return the path."""

    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        render_dashboard(
            report_to_data(run), title=title, refresh_seconds=refresh_seconds
        ),
        encoding="utf-8",
    )
    return out


_CSS = """
@import url('https://fonts.googleapis.com/css2?family=Orbitron:wght@500;700&family=Share+Tech+Mono&display=swap');
:root{--cyan:#25d0ff;--amber:#ffb84d;--green:#38ffb0;--red:#ff4d5e;--bg:#02060c;--panel:rgba(10,24,38,.55);--line:rgba(37,208,255,.22);}
*{box-sizing:border-box}
body{margin:0;min-height:100vh;background:radial-gradient(1200px 700px at 50% -10%,#06223a 0%,#03101d 45%,var(--bg) 100%);color:#cfe9ff;font-family:'Share Tech Mono',ui-monospace,Consolas,monospace;overflow-x:hidden}
.grid-bg{position:fixed;inset:0;background-image:linear-gradient(var(--line) 1px,transparent 1px),linear-gradient(90deg,var(--line) 1px,transparent 1px);background-size:42px 42px;opacity:.18;pointer-events:none;mask-image:radial-gradient(circle at 50% 30%,#000 30%,transparent 80%)}
.scan{position:fixed;inset:0;pointer-events:none;background:linear-gradient(transparent 0,rgba(37,208,255,.06) 50%,transparent 100%);background-size:100% 6px;mix-blend-mode:screen;animation:scan 7s linear infinite;opacity:.5}
@keyframes scan{from{background-position:0 0}to{background-position:0 100%}}
.wrap{position:relative;max-width:1180px;margin:0 auto;padding:26px 20px 60px}
.topbar{display:flex;align-items:center;gap:22px;border:1px solid var(--line);background:var(--panel);padding:16px 22px;border-radius:14px;backdrop-filter:blur(4px);box-shadow:0 0 40px rgba(37,208,255,.08),inset 0 0 30px rgba(37,208,255,.05)}
.titles{flex:1}
h1{font-family:'Orbitron',sans-serif;margin:0;font-size:30px;letter-spacing:8px;color:#eaffff;text-shadow:0 0 18px var(--cyan),0 0 4px var(--cyan)}
.subtitle{font-size:12px;letter-spacing:2px;color:#7fb6d8;margin-top:4px}
.mode{color:var(--cyan)}
.ro{margin-left:8px;color:var(--amber);border:1px solid var(--amber);padding:1px 7px;border-radius:6px;font-size:10px;box-shadow:0 0 10px rgba(255,184,77,.25)}
.clock{text-align:right;font-size:12px}
.online{color:var(--green);text-shadow:0 0 10px var(--green);letter-spacing:2px;animation:pulse 2.2s ease-in-out infinite}
.ts{color:#6f93ad;margin-top:4px}
.auto{display:inline-block;margin-top:5px;font-size:10px;letter-spacing:1px;color:var(--cyan);border:1px solid rgba(37,208,255,.5);border-radius:6px;padding:1px 7px;box-shadow:0 0 10px rgba(37,208,255,.2)}
@keyframes pulse{50%{opacity:.45}}
.reactor{position:relative;width:72px;height:72px;flex:0 0 72px}
.reactor .ring{position:absolute;inset:0;border-radius:50%;border:2px solid transparent}
.r1{border-top-color:var(--cyan);border-bottom-color:var(--cyan);animation:spin 4s linear infinite;box-shadow:0 0 18px rgba(37,208,255,.4)}
.r2{inset:10px;border-left-color:var(--amber);border-right-color:var(--amber);animation:spin 6s linear infinite reverse}
.r3{inset:20px;border-top-color:#bfefff;border-left-color:#bfefff;animation:spin 3s linear infinite}
.core{position:absolute;inset:26px;border-radius:50%;background:radial-gradient(circle,#eaffff 0%,var(--cyan) 55%,transparent 75%);box-shadow:0 0 26px var(--cyan),0 0 60px rgba(37,208,255,.5);animation:pulse 2.4s ease-in-out infinite}
@keyframes spin{to{transform:rotate(360deg)}}
.stats{display:grid;grid-template-columns:repeat(5,1fr);gap:14px;margin:18px 0}
.stat{border:1px solid var(--line);background:var(--panel);border-radius:12px;padding:14px;text-align:center;box-shadow:inset 0 0 22px rgba(37,208,255,.05)}
.stat-val{font-family:'Orbitron',sans-serif;font-size:26px;font-weight:700}
.stat-label{font-size:10px;letter-spacing:2px;color:#7fb6d8;margin-top:6px}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:16px}
.card{position:relative;border:1px solid var(--line);background:var(--panel);border-radius:12px;padding:16px;overflow:hidden;transition:transform .2s,box-shadow .2s}
.card:hover{transform:translateY(-3px);box-shadow:0 8px 30px rgba(37,208,255,.18)}
.card.ok{box-shadow:inset 0 0 26px rgba(56,255,176,.08)}
.card.bad{box-shadow:inset 0 0 26px rgba(255,77,94,.08)}
.card.warn{box-shadow:inset 0 0 26px rgba(255,184,77,.08)}
.corner{position:absolute;width:14px;height:14px;border:2px solid var(--cyan);opacity:.7}
.tl{top:6px;left:6px;border-right:0;border-bottom:0}.tr{top:6px;right:6px;border-left:0;border-bottom:0}
.bl{bottom:6px;left:6px;border-right:0;border-top:0}.br{bottom:6px;right:6px;border-left:0;border-top:0}
.card-head{display:flex;justify-content:space-between;align-items:center}
.sym{font-family:'Orbitron',sans-serif;font-size:20px;letter-spacing:3px;color:#eaffff}
.badge{font-size:10px;letter-spacing:1px;border:1px solid;border-radius:6px;padding:3px 8px}
.card-row{display:flex;justify-content:space-between;align-items:center;margin:10px 0 8px;font-size:12px;color:#9fc6e0}
.dir.long{color:var(--green)}.dir.short{color:var(--red)}.dir.flat{color:#6f93ad}
.score{font-family:'Orbitron',sans-serif;color:#eaffff;font-size:16px}
.meter{display:flex;align-items:center;gap:8px;margin:5px 0;font-size:10px;color:#84acc8}
.meter-label{width:42px;text-transform:uppercase;letter-spacing:1px}
.meter-track{flex:1;height:7px;background:rgba(255,255,255,.06);border-radius:4px;overflow:hidden}
.meter-fill{display:block;height:100%;border-radius:4px;transition:width .6s}
.meter-val{width:34px;text-align:right;color:#b9dcf2}
.subscores{margin-top:8px;border-top:1px dashed rgba(37,208,255,.15);padding-top:8px}
.levels{margin-top:8px;font-size:11px;color:#7fb6d8}
.reasons{margin-top:8px;display:flex;flex-wrap:wrap;gap:5px}
.tag{font-size:9px;color:var(--red);border:1px solid rgba(255,77,94,.5);border-radius:5px;padding:2px 6px;letter-spacing:.5px}
.panel{margin-top:20px;border:1px solid var(--line);background:var(--panel);border-radius:12px;padding:16px}
.panel-title{font-family:'Orbitron',sans-serif;letter-spacing:3px;color:var(--cyan);font-size:13px;margin-bottom:10px;text-shadow:0 0 10px rgba(37,208,255,.4)}
.console{white-space:pre-wrap;font-size:13px;color:#bfe6ff;margin:0;line-height:1.5;border-left:2px solid var(--cyan);padding-left:12px}
.ticker{margin-top:20px;border-top:1px solid var(--line);border-bottom:1px solid var(--line);overflow:hidden;background:rgba(2,12,22,.6)}
.ticker-track{display:flex;gap:30px;white-space:nowrap;padding:8px 0;animation:marquee 26s linear infinite}
.tick{font-size:11px;color:#7fb6d8;letter-spacing:1px}.tick b{color:var(--cyan)}
@keyframes marquee{from{transform:translateX(20%)}to{transform:translateX(-100%)}}
.foot{margin-top:26px;text-align:center;font-size:11px;color:#5d7e96;letter-spacing:1px}
.glitch{position:relative}
@media(max-width:760px){.stats{grid-template-columns:repeat(2,1fr)}h1{font-size:22px;letter-spacing:5px}.topbar{flex-wrap:wrap}.clock{text-align:left}}
"""
