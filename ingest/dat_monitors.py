"""Final monitor values stored inside the .dat.h5, for cases without the -rfile.out files.

Fluent keeps, in the "Data Variables" Scheme text of the data file, a table of 100
samples per report monitor (`monitor/average-over-state`). It is NOT a history: the
first sample is the final instantaneous value and the last one the final running
average, and the numbers between are a smooth curve that does not follow the run
(checked against the report files of two cases). So only those two ends are used.
Their gap is a rough sign of whether the flow still moves: the real drift over the last
iterations needs the report files.
"""

from __future__ import annotations

from pathlib import Path

KEY = "(monitor/average-over-state"
GAP_LIMIT_PCT = 0.5


def parse_scheme(text: str):
    """Minimal Scheme reader: nested lists, strings and numbers. Enough for these tables."""
    pos = 0
    size = len(text)

    def skip() -> None:
        nonlocal pos
        while pos < size and text[pos] in " \n\t\r":
            pos += 1

    def atom():
        nonlocal pos
        if text[pos] == '"':
            end = text.index('"', pos + 1)
            value = text[pos + 1 : end]
            pos = end + 1
            return value
        end = pos
        while end < size and text[end] not in " \n\t\r()":
            end += 1
        token = text[pos:end]
        pos = end
        try:
            return float(token)
        except ValueError:
            return token

    def sequence():
        nonlocal pos
        pos += 1
        out = []
        while True:
            skip()
            if pos >= size:
                raise ValueError("nieZamknieta lista")
            if text[pos] == ")":
                pos += 1
                return out
            out.append(sequence() if text[pos] == "(" else atom())

    skip()
    return sequence()


def _balanced(text: str, start: int) -> str:
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "(":
            depth += 1
        elif text[i] == ")":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    raise ValueError("nieZamknieta lista")


def monitor_samples(data_variables: str) -> dict[str, dict]:
    """name -> {"zones": [...], "from": it0, "to": it1, "series": [[...], ...]} from the Scheme text."""
    start = data_variables.find(KEY)
    if start < 0:
        return {}
    tree = parse_scheme(_balanced(data_variables, start))
    out = {}
    for item in tree[1] if len(tree) > 1 else []:
        if not (isinstance(item, list) and len(item) >= 3 and isinstance(item[2], list) and len(item[2]) >= 3):
            continue
        name, zones, data = item[0], item[1], item[2]
        out[str(name)] = {"zones": zones, "from": data[0], "to": data[1], "series": [s for s in data[2:] if isinstance(s, list)]}
    return out


def to_monitors(samples: dict[str, dict], limit_pct: float = GAP_LIMIT_PCT) -> dict:
    """The same shape `parse_rfiles` returns, from the two usable ends of each sample table."""
    monitors = {}
    iterations = 0
    for name, rec in samples.items():
        series = max(rec["series"], key=len, default=[])
        if len(series) < 2:
            continue  # a single number is an average over the run
        instantaneous, averaged = float(series[0]), float(series[-1])
        scale = abs(averaged) if abs(averaged) > 1e-9 else None
        gap = None if scale is None else round(100.0 * (instantaneous - averaged) / scale, 3)
        last = int(rec["to"])
        monitors[name] = {
            "file": "dat.h5",
            "monitor": name,
            "iterations": last,
            "averaged": averaged,
            "instantaneous": instantaneous,
            "source": "dat.h5",
            "stability": {
                "proxy": True,
                "window": None,
                "fromIteration": None,
                "startValue": instantaneous,
                "endValue": averaged,
                "delta": round(instantaneous - averaged, 6),
                "driftPct": gap,
                "spreadPct": None,
            },
        }
        iterations = max(iterations, last)
    return {
        "iterations": iterations,
        "monitors": monitors,
        "source": "dat.h5 (tylko stan końcowy: wartość chwilowa i średnia, bez historii)",
        "gapLimitPct": limit_pct,
    }


def read_dat_monitors(dat_path: Path) -> dict | None:
    import h5py

    with h5py.File(dat_path, "r") as data:
        if "settings/Data Variables" not in data:
            return None
        text = data["settings/Data Variables"][0].decode("utf-8", errors="replace")
    samples = monitor_samples(text)
    result = to_monitors(samples)
    return result if result["monitors"] else None
