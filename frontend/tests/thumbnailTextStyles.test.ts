import assert from "node:assert/strict";
import { applyCharacter, captureCharacter, newCharacter, PLAIN_THUMBNAIL } from "../lib/characterPresets";
import { THUMBNAIL_FONTS, thumbnailTextDefaults } from "../lib/thumbnailStyle";
import { DEFAULT_SETTINGS } from "../components/SettingsPanel";

const styles = thumbnailTextDefaults({ ...PLAIN_THUMBNAIL, titleColor: "#123456" });
assert.equal(styles.upper.color, "#123456");
styles.heading.fontPreset = "keifont";
styles.heading.fontSize = 32;
styles.heading.autoFit = false;
styles.lower.color = "#FF0000";
const snapshot = captureCharacter({ ...DEFAULT_SETTINGS, normalThumbnailStyle: { ...PLAIN_THUMBNAIL, textStyles: styles } });
const restored = applyCharacter(newCharacter(DEFAULT_SETTINGS), { name: "A", settings: snapshot });
assert.deepEqual(restored.normalThumbnailStyle?.textStyles, styles);
assert.equal(restored.normalThumbnailStyle?.textStyles?.heading.autoFit, false);
restored.normalThumbnailStyle!.textStyles!.upper.fontSize = 80;
assert.equal(snapshot.normalThumbnailStyle?.textStyles?.upper.fontSize, 155);
assert.equal(thumbnailTextDefaults().lower.color, "#FFD84A");
for (const preset of ["genei_kiwami_go", "genei_mono_go", "genei_antique"]) {
  assert.ok(THUMBNAIL_FONTS.some(font => font.value === preset));
}
console.log("Thumbnail row styles survive character save/restore without aliasing.");
