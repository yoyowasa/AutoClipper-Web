# Bundled subtitle fonts

These files are mounted read-only at `/app/fonts` for FFmpeg/libass and served
from `/fonts` for the browser preview. The UI groups them by intended use; the
group does not restrict where a font can be selected.

## Normal subtitle fonts

| File | UI label | SHA-256 | Source | License |
| --- | --- | --- | --- | --- |
| `NotoSansJP-Black.ttf` | Noto Sans JP Black | `32D4A12A36D8E16B9EF501C56BB3717003418E97A00E44890D2B261A66B12A99` | [Google Fonts](https://github.com/google/fonts/tree/main/ofl/notosansjp) | SIL OFL 1.1 (`LICENSE-NotoSansJP.txt`) |
| `SourceHanSansJP-Heavy.otf` | 源ノ角ゴシック Heavy | `F875DE9C62ACE2082B90AB1DA940F3E8CEFFA933F500E49D205CB74E6E5D03BB` | [Adobe Source Han Sans](https://github.com/adobe-fonts/source-han-sans) | SIL OFL 1.1 (`LICENSE-SourceHanSans.txt`) |
| `MPLUS1-ExtraBold.ttf` | M PLUS 1 ExtraBold | `A102A75045DE6EC2D2073B250C631B7402BA606454A41DC58457EA5D89913BE2` | [M PLUS Fonts](https://github.com/coz-m/MPLUS_FONTS) | SIL OFL 1.1 (`LICENSE-MPLUS.txt`) |
| `MPLUSRounded1c-ExtraBold.ttf` | M PLUS Rounded 1c ExtraBold | `8E7C15901DCA87F1451B356DDA594F7D092BA252A5DCC47DA74523A242493C36` | [Google Fonts](https://github.com/google/fonts/tree/main/ofl/mplusrounded1c) | SIL OFL 1.1 (`LICENSE-MPLUS.txt`) |

`NotoSansJP-Black.ttf` and `MPLUS1-ExtraBold.ttf` are static instances generated
from their official variable fonts at weight 900 and 800 respectively.

## Special emphasis fonts

Use these for short reactions, punch lines, titles, and hooks rather than long
subtitle passages.

| File | UI label | SHA-256 | Source | License |
| --- | --- | --- | --- | --- |
| `851CHIKARA-DZUYOKU-kanaA.ttf` | 851チカラヅヨク | `8ED0A61010D19EFD0B9CB59E6CB114CD1A25FE4A67C9DFB47288AECA78BEEC70` | [851font official site](https://pm85122.onamae.jp/851fontpage.html) | Official terms (`LICENSE-851CHIKARA-DZUYOKU.txt`) |
| `DelaGothicOne-Regular.ttf` | Dela Gothic One | `4FF87A0965F1B0505E5A2C58424BC6AD3CFF27E56A82F21C2FC9D6B0E3857EE2` | [Google Fonts](https://github.com/google/fonts/tree/main/ofl/delagothicone) | SIL OFL 1.1 (`LICENSE-DelaGothicOne.txt`) |
| `Corporate-Logo-Bold-ver3.otf` | コーポレート・ロゴ Bold | `88239D1B11D1F70CDB3A5805791AE6BC0C1B8667BB67FADEE20D73EDF28CBEB3` | [Logotype.jp](https://logotype.jp/corporate-logo-font-dl.html) | SIL OFL 1.1 (`LICENSE-CorporateLogo.txt`) |

## 2026-09-07: Phrase styles

Unmodified font binaries; backend ASS and browser CSS use the same files and Windows ascent/descent metrics.

| Font | File | Official source / terms |
| --- | --- | --- |
| 851チカラヨワク 0.02 | `851CHIKARA-YOWAKU.ttf` | https://pm85122.onamae.jp/851ch-yw.html ; free redistribution/commercial use, no resale or false authorship |
| けいふぉんと！ | `keifont.ttf` | https://font.sumomo.ne.jp/font_1.html ; Apache 2.0 and M+ notices alongside |
| 無心 1.04 | `mushin.otf` | https://modi.jpn.org/font_mushin.php ; MODI terms in LICENSE-Mushin.txt |
| 暗黒ゾン字 | `Zomzi.ttf` | https://www.ankokukoubou.com/font/ankokuzonji.htm ; author explicitly permits redistribution on current page (lines 38–42), superseding old archive readme |
| たぬき油性マジック 1.22 | `TanukiMagic.ttf` | https://tanukifont.com/tanuki-permanent-marker/ ; LICENSE-TanukiMagic.txt |

## 2026-09-25: GenEi fonts

Original, unmodified TTFs from [御琥祢屋](https://okoneya.jp/font/download.html). Each archive's original SIL OFL 1.1 notice is preserved alongside the font. The three presets are available for clip text and normal thumbnails.

| UI label | File | SHA-256 | Official page | License |
| --- | --- | --- | --- | --- |
| 源暎きわみゴ | `GenEiKiwamiGo.ttf` | `BF87353ADFC6D1CCE8F6DCE2297CFD2B3BCCC75A4F3DD039506AB27E54A31613` | [源暎きわみゴ](https://okoneya.jp/font/genei-kiwamigo.html) | `LICENSE-GenEiKiwamiGo.txt` |
| 源暎モノゴ Bold | `GenEiMonoGothic-Bold.ttf` | `9DE1A9FFF00A4BC8D9E5148C1B148A18F0DFD9F7FC58812A4AC6609C00D4088D` | [源暎モノゴ](https://okoneya.jp/font/genei-mono-go.html) | `LICENSE-GenEiMonoGothic.txt` |
| 源暎アンチック v6 | `GenEiAntiqueNv6-M.ttf` | `A04B166A260E67635BFF99512355A14DE459620DF6451D1EE72B4D072370DF55` | [源暎アンチック](https://okoneya.jp/font/genei-antique.html) | `LICENSE-GenEiAntique.txt` |

### Local-only font

キルゴUかなNB: official author package `GN-KillGothic_U.zip`, available via
https://forest.watch.impress.co.jp/library/software/killgothic_u/ .
Archive readme allows video/commercial use but prohibits redistribution of font files without permission.
`GN-KillGothic-U-KanaNB.ttf` and `local/LICENSE-Killgo.txt` are therefore gitignored and **must not be deployed or redistributed**.
On another PC, obtain the original package and place this TTF at `frontend/public/fonts/GN-KillGothic-U-KanaNB.ttf`.
Use only on the user's local app. A missing file is not supplied with this repository.

### Pending file

やさしさゴシック: https://booth.pm/ja/items/5980376 . Official download requires login.
Do not substitute やさしさゴシック手書き, Bold, or another font; add only after the original file and IPA/M+ terms are available.

`ラノベPOP V2` is not bundled yet. Its official BOOTH download requires a user
login, so an unverified third-party copy is not used. Do not expose the preset
until the official font file and its license are added and rendering is tested.
