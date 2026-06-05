import { corsHeaders, json } from "../_shared/http.ts";
import { getCaller, serviceClient } from "../_shared/auth.ts";
import {
  driveFreeBytes, findOrCreateFolder, getAccessToken, initResumableSession,
} from "../_shared/google.ts";

const HEADROOM = 1024 ** 3; // keep 1 GB free after the upload (spec §2)
const ROOT_FOLDER = "SportsAI Submissions";

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: corsHeaders });
  try {
    const user = await getCaller(req);
    if (!user) return json({ error: "Please sign in first." }, 401);

    const { job_id, file_size, mime_type } = await req.json();
    if (!job_id || !Number.isFinite(file_size) || file_size <= 0) {
      return json({ error: "Missing job_id or file_size." }, 400);
    }

    const svc = serviceClient();
    const { data: job } = await svc.from("jobs").select("*").eq("id", job_id).single();
    if (!job || job.user_id !== user.id) return json({ error: "Job not found." }, 404);
    if (!["approved", "uploading", "quota_waiting"].includes(job.state)) {
      return json({ error: "This job is not ready for upload." }, 409);
    }

    const token = await getAccessToken();
    const free = await driveFreeBytes(token);
    if (free < file_size + HEADROOM) {
      await svc.from("jobs").update({
        state: "quota_waiting",
        state_detail:
          "Our storage is full right now — you're in line. We'll email you when it's your turn.",
      }).eq("id", job_id);
      return json({
        queued: true,
        message: "Storage is full right now — you're in line and we'll email you.",
      }, 200);
    }

    let folderId = job.drive_folder_id;
    if (!folderId) {
      const rootId = await findOrCreateFolder(token, ROOT_FOLDER, null);
      const safeName = job.match_name.replace(/[^a-zA-Z0-9 _-]/g, "").slice(0, 40);
      const folderName =
        `${job.created_at.slice(0, 10)}_${safeName}_${job_id.slice(0, 8)}`;
      folderId = await findOrCreateFolder(token, folderName, rootId);
    }

    const origin = req.headers.get("Origin") ??
      Deno.env.get("SITE_ORIGIN") ?? "http://localhost:8788";
    const sessionUri = await initResumableSession(
      token, "raw_video.mp4", folderId, file_size, mime_type ?? "video/mp4", origin,
    );

    await svc.from("jobs").update({
      state: "uploading",
      drive_folder_id: folderId,
      file_size_bytes: file_size,
      state_detail: "Uploading footage",
    }).eq("id", job_id);

    return json({ session_uri: sessionUri }, 200);
  } catch (e) {
    console.error("mint-upload:", e);
    return json({ error: "Something went wrong on our side. Please try again." }, 500);
  }
});
