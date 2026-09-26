# n8n Workflow Automation Directory

This directory stores n8n workflow definitions, node templates, and export JSON files for external business automations.

## Integration Boundary

In the Ages Art architecture, n8n acts as an automation pipeline for:
- Polling external webhooks (WhatsApp Cloud API, Meta Leads, Shopify/WooCommerce, Instagram)
- Triggering background batch synchronizations
- Sending scheduled notifications and follow-ups
- Relaying customer events to the central FastAPI orchestrator via secure webhook calls (`X-Webhook-Secret`)

## Security Contract

All webhooks between n8n and the core FastAPI backend are protected by a shared secret configured via `N8N_WEBHOOK_SECRET`.
Workflows must forward the `X-Request-ID` correlation header to maintain unified observability across all multi-step automations.
