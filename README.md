# Customer Support Assistant

Production-oriented Streamlit support assistant built with CrewAI agents, hybrid RAG, SerpAPI fallback, local voice, optional image input/output, LangSmith AI observability, local cost logs, Google Sheets reporting, Docker deployment, and optional uptime monitoring.

The app has two UI modes:

- `production`: one clean final answer for real users.
- `buildathon`: final answer plus Direct Assistant and Web Search Assistant tabs for demo/evaluator comparison.

## Architecture Summary

| Layer | Component | Purpose | Production role |
|---|---|---|---|
| UI | Streamlit | Web app, sidebar controls, query composer, voice capture, image upload, result rendering | Primary user interface |
| Orchestration | CrewAI `Agent`, `Task`, `Crew`, `Process.sequential` | Runs the support workflow as coordinated agents | Main agent framework |
| LLM | OpenAI chat model | Agent reasoning and final answer generation | Paid via `OPENAI_API_KEY` |
| Local knowledge | `knowledge/*.txt` | Product FAQs, policy notes, assignment text, support documents | Trusted RAG corpus |
| Hybrid RAG | Qdrant + BM25 + reciprocal-rank fusion | Semantic and lexical retrieval | Primary grounding path |
| Web fallback | SerpAPI | Google search fallback when local knowledge is missing or buildathon mode is active | Paid via `SERPAPI_KEY` |
| App access | Password auth or Google OAuth | Blocks unauthenticated users before app UI/workflow loads | Optional security gate |
| Guardrails | Deterministic Python checks | Prompt-injection checks, PII/secret redaction, answer validation | Safety and privacy layer |
| Voice input | Streamlit `st.audio_input` + faster-whisper | Local speech-to-text | Optional free/open-source feature |
| Voice output | Piper/eSpeakNG/macOS `say` fallback | Local text-to-speech response playback | Optional free/open-source feature |
| Image input | Pillow + OpenAI vision | Validate, strip metadata, analyze attached images | Optional multimodal support |
| Image output | OpenAI image generation | Generate visual output only when user asks for image/diagram/mockup | Optional paid feature |
| AI observability | LangSmith | LLM traces, latency, token usage, agent steps | Optional, not infra monitoring |
| App logs | SQLite + JSONL | Source-of-truth run history and cost logs | Required local persistence |
| Reporting | Google Sheets | Business/demo dashboard for safe run summaries | Optional reporting sink |
| Infra monitoring | Docker health checks + Uptime Kuma | Uptime checks and container health | Optional VPS monitoring |
| Deployment | Docker Compose | Streamlit app, Qdrant, optional Uptime Kuma | Hostinger VPS-ready |

## Production Vs Buildathon

| Area | Production mode | Buildathon mode |
|---|---|---|
| User-facing output | One final support answer | Three tabs: Final Answer, Direct Assistant, Web Search Assistant |
| Web search behavior | Uses SerpAPI only when local RAG has no useful hit | Uses SerpAPI so the demo shows web-search comparison |
| Best audience | Real users and support teams | Assignment reviewers and demos |
| UI complexity | Minimal, answer-first | More transparent, comparison-first |
| Debug value | Sources and Trace/Debug expanders available | Direct/web comparison visible as required by the assignment |
| Recommendation | Default for deployment | Use during buildathon/demo walkthrough |

## CrewAI Design

| CrewAI element | Name | Uses tools | Responsibility |
|---|---|---|---|
| Agent | Direct Support Analyst | `rag_retrieval`, `image_analysis` | Answers from local trusted knowledge and attached image analysis |
| Agent | Web Verification Analyst | `serpapi_search` | Verifies with supplied SerpAPI results only |
| Agent | Production Support Responder | `google_sheets_reporting_status` | Synthesizes final customer-safe answer |
| Task | Direct support task | RAG + image analysis | Creates the local/direct answer |
| Task | Web verification task | SerpAPI results | Creates the web-supported answer when needed |
| Task | Final response task | Prior task context | Produces one production answer |
| Process | `Process.sequential` | All tasks run in order | Keeps workflow explainable and deterministic |

Important: Google Sheets row appending is **not** delegated to the LLM. The app writes reporting rows deterministically after each run, so logging is not skipped, duplicated, or polluted by model output. CrewAI only has a read-only status tool for reporting configuration.

## CrewAI Tools

| Tool | File | Used by | Writes data? | Purpose |
|---|---|---|---|---|
| `rag_retrieval` | `support_app/tools.py` | Direct Support Analyst | No | Exposes prefetched hybrid RAG context to CrewAI |
| `serpapi_search` | `support_app/tools.py` | Web Verification Analyst | No | Exposes SerpAPI search results to CrewAI |
| `image_analysis` | `support_app/tools.py` | Direct Support Analyst | No | Exposes sanitized image analysis to CrewAI |
| `google_sheets_reporting_status` | `support_app/tools.py` | Production Support Responder | No | Reports whether Google Sheets logging is configured |

## Code Components

| Path | Responsibility |
|---|---|
| `app.py` | Thin Streamlit entrypoint plus compatibility exports for tests |
| `support_app/ui.py` | Streamlit page chrome, sidebar, composer, voice/image widgets, result display, buildathon tabs |
| `support_app/config.py` | Environment loading, paths, runtime directories, model defaults |
| `support_app/auth.py` | Optional Streamlit password gate and Google OAuth login gate |
| `support_app/models.py` | Shared dataclasses for records, costs, sources, images, voice transcripts |
| `support_app/workflow.py` | End-to-end support flow coordinator |
| `support_app/crewai_flow.py` | CrewAI agents, tasks, crew setup, usage metrics |
| `support_app/tools.py` | CrewAI tool factories |
| `support_app/rag.py` | Hybrid RAG, Qdrant indexing, embeddings, BM25, local fallback |
| `support_app/search.py` | SerpAPI search integration |
| `support_app/guardrails.py` | Input/output validation, prompt-injection checks, PII/secret redaction |
| `support_app/compaction.py` | Context compaction and estimated token-reduction metrics |
| `support_app/costs.py` | Token, embedding, SerpAPI, and image cost estimates |
| `support_app/storage.py` | SQLite persistence, JSONL logs, transcript files |
| `support_app/retention.py` | Retention cleanup for logs, transcripts, audio, images, CrewAI memory |
| `support_app/observability.py` | LangSmith trace handoff |
| `support_app/voice.py` | Local STT/TTS helpers |
| `support_app/image_service.py` | Image validation, metadata stripping, vision analysis, image generation |
| `support_app/google_sheets.py` | Google Drive folder, Google Sheet, safe row append reporting |
| `scripts/google_oauth_bootstrap.py` | One-time OAuth refresh-token helper for client ID/client secret flow |
| `healthcheck.py` | Docker health check endpoint probe |
| `docker-compose.yml` | App, Qdrant, optional Uptime Kuma services |
| `Dockerfile` | Container image for Streamlit app |
| `requirements.txt` | Main app dependencies |
| `requirements-voice.txt` | Optional faster-whisper dependency |
| `requirements-dev.txt` | Test dependencies |
| `tests/test_guardrails.py` | Unit tests for guardrails, costs, compaction, images, Google Sheets summaries |

## Runtime Flow

| Step | What happens | Main modules |
|---|---|---|
| 1 | User enters text, records voice, and/or uploads image | `support_app/ui.py` |
| 2 | Voice is transcribed locally if enabled | `support_app/voice.py` |
| 3 | Uploaded images are validated, resized, metadata-stripped, and analyzed | `support_app/image_service.py` |
| 4 | Input guardrails validate and redact query | `support_app/guardrails.py` |
| 5 | Hybrid RAG retrieves local knowledge from Qdrant/BM25 | `support_app/rag.py` |
| 6 | SerpAPI runs when buildathon mode is active or RAG misses | `support_app/search.py` |
| 7 | Context compaction reduces prompt size and logs estimated token reduction | `support_app/compaction.py` |
| 8 | CrewAI runs Direct, Web, and Final tasks sequentially | `support_app/crewai_flow.py` |
| 9 | Output guardrails validate final answer and source conditions | `support_app/guardrails.py` |
| 10 | Optional image output is generated only when user asks for a visual | `support_app/image_service.py` |
| 11 | SQLite, JSONL, transcripts, LangSmith, and optional Google Sheets are updated | `support_app/storage.py`, `support_app/observability.py`, `support_app/google_sheets.py` |
| 12 | UI renders final answer, audio, generated image, sources, and debug trace | `support_app/ui.py` |

## Storage And Files

| Path | Stored data | Commit to Git? | Retention |
|---|---|---|---|
| `knowledge/*.txt` | Trusted support knowledge for RAG | Yes, for demo/source docs | Manual |
| `data/app.sqlite` | Structured run history | No | `RUN_RETENTION_DAYS` |
| `logs/app.jsonl` | JSONL observability and cost logs | No | `LOG_RETENTION_DAYS` |
| `logs/crewai.log` | CrewAI execution log | No | `LOG_RETENTION_DAYS` |
| `data/transcripts/*.txt` | Per-run text transcripts | No | `TRANSCRIPT_RETENTION_DAYS` |
| `answers.txt` or `data/answers.txt` | Combined answer transcript log | No | Transcript retention |
| `audio/*.wav` | Generated TTS files | No | `AUDIO_RETENTION_DAYS` |
| `data/uploads/` | Sanitized uploaded images | No | `IMAGE_UPLOAD_RETENTION_DAYS` |
| `data/generated_images/` | Generated image outputs | No | `IMAGE_OUTPUT_RETENTION_DAYS` |
| `data/crewai/` | CrewAI memory/runtime storage | No | `CREWAI_MEMORY_RETENTION_DAYS` |
| `data/qdrant/` | Qdrant vector DB storage | No | Manual |
| `data/google_sheets_state.json` | Created Google folder/sheet IDs | No | Manual |
| `data/auth_users.json` | First-admin password auth store | No | Manual |
| `secrets/google-service-account.json` | Google service account secret | Never | Manual |

## Paid And Free Components

| Component | Paid? | Notes |
|---|---|---|
| OpenAI chat model | Yes | Required for CrewAI answers |
| OpenAI embeddings | Yes | Used for semantic RAG when enabled |
| OpenAI vision/image generation | Yes | Image analysis/output uses `OPENAI_API_KEY` |
| SerpAPI | Yes | Required for Google web fallback |
| LangSmith | Optional | Free tier may be enough for demo; paid if quota exceeded |
| Hostinger VPS | Yes | Deployment target |
| Google Sheets API | Usually free within quota | Requires service account or OAuth refresh token |
| Streamlit | Free/open-source | UI framework |
| CrewAI | Free/open-source package | Agent framework |
| SQLite | Free/open-source | Local structured storage |
| Qdrant | Free/open-source | Vector DB container |
| BM25/rank-bm25 | Free/open-source | Lexical search |
| faster-whisper | Free/open-source | Local STT |
| Piper/eSpeakNG | Free/open-source | Local TTS |
| Docker/Uptime Kuma | Free/open-source | Deployment and uptime monitoring |

## Environment Variables

| Variable | Required? | Default | Purpose |
|---|---|---|---|
| `OPENAI_API_KEY` | Yes | none | LLM, embeddings, image analysis/output |
| `OPENAI_MODEL` | No | `gpt-4o-mini` | CrewAI chat model |
| `OPENAI_TEMPERATURE` | No | `0.2` | LLM temperature |
| `OPENAI_EMBEDDING_MODEL` | No | `text-embedding-3-small` | RAG embeddings |
| `SERPAPI_KEY` or `SERAPI_KEY` | For web search | none | SerpAPI Google fallback |
| `LANGSMITH_TRACING` | No | `false` | Enables LangSmith traces |
| `LANGSMITH_API_KEY` | If tracing | none | LangSmith API key |
| `ENABLE_CREWAI_MEMORY` | No | `false` | CrewAI memory toggle |
| `ENABLE_CONTEXT_COMPACTION` | No | `true` | Compact large agent context |
| `ENABLE_PII_REDACTION_FOR_LLM` | No | `true` | Redact before LLM/RAG/web/LangSmith |
| `ENABLE_APP_AUTH` | No | `false` | Enables login gate before app access |
| `APP_AUTH_METHODS` | No | `password` | Comma-separated methods: `password`, `google` |
| `APP_AUTH_USERNAME` | If password auth | `admin` | Username for password auth |
| `APP_AUTH_PASSWORD_HASH` | Recommended for password auth | none | PBKDF2 password hash |
| `APP_AUTH_PASSWORD` | Dev/simple password auth | none | Plain password fallback, not recommended for production |
| `APP_AUTH_SESSION_SECRET` | Recommended | fallback derived | Signs OAuth state |
| `APP_AUTH_ALLOWED_EMAILS` | Optional Google auth | none | Comma-separated allowed Google emails |
| `APP_AUTH_ALLOW_SIGNUP` | No | `true` | Allows first-admin setup when no password/user exists |
| `APP_AUTH_MIN_PASSWORD_LENGTH` | No | `8` | Minimum password length for first-admin setup |
| `GOOGLE_OAUTH_REDIRECT_URI` | If Google app login | none | Redirect URI for Google web-app login |
| `ENABLE_VOICE` | No | `false` | Voice input/output UI |
| `ENABLE_IMAGE_SUPPORT` | No | `true` | Image upload and analysis |
| `ENABLE_IMAGE_OUTPUT` | No | `true` | Image generation when requested |
| `ENABLE_GOOGLE_SHEETS_LOGGING` | No | `false` | Optional Google Sheets reporting |
| `ENABLE_RETENTION_POLICY` | No | `true` | Startup cleanup |

## Cost Tracking Variables

| Variable | Purpose |
|---|---|
| `OPENAI_INPUT_COST_PER_1M` | Estimated prompt/input token cost |
| `OPENAI_OUTPUT_COST_PER_1M` | Estimated completion/output token cost |
| `OPENAI_EMBEDDING_COST_PER_1M` | Estimated embedding token cost |
| `SERPAPI_COST_PER_SEARCH` | Estimated SerpAPI search cost |
| `OPENAI_IMAGE_COST_PER_IMAGE` | Estimated image-generation cost |

These are internal estimates. Final billing truth remains in OpenAI, SerpAPI, LangSmith, Google, and Hostinger dashboards.

## Guardrails And Privacy

| Control | Status | Notes |
|---|---|---|
| Prompt-injection checks | Enabled | Blocks common instruction override patterns |
| Query length checks | Enabled | Prevents oversized requests |
| Secret redaction | Enabled | Masks API-key-like strings before logs |
| PII redaction | Enabled by default | Redacts email, phone, SSN, payment card, IP patterns |
| LLM privacy redaction | Enabled by default | Redacted query is sent to RAG, SerpAPI, CrewAI, memory, LangSmith |
| Image metadata stripping | Enabled | EXIF removed before storage/analysis |
| Output validation | Enabled | Flags empty answers or missing source conditions |
| App login gate | Optional | Password or Google OAuth before the Streamlit app loads |
| Retention cleanup | Enabled by default | Deletes old runtime files by policy |
| DeepSeek guardrail | Not used | Deterministic free guardrails are used instead |

## App Authentication

Authentication is disabled by default for local demos. Enable it before exposing the Streamlit app publicly.

| Method | What user sees | Needs refresh token? | Best for |
|---|---|---|---|
| Password | Username/password form | No | Simple Hostinger/VPS deployment |
| Google OAuth | `Continue with Google` button | No | Better user access control |
| No auth | App opens directly | No | Local-only demo |

Password auth:

```bash
ENABLE_APP_AUTH=true
APP_AUTH_METHODS=password
APP_AUTH_USERNAME=admin
APP_AUTH_PASSWORD_HASH=your-generated-password-hash
APP_AUTH_SESSION_SECRET=long-random-secret
```

First-admin setup:

If `ENABLE_APP_AUTH=true` and no password/user is configured yet, the app shows a `Create admin account` form. It saves the first admin user to:

```text
data/auth_users.json
```

This file is ignored by Git and should live in the persistent Docker `data` volume. After creating the first admin, the app switches to the normal sign-in form.

To disable first-admin setup:

```bash
APP_AUTH_ALLOW_SIGNUP=false
```

Generate a password hash locally:

```bash
.venv312/bin/python -c "from support_app.auth import hash_password; print(hash_password('replace-with-your-password'))"
```

For quick local testing only, you can use:

```bash
ENABLE_APP_AUTH=true
APP_AUTH_METHODS=password
APP_AUTH_USERNAME=admin
APP_AUTH_PASSWORD=your-strong-password
```

Google login for app access:

```bash
ENABLE_APP_AUTH=true
APP_AUTH_METHODS=google
GOOGLE_CLIENT_ID=your-google-client-id
GOOGLE_CLIENT_SECRET=your-google-client-secret
GOOGLE_OAUTH_REDIRECT_URI=https://your-domain.com
APP_AUTH_ALLOWED_EMAILS=you@gmail.com,teammate@gmail.com
APP_AUTH_SESSION_SECRET=long-random-secret
```

For local Google login testing, the redirect URI is usually:

```bash
GOOGLE_OAUTH_REDIRECT_URI=http://localhost:8501
```

Add the exact redirect URI to the Google Cloud OAuth client.

Important distinction:

| Feature | Uses Google client ID/secret? | Needs refresh token? |
|---|---|---|
| Google login to the web app | Yes | No |
| Google Sheets backend logging | Yes, if using OAuth instead of service account | Yes |

## Hybrid RAG

| Feature | Implementation |
|---|---|
| Knowledge source | `knowledge/*.txt` |
| Semantic retrieval | Qdrant vector search |
| Embeddings | OpenAI `text-embedding-3-small` by default |
| Lexical retrieval | BM25 via `rank-bm25` |
| Reranking/fusion | Reciprocal-rank fusion |
| Fallback | Keyword file search if Qdrant/embeddings are unavailable |
| CrewAI exposure | `rag_retrieval` tool |

## Voice

| Feature | Implementation | Cost |
|---|---|---|
| Recording | Streamlit `st.audio_input` | Free |
| STT | `faster-whisper` local CPU | Free/open-source |
| TTS primary | Piper if configured | Free/open-source |
| TTS fallback | eSpeakNG in Docker | Free/open-source |
| macOS fallback | `say` + `afconvert` | Free local fallback |
| UI behavior | User records; transcript goes into editable text box | No manual transcribe button |

Enable voice:

```bash
ENABLE_VOICE=true
```

Install optional local voice dependency:

```bash
.venv312/bin/pip install -r requirements-voice.txt
```

## Images

| Feature | Implementation | Cost |
|---|---|---|
| Upload | Streamlit file uploader | Free |
| Supported formats | PNG, JPG, JPEG, WEBP | Free |
| Metadata stripping | Pillow | Free/open-source |
| Resize limit | `IMAGE_MAX_SIDE_PX` | Free |
| Upload cap | `IMAGE_MAX_UPLOAD_COUNT` | Free |
| Image analysis | OpenAI vision model | Paid via OpenAI |
| Image output | OpenAI image generation | Paid via OpenAI |
| CrewAI exposure | `image_analysis` tool | Included in agent workflow |

Example image config:

```bash
ENABLE_IMAGE_SUPPORT=true
ENABLE_IMAGE_OUTPUT=true
OPENAI_IMAGE_ANALYSIS_MODEL=gpt-4o-mini
OPENAI_IMAGE_GENERATION_MODEL=gpt-image-1
IMAGE_MAX_UPLOAD_MB=8
IMAGE_MAX_UPLOAD_COUNT=3
IMAGE_MAX_SIDE_PX=1600
OPENAI_IMAGE_SIZE=1024x1024
```

## Observability And Monitoring

| Need | Tool | What it answers |
|---|---|---|
| AI trace | LangSmith | Prompts, LLM calls, agent steps, latency, token usage, failures |
| App event log | `logs/app.jsonl` | Cost estimates, source usage, guardrails, mode, status |
| Structured history | SQLite | Query hashes, answers, sources, costs, status |
| Business dashboard | Google Sheets | Safe summary rows for demos/reporting |
| Container health | Docker healthcheck | Is Streamlit responding? |
| Uptime | Uptime Kuma | Is the deployed app reachable? |
| VPS metrics | Hostinger dashboard | CPU, RAM, disk, network |

LangSmith does **not** monitor CPU, RAM, disk, Docker restarts, or VPS uptime. Use Docker health checks, Hostinger metrics, and Uptime Kuma for infrastructure monitoring.

## Google Sheets Reporting

Google Sheets is optional. It is a reporting sink, not the source of truth. SQLite and JSONL remain primary.

| Auth option | Recommended for | Needs refresh token? | Notes |
|---|---|---|---|
| Service account JSON | Docker/Hostinger production | No | Recommended |
| OAuth client ID + client secret | Local user-owned sheet access | Yes | Needs one-time browser consent |
| Client ID + client secret only | Not enough | N/A | Cannot create/update Sheets unattended |

Service account setup:

```bash
ENABLE_GOOGLE_SHEETS_LOGGING=true
GOOGLE_SERVICE_ACCOUNT_JSON=/app/secrets/google-service-account.json
GOOGLE_DRIVE_FOLDER_NAME=CrewAI Support Logs
GOOGLE_SHEET_TITLE=CrewAI Support Run Logs
GOOGLE_SHEET_TAB=Run Logs
GOOGLE_SHARE_WITH_EMAIL=your-email@gmail.com
```

OAuth refresh-token setup:

```bash
export GOOGLE_CLIENT_ID=your-client-id
export GOOGLE_CLIENT_SECRET=your-client-secret
.venv312/bin/python scripts/google_oauth_bootstrap.py
```

Then add the printed value:

```bash
ENABLE_GOOGLE_SHEETS_LOGGING=true
GOOGLE_CLIENT_ID=your-client-id
GOOGLE_CLIENT_SECRET=your-client-secret
GOOGLE_REFRESH_TOKEN=your-refresh-token
GOOGLE_DRIVE_FOLDER_NAME=CrewAI Support Logs
GOOGLE_SHEET_TITLE=CrewAI Support Run Logs
GOOGLE_SHEET_TAB=Run Logs
```

Sheet rows include safe metadata only: run ID, status, model, latency, token estimates, cost estimates, RAG/web flags, image counts, source count, guardrail status, LangSmith trace ID, and query hash. They do not include raw query text, raw images, audio, full prompts, or full answers.

## Retention

| Variable | Default | Cleans |
|---|---:|---|
| `RUN_RETENTION_DAYS` | `30` | SQLite rows |
| `LOG_RETENTION_DAYS` | `30` | JSONL and CrewAI log files |
| `TRANSCRIPT_RETENTION_DAYS` | `30` | Transcript text files and answer log |
| `AUDIO_RETENTION_DAYS` | `7` | Generated audio files |
| `IMAGE_UPLOAD_RETENTION_DAYS` | `7` | Sanitized uploaded images |
| `IMAGE_OUTPUT_RETENTION_DAYS` | `14` | Generated image outputs |
| `CREWAI_MEMORY_RETENTION_DAYS` | `30` | CrewAI runtime memory files |

Enable or disable cleanup:

```bash
ENABLE_RETENTION_POLICY=true
```

## Docker Services

| Service | Image/build | Purpose | Port |
|---|---|---|---|
| `app` | Local `Dockerfile` | Streamlit + CrewAI + RAG + voice/image/reporting | `8501` |
| `qdrant` | `qdrant/qdrant:v1.12.5` | Vector database | `6333`, `6334` |
| `uptime-kuma` | `louislam/uptime-kuma:1` | Optional uptime dashboard | `3001` |

Docker volumes:

| Host path | Container path | Purpose |
|---|---|---|
| `./data` | `/app/data` | SQLite, transcripts, Qdrant storage, generated images, state |
| `./logs` | `/app/logs` | JSONL and CrewAI logs |
| `./knowledge` | `/app/knowledge` | RAG text files |
| `./audio` | `/app/audio` | Generated audio and optional Piper voices |
| `./secrets` | `/app/secrets:ro` | Google service account JSON |

## Local Run

```bash
python3.12 -m venv .venv312
.venv312/bin/pip install -r requirements.txt
.venv312/bin/streamlit run app.py
```

Open:

```text
http://localhost:8501
```

Run tests:

```bash
.venv312/bin/pip install -r requirements-dev.txt
.venv312/bin/pytest
```

## Docker Run

```bash
docker compose up --build
```

Open:

```text
http://localhost:8501
```

Optional uptime monitoring:

```bash
docker compose --profile monitoring up -d uptime-kuma
```

Open:

```text
http://localhost:3001
```

## Hostinger VPS Deployment

| Step | Action |
|---|---|
| 1 | Use Hostinger VPS, not shared hosting |
| 2 | Install Docker and Docker Compose plugin |
| 3 | Copy this repo to the VPS |
| 4 | Create `.env` with required keys and feature flags |
| 5 | Put optional Google service account JSON under `secrets/` |
| 6 | Run `docker compose up -d --build` |
| 7 | Point Uptime Kuma to `http://app:8501/_stcore/health` or the public Streamlit URL |
| 8 | Keep `data`, `logs`, `knowledge`, `audio`, and `secrets` mounted |

## Assignment Showcase Checklist

| Requirement/demo point | Where to show it |
|---|---|
| CrewAI framework | Explain `support_app/crewai_flow.py` and the three CrewAI agents |
| Three-agent buildathon output | Switch UI to `buildathon` mode and show three tabs |
| Production answer | Switch UI to `production` mode and show one final answer |
| RAG | Put `.txt` docs in `knowledge/`, ask a policy/product question, open Sources |
| SerpAPI fallback | Use buildathon mode or ask a question missing from local knowledge |
| Guardrails | Ask prompt-injection style question and show blocked status |
| Cost tracking | Open Trace/Debug and `logs/app.jsonl` |
| LangSmith | Show trace ID and LangSmith project dashboard if enabled |
| Voice | Enable `ENABLE_VOICE=true`, record audio, show transcript and audio response |
| Image input | Upload image and ask a support question about it |
| Image output | Ask for a diagram/mockup/image and show generated image |
| Google Sheets | Enable Sheets logging and show safe summary row appended |
| Docker | Run `docker compose up --build` |
| Monitoring | Show Docker health check and optional Uptime Kuma |

## Upgrade Path

| Current choice | When to upgrade | Target |
|---|---|---|
| SQLite | Multiple users or higher write traffic | Postgres |
| Local `.txt` ingestion | Larger corpus or frequent document changes | Separate indexing job |
| In-process RAG indexing | More documents/teams | Scheduled ingestion pipeline |
| JSONL logs | Centralized operations | OpenTelemetry/Loki/ELK |
| Uptime Kuma only | Larger VPS/cluster | Prometheus + Grafana + cAdvisor |
| Deterministic guardrails | Higher-risk production domain | Add policy classifier/evals pipeline |
| Manual evals | Frequent model/prompt changes | LangSmith/OpenAI eval suite |
