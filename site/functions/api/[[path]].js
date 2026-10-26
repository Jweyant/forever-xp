// Cloudflare Pages Function for forever-xp.com/api/*. The logic lives in site/api/app.js.
import { handle } from "../../api/app.js";

export const onRequest = (context) => handle(context.request, context.env, context);
