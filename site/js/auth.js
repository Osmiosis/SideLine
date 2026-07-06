// Email one-time-code sign-in helpers.
//
// This project runs on a $0 stack with no reliable transactional email, so
// sign-in codes are minted by the operator (agent/invite.py) and delivered
// out-of-band (chat, in person). The reviewer types email + code here; a typed
// code can't be consumed by link-preview/prefetch bots the way a magic link
// can. Verification is the standard email-OTP path (verifyOtp type "email"),
// which works for brand-new users too (confirmed against the live project).
//
// The client is passed in so this logic is unit-testable without a network.

/** Email + password sign-in — used by the shared reviewer/demo account. On
 *  success the client stores the session. */
export async function signIn(sb, email, password) {
  const addr = String(email ?? "").trim().toLowerCase();
  const { error } = await sb.auth.signInWithPassword({ email: addr, password: String(password ?? "") });
  if (error) {
    return { ok: false, message: "Wrong email or password — please try again." };
  }
  return { ok: true };
}

/** Tidy a pasted code: drop spaces/hyphens some clients insert. Case/format
 *  preserved — admin-minted codes are 8 chars, email-template codes are 6. */
export function normalizeCode(raw) {
  return String(raw ?? "").replace(/[\s-]+/g, "");
}

/** Optional: email a code to `email` (only useful once real email is wired). */
export async function sendCode(sb, email) {
  const addr = String(email ?? "").trim().toLowerCase();
  const { error } = await sb.auth.signInWithOtp({
    email: addr,
    options: { shouldCreateUser: true },
  });
  if (error) {
    return { ok: false, message: "Couldn't send the code — check the address and try again." };
  }
  return { ok: true };
}

/** Verify a typed code; on success the client stores the session. */
export async function verifyCode(sb, email, rawCode) {
  const token = normalizeCode(rawCode);
  if (token.length < 6) {
    return { ok: false, message: "Enter the full sign-in code you were given." };
  }
  const addr = String(email ?? "").trim().toLowerCase();
  const { error } = await sb.auth.verifyOtp({ email: addr, token, type: "email" });
  if (error) {
    return { ok: false, message: "That code is incorrect or expired — ask for a new one." };
  }
  return { ok: true };
}
