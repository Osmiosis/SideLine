// Shared Supabase client + tiny DOM/format helpers for every page.
import { createClient } from "https://esm.sh/@supabase/supabase-js@2";
import { SUPABASE_URL, SUPABASE_ANON_KEY } from "./config.js";

export const sb = createClient(SUPABASE_URL, SUPABASE_ANON_KEY);

export function el(id) {
  return document.getElementById(id);
}

export function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

export function fmtBytes(n) {
  if (!Number.isFinite(n)) return "?";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let i = 0;
  while (n >= 1024 && i < units.length - 1) { n /= 1024; i++; }
  return `${n.toFixed(n >= 10 || i === 0 ? 0 : 1)} ${units[i]}`;
}

/** Redirect to login when not signed in. Returns the signed-in user. */
export async function requireUser() {
  // a magic-link redirect carries the session in the URL hash; give the
  // client a moment to exchange it before deciding we're signed out
  if (location.hash.includes("access_token")) {
    await new Promise((resolve) => {
      const { data: { subscription } } = sb.auth.onAuthStateChange((event) => {
        if (event === "SIGNED_IN" || event === "INITIAL_SESSION") {
          subscription.unsubscribe();
          resolve();
        }
      });
      setTimeout(resolve, 3000); // never hang the page on a stale hash
    });
  }
  const { data: { session } } = await sb.auth.getSession();
  if (!session) {
    location.replace("index.html");
    throw new Error("not signed in");
  }
  return session.user;
}

/** RLS only lets a user see their OWN app_admins row — perfect for this. */
export async function isAdmin(userId) {
  const { data } = await sb.from("app_admins")
    .select("user_id").eq("user_id", userId).maybeSingle();
  return data !== null;
}

/** Wire the shared header nav (admin link visibility + sign out). */
export async function initNav(user) {
  const adminLink = el("adminLink");
  if (adminLink && await isAdmin(user.id)) adminLink.classList.remove("hidden");
  const out = el("signout");
  if (out) {
    out.onclick = async (e) => {
      e.preventDefault();
      await sb.auth.signOut();
      location.replace("index.html");
    };
  }
}

/** Invoke an Edge Function; throws with the function's friendly message. */
export async function callFn(name, body = {}) {
  const { data, error } = await sb.functions.invoke(name, { body });
  if (error) {
    let msg = "Something went wrong. Please try again.";
    try { msg = (await error.context.json()).error ?? msg; } catch { /* keep default */ }
    throw new Error(msg);
  }
  return data;
}
