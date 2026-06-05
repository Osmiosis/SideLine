import { corsHeaders, json } from "../_shared/http.ts";
import { getCaller, isAdmin, serviceClient } from "../_shared/auth.ts";
import { getAccessToken } from "../_shared/google.ts";

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: corsHeaders });
  try {
    const user = await getCaller(req);
    if (!user) return json({ error: "Please sign in first." }, 401);
    const svc = serviceClient();
    if (!(await isAdmin(svc, user.id))) return json({ error: "Admins only." }, 403);

    const token = await getAccessToken();
    const res = await fetch(
      "https://www.googleapis.com/drive/v3/about?fields=storageQuota",
      { headers: { Authorization: `Bearer ${token}` } },
    );
    const { storageQuota } = await res.json();
    const limit = Number(storageQuota.limit ?? 0);
    const usage = Number(storageQuota.usage ?? 0);
    return json({
      limit_bytes: limit,
      usage_bytes: usage,
      free_bytes: limit ? limit - usage : Number.MAX_SAFE_INTEGER,
    }, 200);
  } catch (e) {
    console.error("quota:", e);
    return json({ error: "Something went wrong on our side." }, 500);
  }
});
