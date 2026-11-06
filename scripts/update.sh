#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

docker compose config --quiet
# Use SQLite's online backup API: copying an open database file is not sufficient.
if docker compose ps --status running --services | grep -qx elektrik; then
  docker compose exec -T elektrik python - <<'PY'
import os
import sqlite3
from datetime import datetime
os.makedirs('/app/data/backups', exist_ok=True)
name = '/app/data/backups/bills-' + datetime.now().strftime('%Y%m%d-%H%M%S-%f') + '.db'
source = sqlite3.connect('/app/data/bills.db')
target = sqlite3.connect(name)
try:
    source.backup(target)
finally:
    target.close()
    source.close()
print('Veritabanı yedeği hazır: ' + name)
PY
else
  echo 'Çalışan elektrik servisi bulunamadı; mevcut kurulumun proje klasöründe çalıştırın.' >&2
  exit 1
fi

docker compose build elektrik
docker compose up -d --no-deps elektrik
docker compose exec -T elektrik python - <<'PY'
import time
import urllib.request
for attempt in range(30):
    try:
        with urllib.request.urlopen('http://127.0.0.1:5000/api/last-readings', timeout=2) as response:
            assert response.status == 200
        print('Energy Insight güncellendi; API sağlık kontrolü başarılı.')
        break
    except Exception:
        if attempt == 29:
            raise
        time.sleep(1)
PY
