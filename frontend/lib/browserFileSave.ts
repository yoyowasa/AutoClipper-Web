export type BrowserFileSaveResult = "saved" | "cancelled";

type SaveFilePickerAcceptType = {
  description?: string;
  accept: Record<string, string[]>;
};

type SaveFilePickerOptions = {
  suggestedName?: string;
  types?: SaveFilePickerAcceptType[];
  excludeAcceptAllOption?: boolean;
};

type BrowserWritableFileHandle = {
  createWritable: () => Promise<WritableStream<Uint8Array>>;
};

export type BrowserSaveFilePicker = (
  options?: SaveFilePickerOptions
) => Promise<BrowserWritableFileHandle>;

export type BrowserFileFetch = (
  input: RequestInfo | URL,
  init?: RequestInit
) => Promise<Response>;

type SavePickerWindow = Window & {
  showSaveFilePicker?: BrowserSaveFilePicker;
};

export type BrowserFileSaveRequest = {
  url: string;
  suggestedName: string;
  mimeType: string;
  extension: string;
  description: string;
};

function activeSaveFilePicker(): BrowserSaveFilePicker | null {
  if (typeof window === "undefined") {
    return null;
  }
  const picker = (window as SavePickerWindow).showSaveFilePicker;
  return typeof picker === "function" ? picker.bind(window) : null;
}

export function browserFileSaveSupported(): boolean {
  return activeSaveFilePicker() !== null;
}

export async function saveBrowserFileWith(
  request: BrowserFileSaveRequest,
  picker: BrowserSaveFilePicker,
  fetchFile: BrowserFileFetch
): Promise<BrowserFileSaveResult> {
  let handle: BrowserWritableFileHandle;
  try {
    handle = await picker({
      suggestedName: request.suggestedName,
      types: [
        {
          description: request.description,
          accept: {
            [request.mimeType]: [request.extension]
          }
        }
      ],
      excludeAcceptAllOption: true
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      return "cancelled";
    }
    throw error;
  }

  const response = await fetchFile(request.url, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`保存データの取得に失敗しました（HTTP ${response.status}）`);
  }
  if (!response.body) {
    throw new Error("保存データを読み取れませんでした");
  }
  const responseType = response.headers.get("content-type")?.toLowerCase() ?? "";
  if (responseType && !responseType.startsWith(request.mimeType.toLowerCase())) {
    throw new Error("保存データの形式が一致しません");
  }

  const writable = await handle.createWritable();
  await response.body.pipeTo(writable);
  return "saved";
}

export async function saveBrowserFile(
  request: BrowserFileSaveRequest
): Promise<BrowserFileSaveResult> {
  const picker = activeSaveFilePicker();
  if (!picker) {
    throw new Error("このChromeでは保存先を選ぶ機能を利用できません");
  }
  return saveBrowserFileWith(request, picker, window.fetch.bind(window));
}
