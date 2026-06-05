import { corsHeaders, json } from "../_shared/http.ts";
import { getCaller, isAdmin, serviceClient } from "../_shared/auth.ts";
import { deleteFile, getAccessToken } from "../_shared/google.ts";
import { sendEmail } from "../_shared/email.ts";

// reject is allowed from any state that isn't already terminal
const REJECTABLE = [
  "submitted", "approved", "quota_waiting", "uploading", "uploaded",
];
const APPROVABLE = ["submitted", "quota_waiting"];

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: corsHeaders });
  try {
    const user = await getCaller(req);
    if (!user) return json({ error: "Please sign in first." }, 401);

    const svc = serviceClient();
    if (!(await isAdmin(svc, user.id))) {
      return json({ error: "Admins only." }, 403);
    }

    const { job_id, action, reason } = await req.json();
    if (!job_id || !["approve", "reject"].includes(action)) {
      return json({ error: "Missing job_id or invalid action." }, 400);
    }

    const { data: job } = await svc.from("jobs").select("*").eq("id", job_id).single();
    if (!job) return json({ error: "Job not found." }, 404);

    const { data: target } = await svc.auth.admin.getUserById(job.user_id);
    const email = target?.user?.email;
    const jobUrl = `${Deno.env.get("SITE_ORIGIN") ?? ""}/job.html?id=${job_id}`;

    if (action === "approve") {
      if (!APPROVABLE.includes(job.state)) {
        return json({ error: `Cannot approve a job in state '${job.state}'.` }, 409);
      }
      await svc.from("jobs").update({
        state: "approved",
        state_detail: "Approved — ready for your upload.",
      }).eq("id", job_id);
      if (email) {
        await sendEmail(email, `Approved: ${job.match_name}`,
          `<p>Your match <b>${job.match_name}</b> was approved.</p>
           <p><a href="${jobUrl}">Click here to upload your footage.</a></p>`);
      }
    } else {
      if (!REJECTABLE.includes(job.state)) {
        return json({ error: `Cannot reject a job in state '${job.state}'.` }, 409);
      }
      // free any quota the job already consumed
      if (job.drive_folder_id) {
        await deleteFile(await getAccessToken(), job.drive_folder_id);
      }
      await svc.from("jobs").update({
        state: "rejected",
        reject_reason: reason ?? null,
        drive_file_id: null,
        drive_folder_id: null,
        state_detail: "This submission was not accepted.",
      }).eq("id", job_id);
      if (email) {
        await sendEmail(email, `Update on: ${job.match_name}`,
          `<p>Your submission <b>${job.match_name}</b> wasn't accepted.</p>
           ${reason ? `<p>Reason: ${reason}</p>` : ""}`);
      }
    }
    return json({ ok: true }, 200);
  } catch (e) {
    console.error("decide:", e);
    return json({ error: "Something went wrong on our side. Please try again." }, 500);
  }
});
