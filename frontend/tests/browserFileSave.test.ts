import assert from "node:assert/strict";

import {
  saveBrowserFileWith,
  type BrowserFileFetch,
  type BrowserSaveFilePicker
} from "../lib/browserFileSave";

async function main() {
  const request = {
    url: "/backend-api/exports/exp_test/video.mp4",
    suggestedName: "normal_01.mp4",
    mimeType: "video/mp4",
    extension: ".mp4",
    description: "MP4 video"
  };

  const events: string[] = [];
  const chunks: number[] = [];
  const writable = new WritableStream<Uint8Array>({
    write(chunk) {
      events.push("write");
      chunks.push(...chunk);
    },
    close() {
      events.push("close");
    }
  });
  const picker: BrowserSaveFilePicker = async (options) => {
    events.push("picker");
    assert.equal(options?.suggestedName, "normal_01.mp4");
    return {
      async createWritable() {
        events.push("writable");
        return writable;
      }
    };
  };
  const fetchFile: BrowserFileFetch = async (input) => {
    events.push("fetch");
    assert.equal(input, request.url);
    return new Response(new Uint8Array([1, 2, 3]), {
      headers: { "Content-Type": "video/mp4" }
    });
  };

  assert.equal(await saveBrowserFileWith(request, picker, fetchFile), "saved");
  assert.deepEqual(events, ["picker", "fetch", "writable", "write", "close"]);
  assert.deepEqual(chunks, [1, 2, 3]);

  let fetchCalled = false;
  const cancelledPicker: BrowserSaveFilePicker = async () => {
    throw new DOMException("cancelled", "AbortError");
  };
  const cancelledFetch: BrowserFileFetch = async () => {
    fetchCalled = true;
    return new Response();
  };
  assert.equal(
    await saveBrowserFileWith(request, cancelledPicker, cancelledFetch),
    "cancelled"
  );
  assert.equal(fetchCalled, false);

  const failingFetch: BrowserFileFetch = async () =>
    new Response("failed", { status: 500 });
  await assert.rejects(
    () => saveBrowserFileWith(request, picker, failingFetch),
    /HTTP 500/
  );

  console.log("browser file save: ok");
}

void main().catch((error: unknown) => {
  console.error(error);
  process.exitCode = 1;
});
