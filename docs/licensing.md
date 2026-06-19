# Licensing

This starter kit is released under the MIT License.

## Why MIT for the starter kit

MIT keeps adoption friction low for:

- internal forks of the agent architecture
- demos and workshops
- adapter examples around Meta Ads warehouses

## What the license does not cover

- your `.env` secrets
- your production warehouse data
- provider API usage and billing
- any proprietary knowledge base you plug in through `KNOWLEDGE_DIR`

## Suggested split for production teams

| Artifact | Suggested license / location |
|---|---|
| This starter repo | MIT (public) |
| Company-specific knowledge pages | private internal docs |
| Production credentials and cron wiring | private ops repo or secret store |
| Ingestion ETL | public [fb_audit](https://github.com/KhatkevichKirill/fb_audit) Python loaders |

If you publish adapters built on top of this starter, document which files are MIT starter code and which files contain proprietary business logic.
