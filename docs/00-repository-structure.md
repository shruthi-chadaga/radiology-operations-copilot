# Proposed Repository Structure

This structure follows feature boundaries while keeping one frontend and one backend deployable.

```text
radiology-operations-copilot/
├── AGENTS.md
├── README.md
├── Makefile
├── docker-compose.yml
├── .env.example
├── .gitignore
├── docs/
│   ├── adr/0001-local-first-modular-monolith.md
│   ├── 00-repository-structure.md
│   ├── 08-data-model.md
│   ├── 09-api-contract.md
│   ├── 10-risk-and-safety-analysis.md
│   ├── 15-implementation-plan.md
│   ├── architecture.md
│   ├── ai-governance.md
│   ├── test-strategy.md
│   ├── uat-plan.md
│   ├── demo-script.md
│   └── phase-reports/
├── frontend/
│   ├── app/
│   │   ├── (auth)/login/page.tsx
│   │   ├── (workspace)/layout.tsx
│   │   ├── (workspace)/scheduling/page.tsx
│   │   ├── (workspace)/pacs-ops/page.tsx
│   │   ├── (workspace)/exceptions/page.tsx
│   │   ├── (workspace)/audit/page.tsx
│   │   ├── (workspace)/analytics/page.tsx
│   │   └── api/health/route.ts
│   ├── components/
│   ├── features/{scheduling,pacs-ops,exceptions,audit,analytics}/
│   ├── lib/{api,auth,schemas}/
│   ├── tests/
│   ├── Dockerfile
│   └── package.json
├── backend/
│   ├── app/
│   │   ├── main.py
│   │   ├── config.py
│   │   ├── api/{dependencies,router}.py
│   │   ├── auth/
│   │   ├── scheduling/
│   │   ├── pacs_ops/
│   │   ├── exceptions/
│   │   ├── audit/
│   │   ├── analytics/
│   │   ├── rules/
│   │   ├── ai/
│   │   │   ├── provider.py
│   │   │   ├── schemas.py
│   │   │   └── prompts/
│   │   ├── integrations/{orthanc,mail}/
│   │   ├── db/{base,session,models}.py
│   │   └── workers/{celery_app,tasks}.py
│   ├── alembic/
│   ├── tests/{unit,integration,contract,safety}/
│   ├── Dockerfile
│   └── pyproject.toml
├── orthanc/{source,destination}/orthanc.json
├── synthetic-data/{referrals,schedules,dicom,incidents,expected-results}/
├── scripts/
│   ├── seed_database.py
│   ├── generate_dicom.py
│   ├── load_source_orthanc.py
│   ├── run_demo_scenario.py
│   ├── reset_demo.py
│   └── verify_environment.py
└── .github/workflows/ci.yml
```

## Conventions

- Backend modules contain `models.py`, `schemas.py`, `service.py`, and `router.py` only when needed; domain rules remain independent from FastAPI.
- Integrations depend on typed protocols so mock providers/adapters can replace network services in unit tests.
- Alembic owns schema changes; application startup never calls `create_all` outside isolated tests.
- The frontend consumes versioned API DTOs and validates responses with Zod.
- `synthetic-data/` contains conspicuously fictional identifiers and non-clinical DICOM payloads only.
- Each phase adds `docs/phase-reports/phase-N.md` with tests, changed files, decisions, and residual risks.
