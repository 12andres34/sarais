#!/usr/bin/env python3
"""metrics_report.py - Resume el CSV de monitor.sh para el informe (requisito R4).

Uso:
  python3 scripts/metrics_report.py metrics_2026-11.csv [otro.csv ...]
  python3 scripts/metrics_report.py metrics_2026-11.csv --png docs/img/metrics.png
  python3 scripts/metrics_report.py metrics_2026-11.csv --since 2026-11-18T08:00 --until 2026-11-18T12:00

Imprime una tabla Markdown (en inglés, lista para el informe IEEE) con min / promedio /
p95 / max de CPU, RAM, disco y carga, y cuántas mediciones tuvieron alerta.
--png necesita matplotlib (pip install matplotlib). Sin él, solo sale la tabla.
Solo usa la biblioteca estándar para la tabla: funciona en la VM (python3 de Ubuntu).
"""
import argparse
import csv
import statistics
import sys
from datetime import datetime

# columna del CSV -> (nombre en el informe, unidad)
METRICS = {
    "cpu_pct": ("CPU usage", "%"),
    "load_1m": ("Load average (1 min)", ""),
    "ram_pct": ("RAM usage", "%"),
    "ram_used_mb": ("RAM used", "MB"),
    "swap_pct": ("Swap usage", "%"),
    "disk_used_pct": ("Disk usage (/)", "%"),
    "processes": ("Processes", ""),
}


def parse_args():
    p = argparse.ArgumentParser(description="Resumen de métricas de monitor.sh")
    p.add_argument("csv", nargs="+", help="Archivos metrics_AAAA-MM.csv")
    p.add_argument("--png", help="Guarda una gráfica PNG (necesita matplotlib)")
    p.add_argument("--since", help="Desde (ISO, p. ej. 2026-11-18T08:00)")
    p.add_argument("--until", help="Hasta (ISO)")
    return p.parse_args()


def load_rows(paths, since, until):
    rows = []
    for path in paths:
        with open(path, newline="", encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                try:
                    ts = datetime.fromisoformat(r["timestamp"])
                except (KeyError, ValueError):
                    continue  # línea dañada: se ignora
                naive = ts.replace(tzinfo=None)  # comparar en hora local de la VM
                if since and naive < since:
                    continue
                if until and naive > until:
                    continue
                r["_ts"] = ts
                rows.append(r)
    rows.sort(key=lambda r: r["_ts"])
    return rows


def p95(values):
    if len(values) < 2:
        return values[0]
    return statistics.quantiles(values, n=20, method="inclusive")[18]


def summary_table(rows):
    lines = [
        f"Period: {rows[0]['_ts']:%Y-%m-%d %H:%M} to {rows[-1]['_ts']:%Y-%m-%d %H:%M} "
        f"({len(rows)} samples, host {rows[-1].get('hostname', '?')}, "
        f"RAM total {rows[-1].get('ram_total_mb', '?')} MB)",
        "",
        "| Metric | Min | Mean | P95 | Max |",
        "|---|---:|---:|---:|---:|",
    ]
    for col, (name, unit) in METRICS.items():
        vals = []
        for r in rows:
            try:
                vals.append(float(r[col]))
            except (KeyError, ValueError):
                pass
        if not vals:
            continue
        label = f"{name} ({unit})" if unit else name
        lines.append(f"| {label} | {min(vals):.1f} | {statistics.mean(vals):.1f} | "
                     f"{p95(vals):.1f} | {max(vals):.1f} |")
    alerts = [r for r in rows if r.get("status", "OK") != "OK"]
    healthy = sum(1 for r in rows if all(r.get(s) in ("healthy", "running") for s in ("nginx", "app", "mysql", "mongo")))
    lines += [
        "",
        f"Samples with all four containers healthy: {healthy}/{len(rows)} "
        f"({healthy * 100 / len(rows):.1f}%)",
        f"Samples with an alert: {len(alerts)}",
    ]
    for a in alerts[:10]:
        lines.append(f"  - {a['_ts']:%Y-%m-%d %H:%M} {a['status']}")
    return "\n".join(lines)


def save_png(rows, path):
    try:
        import matplotlib
        matplotlib.use("Agg")  # sin pantalla
        import matplotlib.pyplot as plt
    except ImportError:
        print("\n[aviso] matplotlib no está instalado: no se generó el PNG "
              "(en WSL: source .venv/bin/activate && pip install matplotlib)", file=sys.stderr)
        return
    ts = [r["_ts"] for r in rows]
    # Paneles separados con la misma escala 0-100 % (no se mezclan ejes distintos)
    panels = [("cpu_pct", "CPU usage (%)", "ALERT_CPU"),
              ("ram_pct", "RAM usage (%)", "ALERT_RAM"),
              ("disk_used_pct", "Disk usage, / (%)", "ALERT_DISK")]
    fig, axes = plt.subplots(len(panels), 1, figsize=(8, 6.5), sharex=True)
    ink, muted, line = "#1f2328", "#6e7781", "#2a6fdb"
    for ax, (col, title, _) in zip(axes, panels):
        vals = [float(r[col]) for r in rows]
        ax.plot(ts, vals, color=line, linewidth=1.6)
        ax.axhline(85, color=muted, linewidth=1, linestyle="--")  # umbral de alerta por defecto
        ax.text(ts[0], 87, "alert threshold (85%)", color=muted, fontsize=8, va="bottom")
        ax.set_ylim(0, 100)
        ax.set_title(title, loc="left", fontsize=10, color=ink)
        ax.grid(axis="y", color="#d0d7de", linewidth=0.6)
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)
        ax.tick_params(colors=muted, labelsize=8)
    axes[-1].set_xlabel("Time (VM local time)", fontsize=9, color=muted)
    fig.suptitle("SARAIS VM resource usage (monitor.sh, 5-min samples)", fontsize=11, color=ink)
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(path, dpi=200)
    print(f"\nGráfica guardada en {path}")


def main():
    args = parse_args()
    since = datetime.fromisoformat(args.since) if args.since else None
    until = datetime.fromisoformat(args.until) if args.until else None
    rows = load_rows(args.csv, since, until)
    if not rows:
        sys.exit("No hay mediciones en ese rango.")
    print(summary_table(rows))
    if args.png:
        save_png(rows, args.png)


if __name__ == "__main__":
    main()
