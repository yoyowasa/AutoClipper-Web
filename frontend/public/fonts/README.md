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

## Not bundled

`ラノベPOP V2` is not bundled yet. Its official BOOTH download requires a user
login, so an unverified third-party copy is not used. Do not expose the preset
until the official font file and its license are added and rendering is tested.
