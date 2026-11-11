# GraphQL load tests

The Locust scenario is intentionally outside Django's unit-test discovery.

```bash
locust -f qa/load/locustfile.py --host https://api.example.test
```

Use a staging environment and add an authenticated session/header in a private
load-test extension before exercising protected queries. Never place production
credentials in this file or in shell history.
