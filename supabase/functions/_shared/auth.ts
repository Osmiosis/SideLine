import { createClient, SupabaseClient } from "npm:@supabase/supabase-js@2";

export function serviceClient(): SupabaseClient {
  return createClient(
    Deno.env.get("SUPABASE_URL")!,
    Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!,
  );
}

/** Resolve the calling user from the request's Authorization header. */
export async function getCaller(req: Request) {
  const anon = createClient(
    Deno.env.get("SUPABASE_URL")!,
    Deno.env.get("SUPABASE_ANON_KEY")!,
    { global: { headers: { Authorization: req.headers.get("Authorization") ?? "" } } },
  );
  const { data: { user } } = await anon.auth.getUser();
  return user; // null when not signed in
}

export async function isAdmin(svc: SupabaseClient, userId: string): Promise<boolean> {
  const { data } = await svc.from("app_admins").select("user_id")
    .eq("user_id", userId).maybeSingle();
  return data !== null;
}
