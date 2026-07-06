import test from "node:test";
import assert from "node:assert/strict";
import { normalizeCode, sendCode, verifyCode, signIn } from "../js/auth.js";

test("normalizeCode strips spaces/hyphens but preserves the code itself", () => {
  assert.equal(normalizeCode("123456"), "123456");     // 6-digit (email template)
  assert.equal(normalizeCode("123 456"), "123456");    // spaces some clients insert
  assert.equal(normalizeCode(" 12-34-56 "), "123456"); // dashes/padding
  assert.equal(normalizeCode("A1B2C3D4"), "A1B2C3D4"); // 8-char admin code, alnum kept
  assert.equal(normalizeCode("a1b2 c3d4"), "a1b2c3d4"); // case preserved
  assert.equal(normalizeCode(null), "");
});

// A minimal stub of the Supabase auth client that records calls.
function stubClient(result = {}) {
  const calls = [];
  return {
    calls,
    auth: {
      signInWithOtp: async (arg) => { calls.push(["signInWithOtp", arg]); return result; },
      verifyOtp: async (arg) => { calls.push(["verifyOtp", arg]); return result; },
      signInWithPassword: async (arg) => { calls.push(["signInWithPassword", arg]); return result; },
    },
  };
}

test("signIn passes trimmed/lowercased email + password to the client", async () => {
  const sb = stubClient({ error: null });
  const r = await signIn(sb, "  Demo@Sideline.Review ", "s3cret");
  assert.equal(r.ok, true);
  const [name, arg] = sb.calls[0];
  assert.equal(name, "signInWithPassword");
  assert.equal(arg.email, "demo@sideline.review");
  assert.equal(arg.password, "s3cret");
});

test("signIn surfaces a friendly error on bad credentials, never throws", async () => {
  const sb = stubClient({ error: { message: "Invalid login credentials" } });
  const r = await signIn(sb, "demo@sideline.review", "wrong");
  assert.equal(r.ok, false);
  assert.match(r.message, /wrong email or password/i);
});

test("sendCode requests an email OTP for the address (user auto-created)", async () => {
  const sb = stubClient({ error: null });
  const r = await sendCode(sb, "  Coach@Club.com ");
  assert.equal(r.ok, true);
  const [name, arg] = sb.calls[0];
  assert.equal(name, "signInWithOtp");
  assert.equal(arg.email, "coach@club.com");            // trimmed + lowercased
  assert.equal(arg.options.shouldCreateUser, true);      // reviewers are new users
});

test("sendCode surfaces a friendly error, never throws", async () => {
  const sb = stubClient({ error: { message: "rate limit exceeded" } });
  const r = await sendCode(sb, "coach@club.com");
  assert.equal(r.ok, false);
  assert.match(r.message, /couldn.t send/i);
});

test("verifyCode verifies the typed code as an email OTP", async () => {
  const sb = stubClient({ error: null });
  const r = await verifyCode(sb, "coach@club.com", "12 34 56");
  assert.equal(r.ok, true);
  const [name, arg] = sb.calls[0];
  assert.equal(name, "verifyOtp");
  assert.equal(arg.email, "coach@club.com");
  assert.equal(arg.token, "123456");                     // normalized before send
  assert.equal(arg.type, "email");
});

test("verifyCode accepts an 8-char admin-minted code", async () => {
  const sb = stubClient({ error: null });
  const r = await verifyCode(sb, "coach@club.com", "A1B2-C3D4");
  assert.equal(r.ok, true);
  assert.equal(sb.calls[0][1].token, "A1B2C3D4");
  assert.equal(sb.calls[0][1].type, "email");
});

test("verifyCode rejects an obviously incomplete code without a network call", async () => {
  const sb = stubClient({ error: null });
  const r = await verifyCode(sb, "coach@club.com", "123");
  assert.equal(r.ok, false);
  assert.equal(sb.calls.length, 0);                      // never hit the network
  assert.match(r.message, /full sign-in code/i);
});

test("verifyCode surfaces a friendly error on a wrong/expired code", async () => {
  const sb = stubClient({ error: { message: "Token has expired or is invalid" } });
  const r = await verifyCode(sb, "coach@club.com", "123456");
  assert.equal(r.ok, false);
  assert.match(r.message, /incorrect or expired/i);
});
