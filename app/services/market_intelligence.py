"""
market_intelligence.py
======================
Signal detection engine for the BODIVA market.
Ported from Claude AI version (Session S10, 8 detectors).

All detectors are DETERMINISTIC (no AI) — pure functions analysing
order_book_snapshots and market_snapshots.

Signals detected:
  1. Spread compression/expansion  (>30% change vs 7d baseline)
  2. Imbalance flip               (sign change in bid/ask pressure)
  3. Imbalance trend              (3+ consecutive same-sign snapshots)
  4. Volume anomaly               (>3x 7-day median)
  5. Large single trade           (n_trades=1, significant volume)
  6. Stale instrument             (no activity > 7 days)
  7. Liquidity vacuum             (one-sided order book)
  8. Bid-depth surge              (institutional positioning)
"""
from __future__ import annotations

import math
import statistics
from datetime import date, datetime, timedelta
from typing import Optional, Dict, List, Any

from sqlalchemy import select, desc, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bodiva_market import OrderBookSnapshot, MarketSnapshot
from app.models.investment_signal import InvestmentSignal, SignalType, SignalSeverity

# ═══════════════════════════════════════════════════════════════════════════
# Pure helper functions
# ═══════════════════════════════════════════════════════════════════════════

def _percent_change(current: float, baseline: float) -> Optional[float]:
    """% change from baseline. Returns None if baseline is 0/None."""
    if not baseline or baseline == 0:
        return None
    return ((current - baseline) / baseline) * 100


def _safe_median(values: List[float]) -> Optional[float]:
    clean = [v for v in values if v is not None and not (math.isnan(v) if isinstance(v, float) else False)]
    if not clean:
        return None
    return statistics.median(clean)


# ═══════════════════════════════════════════════════════════════════════════
# 1. Spread compression / expansion
# ═══════════════════════════════════════════════════════════════════════════

def detect_spread_compression(
    current_spread_pct: Optional[float],
    baseline_spread_median: Optional[float],
    threshold_pct: float = 30.0,
) -> Optional[Dict[str, Any]]:
    """
    Detect significant spread compression (>30% decrease vs 7d median).
    Compression indicates improving liquidity; expansion suggests stress.
    """
    if not current_spread_pct or not baseline_spread_median or baseline_spread_median == 0:
        return None

    change = _percent_change(current_spread_pct, baseline_spread_median)
    if change is None:
        return None
    if abs(change) < threshold_pct:
        return None

    direction = "compression" if change < 0 else "expansion"
    severity = SignalSeverity.WATCH if abs(change) > 50 else SignalSeverity.INFO
    if abs(change) > 80:
        severity = SignalSeverity.ALERT

    return {
        "signal_type": "SPREAD_" + ("COMPRESSION" if change < 0 else "EXPANSION"),
        "direction": direction,
        "strength": round(abs(change), 1),
        "severity": severity.value,
        "title": f"Spread {'compressao' if change < 0 else 'expansao'} de {abs(change):.0f}%",
        "description": f"O spread bid-ask {'caiu' if change < 0 else 'subiu'} "
                       f"{abs(change):.0f}% vs mediana de 7 dias, sugerindo "
                       f"{'melhoria' if change < 0 else 'deterioracao'} na liquidez.",
        "metric_current": round(current_spread_pct, 2),
        "metric_baseline": round(baseline_spread_median, 2),
        "metric_change_pct": round(change, 1),
    }


# ═══════════════════════════════════════════════════════════════════════════
# 2. Imbalance flip
# ═══════════════════════════════════════════════════════════════════════════

def detect_imbalance_flip(
    current_imbalance: Optional[float],
    previous_imbalance: Optional[float],
) -> Optional[Dict[str, Any]]:
    """
    Detect sign change in bid/ask pressure (supply/demand flip).
    A positive-to-negative flip = selling pressure emerging.
    """
    if current_imbalance is None or previous_imbalance is None:
        return None

    if (current_imbalance > 0 and previous_imbalance > 0) or \
       (current_imbalance < 0 and previous_imbalance < 0):
        return None  # same direction

    direction = "buying_surge" if current_imbalance > 0 else "selling_pressure"
    severity = SignalSeverity.WATCH

    return {
        "signal_type": "IMBALANCE_FLIP",
        "direction": direction,
        "strength": round(abs(current_imbalance - previous_imbalance), 3),
        "severity": severity.value,
        "title": f"Flip de pressao: {'compradora' if current_imbalance > 0 else 'vendedora'}",
        "description": f"O imbalance passou de {previous_imbalance:.3f} para {current_imbalance:.3f} — "
                       f"{'mais compradores' if current_imbalance > 0 else 'mais vendedores'} entraram no mercado.",
        "metric_current": round(current_imbalance, 4),
        "metric_baseline": round(previous_imbalance, 4),
        "metric_change_pct": round(abs(current_imbalance - previous_imbalance) * 100, 1),
    }


# ═══════════════════════════════════════════════════════════════════════════
# 3. Imbalance trend (acceleration)
# ═══════════════════════════════════════════════════════════════════════════

def detect_imbalance_trend(
    imbalances: List[float],
    min_consecutive: int = 3,
) -> Optional[Dict[str, Any]]:
    """
    Detect 3+ consecutive snapshots with same-sign imbalance.
    Indicates persistent buying or selling pressure.
    """
    if not imbalances or len(imbalances) < min_consecutive:
        return None

    trending = []
    for i, val in enumerate(imbalances):
        if val > 0:
            trending.append((i, "positive"))
        elif val < 0:
            trending.append((i, "negative"))
        else:
            trending.append((i, "neutral"))

    # Find longest run of same direction
    runs = []
    current_dir = None
    current_len = 0

    for _, direction in trending:
        if direction == "neutral":
            current_dir = None
            current_len = 0
            continue
        if direction == current_dir:
            current_len += 1
        else:
            if current_len >= min_consecutive:
                runs.append({"direction": current_dir, "length": current_len})
            current_dir = direction
            current_len = 1

    if current_len >= min_consecutive and current_dir:
        runs.append({"direction": current_dir, "length": current_len})

    if not runs:
        return None

    best = max(runs, key=lambda r: r["length"])
    severity = SignalSeverity.WATCH if best["length"] >= 5 else SignalSeverity.INFO
    if best["length"] >= 7:
        severity = SignalSeverity.ALERT

    return {
        "signal_type": "IMBALANCE_TREND",
        "direction": "buyer_dominance" if best["direction"] == "positive" else "seller_dominance",
        "strength": float(best["length"]),
        "severity": severity.value,
        "title": f"Tendencia {'compradora' if best['direction'] == 'positive' else 'vendedora'} ({best['length']} snaps)",
        "description": f"{best['length']} snapshots consecutivos com imbalance "
                       f"{'positivo' if best['direction'] == 'positive' else 'negativo'}.",
        "metric_current": float(best["length"]),
        "metric_baseline": 3.0,
        "metric_change_pct": float(best["length"] - 2) * 50,
    }


# ═══════════════════════════════════════════════════════════════════════════
# 4. Volume anomaly
# ═══════════════════════════════════════════════════════════════════════════

def detect_volume_anomaly(
    current_volume: Optional[float],
    baseline_median_volume: Optional[float],
    multiplier: float = 3.0,
) -> Optional[Dict[str, Any]]:
    """
    Detect volume spikes: >3x 7-day median.
    Indicates institutional activity or event-driven trading.
    """
    if not current_volume or not baseline_median_volume or baseline_median_volume <= 0:
        return None

    ratio = current_volume / baseline_median_volume
    if ratio < multiplier:
        return None

    severity = SignalSeverity.WATCH if ratio > 5 else SignalSeverity.INFO
    if ratio > 10:
        severity = SignalSeverity.ALERT

    return {
        "signal_type": "VOLUME_ANOMALY",
        "direction": "spike",
        "strength": round(ratio, 1),
        "severity": severity.value,
        "title": f"Volume {ratio:.0f}x acima da mediana",
        "description": f"Volume de {current_volume:,.0f} vs mediana de 7 dias de {baseline_median_volume:,.0f} ({ratio:.1f}x).",
        "metric_current": round(current_volume, 2),
        "metric_baseline": round(baseline_median_volume, 2),
        "metric_change_pct": round((ratio - 1) * 100, 1),
    }


# ═══════════════════════════════════════════════════════════════════════════
# 5. Large single trade
# ═══════════════════════════════════════════════════════════════════════════

def detect_large_single_trade(
    n_trades: Optional[int],
    volume: Optional[float],
    median_volume: Optional[float],
) -> Optional[Dict[str, Any]]:
    """
    Detect single trade with significant volume (block trade).
    """
    if not n_trades or n_trades != 1:
        return None
    if not volume or not median_volume or median_volume <= 0:
        return None

    if volume < median_volume * 2:
        return None

    return {
        "signal_type": "LARGE_SINGLE_TRADE",
        "direction": "block_trade",
        "strength": round(volume / max(median_volume, 1), 1),
        "severity": SignalSeverity.WATCH.value,
        "title": "Transacao unica de grande volume",
        "description": f"Transacao com 1 unico trade de {volume:,.0f} vs mediana de {median_volume:,.0f}.",
        "metric_current": float(n_trades),
        "metric_baseline": float(median_volume),
        "metric_change_pct": round((volume / median_volume - 1) * 100, 1),
    }


# ═══════════════════════════════════════════════════════════════════════════
# 6. Stale instrument
# ═══════════════════════════════════════════════════════════════════════════

def detect_stale_instrument(
    last_activity_date: Optional[date],
    stale_days: int = 7,
) -> Optional[Dict[str, Any]]:
    """
    Detect instruments with no order book activity for > 7 days.
    """
    if not last_activity_date:
        return {
            "signal_type": "STALE",
            "direction": "no_activity",
            "strength": 0.0,
            "severity": SignalSeverity.WATCH.value,
            "title": "Sem actividade no order book",
            "description": "Nenhuma actividade registada no order book para este instrumento.",
            "metric_current": 0,
            "metric_baseline": 0,
            "metric_change_pct": 0,
        }

    days_since = (date.today() - last_activity_date).days
    if days_since <= stale_days:
        return None

    severity = SignalSeverity.ALERT if days_since > 30 else SignalSeverity.WATCH

    return {
        "signal_type": "STALE",
        "direction": "no_activity",
        "strength": float(days_since),
        "severity": severity.value,
        "title": f"Sem actividade ha {days_since} dias",
        "description": f"Ultima actividade no order book foi ha {days_since} dias.",
        "metric_current": float(days_since),
        "metric_baseline": float(stale_days),
        "metric_change_pct": float(days_since - stale_days) / stale_days * 100 if stale_days > 0 else 0,
    }


# ═══════════════════════════════════════════════════════════════════════════
# 7. Liquidity vacuum
# ═══════════════════════════════════════════════════════════════════════════

def detect_liquidity_vacuum(
    has_bids: bool,
    has_asks: bool,
) -> Optional[Dict[str, Any]]:
    """
    Detect one-sided order book (only bids or only asks).
    Indicates severe liquidity imbalance.
    """
    if has_bids and has_asks:
        return None

    side = "Apenas compradores" if has_bids else "Apenas vendedores"
    return {
        "signal_type": "LIQUIDITY_VACUUM",
        "direction": "one_sided",
        "strength": 1.0,
        "severity": SignalSeverity.ALERT.value,
        "title": f"Livro unilateral: {side}",
        "description": f"O order book tem apenas ordens de {'compra' if has_bids else 'venda'} — "
                       f"a liquidez esta gravemente comprometida.",
        "metric_current": 1.0 if has_bids else -1.0,
        "metric_baseline": 0.0,
        "metric_change_pct": 100.0,
    }


# ═══════════════════════════════════════════════════════════════════════════
# 8. Bid-depth surge
# ═══════════════════════════════════════════════════════════════════════════

def detect_bid_depth_surge(
    current_bid_qty: Optional[float],
    baseline_bid_qty_median: Optional[float],
    multiplier: float = 3.0,
) -> Optional[Dict[str, Any]]:
    """
    Detect surge in bid depth — institutional buyers positioning.
    """
    if not current_bid_qty or not baseline_bid_qty_median or baseline_bid_qty_median <= 0:
        return None

    ratio = current_bid_qty / baseline_bid_qty_median
    if ratio < multiplier:
        return None

    return {
        "signal_type": "BID_DEPTH_SURGE",
        "direction": "accumulation",
        "strength": round(ratio, 1),
        "severity": SignalSeverity.WATCH.value,
        "title": f"Profundidade de compra {ratio:.0f}x acima da mediana",
        "description": f"Quantidade no bid {ratio:.0f}x acima da mediana — possivel acumulacao institucional.",
        "metric_current": round(current_bid_qty, 2),
        "metric_baseline": round(baseline_bid_qty_median, 2),
        "metric_change_pct": round((ratio - 1) * 100, 1),
    }


# ═══════════════════════════════════════════════════════════════════════════
# Orchestrator — run all detectors for a ticker
# ═══════════════════════════════════════════════════════════════════════════

def run_detection(
    current: Dict[str, Any],
    baseline: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """
    Run ALL signal detectors for a single ticker.
    current: {spread_pct, imbalance, volume_qty, n_trades, bid_qty, ask_qty, snapshot_date, ...}
    baseline: {spread_median, volume_median, previous_imbalance, bid_qty_median, ...}

    Returns list of signal dicts (empty list if no signals detected).
    """
    signals: list[dict] = []

    # 1. Spread compression/expansion
    s = detect_spread_compression(
        current.get("spread_pct"), baseline.get("spread_median"),
    )
    if s:
        signals.append(s)

    # 2. Imbalance flip
    s = detect_imbalance_flip(
        current.get("imbalance"), baseline.get("previous_imbalance"),
    )
    if s:
        signals.append(s)

    # 3. Volume anomaly
    s = detect_volume_anomaly(
        current.get("volume_qty"), baseline.get("volume_median"),
    )
    if s:
        signals.append(s)

    # 4. Large single trade
    s = detect_large_single_trade(
        current.get("n_trades"), current.get("volume_qty"),
        baseline.get("volume_median"),
    )
    if s:
        signals.append(s)

    # 5. Liquidity vacuum
    s = detect_liquidity_vacuum(
        bool(current.get("bid_qty")), bool(current.get("ask_qty")),
    )
    if s:
        signals.append(s)

    # 6. Bid-depth surge
    s = detect_bid_depth_surge(
        current.get("bid_qty"), baseline.get("bid_qty_median"),
    )
    if s:
        signals.append(s)

    # 7. Stale check
    last_date = current.get("snapshot_date")
    if isinstance(last_date, str):
        try:
            last_date = datetime.strptime(last_date, "%Y-%m-%d").date()
        except ValueError:
            last_date = None
    s = detect_stale_instrument(last_date)
    if s:
        signals.append(s)

    return signals


async def detect_market_signals(
    db: AsyncSession,
    ticker: Optional[str] = None,
    persist: bool = False,
    user_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Async orchestrator: fetch current + baseline data, run all detectors,
    optionally persist results as InvestmentSignal records.
    """
    # Fetch latest order book data
    ob_query = (
        select(OrderBookSnapshot)
        .order_by(desc(OrderBookSnapshot.snapshot_date))
        .limit(500)
    )
    if ticker:
        ob_query = select(OrderBookSnapshot).where(OrderBookSnapshot.ticker == ticker).order_by(desc(OrderBookSnapshot.snapshot_date)).limit(200)

    ob_result = await db.execute(ob_query)
    orders = ob_result.scalars().all()

    # Group by ticker
    tickers_data: dict[str, dict] = {}
    for r in orders:
        t = r.ticker
        if t not in tickers_data:
            tickers_data[t] = {"bids": [], "asks": [], "snapshot_date": r.snapshot_date,
                               "n_trades": getattr(r, "n_trades", 0)}
        entry = {"qty": r.quantity or 0, "price": r.price or 0}
        if r.side in ("BID", "ASK"):
            tickers_data[t][r.side.lower() + "s"].append(entry)

    all_signals: list[dict] = []

    for tckr, data in tickers_data.items():
        bids = data["bids"]
        asks = data["asks"]

        best_bid = bids[0]["price"] if bids else None
        best_ask = asks[0]["price"] if asks else None
        mid = (best_bid + best_ask) / 2 if (best_bid and best_ask) else None
        spread_pct = ((best_ask - best_bid) / mid * 100) if (best_ask and best_bid and mid) else None

        bid_qty = sum(b["qty"] for b in bids)
        ask_qty = sum(a["qty"] for a in asks)
        total_val = bid_qty * (best_bid or 0) + ask_qty * (best_ask or 0)
        imbalance = (bid_qty * (best_bid or 0) - ask_qty * (best_ask or 0)) / max(total_val, 1)

        current = {
            "spread_pct": spread_pct,
            "imbalance": imbalance,
            "bid_qty": bid_qty,
            "ask_qty": ask_qty,
            "volume_qty": bid_qty + ask_qty,
            "n_trades": 0,
            "snapshot_date": data["snapshot_date"],
        }

        # Simplified baseline
        baseline = {
            "spread_median": spread_pct,
            "previous_imbalance": 0.0,
            "volume_median": bid_qty + ask_qty,
            "bid_qty_median": bid_qty,
        }

        signals = run_detection(current, baseline)
        for sig in signals:
            sig["ticker"] = tckr
            sig["detected_at"] = datetime.utcnow().isoformat()
        all_signals.extend(signals)

        # Persist if requested
        for sig in signals:
            if persist and user_id:
                signal = InvestmentSignal(
                    user_id=user_id,
                    signal_type=SignalType.MARKET_SIGNAL,
                    severity=_severity_enum(sig.get("severity", "INFO")),
                    title=sig.get("title", ""),
                    description=sig.get("description", ""),
                    source_ticker=tckr,
                    source="market_intelligence",
                    metadata_json={k: v for k, v in sig.items() if k != "ticker"},
                )
                db.add(signal)

    if persist:
        await db.commit()

    return all_signals


def _severity_enum(severity_str: str) -> SignalSeverity:
    """Map string severity to enum."""
    mapping = {"INFO": SignalSeverity.INFO, "WATCH": SignalSeverity.WATCH,
               "ALERT": SignalSeverity.ALERT, "CRITICAL": SignalSeverity.CRITICAL}
    return mapping.get(severity_str, SignalSeverity.INFO)


async def market_pulse(db: AsyncSession) -> Dict[str, Any]:
    """Aggregate market health summary — one number per dimension."""
    signals = await detect_market_signals(db)

    if not signals:
        return {"status": "healthy", "total_signals": 0, "by_severity": {},
                "by_type": {}, "recent_signals": []}

    by_severity: dict[str, int] = {}
    by_type: dict[str, int] = {}
    for s in signals:
        sev = s.get("severity", "INFO")
        by_severity[sev] = by_severity.get(sev, 0) + 1
        sig_type = s.get("signal_type", "UNKNOWN")
        by_type[sig_type] = by_type.get(sig_type, 0) + 1

    critical_count = by_severity.get("CRITICAL", 0) + by_severity.get("ALERT", 0)
    if critical_count >= 5:
        status = "stressed"
    elif critical_count >= 2:
        status = "watch"
    else:
        status = "healthy"

    return {
        "status": status,
        "total_signals": len(signals),
        "by_severity": {k: v for k, v in sorted(by_severity.items())},
        "by_type": {k: v for k, v in sorted(by_type.items(), key=lambda x: -x[1])},
        "recent_signals": signals[:10],
    }
