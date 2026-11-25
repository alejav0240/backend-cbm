import http from "k6/http";
import { check } from "k6";

let targetUrl = __ENV.TARGET_URL || "";
while (targetUrl.endsWith("/")) {
  targetUrl = targetUrl.slice(0, -1);
}

export const options = {
  vus: 2,
  duration: "15s",
  thresholds: {
    http_req_failed: ["rate<0.01"],
    http_req_duration: ["p(95)<1000"],
  },
};

export default function () {
  const response = http.get(`${targetUrl}/health/`, {
    headers: {
      "X-Request-ID": "k6-health-smoke",
    },
  });

  check(response, {
    "health endpoint responds successfully": (res) =>
      res.status >= 200 && res.status < 300,
  });
}
