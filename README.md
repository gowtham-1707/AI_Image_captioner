# AI Image Captioner

## Overview
A production-grade monitoring stack for a **CPU-only BLIP Image Captioning** Streamlit app.
The app is fully instrumented with Prometheus metrics and visualized through a Grafana dashboard
with automated alerting via AlertManager and email notifications via Mailtrap.

---

## Project Structure

```
a5-monitoring/
├── docker-compose.yml                  ← starts all 5 services
├── README.md
│
├── app/
│   ├── app.py                          ← Streamlit app + all Prometheus metrics
│   ├── requirements.txt
│   └── Dockerfile
│
├── prometheus/
│   ├── prometheus.yml                  ← scrape config (app + node_exporter)
│   └── rules/
│       ├── recording_rules.yml         ← precomputed aggregations
│       └── alerting_rules.yml          ← all alert definitions
│
├── alertmanager/
│   ├── alertmanager.yml                ← email routing + inhibition rules
│   └── templates/
│       └── email.tmpl                  ← HTML email template
│
└── grafana/
    ├── dashboards/
    │   └── captioner.json              ← auto-provisioned dashboard
    └── provisioning/
        ├── datasources/
        │   └── datasources.yml         ← connects Grafana to Prometheus
        └── dashboards/
            └── dashboards.yml          ← tells Grafana where to find JSONs
```

---

## Quick Start

### Prerequisites
- [Docker Desktop](https://www.docker.com/products/docker-desktop/) installed and running
- At least 4 GB RAM available (BLIP model ~440 MB)

### 1. Configure Email Alerts
Edit `alertmanager/alertmanager.yml` and replace:
```yaml
smtp_auth_username: "YOUR_MAILTRAP_USERNAME"
smtp_auth_password: "YOUR_MAILTRAP_PASSWORD"
```
Also replace both `to: "your-email@example.com"` with your actual email.

> Sign up free at [mailtrap.io](https://mailtrap.io) → Email Testing → My Inbox → SMTP Settings

### 2. Start the Stack
```bash
cd a5-monitoring
docker-compose up --build
```
> First run takes ~10 minutes (downloading images + building app)

### 3. Access Services

| Service | URL | Login |
|---|---|---|
| Streamlit App | http://localhost:8501 | none |
| Prometheus | http://localhost:9090 | none |
| AlertManager | http://localhost:9093 | none |
| Grafana | http://localhost:3001 | admin / admin123 |
| Metrics Endpoint | http://localhost:8001/metrics | none |
| Node Exporter | http://localhost:9100/metrics | none |

### 4. Stop the Stack
```bash
docker-compose down
```

---

## Application Features

### Single Image Mode
1. Open http://localhost:8501
2. Select **Single Image** in the sidebar
3. Upload any JPG / PNG image
4. Click **Generate Caption**
5. View the caption and inference time

### Bulk Mode
1. Select **Bulk (ZIP)** in the sidebar
2. Create a ZIP file containing images (right-click folder → Send to → Compressed)
3. Upload the ZIP file
4. Watch the progress bar and queue depth metric in Grafana

---

## Prometheus Metrics Reference

### Counters — only go UP
| Metric | Labels | Description |
|---|---|---|
| `captioner_images_processed_total` | `mode`, `status` | All images processed |
| `captioner_requests_total` | `mode`, `session_id` | Requests with client tracking |
| `captioner_errors_total` | `mode`, `error_type` | Errors by type |
| `captioner_zip_uploads_total` | — | ZIP file uploads |

### Gauges — go UP and DOWN
| Metric | Labels | Description |
|---|---|---|
| `captioner_active_requests` | `mode` | Live request count |
| `captioner_model_memory_bytes` | — | Model RAM (~440 MB) |
| `captioner_bulk_queue_size` | — | Images pending in batch |

### Histograms — distribution across buckets
| Metric | Labels | Buckets |
|---|---|---|
| `captioner_inference_latency_seconds` | `mode` | 0.5, 1, 2, 4, 8, 15, 30s |
| `captioner_image_size_bytes` | `mode` | 10KB → 5MB |
| `captioner_caption_length_chars` | `mode` | 10 → 150 chars |

### Summaries — expose `_sum` and `_count`
| Metric | Labels | Description |
|---|---|---|
| `captioner_inference_duration_summary` | `mode` | Inference duration |
| `captioner_image_size_summary` | `mode` | Upload sizes |
| `captioner_caption_words_summary` | `mode` | Caption word count |

---

## Alert Rules

### Application Health
| Alert | Condition | Severity |
|---|---|---|
| `CaptionerAppDown` | App unreachable for 30s | critical |
| `NodeExporterDown` | node_exporter unreachable for 1m | warning |

### Error Rates
| Alert | Condition | Severity |
|---|---|---|
| `CaptionerHighErrorRate` | > 0.1 errors/s for 2m | critical |
| `CaptionerElevatedErrorRatio` | > 10% images failing for 3m | warning |
| `BulkModeError` | Any bulk error in 5m | warning |

### Resource Overuse
| Alert | Condition | Threshold Justification |
|---|---|---|
| `HighCPUUsage` | CPU > 80% for 2m | warning | BLIP saturates CPU during inference |
| `CriticalCPUUsage` | CPU > 95% for 1m | critical | System becomes unresponsive |
| `HighMemoryUsage` | RAM > 85% for 2m | warning | Model (440MB) + batch tensors |
| `CriticalMemoryUsage` | RAM > 95% for 1m | critical | OOM kill imminent |
| `DiskSpaceLow` | Disk > 90% for 5m | warning | HF cache fills disk fast |

### Latency Anomalies
| Alert | Condition | Severity |
|---|---|---|
| `InferenceLatencyHigh` | P95 > 10s for 2m |  warning |
| `InferenceLatencyCritical` | P99 > 30s for 1m |  critical |
| `InferenceLatencyAnomaly` | avg > 3× 1h baseline for 3m |  warning |
| `CaptionerIdle` | 0 images in 10m (9am–9pm) |  info |

---

## Grafana Dashboard

The dashboard has **6 sections** and **20+ panels**, following all **7 Commandments of Plotting**:

| Section | What it shows |
|---|---|
| 1. Application Health | App Up/Down, Node Exporter status, active requests, model memory, total errors |
| 2. Throughput & Errors | Images/sec by mode, error rate, error ratio |
| 3. Inference Latency | P50/P95/P99 time series, live gauge vs threshold |
| 4. System Resources | CPU vs throughput (correlated), RAM vs model size, disk, network |
| 5. Alert Events | Firing alerts table, success vs error stacked bars |
| 6. Bulk Deep Dive | Queue depth countdown, caption length distribution |

### 7 Commandments Compliance
- **Color-blind safe palette** — blue, green, red, amber (no red/green only distinctions)
- **Print-safe markers** — solid/dashed lines and bars, not dots only
- **Named axes** — every axis has a label with units
- **Explicit scale & units** — linear scale; s, bytes, percent, Bps specified
- **Legends** — table-format legend on all multi-series panels
- **Title + subtitle** — every panel has a descriptive title
- **Self-explanatory descriptions** — every panel has a description field

---

## AlertManager Silences

### Create a silence via UI (for maintenance windows)
1. Go to http://localhost:9093
2. Click **New Silence**
3. Add matcher: `alertname = CaptionerAppDown`
4. Set start and end time
5. Add comment: `Planned maintenance window`
6. Click **Create**

### Create a silence via API
```bash
curl -X POST http://localhost:9093/api/v2/silences \
  -H "Content-Type: application/json" \
  -d '{
    "matchers": [{"name": "alertname", "value": "CaptionerAppDown", "isRegex": false}],
    "startsAt": "2024-01-01T00:00:00Z",
    "endsAt":   "2024-01-01T02:00:00Z",
    "createdBy": "student",
    "comment":   "Maintenance window"
  }'
```

---

##  Testing Alerts

### Trigger CaptionerAppDown (easiest)
```bash
docker stop captioner-app
# wait ~90 seconds → check Prometheus Alerts + Mailtrap inbox
docker start captioner-app
```

### Trigger HighCPUUsage
Upload a large ZIP of 20+ images in bulk mode — CPU will spike to 80%+

### Trigger a latency anomaly
Upload a very large image (10+ megapixels) in single mode

---

## Assignment Deliverables Checklist

- [x] Streamlit app — Single + Bulk ZIP modes
- [x] Counters, Gauges, Histograms, Summaries with custom labels
- [x] node_exporter integrated into Prometheus scrape config
- [x] Recording rules — precomputed aggregations
- [x] Alerting rules — failures, resource overuse, latency anomalies
- [x] AlertManager email pipeline via Mailtrap
- [x] Inhibition rules to suppress redundant alerts
- [x] Silence configured in AlertManager UI
- [x] Grafana dashboard — 6 sections, 20+ panels, 7 commandments
- [x] docker-compose.yml — one command deployment
- [ ] Screenshot of email alert in Mailtrap inbox
- [ ] Screenshot of AlertManager silence interface
- [ ] 1-minute Grafana dashboard video at 5s refresh rate
- [ ] GitHub repo with all files

---

## AI Usage Attribution

Per assignment Code of Conduct:

- **PromQL queries** in `captioner.json` dashboard panels were generated with AI assistance.
  Each panel description documents what the query computes.
- **Alerting thresholds** were manually justified based on observed BLIP CPU inference
  benchmarks (P50 ~2s, model RAM ~440 MB, CPU saturation during bulk batches).
- **Complex PromQL** (anomaly detection rule in `alerting_rules.yml`) was AI-generated.
  Prompt used: *"alert when 5min avg latency is more than 3 times the 1 hour p50 baseline per mode"*

  ## Google drive link: https://drive.google.com/drive/folders/1l5atoA1-MDzb9KXjBScsrddgDvUYJF9G?usp=drive_link
