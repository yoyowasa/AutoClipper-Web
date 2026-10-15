"""Official YouTube recommendation explanations used in one-click analysis.

These are public descriptions, not a reverse-engineered ranking formula. Keep
source URLs and the applicability of each rule visible in saved proposals.
"""

FRAMEWORK_VERSION = "youtube_official_2026_09_24"

RULES = {
    "viewer_fit": {
        "label": "視聴者ごとの興味・履歴との適合",
        "source": "https://support.google.com/youtube/answer/16533387?hl=en-GB",
        "claim": "推薦は視聴者ごとの履歴・興味と動画の適合を考慮する。",
    },
    "surface_context": {
        "label": "表示面ごとに異なる視聴文脈",
        "source": "https://support.google.com/youtube/answer/16089387?hl=en",
        "claim": "ホームは主に視聴履歴、次の動画は視聴中の動画、Shortsフィードは個人化された短尺視聴の文脈を使う。",
    },
    "shorts_response": {
        "label": "Shortsの選択・継続・満足度",
        "source": "https://support.google.com/youtube/answer/11914225?co=YOUTUBE._YTVideoType%3Dshorts&hl=en-GB",
        "claim": "Shortsは視聴選択、平均視聴時間・割合、いいね・視聴後調査などを手掛かりにする。",
    },
    "appeal_engagement_satisfaction": {
        "label": "選択・視聴継続・満足度の三段階",
        "source": "https://support.google.com/youtube/answer/16559650?hl=en",
        "claim": "動画反応をAppeal、Engagement、Satisfactionに分けて考える。",
    },
    "search_relevance": {
        "label": "検索意図との一致",
        "source": "https://support.google.com/youtube/answer/16090438?hl=en",
        "claim": "検索はクエリとタイトル・説明・内容の関連、クエリごとの視聴者反応を考慮する。",
    },
    "topic_competition": {
        "label": "題材需要・競争・季節性",
        "source": "https://support.google.com/youtube/answer/16558238?hl=en",
        "claim": "題材への関心、他動画との競争、季節性は表示機会に影響する。",
    },
    "packaging_expectation": {
        "label": "見せ方と内容の期待一致",
        "source": "https://support.google.com/youtube/answer/16559650?hl=en",
        "claim": "題材・タイトル・サムネイルの伝え方と、冒頭から内容が期待に応えることを重視する。",
    },
    "audience_expansion": {
        "label": "狭い層から広い層への拡大時の数字",
        "source": "https://support.google.com/youtube/answer/16767369?hl=en",
        "claim": "表示対象が広がるとCTRが下がっても再生が増え得る。高CTR・高平均視聴時間だけで拡大は保証されない。",
    },
}


def prompt_rules():
    return "\n".join(f"{key}: {rule['claim']} 出典={rule['source']}" for key, rule in RULES.items())
