import type { ChoiceEvaluations as EvaluationData } from "../../lib/productionPerformance";
import { goalLabel, type DashboardVideo } from "../../lib/intelligenceDashboard";
import { youtubeSyncTime } from "../../lib/intelligence";

const kinds: Record<string, string> = { range: "範囲", title_hook: "タイトル・フック", thumbnail: "サムネ", framing: "画角",
  text_style: "文字スタイル", effects: "演出", post_copy: "投稿文", publication: "公開用の選択" };
const sources: Record<string, string> = { automatic: "自動", manual: "手動", fallback: "fallback（代替）",
  preset: "プリセット", default: "既定", unrecorded: "出所未記録" };
const roles: Record<string, string> = { titleStyle: "タイトル", hookStyle: "フック", subtitleStyle: "字幕" };
const optionNames: Record<string, string> = { shortLayout: "画角", resolvedLayout: "書き出し画角", source: "画像の出所",
  fontPreset: "フォント", fontSize: "文字サイズ", bold: "太字", intent: "狙い", cropMode: "構図",
  templateVersion: "テンプレート版", emotion: "表情", type: "種類", postMetadataSource: "投稿文の出所" };
const optionLabels: Record<string, string> = { blur_background: "全体表示（ぼかし背景）", center_crop: "中央を拡大",
  face_tracking_crop: "人物アップ（顔を追従）", subject_tracking_crop: "人物を追従", speaker_tracking_crop: "話者を追従",
  character_asset: "予備素材", video_frame: "動画のコマ", standard: "半身", close: "顔のアップ",
  joy: "喜", anger: "怒", sorrow: "哀", fun: "楽", normal: "通常", short: "ショート", true: "あり", false: "なし" };

export function ChoiceEvaluations({ data, videos = [], onVideo }: {
  data?: EvaluationData | null; videos?: DashboardVideo[]; onVideo?: (id: string) => void;
}) {
  return <section className="space-y-3 rounded border border-violet-200 bg-violet-50 p-5" aria-label="制作上の選択の30日評価">
    <h2 className="font-bold">独自集計：制作上の選択ごとの30日評価</h2>
    <p className="text-sm">通常10万・ショート100万再生。7日は途中評価、30日未到達・未返却は未判定です。
      自動・手動・fallback・方針版を分けた観測です。5本未満は効果未確認。
      同じ動画が複数の選択に属するため件数を合算せず、因果効果は断定しません。選び方の自動更新は行いません。</p>
    {!data || data.groups.length === 0 ? <p>データ不足：結び付いた制作上の選択はまだ評価できません。</p> :
      <div className="max-h-[36rem] overflow-auto"><table className="w-full text-left text-sm"><thead><tr>
        <th>キャラ・形式</th><th>選択・出所・方針版</th><th>対象／30日判定済み</th><th>観測結果</th><th>根拠</th>
      </tr></thead><tbody>{data.groups.map(group => <tr className="border-t align-top" key={group.id}>
        <td className="p-2">{group.character_preset_name} ／ {group.format === "short" ? "ショート" : "通常"}</td>
        <td className="p-2">{kinds[group.kind] ?? group.kind}{group.role && `（${roles[group.role] ?? group.role}）`}
          <p>{sources[group.source] ?? group.source} ／ {group.policy_version ?? "版未記録"}</p>
          <p>{Object.entries(group.option_values).map(([key, value]) =>
            `${optionNames[key] ?? key}: ${optionLabels[String(value)] ?? String(value)}`).join(" ／ ") || "方針ごとの観測"}</p></td>
        <td className="p-2">{group.count}本 ／ {group.judged_count}本</td>
        <td className="p-2"><p>{group.sufficient ? "観測を蓄積（効果は未確認）" : "データ不足・効果未確認"}</p>
          <p>30日再生の中央値：{group.median_views?.toLocaleString() ?? "未取得"}</p>
          <p>目標到達：{group.judged_count ? `${group.reached_count}/${group.judged_count}本（参考値）` : "未判定"}</p></td>
        <td className="p-2"><details><summary>対象動画・観測時点</summary>{group.observations.map(row =>
          <div key={`${row.video_id}:${row.choice_id}`} className="my-2 border-t pt-2">
            <button type="button" className="text-sky-800 underline" onClick={() => onVideo?.(row.video_id)}>
              {videos.find(v => v.id === row.video_id)?.title ?? "根拠動画を開く"}</button>
            <p>{goalLabel(row.evaluation)}</p><p>{row.evaluation.first30.start ?? "未定"}〜{row.evaluation.first30.end ?? "未定"}</p>
            <p>観測：{youtubeSyncTime(row.evaluation.first30.observedAt)}</p>
            <details><summary>制作上の選択</summary><pre className="max-w-md whitespace-pre-wrap break-all text-xs">
              {row.values_omitted ? "値は長いため省略（制作記録の選択ID・ハッシュで追跡できます）" : JSON.stringify(row.values, null, 2)}
            </pre></details>
          </div>)}</details></td>
      </tr>)}</tbody></table></div>}
  </section>;
}
