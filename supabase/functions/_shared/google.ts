// Drive API helpers. The refresh token is a function secret; access tokens
// are minted per-invocation (they live ~1h; functions are short-lived).
const TOKEN_URL = "https://oauth2.googleapis.com/token";
const API = "https://www.googleapis.com/drive/v3";
const UPLOAD = "https://www.googleapis.com/upload/drive/v3";

export async function getAccessToken(): Promise<string> {
  const res = await fetch(TOKEN_URL, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({
      client_id: Deno.env.get("GOOGLE_CLIENT_ID")!,
      client_secret: Deno.env.get("GOOGLE_CLIENT_SECRET")!,
      refresh_token: Deno.env.get("GOOGLE_REFRESH_TOKEN")!,
      grant_type: "refresh_token",
    }),
  });
  if (!res.ok) throw new Error(`google token refresh failed: ${res.status}`);
  return (await res.json()).access_token;
}

export async function driveFreeBytes(token: string): Promise<number> {
  const res = await fetch(`${API}/about?fields=storageQuota`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) throw new Error(`drive about failed: ${res.status}`);
  const { storageQuota } = await res.json();
  if (!storageQuota.limit) return Number.MAX_SAFE_INTEGER; // unlimited plan
  return Number(storageQuota.limit) - Number(storageQuota.usage);
}

export async function findOrCreateFolder(
  token: string, name: string, parentId: string | null,
): Promise<string> {
  const safe = name.replace(/'/g, "\\'");
  let q = `name = '${safe}' and mimeType = 'application/vnd.google-apps.folder' and trashed = false`;
  if (parentId) q += ` and '${parentId}' in parents`;
  const list = await fetch(
    `${API}/files?q=${encodeURIComponent(q)}&fields=files(id)`,
    { headers: { Authorization: `Bearer ${token}` } },
  ).then((r) => r.json());
  if (list.files?.length) return list.files[0].id;

  const res = await fetch(`${API}/files`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
    body: JSON.stringify({
      name,
      mimeType: "application/vnd.google-apps.folder",
      ...(parentId ? { parents: [parentId] } : {}),
    }),
  });
  if (!res.ok) throw new Error(`folder create failed: ${res.status}`);
  return (await res.json()).id;
}

export async function initResumableSession(
  token: string, fileName: string, folderId: string,
  fileSize: number, mimeType: string, origin: string,
): Promise<string> {
  // IMPORTANT: the Origin header set HERE binds CORS for the browser's
  // subsequent PUTs to the session URI. Without it, browser uploads fail.
  const res = await fetch(`${UPLOAD}/files?uploadType=resumable`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
      "X-Upload-Content-Type": mimeType,
      "X-Upload-Content-Length": String(fileSize),
      Origin: origin,
    },
    body: JSON.stringify({ name: fileName, parents: [folderId] }),
  });
  const uri = res.headers.get("Location");
  if (!res.ok || !uri) throw new Error(`resumable init failed: ${res.status}`);
  return uri;
}

export async function getFile(
  token: string, fileId: string,
): Promise<{ id: string; name: string; size?: string; parents?: string[] } | null> {
  const res = await fetch(`${API}/files/${fileId}?fields=id,name,size,parents`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  return res.ok ? await res.json() : null;
}

export async function deleteFile(token: string, fileId: string): Promise<void> {
  await fetch(`${API}/files/${fileId}`, {
    method: "DELETE",
    headers: { Authorization: `Bearer ${token}` },
  }); // 404s are fine (already gone)
}
