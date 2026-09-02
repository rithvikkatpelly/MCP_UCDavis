# Deploying the MCP server to Google Cloud Run

One Cloud Run service (`mcp-ucdavis`) plus one Cloud SQL for PostgreSQL
instance (`mcp-db`) holding the `pgvector` knowledge‑base embeddings.

GitHub Actions (`.github/workflows/deploy.yml`) builds the image, pushes it to
Artifact Registry, and deploys on every push to `main`, authenticating with
Workload Identity Federation (no long‑lived JSON key in GitHub secrets).

The service is deployed `--allow-unauthenticated` — anyone with the URL can
call the MCP tools. There is no per‑caller auth (as chosen). If you later want
to gate access, put the service behind an API gateway or add a token check in
`server.py`.

> **Reusing the UAC database instead.** If you've already deployed the sibling
> **UAC** project, its Cloud SQL instance already has the `uc_davis_ai`
> collection built. You can skip steps 4–5's *database creation* and the seed
> step: just set this workflow's `CLOUD_SQL_CONNECTION_NAME` / `DB_*` variables
> to UAC's values and grant this service's runtime SA `roles/cloudsql.client`
> plus access to UAC's `db-app-password` secret.

---

## 0. What you'll need

- A Google account with billing enabled (new accounts get $300 / 90 days free).
  **Cloud SQL has no free tier** — the smallest instance is ~$8–10/month even
  when idle. Cloud Run scales to zero and is effectively free at low traffic.
- `gcloud` CLI (`brew install --cask google-cloud-sdk`).
- Push access to this GitHub repo.

```bash
gcloud auth login
gcloud config set project YOUR_PROJECT_ID
```

Replace `YOUR_PROJECT_ID` everywhere below.

---

## 1. Enable APIs

```bash
gcloud services enable \
  run.googleapis.com \
  artifactregistry.googleapis.com \
  secretmanager.googleapis.com \
  iamcredentials.googleapis.com \
  cloudresourcemanager.googleapis.com \
  sqladmin.googleapis.com
```

---

## 2. Artifact Registry repo

```bash
gcloud artifacts repositories create mcp-ucdavis \
  --repository-format=docker \
  --location=us-central1 \
  --description="UC Davis AI MCP server images"
```

Use the **same region** everywhere. `us-central1` is a low‑cost default.

---

## 3. Cloud SQL database

```bash
REGION=us-central1
DB_ROOT_PASSWORD=$(openssl rand -base64 24 | tr -d '/+=' | cut -c1-24)
DB_APP_PASSWORD=$(openssl rand -base64 24 | tr -d '/+=' | cut -c1-24)

gcloud sql instances create mcp-db \
  --database-version=POSTGRES_15 \
  --tier=db-f1-micro \
  --region="$REGION" \
  --storage-size=10GB \
  --storage-auto-increase \
  --root-password="$DB_ROOT_PASSWORD" \
  --no-backup

gcloud sql databases create mcp --instance=mcp-db
gcloud sql users create mcp-app --instance=mcp-db --password="$DB_APP_PASSWORD"

printf '%s' "$DB_ROOT_PASSWORD" | gcloud secrets create db-root-password --data-file=- --replication-policy=automatic
printf '%s' "$DB_APP_PASSWORD"  | gcloud secrets create db-app-password  --data-file=- --replication-policy=automatic
```

### Enable the `vector` extension

```bash
brew install libpq && export PATH="/opt/homebrew/opt/libpq/bin:$PATH"

MY_IP=$(curl -s https://api.ipify.org)
gcloud sql instances patch mcp-db --authorized-networks="${MY_IP}/32" --quiet

DB_HOST=$(gcloud sql instances describe mcp-db --format='value(ipAddresses[0].ipAddress)')
DB_ROOT_PW=$(gcloud secrets versions access latest --secret=db-root-password)

PGPASSWORD="$DB_ROOT_PW" psql "host=$DB_HOST user=postgres dbname=postgres sslmode=require" <<'SQL'
\c mcp
CREATE EXTENSION IF NOT EXISTS vector;
GRANT ALL ON SCHEMA public TO "mcp-app";
SQL

gcloud sql instances patch mcp-db --clear-authorized-networks --quiet
```

Get the connection name (differs from the IP):

```bash
gcloud sql instances describe mcp-db --format='value(connectionName)'
# -> your-project:us-central1:mcp-db
```

---

## 4. Service accounts

Deployer SA (used by GitHub Actions):

```bash
gcloud iam service-accounts create github-deployer --display-name="GitHub Actions deployer"

PROJECT_ID=$(gcloud config get-value project)
SA_EMAIL="github-deployer@${PROJECT_ID}.iam.gserviceaccount.com"

for ROLE in roles/run.admin roles/artifactregistry.writer roles/secretmanager.secretAccessor roles/iam.serviceAccountUser; do
  gcloud projects add-iam-policy-binding "$PROJECT_ID" --member="serviceAccount:${SA_EMAIL}" --role="$ROLE"
done
```

Runtime SA (the identity the container runs as — the default Compute Engine SA):

```bash
PROJECT_NUMBER=$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')
RUNTIME_SA="${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"

gcloud secrets add-iam-policy-binding db-app-password \
  --member="serviceAccount:${RUNTIME_SA}" --role="roles/secretmanager.secretAccessor"

gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:${RUNTIME_SA}" --role="roles/cloudsql.client"
```

(The seed step in the workflow also needs the **deployer** SA to read
`db-app-password` — already granted above via `secretmanager.secretAccessor`.)

---

## 5. Workload Identity Federation (keyless GitHub auth)

```bash
PROJECT_ID=$(gcloud config get-value project)
PROJECT_NUMBER=$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')
REPO="rithvikkatpelly/MCP_UCDavis"   # adjust if your repo path differs

gcloud iam workload-identity-pools create "github-pool" \
  --location="global" --display-name="GitHub Actions pool"

gcloud iam workload-identity-pools providers create-oidc "github-provider" \
  --location="global" --workload-identity-pool="github-pool" \
  --display-name="GitHub provider" \
  --attribute-mapping="google.subject=assertion.sub,attribute.repository=assertion.repository" \
  --attribute-condition="assertion.repository=='${REPO}'" \
  --issuer-uri="https://token.actions.githubusercontent.com"

gcloud iam service-accounts add-iam-policy-binding \
  "github-deployer@${PROJECT_ID}.iam.gserviceaccount.com" \
  --role="roles/iam.workloadIdentityUser" \
  --member="principalSet://iam.googleapis.com/projects/${PROJECT_NUMBER}/locations/global/workloadIdentityPools/github-pool/attribute.repository/${REPO}"

gcloud iam workload-identity-pools providers describe "github-provider" \
  --location="global" --workload-identity-pool="github-pool" --format="value(name)"
```

---

## 6. GitHub repo secrets and variables

**Settings → Secrets and variables → Actions**

**Secrets:**

| Name | Value |
|---|---|
| `WIF_PROVIDER` | the provider resource name from step 5 |
| `WIF_SERVICE_ACCOUNT` | `github-deployer@YOUR_PROJECT_ID.iam.gserviceaccount.com` |

**Variables:**

| Name | Value |
|---|---|
| `GCP_PROJECT_ID` | your project ID |
| `GCP_REGION` | `us-central1` |
| `AR_REPO` | `mcp-ucdavis` |
| `MCP_SERVICE` | `mcp-ucdavis` |
| `CLOUD_SQL_CONNECTION_NAME` | `your-project:us-central1:mcp-db` |
| `DB_USER` | `mcp-app` |
| `DB_NAME` | `mcp` |

---

## 7. Seed the vector store (one time)

The deploy sets `SEED_ON_STARTUP=false`, so seed the collection explicitly.
Either:

- **From GitHub Actions:** Actions tab → *Deploy MCP server to Cloud Run* →
  **Run workflow** → tick **seed** → Run. It connects to Cloud SQL via the Auth
  Proxy, runs `knowledge_base.build_index`, then deploys.
- **Locally:** temporarily re‑authorize your IP (step 3), then
  ```bash
  DATABASE_URL="postgresql+psycopg://mcp-app:${DB_APP_PASSWORD}@${DB_HOST}:5432/mcp" \
    uv run python -m knowledge_base.build_index
  ```

`build_index` always wipes and rebuilds the collection, so it's safe to re‑run
whenever the bundled PDFs change.

---

## 8. Deploy

Push to `main` (or run the workflow manually). The job builds the image,
deploys to Cloud Run wired to Cloud SQL, and prints the endpoint in the job
summary:

```
https://mcp-ucdavis-XXXXXXXX-uc.a.run.app/mcp
```

Verify:

```bash
URL=$(gcloud run services describe mcp-ucdavis --region=us-central1 --format='value(status.url)')
curl -s "$URL/health"      # -> {"status":"ok"}
```

---

## 9. Give it to other people

Any MCP client that speaks **Streamable HTTP** can use it — no key, no signup:

- **Claude Code:** `claude mcp add --transport http ucdavis-ai <URL>/mcp`
- **Claude Desktop / Cursor / etc.:** add an HTTP MCP server pointing at `<URL>/mcp`
- **Custom agents (Python):** `mcp.client.streamable_http.streamable_http_client("<URL>/mcp")`

---

## 10. Updating the knowledge base

Add/replace PDFs in `UC Davis AI/`, commit, push — then run the workflow with
**seed** ticked (or run `build_index` locally) to rebuild the collection. A
plain push redeploys the code but does **not** re‑ingest.

---

## 11. Cost control and teardown

- Cloud Run: `--min-instances=0`, scales to zero, ~free at low traffic. Cold
  start is ~10–20s (model cache is baked into the image).
- Cloud SQL `db-f1-micro`: **~$8–10/month, always on.** The only piece that
  costs money while idle.
- DuckDuckGo search is free but unofficial — it can rate‑limit under load.

```bash
gcloud run services delete mcp-ucdavis --region=us-central1 --quiet
gcloud sql instances delete mcp-db --quiet
gcloud artifacts repositories delete mcp-ucdavis --location=us-central1 --quiet
gcloud secrets delete db-app-password db-root-password --quiet
```

---

## Troubleshooting

- **`/health` OK but `search_uc_davis_ai_docs` returns `[]`** — the collection
  isn't seeded. Run step 7.
- **500 / DB connection error in logs** — runtime SA missing
  `roles/cloudsql.client`, or `--add-cloudsql-instances` not passed.
  `gcloud run services logs read mcp-ucdavis --region=us-central1`.
- **"Container failed to start and listen on PORT"** — check logs for the real
  startup error (often a DB failure during model/cache warmup).
- **Revision fails health check after a long time** — if you left
  `SEED_ON_STARTUP=true`, first‑boot ingestion can exceed the startup timeout;
  set it `false` and seed via step 7.
- **Web search intermittently returns an `error` row** — DuckDuckGo rate‑limit;
  retry, or lower call volume.
