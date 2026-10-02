import { toBrowserApiUrl } from "./api";
import type { BrowserFileFetch, BrowserFileSaveResult } from "./browserFileSave";

export type PostingSetManifest = {
  stem: string;
  truncated: boolean;
  files: { name: string; url: string; mimeType: string }[];
};

export type PostingDirectory = {
  name: string;
  queryPermission?: (options: { mode: "readwrite" }) => Promise<PermissionState>;
  requestPermission?: (options: { mode: "readwrite" }) => Promise<PermissionState>;
  getFileHandle: (name: string, options?: { create: boolean }) => Promise<{
    createWritable: () => Promise<WritableStream<Uint8Array>>;
  }>;
};

export type PostingDirectoryPicker = (options: { mode: "readwrite"; id: string }) => Promise<PostingDirectory>;
export type PostingSetRequest = { manifestUrl: string; zipUrl: string; zipFilename: string };

export class PostingSetSaver {
  private directory: PostingDirectory | null = null;
  private writes: Promise<void> = Promise.resolve();

  constructor(private readonly dependencies: {
    picker: () => PostingDirectoryPicker | null;
    fetchFile: BrowserFileFetch;
    downloadZip: (url: string, filename: string) => void;
    confirmOverwrite: (names: string[]) => boolean;
    rememberDirectory?: (directory: PostingDirectory) => Promise<void>;
  }) {}

  get directoryName(): string | null { return this.directory?.name ?? null; }
  restoreDirectory(directory: PostingDirectory): void { this.directory ??= directory; }

  async save(request: PostingSetRequest, chooseNewDirectory = false): Promise<BrowserFileSaveResult> {
    const picker = this.dependencies.picker();
    if (!picker) {
      this.dependencies.downloadZip(request.zipUrl, request.zipFilename);
      return "saved";
    }
    let directory = chooseNewDirectory ? null : this.directory;
    try {
      // The picker must run during the click's activation, before any network request.
      if (!directory) {
        directory = await picker({ mode: "readwrite", id: "autoclipper-posting-sets" });
        this.directory = directory;
        // Persist the handle when available; saving files also works without IndexedDB.
        void this.dependencies.rememberDirectory?.(directory).catch(() => undefined);
      } else if (directory.queryPermission &&
                 await directory.queryPermission({ mode: "readwrite" }) !== "granted") {
        if (!directory.requestPermission ||
            await directory.requestPermission({ mode: "readwrite" }) !== "granted") {
          throw new Error("保存先フォルダへの書き込みが許可されていません。保存先を選び直してください。");
        }
      }
    } catch (error) {
      if (error instanceof DOMException && error.name === "AbortError") return "cancelled";
      throw error;
    }
    const response = await this.dependencies.fetchFile(request.manifestUrl, { cache: "no-store" });
    if (!response.ok) throw new Error(`投稿セットを取得できません（HTTP ${response.status}）`);
    const manifest: PostingSetManifest = await response.json();
    const previousWrite = this.writes;
    let release!: () => void;
    this.writes = new Promise<void>(resolve => { release = resolve; });
    await previousWrite;
    try {
      // Serialize cards so equal titles cannot both pass the existence check before writing.
      const existing: string[] = [];
      for (const file of manifest.files) {
        try {
          await directory.getFileHandle(file.name);
          existing.push(file.name);
        } catch (error) {
          if (!(error instanceof DOMException && error.name === "NotFoundError")) throw error;
        }
      }
      if (existing.length && !this.dependencies.confirmOverwrite(existing)) return "cancelled";
      for (const file of manifest.files) {
        const content = await this.dependencies.fetchFile(toBrowserApiUrl(file.url), { cache: "no-store" });
        if (!content.ok || !content.body) throw new Error(`${file.name} を取得できません（HTTP ${content.status}）`);
        if (!content.headers.get("content-type")?.toLowerCase().startsWith(file.mimeType)) {
          await content.body.cancel();
          throw new Error(`${file.name} の形式が一致しません`);
        }
        const handle = await directory.getFileHandle(file.name, { create: true });
        await content.body.pipeTo(await handle.createWritable());
      }
      return "saved";
    } finally {
      release();
    }
  }
}

function directoryPicker(): PostingDirectoryPicker | null {
  if (typeof window === "undefined") return null;
  const picker = (window as Window & { showDirectoryPicker?: PostingDirectoryPicker }).showDirectoryPicker;
  return typeof picker === "function" ? picker.bind(window) : null;
}

export function postingDirectorySupported(): boolean { return directoryPicker() !== null; }

export function downloadWithBrowser(url: string, filename: string): void {
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
}

function storedDirectory(write?: PostingDirectory): Promise<PostingDirectory | null> {
  if (typeof window === "undefined" || !window.indexedDB) return Promise.resolve(null);
  return new Promise((resolve, reject) => {
    const open = window.indexedDB.open("autoclipper-downloads", 1);
    open.onupgradeneeded = () => open.result.createObjectStore("directories");
    open.onerror = () => reject(open.error);
    open.onsuccess = () => {
      const database = open.result;
      const transaction = database.transaction("directories", write ? "readwrite" : "readonly");
      const store = transaction.objectStore("directories");
      let result: PostingDirectory | null = null;
      try {
        const request = write ? store.put(write, "posting-sets") : store.get("posting-sets");
        request.onsuccess = () => { if (!write) result = request.result ?? null; };
      } catch (error) {
        database.close();
        reject(error);
        return;
      }
      transaction.oncomplete = () => { database.close(); resolve(result); };
      transaction.onabort = transaction.onerror = () => { database.close(); reject(transaction.error); };
    };
  });
}

// Reuse across cards/jobs and restore on reload; permission is checked on each later click.
export const postingSetSaver = new PostingSetSaver({
  picker: directoryPicker,
  fetchFile: (input, init) => window.fetch(input, init),
  downloadZip: downloadWithBrowser,
  confirmOverwrite: names => window.confirm(`同じ名前のファイルがあります。上書きしますか？\n${names.join("\n")}`),
  rememberDirectory: async directory => { await storedDirectory(directory); }
});

let restoration: Promise<void> | null = null;
export function restorePostingSetDirectory(): Promise<void> {
  restoration ??= storedDirectory().then(directory => {
    if (directory) postingSetSaver.restoreDirectory(directory);
  }).catch(() => undefined);
  return restoration;
}
