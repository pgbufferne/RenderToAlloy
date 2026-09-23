FROM grafana/alloy:latest

RUN apt-get update && apt-get install -y --no-install-recommends \
        python3 python3-pip \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt ./
RUN pip3 install --no-cache-dir --break-system-packages -r requirements.txt

COPY exporter.py ./
COPY config.alloy /etc/alloy/config.alloy
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Render fournit le port d'écoute via $PORT (obligatoire pour un Web Service)
ENTRYPOINT ["/entrypoint.sh"]
