# Hound Deploy (24/7 hosted MCP)

## Required env
- `HOUND_ADMIN_KEY` – create/list/revoke API keys via `/admin/*`.
- (optional) `HOUND_API_KEY`/`HOUND_API_KEYS` – bootstrap keys; migrated into meter DB.
- `HOUND_METER_DB=/data/hound-meter.db`, `HOUND_DB=/data/hound-selectors.db` on persistent volume.

## Docker Compose (local/VPS)
```bash
export HOUND_ADMIN_KEY=$(openssl rand -hex 24)
docker compose up -d --build
curl http://127.0.0.1:8000/health
# create client key
curl -X POST http://127.0.0.1:8000/admin/keys -H "Authorization: Bearer $HOUND_ADMIN_KEY" \
  -H 'content-type: application/json' -d '{"name":"client1","rpm":60,"daily":2000}'
```

## Fly.io (student/credits friendly)
```bash
fly launch --copy-config --no-deploy
fly volumes create hound_data --size 1
fly secrets set HOUND_ADMIN_KEY=$(openssl rand -hex 24)
fly deploy
```
HTTPS enforced by `fly.toml` (`force_https=true`). Endpoint: `https://<app>.fly.dev/mcp`.

## Railway
Connect repo, set `HOUND_ADMIN_KEY` secret, deploy (uses `railway.json` + Dockerfile). Attach volume for `/data` in Railway UI.

## Client usage
```json
{"mcpServers":{"hound-hosted":{"url":"https://YOUR-HOST/mcp","headers":{"Authorization":"Bearer hk_..."}}}}
```
`x-api-key: hk_...` also accepted.

## Production notes
- Put behind HTTPS (Fly/Railway provide TLS; on VPS use Caddy/Nginx).
- Rotate admin key; store secrets in platform secret manager.
- SQLite is fine for single instance + volume; use Postgres-backed metering for multi-instance.
- Browser automation runs Chromium in-container: budget 1GB+ RAM; set `auto_stop_machines=off` for 24/7.
- Only automate authorized targets; enforce ToS/rate limits.
