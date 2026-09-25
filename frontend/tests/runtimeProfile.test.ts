import assert from "node:assert/strict";
import { getRuntimeProfile } from "../lib/api";
import { settingsForRuntimeProfile } from "../components/SettingsPanel";
import { applyCharacter, captureCharacter } from "../lib/characterPresets";

async function main() {
  const original = globalThis.fetch;
  try {
    globalThis.fetch = async () => new Response(JSON.stringify({ profile: "gpu" }));
    const settings = settingsForRuntimeProfile(await getRuntimeProfile());
    assert.equal(settings.whisperModelSize, "turbo");
    assert.equal(settings.transcriptionDevice, "cuda");
    assert.equal(settings.transcriptionComputeType, "float16");
    const loaded = applyCharacter(settings, { name: "test", settings: captureCharacter(settingsForRuntimeProfile("cpu")) });
    assert.equal(loaded.whisperModelSize, "turbo");
    assert.equal(loaded.transcriptionDevice, "cuda");
    globalThis.fetch = async () => new Response(JSON.stringify({ profile: "unknown" }));
    await assert.rejects(getRuntimeProfile);
    globalThis.fetch = async () => new Response("unavailable", { status: 503 });
    await assert.rejects(getRuntimeProfile);
    globalThis.fetch = async () => { throw new Error("offline"); };
    await assert.rejects(getRuntimeProfile);
  } finally { globalThis.fetch = original; }
  console.log("runtime profile tests passed");
}
void main();
