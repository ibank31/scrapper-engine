import api from "../../../cloudflare/api.js";

// Keep the API wrapper in the Pages build graph when cloudflare/api.js changes.
export async function onRequest(context) {
  return api.fetch(context.request, context.env);
}
