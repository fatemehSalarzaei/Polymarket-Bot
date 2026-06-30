# Docker Deployment

## Local Build

```bash
cp .env.production.example .env
# Fill CREDENTIAL_ENCRYPTION_KEY, JWT_SECRET_KEY, and POSTGRES_PASSWORD.
# Keep real trading disabled unless you have intentionally passed production readiness checks.
docker compose config
docker compose up --build
```

Open the app at `http://localhost:3000` and check the backend at `http://localhost:8000/api/health`.

## Server Image Deployment

```bash
cp .env.production.example .env
# Edit IMAGE_TAG, domains, public URLs, secrets, and POSTGRES_PASSWORD.
docker compose -f docker-compose.server.yml config
docker compose -f docker-compose.server.yml pull
docker compose -f docker-compose.server.yml up -d
```

## Notes

- The frontend image bundles `NEXT_PUBLIC_API_BASE_URL` and `NEXT_PUBLIC_WS_URL` at build time.
- Redis is bound to localhost on the host in both compose files.
- Real trading and redeem actions are disabled by default with dry-run settings enabled.
