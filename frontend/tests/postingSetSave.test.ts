import assert from "node:assert/strict";
import { downloadWithBrowser, PostingSetSaver, type PostingDirectory } from "../lib/postingSetSave";

async function main() {
  const files = [
    { name: "公開タイトル？：話題.mp4", url: "/api/exports/exp/download", mimeType: "video/mp4" },
    { name: "公開タイトル？：話題.png", url: "/api/exports/exp/thumbnail/download", mimeType: "image/png" },
    { name: "公開タイトル？：話題_投稿文.txt", url: "/api/exports/exp/posting-text", mimeType: "text/plain" }
  ];
  const request = { manifestUrl: "/manifest", zipUrl: "/posting-set.zip", zipFilename: "公開タイトル？：話題.zip" };
  const events: string[] = [];
  const saved = new Map<string, number[]>();
  let picked = 0;
  let confirms = 0;
  const directory: PostingDirectory = {
    name: "投稿用",
    async getFileHandle(name, options) {
      if (!options?.create && !saved.has(name)) throw new DOMException("missing", "NotFoundError");
      return {
        async createWritable() {
          const chunks: number[] = [];
          return new WritableStream({
            write(chunk: Uint8Array) { chunks.push(...chunk); },
            close() { saved.set(name, chunks); }
          });
        }
      };
    }
  };
  const fetchFile = async (url: RequestInfo | URL) => {
    events.push("fetch");
    if (url === request.manifestUrl) return Response.json({ stem: "公開タイトル？：話題", truncated: false, files });
    const file = files.find(f => String(url).endsWith(f.url.replace("/api/", "")) ||
      (f.url.endsWith("/download") && String(url).endsWith("/video.mp4")))!;
    assert.ok(file);
    return new Response(new Uint8Array([1, 2, 3]), { headers: { "content-type": file.mimeType } });
  };
  const saver = new PostingSetSaver({
    picker: () => async () => { events.push("picker"); picked += 1; return directory; },
    fetchFile,
    downloadZip: () => assert.fail("folder-capable browser must not download a ZIP"),
    confirmOverwrite: names => { confirms += 1; assert.deepEqual(names, files.map(f => f.name)); return true; }
  });
  assert.equal(await saver.save(request), "saved");
  assert.equal(events[0], "picker", "pick before any network call");
  assert.equal(picked, 1);
  assert.equal(confirms, 0);
  assert.equal(saver.directoryName, "投稿用");
  assert.deepEqual([...saved.keys()], files.map(f => f.name));
  for (const data of saved.values()) assert.deepEqual(data, [1, 2, 3]);
  assert.equal(await saver.save(request), "saved");
  assert.equal(picked, 1, "the next posting set uses the same directory");
  assert.equal(confirms, 1);
  assert.equal(await saver.save(request, true), "saved");
  assert.equal(picked, 2, "users can choose another folder");

  let zipCalls = 0;
  const fallback = new PostingSetSaver({
    picker: () => null,
    fetchFile: async () => assert.fail("the ZIP endpoint supplies all three files"),
    downloadZip: (url, filename) => { zipCalls += 1; assert.equal(url, request.zipUrl); assert.equal(filename, request.zipFilename); },
    confirmOverwrite: () => assert.fail("not a folder write")
  });
  assert.equal(await fallback.save(request), "saved");
  assert.equal(zipCalls, 1);
  const originalDocument = Object.getOwnPropertyDescriptor(globalThis, "document");
  let clicked = false;
  let removed = false;
  const anchor = { href: "", download: "", click() { clicked = true; }, remove() { removed = true; } };
  Object.defineProperty(globalThis, "document", { configurable: true, value: {
    createElement: (name: string) => { assert.equal(name, "a"); return anchor; },
    body: { appendChild: (element: unknown) => assert.equal(element, anchor) }
  } });
  try {
    downloadWithBrowser(request.zipUrl, request.zipFilename);
    assert.equal(anchor.href, request.zipUrl);
    assert.equal(anchor.download, request.zipFilename);
    assert.ok(clicked && removed);
  } finally {
    if (originalDocument) Object.defineProperty(globalThis, "document", originalDocument);
    else Reflect.deleteProperty(globalThis, "document");
  }

  const cancelled = new PostingSetSaver({
    picker: () => async () => { throw new DOMException("cancelled", "AbortError"); },
    fetchFile: async () => assert.fail("cancelled picker must not fetch"),
    downloadZip: () => assert.fail("cancelled is not unsupported"), confirmOverwrite: () => false
  });
  assert.equal(await cancelled.save(request), "cancelled");

  const declined = new PostingSetSaver({
    picker: () => async () => directory,
    fetchFile,
    downloadZip: () => assert.fail(), confirmOverwrite: () => false
  });
  const before = events.length;
  assert.equal(await declined.save(request), "cancelled");
  assert.equal(events.length, before + 1, "only fetch manifest when overwrite is declined");

  const denied = new PostingSetSaver({
    picker: () => async () => ({ ...directory, queryPermission: async () => "denied", requestPermission: async () => "denied" }),
    fetchFile, downloadZip: () => assert.fail(), confirmOverwrite: () => true
  });
  await denied.save(request);
  await assert.rejects(() => denied.save(request), /書き込みが許可されていません/);

  const failed = new PostingSetSaver({
    picker: () => async () => directory,
    fetchFile: async () => new Response("failed", { status: 500 }),
    downloadZip: () => assert.fail(), confirmOverwrite: () => true
  });
  await assert.rejects(() => failed.save(request), /HTTP 500/);
  const restored = new PostingSetSaver({
    picker: () => async () => assert.fail("restored directory must be reused"),
    fetchFile, downloadZip: () => assert.fail(), confirmOverwrite: () => true
  });
  restored.restoreDirectory(directory);
  assert.equal(await restored.save(request), "saved");
  const brokenWriter = new PostingSetSaver({
    picker: () => async () => ({
      name: "broken",
      async getFileHandle(name, options) {
        if (!options?.create) throw new DOMException("missing", "NotFoundError");
        return { createWritable: async () => new WritableStream({ write() { throw new Error("disk write failed"); } }) };
      }
    }),
    fetchFile, downloadZip: () => assert.fail(), confirmOverwrite: () => true
  });
  await assert.rejects(() => brokenWriter.save(request), /disk write failed/);
  saved.clear();
  let concurrentConfirmation = 0;
  const concurrent = new PostingSetSaver({
    picker: () => async () => directory,
    fetchFile, downloadZip: () => assert.fail(),
    confirmOverwrite: () => { concurrentConfirmation += 1; return false; }
  });
  concurrent.restoreDirectory(directory);
  assert.deepEqual(await Promise.all([concurrent.save(request), concurrent.save(request)]), ["saved", "cancelled"]);
  assert.equal(concurrentConfirmation, 1, "the second save sees and confirms the first save's files");
  console.log("posting set folder/ZIP saving: ok");
}

void main().catch((error: unknown) => { console.error(error); process.exitCode = 1; });
