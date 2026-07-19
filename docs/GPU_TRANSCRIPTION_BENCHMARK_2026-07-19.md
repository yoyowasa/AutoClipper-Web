# Task 67 GPU transcription benchmark

## 結論

RTX 5070 Ti環境のGPU推奨profileは次です。

```text
whisperModelSize=turbo
transcriptionLanguage=ja
transcriptionDevice=cuda
transcriptionComputeType=float16
```

`turbo`は今回の実話者・58分素材で、`large-v3`より速度、既知難所、
OpenAI校正需要が良好でした。ただし既知難所29件中13件は未解決です。
OpenAI校正を完全に不要とする精度ではありません。

## 環境

```text
tested main: 005c3b7 + Task 67 worktree
GPU: NVIDIA GeForce RTX 5070 Ti
VRAM: 16303 MiB
driver: 595.97
compute capability: 12.0
Docker Desktop: 29.5.3
Compose: v5.1.4
CUDA image: 12.8.1 + cuDNN runtime
faster-whisper: 1.2.1
CTranslate2: 4.8.1
```

58分入力:

```text
duration: 3495.8924 seconds
SHA-256: 25DF7F71CAC8DBBDDC731D2C41A55F31A852E7981CC42DB5E2F9F29816D61890
```

入力動画、transcript、benchmark生成物はignored local storageに保持し、commitしません。

## Controlled TTS

入力は119.628625秒の日本語TTSです。下表はモデルcache済みの値です。

| profile | raw CER | transcribe | RTF | peak VRAM |
| --- | ---: | ---: | ---: | ---: |
| `small / ja / CUDA FP16` | 0.1583 | 3.908s | 0.0327 | 3300 MB |
| `medium / ja / CUDA FP16` | 0.1463 | 5.968s | 0.0499 | 4676 MB |
| `large-v3 / ja / CUDA FP16` | 0.2846 | 7.417s | 0.0620 | 6724 MB |
| `turbo / ja / CUDA FP16` | 0.1804 | 2.715s | 0.0227 | 4642 MB |

TTSでは`medium`がCER最良、`turbo`が最速でした。モデルサイズと日本語CERは
単調に比例していません。

## 124秒実話者

全文の人手正解原稿がないため、CERは算出していません。Task64で確認済みの
固有名詞4語と、local suspicion filterの需要を比較しました。

| profile | 固有名詞 | suspicious | text proxy | transcribe | peak VRAM |
| --- | ---: | ---: | ---: | ---: | ---: |
| `small` | 2/4 | 34/47 | 714 chars | 5.845s | 3332 MB |
| `medium` | 2/4 | 45/69 | 621 chars | 8.693s | 4708 MB |
| `large-v3` | 3/4 | 24/67 | 328 chars | 11.245s | 6820 MB |
| `turbo` | 3/4 | 23/62 | 294 chars | 3.726s | 4644 MB |

既知誤変換として`ジェーンストリート -> ジェインストリート`、
`ごぼう抜き -> 5棒抜き`等は残りました。

## 58分実話者

`large-v3`と`turbo`だけを全編比較しました。OpenAI APIは使用していません。

| profile | segments | transcribe | RTF | peak VRAM | 重要語 |
| --- | ---: | ---: | ---: | ---: | ---: |
| `large-v3` | 1260 | 265.400s | 0.0759 | 7716 MB | 2/5 |
| `turbo` | 1396 | 100.963s | 0.0289 | 4772 MB | 4/5 |

Task65で人間確認済みの難所29件を同じ時刻へ重ねた厳格一致:

```text
large-v3: 13/29
turbo:    16/29
```

`turbo`で改善した例:

```text
キオクシア
フジテレビ
SDカード
10億
何兆円
経産省
コンセンサス
```

両profileで未解決の例:

```text
PER -> PR
簿価 -> ボカ
キオクシア -> 記憶者（複数箇所）
千鳥ヶ淵 -> 千鳥ヶ富士
日本電産のニデック
ReHacQ
```

## OpenAI校正需要

同じ`threshold=0.4 / context=2 / batch=100 / glossary=[]`で再評価しました。

| profile | target | calls | target speech | context込みtoken proxy |
| --- | ---: | ---: | ---: | ---: |
| 現行`small / CPU / int8` | 1304/1695 | 14 | 2183.88s | 14343 |
| `large-v3 / CUDA / FP16` | 816/1260 | 9 | 1927.60s | 12542 |
| `turbo / CUDA / FP16` | 850/1396 | 9 | 1813.80s | 11876 |

`turbo`の現行比:

```text
suspicion targets: -34.8%
estimated API calls: -35.7%
target speech seconds: -16.9%
context込みtoken proxy: -17.2%
```

これは入力textの見込みです。prompt、schema、reasoning、API出力を含む実token費用は
Task66 changes-only schemaと組み合わせて別途測定します。

## 58分統合E2E

```text
job: job_e7f350f808164c679cdd27f27bc3f63e
profile: turbo / ja / CUDA / FP16
OpenAI correction: off
total runtime: 303.391s
transcription stage: 89.063s
engine transcription: 86.102s
peak VRAM: 4777 MB
normal: 1/1, 1280x720
short: 2/2, 1080x1920
render failures: 0
ZIP: 76050538 bytes
audit inspection: 0
subtitle sidecar risk: 0
```

## 判定

```text
CPU互換default:
  base / auto / cpu / auto

RTX 5070 Ti GPU推奨:
  turbo / ja / cuda / float16

品質優先:
  turbo / ja / cuda / float16
  + suspicious OpenAI correction
  + Task66 changes-only schema（未merge）
```

`aTrain + large-v3`相当のローカル方式は技術的に成立しますが、この素材では
`large-v3`が自動的に最高精度にはなりませんでした。AutoClipperへ同じ
faster-whisper GPU基盤を直接統合するため、別GUIへ動画を渡す必要はありません。
