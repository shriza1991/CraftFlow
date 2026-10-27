> **Historical Ages Art design:** This document includes the original single-business example and planned capabilities. See the root README for the current configurable scope and implementation status.

# Agent Architecture — Ages Art AI Automation

## 1. Multi-Agent Vision

In later milestones (P3+), conversational workflows will be handled by a network of specialized agents orchestrated via state machines (prepared for LangGraph):

```
                                  CUSTOMER MESSAGE
                                         │
                                         ▼
                            ┌────────────────────────┐
                            │  SUPERVISOR / ROUTER   │
                            │      Orchestrator      │
                            └────────────┬───────────┘
                                         │
                 ┌───────────────────────┼───────────────────────┐
                 │                       │                       │
                 ▼                       ▼                       ▼
      ┌─────────────────────┐ ┌─────────────────────┐ ┌─────────────────────┐
      │     Sales Agent     │ │    Support Agent    │ │   Marketing Agent   │
      │ - Bathtub catalog   │ │ - Shipping status   │ │ - Content generation│
      │ - Dimension fitting │ │ - Care guides       │ │ - SEO & copy        │
      │ - Pricing & quotes  │ │ - Warranty claims   │ │ - Visual prompts    │
      └──────────┬──────────┘ └──────────┬──────────┘ └──────────┬──────────┘
                 │                       │                       │
                 └───────────────────────┼───────────────────────┘
                                         │
                                         ▼
                            ┌────────────────────────┐
                            │    EXECUTION TOOLS     │
                            │ (Typed Application Code│
                            └────────────┬───────────┘
                                         │
                  ┌──────────────────────┼──────────────────────┐
                  ▼                      ▼                      ▼
           ┌──────────────┐       ┌──────────────┐       ┌──────────────┐
           │   Postgres   │       │   CRM Sync   │       │ WhatsApp API │
           └──────────────┘       └──────────────┘       └──────────────┘
```

---

## 2. P0 Scope & Responsibilities

In Milestone P0:
- The full multi-agent routing network is **not** implemented.
- We establish the core abstract contracts:
  - `BaseAgent`: Interface providing the standard `.run(input_text, context) -> AgentResponse` method.
  - `AgentContext`: Carries `request_id`, `conversation_id`, `agent_run_id`, channel information, and state flags across steps.
  - `AgentRegistry`: Central catalog for registering and retrieving active agents dynamically.
  - `DemoAgent`: Scaffolding agent used in unit tests to verify that prompt handling, tool invocation, and LLM communication work end-to-end without external network calls.

---

## 3. Human Approval Gates (Safety by Design)

Sensitive operations will require human confirmation before execution:
1. High-value discounts (>10%)
2. Finalized sales orders & invoice generation
3. Custom stone carving specifications deviating from architectural safety limits
4. Direct publication to social media or public platforms

In P0, the `AgentResponse` contract and tool boundaries are designed so that tools can return `requires_human_approval=True`, pausing execution until human sign-off is recorded.
