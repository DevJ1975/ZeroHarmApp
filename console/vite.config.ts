import type { IncomingMessage, ServerResponse } from 'node:http';

import react from '@vitejs/plugin-react';
import { defineConfig, loadEnv, type Connect, type Plugin, type ProxyOptions } from 'vite';

/**
 * The console runs on your Mac only. The browser talks to this local server at /api,
 * and this server forwards to the Zero Harm API with the console key added.
 * The key is read here, on the server side, and never sent to the browser.
 */
const PORT = 5174;
const HOST = '127.0.0.1';
const LOCAL_ORIGINS = [`http://${HOST}:${PORT}`, `http://localhost:${PORT}`];
const LOCAL_HOSTS = [`${HOST}:${PORT}`, `localhost:${PORT}`];
const LOCAL_API_HOSTS = ['127.0.0.1', 'localhost', '[::1]'];

function sendError(res: ServerResponse, status: number, error: string) {
  res.writeHead(status, { 'Content-Type': 'application/json' });
  res.end(JSON.stringify({ error }));
}

/**
 * Only the console page itself may use the proxy. Other websites open in your browser
 * could otherwise send requests to 127.0.0.1 and ride along on the key.
 * The console sends a custom header, which a foreign page can't send without a CORS check we never pass.
 */
/**
 * The key travels in the Authorization header, so the API must be https.
 * Plain http is only allowed for a backend running on this Mac.
 */
function apiUrlProblem(apiUrl: string): string {
  if (!apiUrl) return 'Set CONSOLE_API_URL in console/.env.local, then restart npm run dev.';
  let url: URL;
  try {
    url = new URL(apiUrl);
  } catch {
    return `CONSOLE_API_URL "${apiUrl}" is not a web address. Use https://, then restart npm run dev.`;
  }
  if (url.protocol === 'https:') return '';
  if (url.protocol === 'http:' && LOCAL_API_HOSTS.includes(url.hostname)) return '';
  return 'CONSOLE_API_URL must start with https:// (http:// only for a backend on this Mac), so the key is never sent in the clear.';
}

function guard(apiUrl: string, key: string): Connect.NextHandleFunction {
  const urlProblem = apiUrlProblem(apiUrl);
  return (req: IncomingMessage, res: ServerResponse, next: Connect.NextFunction) => {
    if (!req.url?.startsWith('/api')) return next();
    const origin = req.headers.origin;
    if (!LOCAL_HOSTS.includes(req.headers.host ?? '')) return sendError(res, 403, 'Open the console at http://127.0.0.1:5174.');
    if (origin && !LOCAL_ORIGINS.includes(origin)) return sendError(res, 403, 'Requests from other sites are blocked.');
    if (req.headers['x-zeroharm-console'] !== '1') return sendError(res, 403, 'Requests must come from the console page.');
    if (urlProblem) return sendError(res, 503, urlProblem);
    if (!key) return sendError(res, 503, 'Set CONSOLE_KEY in console/.env.local, then restart npm run dev.');
    next();
  };
}

function guardPlugin(apiUrl: string, key: string): Plugin {
  return {
    name: 'zero-harm-console-guard',
    configureServer(server) {
      server.middlewares.use(guard(apiUrl, key));
    },
    configurePreviewServer(server) {
      server.middlewares.use(guard(apiUrl, key));
    },
  };
}

function proxyTo(apiUrl: string, key: string): Record<string, ProxyOptions> {
  if (apiUrlProblem(apiUrl)) return {}; // no proxy at all, so the key can't leave over plain http
  return {
    '/api': {
      target: apiUrl,
      changeOrigin: true,
      secure: true,
      configure(proxy) {
        proxy.on('proxyReq', (proxyReq) => {
          proxyReq.setHeader('Authorization', `Bearer ${key}`);
          proxyReq.removeHeader('x-zeroharm-console');
          proxyReq.removeHeader('cookie');
          proxyReq.removeHeader('origin');
          proxyReq.removeHeader('referer');
        });
        proxy.on('error', (err, _req, res) => {
          if (res && 'writeHead' in res && !res.headersSent) {
            sendError(res, 502, `Can't reach the Zero Harm API at ${apiUrl} (${err.message}).`);
          }
        });
      },
    },
  };
}

export default defineConfig(({ mode }) => {
  // The empty prefix reads every variable in .env.local. None of them reach the browser,
  // because only VITE_-prefixed variables are ever exposed to client code.
  const env = loadEnv(mode, process.cwd(), '');
  const apiUrl = (env.CONSOLE_API_URL ?? '').trim().replace(/\/+$/, '');
  const key = (env.CONSOLE_KEY ?? '').trim();
  const proxy = proxyTo(apiUrl, key);

  return {
    plugins: [react(), guardPlugin(apiUrl, key)],
    envPrefix: 'VITE_',
    server: { host: HOST, port: PORT, strictPort: true, proxy },
    preview: { host: HOST, port: PORT, strictPort: true, proxy },
  };
});
