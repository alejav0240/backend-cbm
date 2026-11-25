# GraphQL load tests

The Locust scenario is intentionally outside Django's unit-test discovery.

```bash
locust -f qa/load/locustfile.py --host https://api.example.test
```

Use a staging environment and add an authenticated session/header in a private
load-test extension before exercising protected queries. Never place production
credentials in this file or in shell history.

## k6 smoke test

The repository workflow runs `qa/load/k6-smoke.js` against the configured
staging URL. It exercises the unauthenticated health endpoint and does not
modify application data.

```bash
TARGET_URL=https://staging.example.test k6 run qa/load/k6-smoke.js
```

Configure the workflow variable after the file is merged:

```bash
gh variable set BACKEND_K6_SCRIPT \
  --repo alejav0240/backend-cbm \
  --body 'qa/load/k6-smoke.js'
```
