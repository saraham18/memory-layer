# Memory Layer

**Universal memory for AI agents. Any model. Any provider. Your keys.**

## The Problem

Every time you start a new conversation with an AI agent, it forgets everything. Your projects, your preferences, the decisions you made yesterday, the people you told it about — gone. Some tools offer memory, but they lock you into one provider, store your data on their servers, or give you a shallow key-value store that can't represent how information actually connects.

## What Memory Layer Does

Memory Layer gives any AI agent a persistent, structured memory that works across sessions, across providers, and across tools — without sending your data to a third party.

When you share information with your agent, Memory Layer doesn't just save the text. It **understands** it:

```
You say: "Alice is a senior engineer at Acme Corp. She's mentoring Bob,
          who just joined from Stanford. They're working on the search rewrite."

Memory Layer extracts:
  Entities:      Alice (Person), Bob (Person), Acme Corp (Org), Stanford (Org)
  Relationships: Alice --[WORKS_AT]--> Acme Corp
                 Alice --[MENTORS]--> Bob
                 Bob --[GRADUATED_FROM]--> Stanford
                 Alice --[INVOLVES]--> Search Rewrite
                 Bob --[INVOLVES]--> Search Rewrite
  Assertions:    "Alice is a senior engineer" (confidence: 0.95)
                 "Bob recently joined Acme Corp" (confidence: 0.90)
```

Later, when you or any agent asks "Who's working on the search rewrite?" — Memory Layer traverses the graph, pulls the relevant subgraph, and synthesizes a context-rich answer. Not keyword matching. Not vector similarity. **Graph traversal over structured knowledge.**

## Why Memory Layer

| | Memory Layer | Vector Store (RAG) | Chat History | Platform Memory (ChatGPT, etc.) |
|---|---|---|---|---|
| **Structure** | Knowledge graph — entities, relationships, confidence scores | Flat chunks with embeddings | Raw transcript | Opaque, provider-controlled |
| **Retrieval** | Multi-hop graph traversal (follows connections) | Nearest-neighbor similarity | Scroll back or keyword search | Provider decides what's relevant |
| **Cross-session** | Yes — persistent Neo4j graph | Yes (if you set it up) | No (per-conversation) | Limited, provider-dependent |
| **Cross-provider** | Yes — works with OpenAI, Anthropic, Google | Tied to embedding model | Tied to one provider | Locked to one platform |
| **Contradictions** | Detects and tracks conflicting information | Silently returns both | No awareness | No awareness |
| **Your data** | Runs locally or on your infra. You own the database. | Depends on hosting | Stored by provider | Stored by provider |
| **Bring your own keys** | Yes — encrypted at rest, never leaves your server | Varies | No | No |

## How It Works

```
┌──────────────┐     ┌──────────────────────────────────────────────┐
│  Any Agent   │     │              Memory Layer                    │
│              │     │                                              │
│  Claude      │────>│  1. INGEST                                   │
│  GPT         │     │     Text/conversation comes in               │
│  Gemini      │     │     ↓                                        │
│  Cursor      │     ���     LLM extracts entities, relationships,    │
│  Custom bot  │     │     goals, and factual assertions             │
│              │     │     ↓                                        │
│              │     │     Integrity checker deduplicates,           │
│              │     │     detects contradictions, assigns           │
│              │     │     confidence scores                         │
│              │     │     ↓                                        │
│              │     │     Commits to Neo4j knowledge graph          │
│              │     │                                              │
│              │<────│  2. QUERY                                     │
│              │     │     Natural language question comes in        │
│              │     │     ↓                                        │
│              │     │     Seed terms extracted, full-text search    │
│              │     │     finds entry points in the graph           │
│              │     │     ↓                                        │
│              │     │     Multi-hop traversal walks the graph       │
│              │     │     (configurable depth: 1–5 hops)            │
│              │     │     ↓                                        │
│              │     │     Returns synthesized context + subgraph    │
│              │     │                                              │
│              │     │  3. SLEEP (consolidation)                     │
│              │     │     Periodically prunes low-confidence nodes  │
│              │     │     and consolidates the graph                │
└──────────────┘     └──────────────────────────────────────────────┘
                                        │
                                        ▼
                              ┌──────────────────┐
                              │   Neo4j Graph DB  │
                              │  (local or cloud) │
                              └──────────────────┘
```

Memory Layer is a **REST API + MCP server**. You don't need to change your agent's code — just give it the API endpoint (or connect via MCP) and tell it to query at the start and ingest at the end of each conversation. Instructions for that are in the [Agent Skills](#agent-skills--give-this-to-your-agent) section below.

## Quick Start

```bash
git clone <repo-url>
cd Memory-Layer
pip install -e ".[dev]"
# Set up .env (see Configuration below)
make run
# Server starts at http://localhost:8000
```

## Requirements

- **Python 3.11–3.14**
- **Neo4j 5.x** (local or cloud — see Database Setup)
- At least one LLM API key: **OpenAI**, **Anthropic**, or **Google GenAI**

## Database Setup

You need a Neo4j instance. Pick one:

### Option A: Local with Docker

```bash
docker run -d \
  --name memory-neo4j \
  -p 7474:7474 -p 7687:7687 \
  -e NEO4J_AUTH=neo4j/your-password-here \
  neo4j:5
```

Then set in `.env`:
```
NEO4J_URI=bolt://localhost:7687
NEO4J_USERNAME=neo4j
NEO4J_PASSWORD=your-password-here
NEO4J_DATABASE=neo4j
```

Browse the graph visually at http://localhost:7474.

### Option B: Neo4j Desktop

Download [Neo4j Desktop](https://neo4j.com/download/), create a local database, start it, and use the same bolt URI.

### Option C: Neo4j Aura (Cloud)

1. Create a free instance at [neo4j.com/cloud/aura](https://neo4j.com/cloud/aura/)
2. Copy the connection URI, username, and password
3. Set in `.env`:
```
NEO4J_URI=neo4j+s://xxxxxxxx.databases.neo4j.io
NEO4J_USERNAME=neo4j
NEO4J_PASSWORD=your-aura-password
NEO4J_DATABASE=neo4j
```

## Configuration

Copy `.env.example` to `.env` and edit. All settings are configured via environment variables (or the `.env` file). There is no UI for configuration — everything is controlled here.

### Generate Secrets

```bash
# Generate a Fernet key (required for API key encryption)
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

# Generate a secure random secret
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

### All Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `APP_NAME` | `memory-layer` | Application identifier |
| `APP_ENV` | `development` | Set to `production` to enable the sleep consolidation scheduler |
| `DEBUG` | `false` | Enable FastAPI debug mode |
| `SECRET_KEY` | `change-me` | General application secret (use a strong random value) |
| `JWT_SECRET_KEY` | `change-me` | JWT signing key — must be at least 32 characters |
| `JWT_ALGORITHM` | `HS256` | JWT signing algorithm |
| `JWT_EXPIRY_HOURS` | `24` | How long auth tokens last before expiring |
| `FERNET_KEYS` | `[]` | JSON list of Fernet keys for encrypting stored API keys, e.g. `["key1","key2"]` |
| `NEO4J_URI` | `neo4j+s://localhost:7687` | Neo4j connection string (`bolt://` for local, `neo4j+s://` for Aura) |
| `NEO4J_USERNAME` | `neo4j` | Neo4j username |
| `NEO4J_PASSWORD` | (empty) | Neo4j password |
| `NEO4J_DATABASE` | `neo4j` | Neo4j database name |
| `RATE_LIMIT_DEFAULT` | `60/minute` | Default rate limit for API endpoints |
| `RATE_LIMIT_INGEST` | `20/minute` | Rate limit for the ingest endpoint (LLM calls are expensive) |
| `SLEEP_CRON_HOUR` | `2` | Hour (0–23) when the sleep consolidation cycle runs (production only) |
| `SLEEP_CRON_MINUTE` | `0` | Minute (0–59) when the sleep consolidation cycle runs |
| `LOG_LEVEL` | `INFO` | Logging level (DEBUG, INFO, WARNING, ERROR) |

### Sleep Consolidation Schedule

The "sleep cycle" prunes low-confidence nodes and consolidates the graph. It runs automatically **only in production** (`APP_ENV=production`) on a cron schedule.

To configure when it runs, set these in `.env`:
```
SLEEP_CRON_HOUR=2      # Run at 2 AM
SLEEP_CRON_MINUTE=0
```

You can also trigger it manually at any time via the admin API:
```bash
curl -X POST http://localhost:8000/api/v1/admin/sleep/trigger \
  -H "Authorization: Bearer <token>"
```

## Installation

```bash
# Production install
pip install -e .

# Development install (includes pytest, ruff, mypy)
pip install -e ".[dev]"

# Or use make
make dev
```

**Note on Python 3.14**: This project uses `bcrypt` directly for password hashing (not `passlib`, which is incompatible with Python 3.14).

## Running the Server

```bash
# Development (auto-reload on code changes)
make run
# or: uvicorn memory_layer.main:app --reload --host 0.0.0.0 --port 8000

# Production
uvicorn memory_layer.main:app --host 0.0.0.0 --port 8000 --workers 4
```

Server runs at `http://localhost:8000`. OpenAPI docs at `http://localhost:8000/docs`.

## Usage Guide

Everything below uses `curl`, but any HTTP client or AI agent works the same way.

### 1. Register

```bash
curl -X POST http://localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "email": "you@example.com",
    "password": "YourSecurePassword",
    "display_name": "Your Name"
  }'
```

### 2. Get a Token

```bash
curl -X POST MEMORY_LAYER_URL/api/v1/auth/token \
  -H "Content-Type: application/json" \
  -d '{
    "email": "you@example.com",
    "password": "YourSecurePassword"
  }'
```

Save the `access_token` — use it as `Authorization: Bearer <token>` on all other requests. Tokens expire after `JWT_EXPIRY_HOURS` (default 24h). Refresh with `POST /api/v1/auth/refresh`.

### 3. Store Your LLM API Key

Your API keys are encrypted at rest with Fernet. They're never exposed in API responses.

```bash
curl -X POST http://localhost:8000/api/v1/keys \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "provider": "anthropic",
    "api_key": "sk-ant-...",
    "label": "my-claude-key"
  }'
```

Supported providers: `openai`, `anthropic`, `google`.

### 4. Ingest Content

Feed text, conversations, or documents into the knowledge graph. The extraction pipeline uses your stored LLM key to identify entities, relationships, goals, and factual assertions.

```bash
curl -X POST http://localhost:8000/api/v1/ingest \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "content": "Alice is a senior engineer at Acme Corp. She leads the search team and is mentoring Bob, a new hire from Stanford.",
    "content_type": "text",
    "metadata": {"source": "meeting_notes", "date": "2026-04-21"},
    "provider": "anthropic"
  }'
```

| Field | Required | Description |
|-------|----------|-------------|
| `content` | Yes | Text to ingest (1–100,000 characters) |
| `content_type` | No | `text` (default), `conversation`, or `document` |
| `metadata` | No | Arbitrary key-value pairs to tag the ingest |
| `provider` | No | LLM provider to use (default: `openai`) |

### 5. Query the Knowledge Graph

```bash
curl -X POST http://localhost:8000/api/v1/query \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Who works at Acme Corp?",
    "max_hops": 3,
    "max_tokens": 4000,
    "provider": "anthropic"
  }'
```

Returns a `master_context` (synthesized answer from the graph), the relevant `subgraph` (nodes and edges), `seed_terms` used for retrieval, and `token_count`.

For detailed traversal info, use `/api/v1/query/explain` with the same body.

### 6. Explore the Graph

```bash
# Graph statistics
curl http://localhost:8000/api/v1/graph/stats -H "Authorization: Bearer <token>"

# Export entire graph
curl http://localhost:8000/api/v1/graph/export -H "Authorization: Bearer <token>"

# Get a specific node
curl http://localhost:8000/api/v1/graph/nodes/<node-id> -H "Authorization: Bearer <token>"

# Get edges for a node
curl http://localhost:8000/api/v1/graph/edges/<node-id> -H "Authorization: Bearer <token>"
```

## MCP Integration

Memory Layer exposes an [MCP (Model Context Protocol)](https://modelcontextprotocol.io/) server at `/mcp` for direct integration with Claude, Cursor, and other MCP-compatible agents.

### Available MCP Tools

| Tool | Description |
|------|-------------|
| `memory_ingest` | Ingest content into the knowledge graph |
| `memory_query` | Query the graph and get synthesized context |
| `memory_status` | Get graph statistics and connectivity info |

### Connecting from Claude Desktop

Add to your Claude Desktop MCP config (`claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "memory-layer": {
      "url": "http://localhost:8000/mcp"
    }
  }
}
```

Each MCP tool requires a `token` parameter (your JWT bearer token).

## Agent Skills — Give This to Your Agent

Copy the block below into your agent's instructions — `CLAUDE.md`, Cursor rules, system prompt, custom GPT instructions, or wherever your agent reads its config. Replace the placeholder values:

| Placeholder | Replace With |
|-------------|-------------|
| `MEMORY_LAYER_URL` | Your server address (e.g., `http://localhost:8000` for local, or your deployed URL) |
| `YOUR_EMAIL` | The email you registered with |
| `YOUR_PASSWORD` | Your account password |
| `anthropic` | Your LLM provider (`anthropic`, `openai`, or `google`) |

This makes your agent **memory-aware**: it recalls context at the start and saves what it learned at the end.

### The Prompt

````markdown
# Memory Layer Integration

You have access to a persistent knowledge graph via the Memory Layer API at `MEMORY_LAYER_URL`.

## Credentials
- **Server**: MEMORY_LAYER_URL
- **Email**: YOUR_EMAIL
- **Password**: YOUR_PASSWORD
- **Provider**: anthropic (or openai, google)

## On Every Conversation Start

Before responding to the user, retrieve relevant memory. First get a token, then query:

```bash
# 1. Authenticate
TOKEN=$(curl -s -X POST MEMORY_LAYER_URL/api/v1/auth/token \
  -H "Content-Type: application/json" \
  -d '{"email":"YOUR_EMAIL","password":"YOUR_PASSWORD"}' | jq -r '.access_token')

# 2. Query memory for context relevant to what the user is asking about
curl -s -X POST MEMORY_LAYER_URL/api/v1/query \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "<summarize what the user is asking about>",
    "max_hops": 3,
    "max_tokens": 4000,
    "provider": "anthropic"
  }'
```

Use the `master_context` from the response to inform your answer. If the query returns relevant context, reference it naturally — don't say "according to my memory database."

## On Every Conversation End

When the conversation is wrapping up, or when you learn something new and significant (facts, preferences, decisions, project context), save it:

```bash
curl -s -X POST MEMORY_LAYER_URL/api/v1/ingest \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "content": "<concise summary of key facts, decisions, and context from this conversation>",
    "content_type": "conversation",
    "metadata": {"source": "agent_session", "date": "YYYY-MM-DD"},
    "provider": "anthropic"
  }'
```

## What to Save
- New facts about the user, their projects, preferences, and goals
- Decisions made during the conversation
- Technical context (architecture choices, stack details, key file paths)
- People, organizations, and relationships mentioned
- Corrections to previously known information

## What NOT to Save
- Transient debugging output or error logs
- Generic knowledge you already have (e.g., "Python is a programming language")
- Verbatim conversation transcripts — summarize instead

## Checking Memory Health

If you need to verify the memory system is working:
```bash
curl -s MEMORY_LAYER_URL/ready
curl -s MEMORY_LAYER_URL/api/v1/graph/stats -H "Authorization: Bearer $TOKEN"
```
````

### For MCP-Compatible Agents (Claude Desktop, Cursor, etc.)

If your agent supports MCP, you can skip the curl commands. Add Memory Layer as an MCP server and use the built-in tools:

| Tool | When to Use |
|------|-------------|
| `memory_query(query_text, token)` | Start of conversation — retrieve relevant context |
| `memory_ingest(content, token)` | End of conversation — save new knowledge |
| `memory_status(token)` | Check that memory is connected and healthy |

### For Agents Without Shell Access

If your agent can't run curl (e.g., a custom GPT or API-only bot), make HTTP requests directly using your framework's HTTP client. The pattern is the same:

1. `POST /api/v1/auth/token` to authenticate
2. `POST /api/v1/query` at conversation start
3. `POST /api/v1/ingest` at conversation end

## API Reference

### Health
| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Liveness check |
| `GET` | `/ready` | Readiness check (verifies Neo4j connection) |

### Auth
| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/v1/auth/register` | Create account |
| `POST` | `/api/v1/auth/token` | Login, get bearer token |
| `POST` | `/api/v1/auth/refresh` | Refresh an existing token |
| `GET` | `/api/v1/auth/me` | Get current user profile |

### API Keys
| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/v1/keys` | Store an encrypted LLM key |
| `GET` | `/api/v1/keys` | List all keys (masked) |
| `GET` | `/api/v1/keys/{id}` | Get key metadata |
| `PUT` | `/api/v1/keys/{id}` | Update a key |
| `DELETE` | `/api/v1/keys/{id}` | Delete a key |
| `POST` | `/api/v1/keys/{id}/validate` | Validate a key is decryptable |

### Ingestion
| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/v1/ingest` | Ingest content |
| `GET` | `/api/v1/ingest/{id}` | Get ingest event status |
| `GET` | `/api/v1/ingest/history` | List ingest history |

### Query
| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/v1/query` | Query the knowledge graph |
| `POST` | `/api/v1/query/explain` | Query with traversal explanation |

### Graph
| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/v1/graph/stats` | Graph statistics |
| `POST` | `/api/v1/graph/nodes` | Create a node manually |
| `GET` | `/api/v1/graph/nodes/{id}` | Get a node |
| `PUT` | `/api/v1/graph/nodes/{id}` | Update a node |
| `DELETE` | `/api/v1/graph/nodes/{id}` | Delete a node |
| `POST` | `/api/v1/graph/edges` | Create an edge manually |
| `GET` | `/api/v1/graph/edges/{id}` | Get edges for a node |
| `DELETE` | `/api/v1/graph` | Delete an edge (query params: source_id, target_id, relationship) |
| `GET` | `/api/v1/graph/export` | Export entire graph |

### Admin
| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/v1/admin/sleep/trigger` | Manually trigger sleep consolidation |
| `GET` | `/api/v1/admin/sleep/status` | Get consolidation status |

## Graph Schema

### Node Types
- **Entity** — People, organizations, places, technologies, products, events
- **UserGoal** — Intentions and objectives extracted from content
- **FactualAssertion** — Claims and factual statements with confidence scores
- **Concept** — Abstract concepts and topics

### Relationship Types
`DEPENDS_ON`, `CONTRADICTS`, `SUPPORTS`, `RELATED_TO`, `HAS_GOAL`, `ASSERTS`, `DERIVED_FROM`, `PART_OF`, `SUPERSEDES`, `INVOLVES`, `REQUIRES`

## Testing

```bash
# Run all unit tests (no database needed)
make test

# Run specific test files
pytest tests/unit/ -v

# Integration/E2E tests (requires running Neo4j — set NEO4J_URI)
pytest tests/e2e/ -v

# Lint and type check
make lint

# Auto-format
make format

# Full check (lint + test)
make check
```

## Security Notes

- Passwords are hashed with bcrypt (never stored in plaintext)
- JWT tokens are signed with HS256 and expire after the configured interval
- LLM API keys are encrypted at rest with Fernet/MultiFernet (supports key rotation)
- All graph queries are scoped to the authenticated user (multi-tenant isolation)
- CORS is open by default (`*`) — restrict `allow_origins` in production
- Rate limiting is enforced per-IP on all endpoints

## License

This project is licensed under [CC BY-NC 4.0](https://creativecommons.org/licenses/by-nc/4.0/). You are free to use, share, and adapt it for non-commercial purposes with attribution.
