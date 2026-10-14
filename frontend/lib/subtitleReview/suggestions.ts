export function canonicalSuggestionDraft(
  segments: Array<{ segmentId: string; text: string }>
): string {
  return JSON.stringify(
    segments.map((segment) => ({
      segmentId: segment.segmentId,
      text: segment.text
    }))
  );
}

export async function sha256Hex(value: string): Promise<string> {
  const digest = await globalThis.crypto.subtle.digest(
    "SHA-256",
    new TextEncoder().encode(value)
  );
  return Array.from(new Uint8Array(digest), (byte) =>
    byte.toString(16).padStart(2, "0")
  ).join("");
}
