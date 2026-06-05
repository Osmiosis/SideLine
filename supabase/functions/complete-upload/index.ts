import { corsHeaders, json } from "../_shared/http.ts";
import { getCaller, serviceClient } from "../_shared/auth.ts";
import { getAccessToken, getFile } from "../_shared/google.ts";

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: corsHeaders });
  try {
    const user = await getCaller(req);
    if (!user) return json({ error: "Please sign in first." }, 401);

    const { job_id, drive_file_id } = await req.json();
    if (!job_id || !drive_file_id) {
      return json({ error: "Missing job_id or drive_file_id." }, 400);
    }

    const svc = serviceClient();
    const { data: job } = await svc.from("jobs").select("*").eq("id", job_id).single();
    if (!job || job.user_id !== user.id) return json({ error: "Job not found." }, 404);
    if (job.state !== "uploading") {
      return json({ error: "This job is not in an uploading state." }, 409);
    }

    const token = await getAccessToken();
    const file = await getFile(token, drive_file_id);
    if (!file || !file.parents?.includes(job.drive_folder_id)) {
      return json({
        error: "We couldn't verify your upload. Please try uploading again.",
      }, 400);
    }

    await svc.from("jobs").update({
      state: "uploaded",
      drive_file_id,
      file_size_bytes: Number(file.size ?? 0),
      progress: 0,
      state_detail:
        "Footage received — processing starts when the studio comes online.",
    }).eq("id", job_id);

    return json({ ok: true }, 200);
  } catch (e) {
    console.error("complete-upload:", e);
    return json({ error: "Something went wrong on our side. Please try again." }, 500);
  }
});
