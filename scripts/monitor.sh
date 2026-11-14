#!/usr/bin/env bash
# monitor.sh - Toma una "foto" de los recursos del servidor y la agrega a un CSV.
# Mide: CPU, carga, RAM, swap, disco, procesos, zombies, proceso que más CPU usa
# y el estado (healthcheck) de cada contenedor.
# Uso:   ./scripts/monitor.sh            (una medición)
# Cron:  */5 * * * * /opt/sarais/scripts/monitor.sh >/dev/null 2>&1
set -euo pipefail

source "$(dirname "${BASH_SOURCE[0]}")/lib/common.sh"
load_env
init_logging
require_cmd awk df ps

METRICS_DIR="${METRICS_DIR:-$LOG_DIR/metrics}"
mkdir -p "$METRICS_DIR" 2>/dev/null || METRICS_DIR="$LOG_DIR/metrics"
mkdir -p "$METRICS_DIR"
CSV="$METRICS_DIR/metrics_$(date '+%Y-%m').csv"   # un archivo por mes

ALERT_CPU="${ALERT_CPU:-85}"
ALERT_RAM="${ALERT_RAM:-85}"
ALERT_DISK="${ALERT_DISK:-85}"

# --- CPU: dos lecturas de /proc/stat con 1 segundo de diferencia ---
read_cpu() { awk '/^cpu /{idle=$5+$6; total=0; for(i=2;i<=NF;i++) total+=$i; print idle, total}' /proc/stat; }
read -r idle1 total1 < <(read_cpu)
sleep 1
read -r idle2 total2 < <(read_cpu)
cpu_pct="$(awk -v i1="$idle1" -v t1="$total1" -v i2="$idle2" -v t2="$total2" \
  'BEGIN{dt=t2-t1; printf "%.1f", (dt>0 ? (1-(i2-i1)/dt)*100 : 0)}')"
load_1m="$(awk '{print $1}' /proc/loadavg)"

# --- RAM y swap (MemAvailable = memoria realmente disponible) ---
read -r ram_total_mb ram_used_mb ram_pct swap_pct < <(awk '
  /^MemTotal:/{t=$2} /^MemAvailable:/{a=$2} /^SwapTotal:/{st=$2} /^SwapFree:/{sf=$2}
  END{ printf "%d %d %.1f %.1f\n", t/1024, (t-a)/1024, (t-a)*100/t, (st>0 ? (st-sf)*100/st : 0) }' /proc/meminfo)

# --- Disco de la raíz ---
read -r disk_pct disk_free_gb < <(df -P -k / | awk 'NR==2{gsub("%","",$5); printf "%d %.1f\n", $5, $4/1048576}')

# --- Procesos ---
procs="$(ps -e --no-headers | wc -l)"
zombies="$(ps -eo stat --no-headers | grep -c '^Z' || true)"
top_proc="$(ps -eo comm,pcpu --sort=-pcpu --no-headers | head -n1 | awk '{gsub(",","_",$1); print $1":"$2"%"}')"

# --- Servicios (contenedores) ---
svc_state() {
  # healthy | unhealthy | starting | running (sin healthcheck) | stopped | missing
  local s
  s="$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{if .State.Running}}running{{else}}stopped{{end}}{{end}}' "$1" 2>/dev/null)" \
    || s="missing"
  echo "$s"
}
if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
  docker_daemon="up"
  s_nginx="$(svc_state "$NGINX_CONTAINER")"
  s_app="$(svc_state "$APP_CONTAINER")"
  s_mysql="$(svc_state "$MYSQL_CONTAINER")"
  s_mongo="$(svc_state "$MONGO_CONTAINER")"
else
  docker_daemon="down"
  s_nginx="n/a"; s_app="n/a"; s_mysql="n/a"; s_mongo="n/a"
fi

# --- Alertas ---
alerts=()
awk -v v="$cpu_pct"  -v l="$ALERT_CPU"  'BEGIN{exit !(v>=l)}' && alerts+=("CPU")
awk -v v="$ram_pct"  -v l="$ALERT_RAM"  'BEGIN{exit !(v>=l)}' && alerts+=("RAM")
(( disk_pct >= ALERT_DISK )) && alerts+=("DISK")
[[ "$docker_daemon" == "down" ]] && alerts+=("DOCKER")
for pair in "nginx:$s_nginx" "app:$s_app" "mysql:$s_mysql" "mongo:$s_mongo"; do
  [[ "${pair#*:}" =~ ^(healthy|running|n/a)$ ]] || alerts+=("${pair%%:*}")
done
if (( ${#alerts[@]} )); then
  status="ALERT:$(IFS='|'; echo "${alerts[*]}")"
  log WARN "$status cpu=${cpu_pct}% ram=${ram_pct}% disk=${disk_pct}%"
else
  status="OK"
fi

# --- Escribir CSV (encabezado si el archivo es nuevo) ---
if [[ ! -f "$CSV" ]]; then
  echo "timestamp,hostname,cpu_pct,load_1m,ram_used_mb,ram_total_mb,ram_pct,swap_pct,disk_used_pct,disk_free_gb,processes,zombies,top_process,docker,nginx,app,mysql,mongo,status" > "$CSV"
fi
row="$(date -Iseconds),$(hostname),$cpu_pct,$load_1m,$ram_used_mb,$ram_total_mb,$ram_pct,$swap_pct,$disk_pct,$disk_free_gb,$procs,$zombies,$top_proc,$docker_daemon,$s_nginx,$s_app,$s_mysql,$s_mongo,$status"
echo "$row" >> "$CSV"
echo "$row"
log INFO "Medición guardada en $CSV ($status)"
