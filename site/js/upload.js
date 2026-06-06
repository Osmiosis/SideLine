// Google Drive resumable-upload client (spec §2). The minted session URI
// authenticates by itself — these requests carry NO Authorization header.
// Pure helpers are unit-tested in node; DriveUploader is browser-only (XHR
// is the one API with upload progress events).
export const CHUNK = 32 * 1024 * 1024; // multiple of 256 KiB (Drive rule)

export function chunkRange(offset, total, chunk = CHUNK) {
  const end = Math.min(offset + chunk, total) - 1;
  return { start: offset, end, header: `bytes ${offset}-${end}/${total}` };
}

export function parseRangeOffset(rangeHeader) {
  // Drive 308 responses confirm received bytes as "bytes=0-12345"
  const m = /bytes=\d+-(\d+)/.exec(rangeHeader ?? "");
  return m ? Number(m[1]) + 1 : 0;
}

export function probeHeader(total) {
  return `bytes */${total}`;
}

const MAX_RETRIES = 5;

export class DriveUploader {
  constructor(file, sessionUri, onProgress = () => {}) {
    this.file = file;
    this.uri = sessionUri;
    this.onProgress = onProgress;
    this.paused = false;
    this.xhr = null;
  }

  /** Abort the in-flight chunk; start(resumeOffset()) continues later. */
  pause() {
    this.paused = true;
    this.xhr?.abort();
  }

  /** Upload from `fromOffset` to the end. Resolves with Drive's file JSON. */
  async start(fromOffset = 0) {
    this.paused = false;
    let offset = fromOffset, retries = 0;
    while (true) {
      try {
        const r = await this.#putChunk(offset);
        if (r.done) return r.file;
        offset = r.next;
        retries = 0;
      } catch (e) {
        if (e.paused || ++retries > MAX_RETRIES) throw e;
        await new Promise((res) => setTimeout(res, 2000 * retries));
        offset = await this.resumeOffset(); // re-sync after a network drop
      }
    }
  }

  /** Ask Drive how much it already has (resume-after-disconnect, spec §2). */
  resumeOffset() {
    return new Promise((resolve) => {
      const xhr = new XMLHttpRequest();
      xhr.open("PUT", this.uri);
      xhr.setRequestHeader("Content-Range", probeHeader(this.file.size));
      xhr.onload = () => resolve(
        xhr.status === 308 ? parseRangeOffset(xhr.getResponseHeader("Range")) : 0);
      xhr.onerror = () => resolve(0);
      xhr.send();
    });
  }

  #putChunk(offset) {
    const { end, header } = chunkRange(offset, this.file.size);
    const blob = this.file.slice(offset, end + 1);
    return new Promise((resolve, reject) => {
      const xhr = this.xhr = new XMLHttpRequest();
      xhr.open("PUT", this.uri);
      xhr.setRequestHeader("Content-Range", header);
      xhr.upload.onprogress = (e) =>
        this.onProgress(Math.round(((offset + e.loaded) / this.file.size) * 100));
      xhr.onload = () => {
        if (xhr.status === 308) {            // chunk accepted, more to come
          resolve({ done: false, next: parseRangeOffset(xhr.getResponseHeader("Range")) });
        } else if (xhr.status === 200 || xhr.status === 201) {  // whole file in
          resolve({ done: true, file: JSON.parse(xhr.responseText) });
        } else {
          reject(new Error(`upload chunk failed: ${xhr.status}`));
        }
      };
      xhr.onabort = () =>
        reject(Object.assign(new Error("paused"), { paused: true }));
      xhr.onerror = () => reject(new Error("network error during upload"));
      xhr.send(blob);
    });
  }
}
