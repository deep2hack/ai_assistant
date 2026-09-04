# ⚡ Autonomous AI Executive Assistant & Multi-Channel Communications Engine

An event-driven, production-ready AI communications engine that autonomously resolves routine customer conversations on WhatsApp and Email using LLMs, while routing complex edge cases and sensitive inquiries to a secure Telegram Human-in-the-Loop (HITL) control hub.

---

## 🚀 Key Features

* **Dual-Runtime Architecture:** Integrates high-performance asynchronous Python (**FastAPI**) for reasoning and storage with a headless **Node.js/Puppeteer** bridge for WhatsApp Web automation.
* **Zero-Latency Autonomous Replies:** Evaluates intent via high-speed LLM inference (**Groq / LLaMA-3**) and dispatches contextual replies in <3 seconds without human intervention.
* **Human-in-the-Loop (HITL) Control Hub:** Interactive Telegram bot equipped with inline action cards (`Approve & Send`, `Edit`, `Dismiss`) for sensitive, negotiation, or high-stakes inquiries.
* **Intelligent Identity Resolution:** Resolves modern WhatsApp `@lid` (Linked Identity) JIDs, public profile pushnames, and verified contact numbers dynamically.
* **Domain Knowledge Base (Grounded Execution):** Injects structured business rules, pricing tiers, and calendar booking links (`business_info.json`) to eliminate hallucinations.
* **Security & Session Gatekeeper:** Telegram control panel protected by password-based authentication with automatic timeout and inactivity locking.
* **Non-Blocking Execution:** Uses `FastAPI.BackgroundTasks` and persistent SQLite schemas to process inbound webhooks without request drops.

---

## 🏗️ System Architecture

```text
Incoming Message (WhatsApp / Email)
              │
              ▼
    [Node.js Bridge / IMAP]
              │ (Webhook POST)
              ▼
    [FastAPI Backend Server]
              │
    ┌─────────┴─────────┐
    │ (Async Ingestion) │
    ▼                   ▼
[SQLite Storage]    [Groq LLM Engine]
                        │
                        ▼
             { Intent Classifier }
             /                  \
   (Routine / High Conf.)      (Sensitive / Quote / Edge Case)
           /                              \
          ▼                                ▼
[Auto-Reply Dispatched]           [Telegram Action Card]
                                         │
                                  [Approve / Edit]
                                         │
                                         ▼
                               [Target Dispatched]