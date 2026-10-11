// In-memory stand-in for an R2 bucket binding (only the calls the worker uses).
import { createHash } from "node:crypto";

export function mockBucket() {
  const store = new Map();
  return {
    store,
    async head(key) {
      const o = store.get(key);
      return o ? { key, size: o.body.byteLength, etag: o.etag, customMetadata: o.customMetadata } : null;
    },
    async get(key) {
      const o = store.get(key);
      if (!o) return null;
      return { body: new Blob([o.body]).stream(), etag: o.etag, customMetadata: o.customMetadata };
    },
    async put(key, body, opts = {}) {
      const buf = new Uint8Array(body);
      store.set(key, {
        body: buf,
        etag: createHash("md5").update(buf).digest("hex"),
        customMetadata: opts.customMetadata || {},
      });
    },
    async list({ prefix = "", cursor, limit = 1000 } = {}) {
      const keys = [...store.keys()].filter((k) => k.startsWith(prefix)).sort();
      const start = cursor ? Number(cursor) : 0;
      const page = keys.slice(start, start + limit);
      return {
        objects: page.map((key) => {
          const o = store.get(key);
          return { key, size: o.body.byteLength, etag: o.etag, customMetadata: o.customMetadata };
        }),
        truncated: start + limit < keys.length,
        cursor: String(start + limit),
      };
    },
  };
}
