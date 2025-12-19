# Technology Stack

## Core Architecture
- **Architecture Pattern:** H3ERE (Hyper3 Ethical Recursive Engine)
- **Services:** 22 modular Core Services (Graph, Infrastructure, Lifecycle, Governance, Runtime, Tool)
- **Message Buses:** 6 distinct buses (Communication, Memory, LLM, Tool, RuntimeControl, Wise)
- **Key Principles:** Zero Untyped Data (Pydantic), No Bypass Patterns, Cryptographic Audit (Ed25519)

## Backend
- **Language:** Python 3.12+ (Strict typing required)
- **Frameworks:**
    - **Pydantic:** Data validation and schema definition (Core requirement)
    - **Instructor:** Structured LLM output handling
    - **FastAPI / Starlette:** (Inferred from API structure) for REST endpoints
    - **AnyIO / AsyncIO:** Asynchronous runtime
- **Database:**
    - **Primary (Production):** PostgreSQL
    - **Local/Testing:** SQLite
    - **ORM:** SQLAlchemy (Async)
- **Graph Memory:** Custom graph implementation with Ed25519 signing

## AI & LLM
- **Inference:** OpenAI-compatible API
- **Providers:** Together.ai (Primary), Groq (Fallback), OpenRouter (Capacity)
- **Proxy:** CIRIS Proxy with Zero Data Retention (ZDR)
- **Local Inference:** Supported (BYOK)

## Frontend (Scout GUI)
- **Framework:** Next.js (React)
- **Deployment:** Static Export
- **Communication:** Server-Sent Events (SSE) for real-time reasoning visualization

## Mobile
- **Platform:** Android (via WebView/PWA wrapper or native integration as per folder structure)

## Infrastructure & DevOps
- **Containerization:** Docker, Docker Compose
- **Testing:** Pytest
- **Linting/Formatting:** Ruff, MyPy (Strict), Vulture (Dead code detection)

## Integrations
- **Protocols:** MCP (Model Context Protocol) Client & Server
- **External Services:** Reddit API, Home Assistant, Weather APIs
- **SQL Connectivity:** Runtime connectors for SQLite, PostgreSQL, MySQL (GDPR compliant)
