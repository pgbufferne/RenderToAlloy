"""
Exporter Prometheus pour les métriques Render.
Interroge périodiquement l'API JSON de Render (/v1/metrics/*) et les
réexpose au format Prometheus sur /metrics (port EXPORTER_PORT).

Variables d'environnement attendues :
  RENDER_API_KEY        - clé API Render (rnd_...)
  RENDER_RESOURCE_IDS    - un ou plusieurs srv-... séparés par des virgules
  EXPORTER_PORT           - port d'écoute local (défaut: 9200)
  POLL_INTERVAL_SECONDS   - fréquence de rafraîchissement (défaut: 60)
"""
import logging
import os
import threading
import time

import requests
from prometheus_client import Gauge, start_http_server

RENDER_API_KEY = os.environ["RENDER_API_KEY"]
RESOURCE_IDS = [
    r.strip() for r in os.environ.get("RENDER_RESOURCE_IDS", "").split(",") if r.strip()
]
POLL_INTERVAL = int(os.environ.get("POLL_INTERVAL_SECONDS", "60"))
EXPORTER_PORT = int(os.environ.get("EXPORTER_PORT", "9200"))

# Les 4 métriques Render qu'on récupère. "instance-count" est volontairement
# exclu par défaut (peu utile sur un service Free à une seule instance) ;
# ajoute-le à la liste si besoin.
METRIC_NAMES = ["cpu", "memory", "bandwidth", "http-requests"]

GAUGES = {
    name: Gauge(
        f"render_{name.replace('-', '_')}_usage",
        f"Dernière valeur remontée par l'API Render pour la métrique '{name}'",
        ["resource", "instance"],
    )
    for name in METRIC_NAMES
}

HEADERS = {
    "Accept": "application/json",
    "Authorization": f"Bearer {RENDER_API_KEY}",
}


def fetch_metric(metric_name: str, resource_id: str):
    url = f"https://api.render.com/v1/metrics/{metric_name}"
    params = {"resource": resource_id, "resolutionSeconds": 60}
    resp = requests.get(url, headers=HEADERS, params=params, timeout=10)
    resp.raise_for_status()
    return resp.json()


def poll_once():
    for metric_name in METRIC_NAMES:
        for resource_id in RESOURCE_IDS:
            try:
                series_list = fetch_metric(metric_name, resource_id)
                for series in series_list:
                    labels = {item["field"]: item["value"] for item in series.get("labels", [])}
                    values = series.get("values", [])
                    if not values:
                        continue
                    latest_value = values[-1]["value"]  # dernier point = valeur la plus récente
                    GAUGES[metric_name].labels(
                        resource=labels.get("resource", resource_id),
                        instance=labels.get("instance", ""),
                    ).set(latest_value)
            except Exception as exc:  # noqa: BLE001 - on ne veut jamais crasher la boucle
                logging.warning("Échec récupération %s pour %s : %s", metric_name, resource_id, exc)


def poll_loop():
    while True:
        poll_once()
        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    if not RESOURCE_IDS:
        raise SystemExit("RENDER_RESOURCE_IDS est requis (ex: srv-xxxx,srv-yyyy)")

    logging.info(
        "Démarrage exporter sur :%s, ressources=%s, intervalle=%ss",
        EXPORTER_PORT, RESOURCE_IDS, POLL_INTERVAL,
    )

    start_http_server(EXPORTER_PORT)
    threading.Thread(target=poll_loop, daemon=True).start()

    while True:
        time.sleep(3600)
