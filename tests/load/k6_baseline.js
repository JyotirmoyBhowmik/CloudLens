import http from 'k6/http';
import { check, sleep } from 'k6';

export const options = {
  vus: 10,
  duration: '5s',
  thresholds: {
    http_req_duration: ['p(95)<200'],
    http_req_failed: ['rate<0.01'],
  },
};

const BASE_URL = __ENV.TARGET_URL || 'http://127.0.0.1:8000';

export default function () {
  const resHealth = http.get(`${BASE_URL}/api/v1/health`);
  check(resHealth, {
    'health status is 200': (r) => r.status === 200,
    'health correlation_id present': (r) => r.json('correlation_id') !== undefined,
  });

  const resJwks = http.get(`${BASE_URL}/.well-known/jwks.json`);
  check(resJwks, {
    'jwks status is 200': (r) => r.status === 200,
    'jwks keys present': (r) => Array.isArray(r.json('keys')),
  });

  sleep(0.1);
}
