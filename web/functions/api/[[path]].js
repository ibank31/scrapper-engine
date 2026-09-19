import api from "../../../cloudflare/api.js";

export async function onRequest(context) {
  return api.fetch(context.request, context.env);
}
