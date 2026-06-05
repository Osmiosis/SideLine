// Resend wrapper. Email is best-effort: missing key or send failure must
// never fail the request (spec §8) — it logs and moves on.
export async function sendEmail(
  to: string, subject: string, html: string,
): Promise<void> {
  const key = Deno.env.get("RESEND_API_KEY");
  if (!key) {
    console.warn(`email skipped (no RESEND_API_KEY): "${subject}" -> ${to}`);
    return;
  }
  const res = await fetch("https://api.resend.com/emails", {
    method: "POST",
    headers: { Authorization: `Bearer ${key}`, "Content-Type": "application/json" },
    body: JSON.stringify({
      from: Deno.env.get("EMAIL_FROM") ?? "SportsAI <onboarding@resend.dev>",
      to: [to],
      subject,
      html,
    }),
  });
  if (!res.ok) console.error("email send failed:", res.status, await res.text());
}
