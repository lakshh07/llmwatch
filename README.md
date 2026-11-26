# LLMWatch

A small observability and evaluation platform for LLM apps. It records every call your app makes to an AI model, shows what it cost and how long it took, scores whether the answers are any good, and alerts you when something goes wrong.

- **SDK**: wrap your OpenAI or Anthropic client with one line; calls are logged in the background and never slow down or crash your app.
- **Cost and latency**: per-call cost from token counts, latency, time-to-first-token for streams, and error tracking.
- **Evals**: rule-based checks (empty output, invalid JSON, slow), an optional LLM-as-judge score, and 👍/👎 feedback from the dashboard.
- **Alerts**: rules like "error rate above 10% in the last hour", posted to a Slack-compatible webhook when they start firing and when they resolve.
- **Dashboard**: Streamlit app with totals, cost by model, quality scores, an event browser and alert management.

## How it works

```mermaid
flowchart LR
    app[Your app + LLMWatch SDK] -- "POST /v1/ingest (batched)" --> api[API · FastAPI]
    api -- XADD --> redis[(Redis stream)]
    redis -- XREADGROUP --> worker[Worker]
    worker -- "events, cost, scores" --> pg[(Postgres)]
    worker -. "new event ids" .-> jstream[(Judge stream)]
    jstream -.-> judge[Judge worker]
    judge -. "helpfulness score" .-> pg
    judge -.-> claude[Claude API]
    alerter[Alerter] -- "every 60s" --> pg
    alerter -- webhook --> slack[Slack / webhook]
    dashboard[Dashboard · Streamlit] -- "/v1/stats, /v1/events, /v1/alerts" --> api
    api --> pg
```

The API only puts events on a Redis stream and returns `202` straight away, so ingest stays fast even when the database is slow. The worker does the heavier work: it saves events, computes cost, and runs the evaluators. Duplicate events, for example from a replay, are ignored.

Delivery is at-least-once:

- **Crashed workers**: a message is acked only after its events are committed. If a worker dies mid-batch, another worker (or the same one after a restart) takes over its messages once they have been pending for `LLMWATCH_RECLAIM_IDLE_MS`, using `XAUTOCLAIM`.
- **Bad messages**: messages that can't be parsed, or that have been delivered more than `LLMWATCH_MAX_DELIVERIES` times, go to the `llmwatch:dead-letter` stream with a `reason`, so they don't block the queue. Inspect them with `redis-cli XRANGE llmwatch:dead-letter - +`.
- **Judge**: the LLM judge runs as its own process (`llmwatch-judge`) reading its own stream, so a slow or down LLM API never delays saving events. It skips events that already have a judge score, so a replay doesn't cost twice.

## Quick start (Docker)

You need Docker with Compose.

```bash
cp .env.example .env          # then set LLMWATCH_API_KEY to any secret string
docker compose --profile app up --build
```

| What      | Where                         |
| --------- | ----------------------------- |
| API       | http://localhost:8000/docs    |
| Dashboard | http://localhost:8501         |

`docker compose up -d` without `--profile app` starts only Postgres and Redis. Use that for local development, below.

## Send your first events

```python
from anthropic import Anthropic
from llmwatch import LLMWatch, wrap_anthropic

watch = LLMWatch(api_key="<your LLMWATCH_API_KEY>", host="http://localhost:8000")
client = wrap_anthropic(Anthropic(), watch)

client.messages.create(
    model="claude-haiku-5-5",
    max_tokens=1024,
    messages=[{"role": "user", "content": "Say hi"}],
)
```

`wrap_openai(OpenAI(), watch)` works the same way for `client.chat.completions.create`. Both support `stream=True`. Events are sent in batches every 2 seconds and flushed when your program exits.

## Local development

Requires [uv](https://docs.astral.sh/uv/) and Python 3.15.

```bash
uv sync --all-packages            # install all three packages + dev tools
cp .env.example .env              # fill in LLMWATCH_API_KEY
docker compose up -d              # Postgres + Redis
uv run llmwatch-migrate           # create / update the database tables
```

Then run each part in its own terminal:

```bash
uv run uvicorn llmwatch_server.app:create_app --factory --reload   # API on :8000
uv run llmwatch-worker                                             # stream -> Postgres
uv run llmwatch-alerter                                            # alert rules
uv run llmwatch-judge                                              # optional: LLM judge
uv run --env-file .env streamlit run dashboard/src/llmwatch_dashboard/app.py   # dashboard on :8501
```

### Checks

```bash
uv run ruff check --fix . && uv run ruff format . && uv run pyright && uv run pytest
```

The same checks run in GitHub Actions on every push and pull request, along with a build of both Docker images. A pre-commit config is included: `uvx pre-commit install`.

### Changing the database schema

Tables are managed with [Alembic](https://alembic.sqlalchemy.org/) migrations. Never use `create_all`. After you change a model in `server/src/llmwatch_server/db.py`:

```bash
uv run alembic -c server/alembic.ini revision --autogenerate -m "describe the change"
# read the generated file in server/src/llmwatch_server/migrations/versions/
uv run llmwatch-migrate
```

The worker and alerter refuse to start if the database is behind the code, and tell you to run `llmwatch-migrate`. A test (`server/tests/test_migrations.py`) fails if a model changes without a matching migration.

## Configuration

All settings are environment variables, read from `.env` in development.

| Variable                          | Default                  | Notes                                          |
| --------------------------------- | ------------------------ | ---------------------------------------------- |
| `LLMWATCH_DATABASE_URL`           | (required)               | e.g. `postgresql+psycopg://user:pass@host/db`  |
| `LLMWATCH_API_KEY`                | (required)               | Clients send it as `Authorization: Bearer ...` |
| `LLMWATCH_REDIS_URL`              | `redis://localhost:6379` |                                                |
| `LLMWATCH_ALERT_INTERVAL_SECONDS` | `60`                     | How often the alerter checks rules             |
| `LLMWATCH_RECLAIM_IDLE_MS`        | `60000`                  | Pending this long = stuck; another worker takes it over |
| `LLMWATCH_MAX_DELIVERIES`         | `5`                      | Then the message is dead-lettered              |
| `LLMWATCH_JUDGE_ENABLED`          | `false`                  | Queue new events for `llmwatch-judge` (costs money) |
| `LLMWATCH_JUDGE_MODEL`            | `claude-haiku-5-5`       |                                                |
| `LLMWATCH_ANTHROPIC_API_KEY`      | (none)                   | Needed when the judge is enabled               |

The dashboard reads `LLMWATCH_API_URL` (default `http://localhost:8000`) and `LLMWATCH_API_KEY` from the environment only, not from `.env`. That's why the command above uses `uv run --env-file .env`.

## API

All endpoints except `/health` need the API key. Interactive docs are at `/docs`.

| Method   | Path                            | What it does                                |
| -------- | ------------------------------- | ------------------------------------------- |
| `POST`   | `/v1/ingest`                    | Accept a batch of events (used by the SDK)  |
| `GET`    | `/v1/events`                    | Recent events, filter by `model` / `status` |
| `GET`    | `/v1/stats`                     | Totals, cost by model, score averages       |
| `GET`    | `/v1/events/{id}/scores`        | Scores for one event                        |
| `POST`   | `/v1/events/{id}/scores`        | Add a score (e.g. human feedback)           |
| `GET`    | `/v1/alerts`                    | Alert rules and their current state         |
| `POST`   | `/v1/alerts`                    | Create an alert rule                        |
| `DELETE` | `/v1/alerts/{id}`               | Delete an alert rule                        |

## Project layout

```
sdk/         Python SDK (pip package "llmwatch"): client + OpenAI/Anthropic wrappers
server/      API, worker, alerter, evaluators, judge, migrations (package "llmwatch_server")
dashboard/   Streamlit dashboard
Dockerfile   two targets: "server" and "dashboard"
```

## License

See [LICENSE](LICENSE).
