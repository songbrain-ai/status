# Songbrain status

Uptime history for the [Songbrain API](https://www.songbrain.ai/api-access), checked every 5 minutes from GitHub Actions, outside our own infrastructure.

**Live page: https://www.songbrain.ai/status** · Live JSON: https://api.songbrain.ai/v1/status

| Component | Checked via |
|---|---|
| API | `GET https://api.songbrain.ai/v1/status` answers 200 |
| Analysis pipeline | `components.pipeline` from that response (all analysis workers polling) |
| Webhooks | `components.webhooks` (the delivery loop ran in the last 2 minutes) |
| Website & docs | `GET https://www.songbrain.ai/api-access` |
| Developer console | `GET https://app.songbrain.ai/login` |

- `history/YYYY-MM.json`: per day and component, the number of checks that were operational, degraded or down.
- `summary.json`: the last 90 days per component plus incidents (two failed checks in a row open an incident; the next good check closes it).
- `monitor.py`: the checker. Standard library only.

GitHub runs scheduled jobs on a best-effort basis, so some 5-minute slots are skipped under load; uptime is computed over the checks that ran.

Questions or an outage we missed: support@songbrain.ai
