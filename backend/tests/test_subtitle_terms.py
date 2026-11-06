"""Per-character learning of repeated exact subtitle corrections, applied before review rows exist."""
import json

from app.audio.transcribe_faster_whisper import TranscriptSegment, TranscriptWord
from app.candidates.merge_boundaries import Candidate
from app.candidates.select_candidates import CandidateSelection
from app.jobs.runner import _apply_learned_subtitle_terms
from app.jobs.subtitle_review import build_subtitle_review, update_review_segment, write_subtitle_review
from app.main import app
from app.render.subtitle_timing import usable_words
from app.storage.paths import StoragePaths, get_storage_paths
from app.subtitle_terms import (
    active_rules, apply_rules, derive_rules, extract_pairs, learn_from_document, read_store, set_disabled,
)
from test_api_routes import client as client  # noqa: F401

CHARACTER = "儒烏風亭らでん"


def document(job_id, texts, character=CHARACTER):
    transcript = [TranscriptSegment(start=i * 5.0, end=i * 5.0 + 4.0, text=text) for i, text in enumerate(texts)]
    candidate = Candidate(id="clip", type="normal", start=0.0, end=len(texts) * 5.0, duration=len(texts) * 5.0,
                          transcript_text="x", title="t")
    return build_subtitle_review(job_id, CandidateSelection(normalClips=[candidate], shorts=[]), transcript,
                                 render_settings={"characterPresetName": character} if character else None)


def correct(review, pairs):
    for segment in list(review.segments):
        fixed = segment.text
        for source, target in pairs:
            fixed = fixed.replace(source, target)
        if fixed != segment.text:
            review = update_review_segment(review, segment.id, fixed)
    return review


def learn(root, job_id, texts, pairs, character=CHARACTER):
    review = correct(document(job_id, texts, character), pairs)
    learn_from_document(review, root)
    return review


def test_only_whole_term_replacements_are_learned():
    assert extract_pairs("今日のラデンです", "今日のらでんです") == [("ラデン", "らでん")]
    assert extract_pairs("マッチ", "バッチ") == []  # one character is not a term
    assert extract_pairs("ラデン", "ラデンさん") == []  # insertion
    assert extract_pairs("ラデンです", "です") == []  # deletion
    assert extract_pairs("ラ デン", "らでん") == []  # a term never contains whitespace


def test_a_rule_needs_three_corrections_in_two_jobs_or_five_in_one(tmp_path):
    texts = ["ラデンです", "こんにちはラデン"]
    learn(tmp_path, "job_1", texts, [("ラデン", "らでん")])
    assert active_rules(tmp_path, CHARACTER) == []  # two corrections, one job
    learn(tmp_path, "job_2", ["ラデンだよ"], [("ラデン", "らでん")])
    rule = active_rules(tmp_path, CHARACTER)[0]
    assert (rule["src"], rule["dst"], rule["count"], rule["jobs"]) == ("ラデン", "らでん", 3, 2)
    learn(tmp_path, "job_2", ["ラデンだよ"], [("ラデン", "らでん")])  # saving again changes nothing
    assert active_rules(tmp_path, CHARACTER)[0]["count"] == 3


def test_three_corrections_in_a_single_job_wait_but_five_do_not(tmp_path):
    learn(tmp_path, "job_1", [f"ラデン{c}" for c in "abc"], [("ラデン", "らでん")], character="三回")
    assert active_rules(tmp_path, "三回") == []
    learn(tmp_path, "job_1", [f"ラデン{c}" for c in "abcde"], [("ラデン", "らでん")], character="五回")
    assert active_rules(tmp_path, "五回")[0]["count"] == 5


def test_learning_is_per_character(tmp_path):
    for job in ("job_1", "job_2"):
        learn(tmp_path, job, ["ラデンです", "またラデン"], [("ラデン", "らでん")])
    assert active_rules(tmp_path, CHARACTER) and active_rules(tmp_path, "宙科そぴあ") == []
    assert active_rules(tmp_path, None) == []


def test_a_term_the_human_often_leaves_alone_is_not_a_rule(tmp_path):
    for job in ("job_1", "job_2"):
        learn(tmp_path, job, ["ラデンです", "またラデン"], [("ラデン", "らでん")])
    assert active_rules(tmp_path, CHARACTER)
    review = document("job_3", [f"ラデン{suffix}" for suffix in "abcdef"])
    review = update_review_segment(review, review.segments[0].id, "らでんa")  # one fixed, five left as they were
    learn_from_document(review, tmp_path)
    rule = derive_rules(read_store(tmp_path, CHARACTER))[0]
    assert (rule["count"], rule["kept"], rule["active"]) == (5, 5, False)


def test_reverting_a_learned_term_twice_switches_it_off(tmp_path):
    for job in ("job_1", "job_2"):
        learn(tmp_path, job, ["ラデンです", "またラデン"], [("ラデン", "らでん")])
    assert active_rules(tmp_path, CHARACTER)
    for job in ("job_3", "job_4"):
        learn(tmp_path, job, ["らでんです"], [("らでん", "ラデン")])
    assert [r["src"] for r in active_rules(tmp_path, CHARACTER)] == []


def test_a_rule_can_be_disabled_and_enabled_again(tmp_path):
    for job in ("job_1", "job_2"):
        learn(tmp_path, job, ["ラデンです", "またラデン"], [("ラデン", "らでん")])
    set_disabled(tmp_path, CHARACTER, "ラデン", "らでん", True)
    assert active_rules(tmp_path, CHARACTER) == [] and derive_rules(read_store(tmp_path, CHARACTER))[0]["disabled"]
    set_disabled(tmp_path, CHARACTER, "ラデン", "らでん", False)
    assert active_rules(tmp_path, CHARACTER)


def test_conflicting_corrections_without_a_clear_winner_are_not_applied(tmp_path):
    learn(tmp_path, "job_1", ["ラデンです", "またラデン"], [("ラデン", "らでん")])
    learn(tmp_path, "job_2", ["ラデンです", "またラデン"], [("ラデン", "雷電")])
    assert active_rules(tmp_path, CHARACTER) == []


def test_apply_replaces_longest_first_in_one_pass_and_keeps_word_timing():
    rules = [{"src": "ソピ", "dst": "そぴ"}, {"src": "ソピア", "dst": "そぴあ"}, {"src": "ラデン", "dst": "らでん"}]
    words = [TranscriptWord(start=0, end=1, word="ソ"), TranscriptWord(start=1, end=2, word="ピア"),
             TranscriptWord(start=2, end=3, word=" ラデン"), TranscriptWord(start=3, end=4, word="です")]
    segment = TranscriptSegment(start=0, end=4, text="ソピア ラデンです", words=words)
    assert usable_words(segment.text, segment.words)
    result, applied = apply_rules([segment], rules)
    assert result[0].text == "そぴあ らでんです"
    assert [(a["src"], a["dst"]) for a in applied] == [("ソピア", "そぴあ"), ("ラデン", "らでん")]
    assert usable_words(result[0].text, result[0].words)
    assert result[0].words[0].start == 0 and result[0].words[0].end == 2  # the term spans both original words
    assert [w.word for w in result[0].words] == ["そぴあ", " らでん", "です"]
    assert segment.text == "ソピア ラデンです"  # the input is not modified


def test_apply_does_not_chain_replacements():
    result, _ = apply_rules([TranscriptSegment(start=0, end=1, text="AAB")],
                            [{"src": "AA", "dst": "BB"}, {"src": "BB", "dst": "CC"}])
    assert result[0].text == "BBB"


def test_review_remembers_the_character_and_saving_learns_only_under_outputs(tmp_path):
    review = correct(document("job_1", ["ラデンです", "またラデン"]), [("ラデン", "らでん")])
    assert review.character_preset_name == CHARACTER
    assert json.loads(review.model_dump_json(by_alias=True))["characterPresetName"] == CHARACTER
    write_subtitle_review(review, tmp_path / "elsewhere" / "job_1" / "subtitle_review.json")
    assert not (tmp_path / "subtitle_terms").exists()
    write_subtitle_review(review, tmp_path / "outputs" / "job_1" / "subtitle_review.json")
    assert read_store(tmp_path, CHARACTER)["jobs"]["job_1"]["pairs"] == {"ラデン\tらでん": 2}
    assert document("job_2", ["x"], character=None).character_preset_name is None


def test_runner_applies_rules_and_records_what_it_changed(tmp_path):
    for job in ("job_1", "job_2"):
        learn(tmp_path, job, ["ラデンです", "またラデン"], [("ラデン", "らでん")])
    paths = StoragePaths(tmp_path)
    segments = [TranscriptSegment(start=0, end=2, text="ラデンです"), TranscriptSegment(start=2, end=4, text="別の話")]
    job_dir = tmp_path / "outputs" / "job_3"
    job_dir.mkdir(parents=True)
    result = _apply_learned_subtitle_terms(segments, {"characterPresetName": CHARACTER}, paths, job_dir)
    assert [s.text for s in result] == ["らでんです", "別の話"]
    record = json.loads((job_dir / "learned_subtitle_terms.json").read_text(encoding="utf-8"))
    assert record["applied"] == [{"segmentIndex": 0, "start": 0, "src": "ラデン", "dst": "らでん"}]
    assert _apply_learned_subtitle_terms(segments, {}, paths, job_dir) is segments
    assert _apply_learned_subtitle_terms(segments, {"characterPresetName": "宙科そぴあ"}, paths, job_dir)[0].text == "ラデンです"


def test_applied_text_is_not_a_human_edit(tmp_path):
    for job in ("job_1", "job_2"):
        learn(tmp_path, job, ["ラデンです", "またラデン"], [("ラデン", "らでん")])
    segments, _ = apply_rules([TranscriptSegment(start=0, end=5, text="ラデンです")], active_rules(tmp_path, CHARACTER))
    review = build_subtitle_review("job_3", CandidateSelection(normalClips=[Candidate(
        id="clip", type="normal", start=0, end=5, duration=5, transcript_text="x", title="t")], shorts=[]), segments,
        render_settings={"characterPresetName": CHARACTER})
    assert review.segments[0].text == review.segments[0].original_text == "らでんです" and not review.segments[0].edited
    learn_from_document(review, tmp_path)
    assert "job_3" not in read_store(tmp_path, CHARACTER)["jobs"]


def test_api_lists_rules_and_switches_one_off_with_origin_check(client):  # noqa: F811
    paths = app.dependency_overrides[get_storage_paths]()
    for job in ("job_1", "job_2"):
        learn(paths.root, job, ["ラデンです", "またラデン"], [("ラデン", "らでん")])
    listed = client.get("/api/subtitle-terms").json()
    assert listed[0]["character"] == CHARACTER
    term = listed[0]["terms"][0]
    assert (term["src"], term["dst"], term["active"], term["disabled"]) == ("ラデン", "らでん", True, False)
    url = f"/api/subtitle-terms/{listed[0]['id']}/disable"
    body = {"src": "ラデン", "dst": "らでん"}
    assert client.post(url, json=body, headers={"Origin": "https://evil.example"}).status_code == 403
    assert client.post(url, json={"src": "なし", "dst": "x"}).status_code == 404
    assert client.post("/api/subtitle-terms/unknown/disable", json=body).status_code == 404
    assert client.post(url, json=body).status_code == 204
    assert client.get("/api/subtitle-terms").json()[0]["terms"][0]["disabled"] is True
    assert client.post(url.replace("disable", "enable"), json=body).status_code == 204
    assert client.get("/api/subtitle-terms").json()[0]["terms"][0]["active"] is True
