// Local HTTP server running the worker against an in-memory bucket, for end-to-end tests.
// Usage: ADMIN_TOKEN=dev node test/devserver.js 8787
import http from "node:http";
import worker from "../src/index.js";
import { mockBucket } from "./mock-r2.js";

const env = { LOGS: mockBucket(), ADMIN_TOKEN: process.env.ADMIN_TOKEN || "dev" };
const port = Number(process.argv[2] || 8787);

http
  .createServer(async (req, res) => {
    const chunks = [];
    for await (const c of req) chunks.push(c);
    const body = chunks.length ? Buffer.concat(chunks) : undefined;
    const request = new Request(`http://localhost:${port}${req.url}`, {
      method: req.method,
      headers: req.headers,
      body: req.method === "GET" || req.method === "HEAD" ? undefined : body,
    });
    const response = await worker.fetch(request, env);
    res.writeHead(response.status, Object.fromEntries(response.headers));
    res.end(Buffer.from(await response.arrayBuffer()));
    console.log(req.method, req.url, response.status);
  })
  .listen(port, () => console.log(`dev server on ${port}`));
