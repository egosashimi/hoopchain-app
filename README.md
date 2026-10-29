# 🏀 Hoopchain

**A daily NBA connection game.** Given two NBA players, build a chain of real-world relationships connecting them — through teammates, coaches, college, draft class, or All-Star appearances.

> Shortest path wins. Daily puzzle. Shareable result. Streak tracking.

---

## Stack

| Layer | Technology |
|---|---|
| Frontend | React 18 + Vite + TypeScript |
| Styling | Tailwind CSS + Framer Motion |
| State | Zustand |
| Backend | Python 3.12 + FastAPI |
| Graph | NetworkX (in-memory BFS) |
| Database | PostgreSQL 16 |
| Cache | Redis 7 |
| ORM | SQLAlchemy 2.0 (async) |
| Deploy | GitHub Pages (frontend) + Railway (backend) |

---

## Quick Start (Local Development)

### Prerequisites

- Docker + Docker Compose
- Node.js 20+
- Python 3.12+
- [Kaggle API credentials](https://www.kaggle.com/docs/api) (for ETL data download)

### 1. Start Local Services

```bash
docker-compose up -d
# Starts PostgreSQL on :5432, Redis on :6379
```

### 2. Backend Setup

```bash
cd backend
pip install -e ".[dev]"
cp .env.example .env
# Edit .env — fill in DATABASE_URL and REDIS_URL
alembic upgrade head
uvicorn app.main:app --reload
# API running at http://localhost:8000
```

### 3. Frontend Setup

```bash
cd frontend
npm install
npm run dev
# App running at http://localhost:5173
```

The game immediately runs in **demo mode** with a mock graph of ~20 well-known players. To load full NBA data, run the ETL pipeline below.

---

## ETL Pipeline (Full NBA Data)

> ⚠️ Requires a Kaggle account. Set `KAGGLE_USERNAME` and `KAGGLE_KEY` in your environment.

```bash
cd data/etl

# 1. Download nbadb from Kaggle (~500MB)
bash 01_download_nbadb.sh

# 2. Build player/team/season tables + graph edges + NetworkX pickle (~15 min)
python 02_build_graph.py

# 3. Enrich coaches data from Basketball-Reference (~2 hours, polite rate limiting)
python 03_enrich_coaches.py

# 4. Fill college/draft gaps via Wikipedia API (~30 min)
python 04_enrich_wikipedia.py

# 5. Generate 90-day puzzle pool
python 05_generate_puzzles.py

# 6. Validate graph integrity
python 06_validate_graph.py
```

After ETL, restart the backend with `USE_MOCK_GRAPH=false` to use the real graph.

---

## Repository Structure

```
hoopchain/
├── README.md
├── HOOPCHAIN_MASTER_BLUEPRINT.md   ← source of truth for all decisions
├── docker-compose.yml
├── .github/
│   └── workflows/
│       ├── deploy-frontend.yml
│       └── deploy-backend.yml
├── frontend/                       ← React 18 + Vite
│   ├── src/
│   │   ├── components/             ← UI components
│   │   ├── store/                  ← Zustand state
│   │   ├── api/                    ← typed API client
│   │   ├── hooks/
│   │   └── types/
├── backend/                        ← FastAPI + SQLAlchemy
│   ├── app/
│   │   ├── routers/                ← API endpoints
│   │   ├── services/               ← business logic
│   │   └── models/                 ← SQLAlchemy models
│   ├── alembic/                    ← DB migrations
│   └── tests/                      ← pytest suite
└── data/
    ├── etl/                        ← data pipeline scripts
    └── seeds/                      ← curated player lists
```

---

## API Reference

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/health` | Graph status |
| `GET` | `/puzzle/today` | Today's puzzle |
| `GET` | `/puzzle/{date}` | Historical puzzle |
| `GET` | `/search/players?q=` | Player autocomplete |
| `POST` | `/validate/hop` | Validate a single connection |
| `POST` | `/validate/path` | Validate full submitted path |
| `POST` | `/game/complete` | Record game result |
| `GET` | `/game/stats/{client_id}` | User statistics |
| `GET` | `/leaderboard/today` | Today's top 10 |

---

## Connection Types

| Color | Type | Example |
|---|---|---|
| 🟢 Green | Teammate | "Both played for 2012-13 Miami Heat" |
| 🔵 Blue | College | "Both attended Duke University" |
| 🟡 Yellow | Draft Class | "Both drafted in 2003 NBA Draft" |
| 🟣 Purple | Coached By | "Both coached by Gregg Popovich" |
| 🔴 Red | All-Star | "Both selected for 2016 All-Star Game" |

---

## Deployment

- **Frontend**: GitHub Pages — `.github/workflows/deploy-pages.yml` builds `frontend/` on push to `main` (Settings → Pages → Source: GitHub Actions)
- **Backend**: Railway — add Postgres + Redis plugins, deploy from `backend/`
- Set env vars per `.env.example` in each directory

---

## License

Non-commercial use. Player names and statistics are factual public record. Hoopchain is not affiliated with the NBA or NBPA.

Data sourced from [wyattowalsh/nbadb](https://www.kaggle.com/datasets/wyattowalsh/basketball) (Kaggle).
