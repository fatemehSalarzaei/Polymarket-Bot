#!/bin/sh
set -eu

node <<'NODE'
const fs = require('fs');
const path = require('path');

const publicDir = '/app/public';
const outputFile = path.join(publicDir, 'runtime-env.js');

const config = {
  NEXT_PUBLIC_API_BASE_URL: process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8000/api',
  NEXT_PUBLIC_WS_URL: process.env.NEXT_PUBLIC_WS_URL || 'ws://localhost:8000/ws/dashboard',
};

fs.mkdirSync(publicDir, { recursive: true });
fs.writeFileSync(
  outputFile,
  `window.__POLYMARKET_BOT_CONFIG__ = ${JSON.stringify(config)};
`,
  'utf8'
);
NODE

exec "$@"
