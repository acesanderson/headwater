# Headwater OTel Infrastructure — NOC Setup Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deploy Alloy agents on caruana and alphablue, stand up Prometheus + Loki + Grafana on Lasker (176.16.0.11), and configure a Sway kiosk on Lasker displaying Grafana on two monitors.

**Architecture:** Pull-based metrics — Alloy scrapes each service's `/metrics` endpoint and remote_writes to Prometheus on Lasker. Logs flow via Alloy reading systemd journal and writing to Loki. Grafana reads both. Sway + Chromium provides the kiosk display. No Headwater code changes.

**Tech Stack:** Grafana Alloy (apt), Prometheus (binary), Loki (binary), Grafana (binary), Sway (apt), Chromium (apt). All on Ubuntu Server 24.04 LTS.

**Prerequisites:**
- Tasks 1–10 of `2026-04-07-headwater-otel-code.md` must be complete and deployed (services must expose `/metrics`)
- SSH access to caruana, alphablue, and lasker (176.16.0.11)
- Lasker display output connector names unknown until first Sway boot (Task 6)

---

## File Map

| Host | Path | Purpose |
|---|---|---|
| caruana | `/etc/alloy/config.alloy` | Alloy scrape + remote_write config |
| alphablue | `/etc/alloy/config.alloy` | Alloy scrape + remote_write config |
| lasker | `/usr/local/bin/prometheus` | Prometheus binary |
| lasker | `/etc/prometheus/prometheus.yml` | Prometheus config (remote_write receiver) |
| lasker | `/etc/systemd/system/prometheus.service` | Prometheus systemd unit |
| lasker | `/usr/local/bin/loki` | Loki binary |
| lasker | `/etc/loki/config.yaml` | Loki config |
| lasker | `/etc/systemd/system/loki.service` | Loki systemd unit |
| lasker | `/etc/grafana/grafana.ini` | Grafana config (default, storage path override) |
| lasker | `/etc/systemd/system/grafana-server.service` | Grafana systemd unit |
| lasker | `~kiosk/.config/sway/config` | Sway kiosk config (fill in output names in Task 6) |
| lasker | `/etc/systemd/system/getty@tty1.service.d/override.conf` | getty autologin for kiosk user |

---

### Task 1: Install and configure Alloy on caruana *(AC-8 partial)*

All commands run on **caruana** via SSH.

- [ ] **Step 1: Add Grafana apt repo and install Alloy**

```bash
ssh caruana
sudo apt-get install -y apt-transport-https software-properties-common wget
sudo mkdir -p /etc/apt/keyrings/
wget -q -O - https://apt.grafana.com/gpg.key | gpg --dearmor | sudo tee /etc/apt/keyrings/grafana.gpg > /dev/null
echo "deb [signed-by=/etc/apt/keyrings/grafana.gpg] https://apt.grafana.com stable main" | sudo tee /etc/apt/sources.list.d/grafana.list
sudo apt-get update
sudo apt-get install -y grafana-alloy
```

Expected: `alloy --version` prints a version string.

- [ ] **Step 2: Write Alloy config**

```bash
sudo tee /etc/alloy/config.alloy > /dev/null << 'EOF'
prometheus.scrape "headwater" {
  targets = [
    {"__address__" = "localhost:8080", "job" = "bywater"},
    {"__address__" = "localhost:8081", "job" = "headwaterrouter"},
  ]
  scrape_interval = "15s"
  forward_to      = [prometheus.remote_write.lasker.receiver]
}

prometheus.remote_write "lasker" {
  endpoint {
    url = "http://176.16.0.11:9090/api/v1/write"
  }
}

loki.source.journal "system" {
  forward_to    = [loki.write.lasker.receiver]
  relabel_rules = loki.relabel.add_host.rules
}

loki.relabel "add_host" {
  forward_to = []
  rule {
    target_label = "host"
    replacement  = "caruana"
  }
}

loki.write "lasker" {
  endpoint {
    url = "http://176.16.0.11:3100/loki/api/v1/push"
  }
}
EOF
```

- [ ] **Step 3: Enable and start Alloy**

```bash
sudo systemctl enable grafana-alloy
sudo systemctl start grafana-alloy
sudo systemctl status grafana-alloy --no-pager
```

Expected: `Active: active (running)`.

- [ ] **Step 4: Confirm Alloy is scraping (check Alloy self-metrics)**

```bash
curl -s http://localhost:12345/metrics | grep alloy_component_controller
```

Expected: lines containing `alloy_component_controller_running_components`. If port 12345 is not responding, check `journalctl -u grafana-alloy -n 50`.

- [ ] **Step 5: Commit config to repo for reference**

On your local machine:
```bash
mkdir -p headwater-server/config/alloy  # create if it doesn't exist
cat > headwater-server/config/alloy/caruana.alloy << 'ALLOYEOF'
# (copy the config from Step 2 above)
ALLOYEOF
git add headwater-server/config/alloy/caruana.alloy
git commit -m "config: add Alloy config for caruana"
```

---

### Task 2: Install and configure Alloy on alphablue *(AC-8 partial)*

All commands run on **alphablue** via SSH.

- [ ] **Step 1: Install Alloy (same as caruana)**

```bash
ssh alphablue
sudo apt-get install -y apt-transport-https software-properties-common wget
sudo mkdir -p /etc/apt/keyrings/
wget -q -O - https://apt.grafana.com/gpg.key | gpg --dearmor | sudo tee /etc/apt/keyrings/grafana.gpg > /dev/null
echo "deb [signed-by=/etc/apt/keyrings/grafana.gpg] https://apt.grafana.com stable main" | sudo tee /etc/apt/sources.list.d/grafana.list
sudo apt-get update
sudo apt-get install -y grafana-alloy
```

- [ ] **Step 2: Write Alloy config (deepwater only)**

```bash
sudo tee /etc/alloy/config.alloy > /dev/null << 'EOF'
prometheus.scrape "headwater" {
  targets = [
    {"__address__" = "localhost:8080", "job" = "deepwater"},
  ]
  scrape_interval = "15s"
  forward_to      = [prometheus.remote_write.lasker.receiver]
}

prometheus.remote_write "lasker" {
  endpoint {
    url = "http://176.16.0.11:9090/api/v1/write"
  }
}

loki.source.journal "system" {
  forward_to    = [loki.write.lasker.receiver]
  relabel_rules = loki.relabel.add_host.rules
}

loki.relabel "add_host" {
  forward_to = []
  rule {
    target_label = "host"
    replacement  = "alphablue"
  }
}

loki.write "lasker" {
  endpoint {
    url = "http://176.16.0.11:3100/loki/api/v1/push"
  }
}
EOF
```

- [ ] **Step 3: Enable and start Alloy**

```bash
sudo systemctl enable grafana-alloy
sudo systemctl start grafana-alloy
sudo systemctl status grafana-alloy --no-pager
```

Expected: `Active: active (running)`.

- [ ] **Step 4: Commit config to repo**

On your local machine:
```bash
cat > headwater-server/config/alloy/alphablue.alloy << 'ALLOYEOF'
# (copy the config from Step 2 above)
ALLOYEOF
git add headwater-server/config/alloy/alphablue.alloy
git commit -m "config: add Alloy config for alphablue"
```

---

### Task 3: Install Prometheus on Lasker *(AC-8)*

All commands run on **lasker** (176.16.0.11) via SSH.

- [ ] **Step 1: Download latest stable Prometheus binary**

```bash
ssh lasker
cd /tmp
PROM_VERSION=$(curl -s https://api.github.com/repos/prometheus/prometheus/releases/latest | grep '"tag_name"' | sed 's/.*"v\([^"]*\)".*/\1/')
wget -q "https://github.com/prometheus/prometheus/releases/download/v${PROM_VERSION}/prometheus-${PROM_VERSION}.linux-amd64.tar.gz"
tar xzf prometheus-${PROM_VERSION}.linux-amd64.tar.gz
sudo cp prometheus-${PROM_VERSION}.linux-amd64/prometheus /usr/local/bin/
sudo cp prometheus-${PROM_VERSION}.linux-amd64/promtool  /usr/local/bin/
prometheus --version
```

Expected: prints `prometheus, version X.Y.Z`.

- [ ] **Step 2: Create Prometheus user and storage directory**

```bash
sudo useradd --no-create-home --shell /bin/false prometheus
sudo mkdir -p /var/lib/prometheus /etc/prometheus
sudo chown prometheus:prometheus /var/lib/prometheus
```

- [ ] **Step 3: Write Prometheus config**

```bash
sudo tee /etc/prometheus/prometheus.yml > /dev/null << 'EOF'
global:
  scrape_interval: 15s

# No scrape_configs — Alloy owns all scraping via remote_write.
EOF
sudo chown prometheus:prometheus /etc/prometheus/prometheus.yml
```

- [ ] **Step 4: Write Prometheus systemd unit**

```bash
sudo tee /etc/systemd/system/prometheus.service > /dev/null << 'EOF'
[Unit]
Description=Prometheus
After=network.target

[Service]
User=prometheus
Group=prometheus
ExecStart=/usr/local/bin/prometheus \
  --config.file=/etc/prometheus/prometheus.yml \
  --storage.tsdb.path=/var/lib/prometheus \
  --storage.tsdb.retention.time=30d \
  --web.enable-remote-write-receiver
Restart=on-failure

[Install]
WantedBy=multi-user.target
EOF
```

- [ ] **Step 5: Enable and start Prometheus**

```bash
sudo systemctl daemon-reload
sudo systemctl enable prometheus
sudo systemctl start prometheus
sudo systemctl status prometheus --no-pager
```

Expected: `Active: active (running)`.

- [ ] **Step 6: Verify AC-8 — Alloy data flowing into Prometheus**

Wait ~30 seconds for Alloy to complete at least one scrape cycle, then:

```bash
curl -s "http://localhost:9090/api/v1/query?query=up" | python3 -m json.tool | grep '"job"'
```

Expected: three entries with `"job": "bywater"`, `"job": "headwaterrouter"`, `"job": "deepwater"`.

If empty: check Alloy logs on caruana and alphablue (`journalctl -u grafana-alloy -n 50`). The remote_write endpoint must be reachable from both hosts.

---

### Task 4: Install Loki on Lasker *(AC-9, AC-10)*

All commands run on **lasker** via SSH.

- [ ] **Step 1: Download latest stable Loki binary**

```bash
cd /tmp
LOKI_VERSION=$(curl -s https://api.github.com/repos/grafana/loki/releases/latest | grep '"tag_name"' | sed 's/.*"v\([^"]*\)".*/\1/')
wget -q "https://github.com/grafana/loki/releases/download/v${LOKI_VERSION}/loki-linux-amd64.zip"
unzip -q loki-linux-amd64.zip
sudo cp loki-linux-amd64 /usr/local/bin/loki
sudo chmod +x /usr/local/bin/loki
loki --version
```

Expected: prints `loki, version X.Y.Z`.

- [ ] **Step 2: Create Loki user and storage directory**

```bash
sudo useradd --no-create-home --shell /bin/false loki
sudo mkdir -p /var/lib/loki /etc/loki
sudo chown loki:loki /var/lib/loki
```

- [ ] **Step 3: Write Loki config**

```bash
sudo tee /etc/loki/config.yaml > /dev/null << 'EOF'
auth_enabled: false

server:
  http_listen_port: 3100

common:
  instance_addr: 127.0.0.1
  path_prefix: /var/lib/loki
  replication_factor: 1
  ring:
    kvstore:
      store: inmemory

schema_config:
  configs:
    - from: 2020-10-24
      store: tsdb
      object_store: filesystem
      schema: v13
      index:
        prefix: index_
        period: 24h
EOF
sudo chown loki:loki /etc/loki/config.yaml
```

- [ ] **Step 4: Write Loki systemd unit**

```bash
sudo tee /etc/systemd/system/loki.service > /dev/null << 'EOF'
[Unit]
Description=Loki
After=network.target

[Service]
User=loki
Group=loki
ExecStart=/usr/local/bin/loki -config.file=/etc/loki/config.yaml
Restart=on-failure

[Install]
WantedBy=multi-user.target
EOF
```

- [ ] **Step 5: Enable and start Loki**

```bash
sudo systemctl daemon-reload
sudo systemctl enable loki
sudo systemctl start loki
sudo systemctl status loki --no-pager
```

Expected: `Active: active (running)`.

- [ ] **Step 6: Verify AC-9 — caruana logs flowing into Loki**

On caruana, emit a probe log entry:
```bash
ssh caruana "logger -t headwater-test 'ac9-probe'"
```

Wait up to 60 seconds, then query Loki from lasker:
```bash
curl -sG http://localhost:3100/loki/api/v1/query \
  --data-urlencode 'query={host="caruana"}' | python3 -m json.tool | grep ac9-probe
```

Expected: the string `ac9-probe` appears in the JSON result. If nothing appears after 60s, check Alloy logs on caruana (`journalctl -u grafana-alloy -n 50`) for Loki write errors.

- [ ] **Step 7: Verify AC-10 — alphablue logs flowing into Loki**

```bash
ssh alphablue "logger -t headwater-test 'ac10-probe'"
```

Wait up to 60 seconds:
```bash
curl -sG http://localhost:3100/loki/api/v1/query \
  --data-urlencode 'query={host="alphablue"}' | python3 -m json.tool | grep ac10-probe
```

Expected: `ac10-probe` appears in the result.

---

### Task 5: Install Grafana on Lasker *(AC-11)*

All commands run on **lasker** via SSH.

- [ ] **Step 1: Download latest stable Grafana binary**

```bash
cd /tmp
GRAFANA_VERSION=$(curl -s https://api.github.com/repos/grafana/grafana/releases/latest | grep '"tag_name"' | grep -v 'beta\|rc' | head -1 | sed 's/.*"v\([^"]*\)".*/\1/')
wget -q "https://dl.grafana.com/oss/release/grafana-${GRAFANA_VERSION}.linux-amd64.tar.gz"
tar xzf grafana-${GRAFANA_VERSION}.linux-amd64.tar.gz
sudo mv grafana-${GRAFANA_VERSION} /usr/local/grafana
```

- [ ] **Step 2: Create Grafana user and storage directory**

```bash
sudo useradd --no-create-home --shell /bin/false grafana
sudo mkdir -p /var/lib/grafana /etc/grafana
sudo chown grafana:grafana /var/lib/grafana
sudo cp /usr/local/grafana/conf/defaults.ini /etc/grafana/grafana.ini
sudo chown grafana:grafana /etc/grafana/grafana.ini
```

- [ ] **Step 3: Set storage path in grafana.ini**

```bash
sudo sed -i 's|^;data = .*|data = /var/lib/grafana|' /etc/grafana/grafana.ini
sudo sed -i 's|^;logs = .*|logs = /var/log/grafana|' /etc/grafana/grafana.ini
sudo mkdir -p /var/log/grafana && sudo chown grafana:grafana /var/log/grafana
```

- [ ] **Step 4: Write Grafana systemd unit**

```bash
sudo tee /etc/systemd/system/grafana-server.service > /dev/null << 'EOF'
[Unit]
Description=Grafana
After=network.target

[Service]
User=grafana
Group=grafana
ExecStart=/usr/local/grafana/bin/grafana server \
  --config=/etc/grafana/grafana.ini \
  --homepath=/usr/local/grafana
Restart=on-failure

[Install]
WantedBy=multi-user.target
EOF
```

- [ ] **Step 5: Enable and start Grafana**

```bash
sudo systemctl daemon-reload
sudo systemctl enable grafana-server
sudo systemctl start grafana-server
sudo systemctl status grafana-server --no-pager
```

Expected: `Active: active (running)`. Grafana is accessible at `http://176.16.0.11:3000` (default admin/admin).

- [ ] **Step 6: Add Prometheus data source via API**

```bash
curl -s -X POST http://admin:admin@localhost:3000/api/datasources \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Prometheus",
    "type": "prometheus",
    "url": "http://localhost:9090",
    "access": "proxy",
    "isDefault": true
  }' | python3 -m json.tool | grep '"message"'
```

Expected: `"message": "Datasource added"`.

- [ ] **Step 7: Add Loki data source via API**

```bash
curl -s -X POST http://admin:admin@localhost:3000/api/datasources \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Loki",
    "type": "loki",
    "url": "http://localhost:3100",
    "access": "proxy"
  }' | python3 -m json.tool | grep '"message"'
```

Expected: `"message": "Datasource added"`.

- [ ] **Step 8: Verify AC-11 — both data sources show green health**

```bash
# Get datasource IDs
PROM_ID=$(curl -s http://admin:admin@localhost:3000/api/datasources/name/Prometheus | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])")
LOKI_ID=$(curl -s http://admin:admin@localhost:3000/api/datasources/name/Loki | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])")

# Health check each
curl -s http://admin:admin@localhost:3000/api/datasources/${PROM_ID}/health | python3 -m json.tool | grep '"status"'
curl -s http://admin:admin@localhost:3000/api/datasources/${LOKI_ID}/health | python3 -m json.tool | grep '"status"'
```

Expected: both print `"status": "OK"`.

- [ ] **Step 9: Build dashboards manually in Grafana UI**

Open `http://176.16.0.11:3000` in a browser. Build at minimum:

**Dashboard 1 — Headwater Metrics:**
- Panel: `headwater_gpu_memory_free_bytes` by `service_name` and `gpu_name` (time series)
- Panel: `headwater_backend_up` by `backend_name` (stat panel, thresholds: 0=red 1=green)
- Panel: `http_server_request_duration_seconds` P95 (histogram quantile)

**Dashboard 2 — Headwater Logs:**
- Panel: Loki logs query `{host=~"caruana|alphablue"}` (logs panel)

Note the dashboard UIDs from the URL bar (e.g. `http://176.16.0.11:3000/d/<UID>/...`). You will need them for Task 6 (kiosk URLs).

---

### Task 6: Install Sway kiosk on Lasker *(AC-12)*

All commands run on **lasker** via SSH unless otherwise noted. This task requires a monitor connected to Lasker.

- [ ] **Step 1: Install Sway, Chromium, and seat management**

```bash
ssh lasker
sudo apt-get update
sudo apt-get install -y sway chromium-browser seatd xdg-utils
sudo systemctl enable seatd
sudo systemctl start seatd
```

- [ ] **Step 2: Create a dedicated kiosk user**

```bash
sudo useradd -m -s /bin/bash kiosk
sudo usermod -aG video,seat kiosk
```

- [ ] **Step 3: Configure getty autologin for kiosk user on tty1**

```bash
sudo mkdir -p /etc/systemd/system/getty@tty1.service.d
sudo tee /etc/systemd/system/getty@tty1.service.d/override.conf > /dev/null << 'EOF'
[Service]
ExecStart=
ExecStart=-/sbin/agetty --autologin kiosk --noclear %I $TERM
EOF
sudo systemctl daemon-reload
sudo systemctl restart getty@tty1
```

- [ ] **Step 4: Create `.bash_profile` for kiosk user to launch Sway on tty1**

```bash
sudo tee /home/kiosk/.bash_profile > /dev/null << 'EOF'
# Launch Sway automatically on tty1 login
if [ -z "$WAYLAND_DISPLAY" ] && [ "$(tty)" = "/dev/tty1" ]; then
    exec sway
fi
EOF
sudo chown kiosk:kiosk /home/kiosk/.bash_profile
```

- [ ] **Step 5: First boot to discover output names**

Reboot Lasker:
```bash
sudo reboot
```

Wait for Sway to start (kiosk user auto-logs in and launches Sway). Then SSH back in and query output names:
```bash
ssh lasker
sudo -u kiosk swaymsg -t get_outputs 2>/dev/null || \
  SWAYSOCK=$(ls /run/user/$(id -u kiosk)/sway-ipc.*.sock 2>/dev/null | head -1) \
  swaymsg -s "$SWAYSOCK" -t get_outputs
```

Expected: JSON listing outputs like `"name": "DP-1"`, `"name": "DP-2"` (or `HDMI-A-1`, etc.). Note both output names — you need them for Step 6.

If Sway started but the above command fails, you can also check: `journalctl -b -u getty@tty1 --no-pager | tail -20`.

- [ ] **Step 6: Create Sway config with kiosk layout**

Replace `<OUTPUT-1>` and `<OUTPUT-2>` with the actual connector names from Step 5. Replace `<DASHBOARD-1-UID>` and `<DASHBOARD-2-UID>` with the UIDs from Task 5 Step 9.

```bash
sudo mkdir -p /home/kiosk/.config/sway
sudo tee /home/kiosk/.config/sway/config > /dev/null << 'EOF'
# Disable all input decorations
seat * hide_cursor 3000
default_border none
default_floating_border none

# Output configuration — fill in actual connector names
output <OUTPUT-1> pos 0 0
output <OUTPUT-2> pos 1920 0

# Launch Chromium on each output
exec chromium-browser \
  --kiosk \
  --noerrdialogs \
  --disable-restore-session-state \
  --no-first-run \
  --disable-infobars \
  "http://176.16.0.11:3000/d/<DASHBOARD-1-UID>?kiosk&orgId=1"

exec chromium-browser \
  --kiosk \
  --noerrdialogs \
  --disable-restore-session-state \
  --no-first-run \
  --disable-infobars \
  "http://176.16.0.11:3000/d/<DASHBOARD-2-UID>?kiosk&orgId=1"
EOF
sudo chown -R kiosk:kiosk /home/kiosk/.config
```

- [ ] **Step 7: Reload Sway config and verify kiosk** *(AC-12)*

```bash
sudo -u kiosk swaymsg reload 2>/dev/null || \
  SWAYSOCK=$(ls /run/user/$(id -u kiosk)/sway-ipc.*.sock | head -1) \
  swaymsg -s "$SWAYSOCK" reload
```

**Manual visual check (AC-12):** Look at the monitors connected to Lasker. Both should show Chromium fullscreen displaying Grafana dashboards.

- [ ] **Step 8: Verify AC-12 survives reboot**

```bash
sudo reboot
```

After reboot, confirm both monitors come up automatically displaying Grafana without any keyboard/mouse input. This is the AC-12 verification — it is manual and visual.

- [ ] **Step 9: Commit final config to repo**

On your local machine:
```bash
cat > headwater-server/config/sway/kiosk.config << 'SWAYEOF'
# (copy the final sway config from Step 6 with actual output names filled in)
SWAYEOF
git add headwater-server/config/sway/kiosk.config
git commit -m "config: add Sway kiosk config for Lasker dual-monitor NOC display; AC-12 verified"
```
