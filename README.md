# 📡 render-observability-stack

Agent de monitoring pour `rok-kvk-dashboard` : collecte les métriques d'infra Render (CPU, mémoire, bande passante) et les métriques applicatives (`/metrics.php` de rok-app), et les relaie vers **Grafana Cloud** (Prometheus hébergé + dashboards).

Déployé comme un **service Render Free séparé** (workspace dédié, pour ne pas consommer le quota d'heures du service applicatif principal).

---

## Architecture

Un **seul conteneur Docker** fait tourner deux process côte à côte :
- **`exporter.py`** — script Python qui interroge l'API JSON propriétaire de Render (`/v1/metrics/*`) toutes les 60s, et réexpose ces valeurs au format texte Prometheus sur `localhost:9200/metrics`.
- **Grafana Alloy** (`grafana/alloy`) — scrape l'exporter local **et** `rok-app`'s `/metrics.php` en HTTPS, puis pousse tout vers Grafana Cloud en `remote_write`.

Les deux tournent dans le même conteneur (pas deux services Render séparés) pour limiter la conso du quota Free (750h/mois partagées par workspace) : un seul service à maintenir éveillé plutôt que deux.

## Pourquoi un exporter custom (et pas Prometheus natif côté Render) ?

L'API Render (`api.render.com/v1/metrics/*`) est **propriétaire, en JSON** — ce n'est pas un endpoint `/metrics` au format Prometheus. `exporter.py` fait juste l'adaptation entre les deux.

## Fichiers

| Fichier | Rôle |
|---|---|
| `Dockerfile` | Image combinée : part de `grafana/alloy`, ajoute Python + les dépendances de l'exporter. |
| `entrypoint.sh` | Lance `exporter.py` en fond, puis Alloy au premier plan (process principal du conteneur). |
| `exporter.py` | Interroge l'API Render, expose `/metrics` (port 9200) au format Prometheus. |
| `requirements.txt` | Dépendances Python (`prometheus-client`, `requests`). |
| `config.alloy` | Configuration Alloy : cibles de scrape + `remote_write` vers Grafana Cloud. |
| `render-dashboard.json` | Dashboard Grafana à importer (11 panels : infra Render + métriques applicatives rok-app). |

## Variables d'environnement requises (Render)

| Variable | Description |
|---|---|
| `RENDER_API_KEY` | Clé API Render (`rnd_...`), pour interroger `/v1/metrics/*`. |
| `RENDER_RESOURCE_IDS` | ID(s) de service Render à surveiller (`srv-...`), séparés par des virgules si plusieurs. |
| `GRAFANA_CLOUD_PROMETHEUS_USER` | User/instance ID Prometheus Grafana Cloud. |
| `GRAFANA_CLOUD_API_KEY` | Token API Grafana Cloud (utilisé comme mot de passe en Basic Auth pour le `remote_write`). |
| `ROK_APP_METRICS_TOKEN` | Token API de `rok-app` (scope `can_read`, créé depuis `tokens.php`), pour scraper `/metrics.php`. |
| `PORT` | Injectée automatiquement par Render — Alloy écoute dessus pour son endpoint santé (`/-/healthy`). |

Optionnelles côté exporter (`exporter.py`), avec défauts raisonnables : `EXPORTER_PORT` (9200), `POLL_INTERVAL_SECONDS` (60).

## Garder le service éveillé (plan Free)

Un service Free Render se met en veille après 15 min sans requête HTTP **entrante**. Or Alloy/l'exporter ne font que du trafic **sortant** (scrape + push) — sans action, le service serait mis en veille malgré lui.

Solution : un ping externe (ex. [cron-job.org](https://cron-job.org)) toutes les 10 minutes sur :
```
https://<ce-service>.onrender.com/-/healthy
```
(endpoint natif d'Alloy, toujours disponible).

## Pièges rencontrés (pour référence future)

- **`honor_labels = true` obligatoire sur le scrape de l'exporter.** Sans ça, Prometheus/Alloy écrase le label `instance` posé par l'exporter (l'ID réel du conteneur Render) avec l'adresse de la cible scrapée (`localhost:9200`) — toutes les séries se retrouvent avec la même légende, rendant les graphes illisibles.
- **`__address__` doit être un hostname nu**, sans schéma ni chemin (`rok-app.onrender.com`, pas `https://rok-app.onrender.com/`) — le schéma va dans `__scheme__`, le chemin dans `__metrics_path__`.
- **Fenêtre temporelle de l'API Render non bornée = pollution de séries.** Sans `startTime`/`endTime` explicites, l'API renvoie un historique large contenant une série par instance de conteneur ayant existé sur cette période (redeploys, cycles spin-down/wake). L'exporter réémettant tout à chaque poll, ces instances mortes restent visibles indéfiniment. Fix : `exporter.py` borne désormais chaque requête à une fenêtre étroite (2× l'intervalle de poll), pour ne remonter que l'instance active.

## Dashboard Grafana

Importer `render-dashboard.json` dans Grafana Cloud (Dashboards → Import). Au moment de l'import, sélectionner la datasource Prometheus hébergée (Hosted Prometheus) pour le champ `Prometheus` demandé.

Panels inclus :
- Statut de l'exporter / durée de scrape Alloy (auto-monitoring)
- CPU / Mémoire / Bande passante (infra Render)
- Requêtes HTTP par route/statut, latence p95 (applicatif rok-app)
- Imports : requêtes par source & résultat, raisons d'échec, joueurs reçus vs traités

## Déploiement

1. Build & push l'image (`Dockerfile` de ce dossier) sur un service Render Free (Docker), workspace dédié.
2. Configurer les variables d'environnement ci-dessus.
3. Mettre en place le ping de keep-alive (cron-job.org).
4. Importer `render-dashboard.json` dans Grafana Cloud.
