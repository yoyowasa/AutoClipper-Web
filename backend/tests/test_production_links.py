from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError

import app.db as app_db
import app.intelligence.production_links as links
import app.intelligence.sync as sync
import app.production_records as records
from app.intelligence.models import Channel, ProductionLink, YouTubeVideo
from app.intelligence.production_catalog import normalize_title
from app.intelligence.youtube_client import YouTubeClient
from app.maintenance import delete_jobs
from app.models import Video
from app.storage.json_io import write_json_atomic
from test_api_routes import client as client
from test_intelligence import CHANNEL_ID, enqueue, transport
from test_intelligence import environment as environment
from test_production_records import example as example

CREATED = datetime(2026, 10, 1, tzinfo=UTC)
BASE = "/api/intelligence/production-links"


def record(paths, id="exp_one", title="題材の話", previous=None, revision=1, created=CREATED):
    item = records.ProductionRecord(recordId=id, revision=revision, previousRecordId=previous,
        createdAt=created, updatedAt=created + timedelta(days=revision), jobId="job_example", type="short",
        publicationTitle=title, titleCandidates=records.RecordTitles(), bodyDurationSeconds=60, completedDurationSeconds=63,
        source=records.RecordSource(), selection=records.RecordSelection(score=1), thumbnail=records.RecordThumbnail(source="unknown"))
    write_json_atomic(paths.production_record(id), item.model_dump(mode="json"))
    return item


def video(db, id="video000001", title="題材の話", published=None):
    if not db.get(Channel, 1):
        db.add(Channel(id=1, external_id=CHANNEL_ID))
        db.flush()
    item = YouTubeVideo(id=id, channel_id=1, title=title, published_at=published or CREATED.replace(tzinfo=None) + timedelta(days=1))
    db.add(item)
    db.commit()
    return item


def test_normalization():
    assert normalize_title("  ＡＢＣ　１２３\n\t 題材  ") == "ABC 123 題材"
    assert normalize_title(None) == ""
    assert normalize_title("A:B") != normalize_title("AB")


def test_auto_match_normalized_title_date_and_idempotence(client, environment):
    record(environment.paths, title=" ＡＢＣ　\n 題材 ")
    video(environment.db, title="ABC 題材", published=CREATED.replace(tzinfo=None))
    response = client.post(BASE + "/reconcile")
    assert response.status_code == 200 and response.json()["linkedCount"] == 1
    first = environment.db.get(ProductionLink, "exp_one")
    assert first.mode == "auto" and first.record_id == "exp_one"
    stamp = first.linked_at
    assert client.post(BASE + "/reconcile").json()["linkedCount"] == 1
    environment.db.expire_all()
    assert environment.db.get(ProductionLink, "exp_one").linked_at == stamp


@pytest.mark.parametrize("problem", ["two_videos", "two_records", "too_early", "mismatch", "unknown_date", "unavailable"])
def test_only_unambiguous_one_to_one_matches(client, environment, problem):
    record(environment.paths)
    item = video(environment.db)
    if problem == "two_videos":
        video(environment.db, id="video000002")
    elif problem == "two_records":
        record(environment.paths, id="exp_two")
    elif problem == "too_early":
        item.published_at = CREATED.replace(tzinfo=None) - timedelta(microseconds=1)
    elif problem == "mismatch":
        item.title = "別の題材"
    elif problem == "unknown_date":
        item.published_at = None
    else:
        item.availability = "unavailable_unconfirmed"
    environment.db.commit()
    assert client.post(BASE + "/reconcile").json()["linkedCount"] == 0


@pytest.mark.parametrize("mode", ["auto", "manual", "manual_unlinked"])
def test_new_record_tracks_family_without_overwriting_manual_choice(client, environment, mode):
    record(environment.paths)
    video(environment.db)
    assert client.post(BASE + "/reconcile").status_code == 200
    if mode != "auto":
        target = None if mode == "manual_unlinked" else "video000001"
        assert client.put(BASE + "/exp_one", json={"youtubeVideoId": target}).status_code == 200
    record(environment.paths, id="exp_two", previous="exp_one", revision=2,
           title="題材の話" if mode == "auto" else "新しい題材")
    assert client.post(BASE + "/reconcile").status_code == 200
    environment.db.expire_all()
    item = environment.db.get(ProductionLink, "exp_one")
    assert item.record_id == "exp_two" and item.mode == mode
    assert item.youtube_video_id == (None if mode == "manual_unlinked" else "video000001")
    payload = client.get(BASE).json()
    assert payload["linkedCount"] == (0 if mode == "manual_unlinked" else 1)
    assert payload["unlinkedRecords"][0]["mode"] == "manual_unlinked" if mode == "manual_unlinked" else not payload["unlinkedRecords"]


def test_family_date_uses_first_record_not_new_export_date(client, environment):
    record(environment.paths)
    record(environment.paths, id="exp_two", previous="exp_one", revision=2, created=CREATED + timedelta(days=5))
    video(environment.db, published=CREATED.replace(tzinfo=None) + timedelta(days=1))
    assert client.post(BASE + "/reconcile").json()["links"][0]["recordId"] == "exp_two"


def test_manual_reservation_unlink_and_relink(client, environment):
    record(environment.paths)
    record(environment.paths, id="exp_two", title="別の題材")
    video(environment.db)
    assert client.put(BASE + "/exp_two", json={"youtubeVideoId": "video000001"}).json()["linkedCount"] == 1
    assert client.post(BASE + "/reconcile").json()["links"][0]["familyId"] == "exp_two"
    assert client.put(BASE + "/exp_one", json={"youtubeVideoId": "video000001"}).status_code == 409
    assert client.put(BASE + "/exp_two", json={"youtubeVideoId": None}).json()["linkedCount"] == 0
    assert client.post(BASE + "/reconcile").json()["links"][0]["familyId"] == "exp_one"
    assert client.put(BASE + "/exp_one", json={"youtubeVideoId": None}).json()["linkedCount"] == 0
    assert client.post(BASE + "/reconcile").json()["linkedCount"] == 0
    assert client.put(BASE + "/exp_one", json={"youtubeVideoId": "video000001"}).json()["links"][0]["mode"] == "manual"


def test_ambiguous_auto_link_is_removed_but_manual_is_preserved(client, environment):
    record(environment.paths)
    video(environment.db)
    assert client.post(BASE + "/reconcile").json()["linkedCount"] == 1
    video(environment.db, id="video000002")
    assert client.post(BASE + "/reconcile").json()["linkedCount"] == 0
    assert client.put(BASE + "/exp_one", json={"youtubeVideoId": "video000001"}).status_code == 200
    assert client.post(BASE + "/reconcile").json()["links"][0]["mode"] == "manual"


def test_invalid_records_and_branches_are_not_silently_selected(client, environment):
    record(environment.paths)
    record(environment.paths, id="exp_two", previous="exp_one", revision=2)
    record(environment.paths, id="exp_three", previous="exp_one", revision=3)
    record(environment.paths, id="exp_missing", previous="exp_absent", revision=2)
    environment.paths.production_record("exp_bad").write_text("{", encoding="utf-8")
    video(environment.db)
    result = client.post(BASE + "/reconcile").json()
    assert result["linkedCount"] == 0
    assert {item["reason"] for item in result["issues"]} == {"INVALID_RECORD", "INVALID_LINEAGE", "AMBIGUOUS_LINEAGE"}
    assert client.put(BASE + "/exp_one", json={"youtubeVideoId": "video000001"}).status_code == 409
    record(environment.paths, id="exp_another_family")
    assert client.post(BASE + "/reconcile").json()["linkedCount"] == 0


def test_mutations_check_origin_and_identifiers(client, environment):
    record(environment.paths)
    video(environment.db)
    for method, url, body in [("POST", BASE + "/reconcile", {}), ("PUT", BASE + "/exp_one", {"youtubeVideoId": None})]:
        assert client.request(method, url, json=body, headers={"Origin": "https://untrusted.example"}).status_code == 403
    assert client.put(BASE + "/missing", json={"youtubeVideoId": None}).status_code == 404
    assert client.put(BASE + "/exp_one", json={"youtubeVideoId": "video000009"}).status_code == 404
    assert client.put(BASE + "/exp_one", json={"youtubeVideoId": "bad"}).status_code == 422
    assert client.get(BASE).headers["cache-control"] == "no-store"


def test_existing_link_can_be_released_even_when_record_is_unreadable(client, environment):
    record(environment.paths)
    video(environment.db)
    assert client.post(BASE + "/reconcile").json()["linkedCount"] == 1
    environment.paths.production_record("exp_one").write_text("{", encoding="utf-8")
    assert client.put(BASE + "/exp_one", json={"youtubeVideoId": None}).json()["linkedCount"] == 0
    assert client.post(BASE + "/reconcile").status_code == 200
    environment.db.expire_all()
    assert environment.db.get(ProductionLink, "exp_one").mode == "manual_unlinked"


def test_unique_video_constraint_and_no_export_foreign_key(client, environment):
    record(environment.paths)
    video(environment.db)
    assert client.post(BASE + "/reconcile").status_code == 200
    environment.db.add(ProductionLink(record_family_id="exp_other", record_id="exp_other",
                                      youtube_video_id="video000001", mode="manual"))
    with pytest.raises(IntegrityError):
        environment.db.commit()
    environment.db.rollback()
    foreign_keys = inspect(environment.db.get_bind()).get_foreign_keys("production_links")
    assert [key["referred_table"] for key in foreign_keys] == ["youtube_videos"]


def test_init_db_adds_table_to_existing_database(client, environment, monkeypatch):
    bind = environment.db.get_bind()
    ProductionLink.__table__.drop(bind)
    monkeypatch.setattr(app_db, "engine", bind)
    monkeypatch.setattr(app_db, "settings", environment.config)
    app_db.init_db()
    assert "production_links" in inspect(bind).get_table_names()


@pytest.mark.parametrize("partial", [False, True])
def test_sync_success_and_partial_both_reconcile(client, environment, partial):
    record(environment.paths, title="公開動画")
    run_id = enqueue(client, environment)
    def mocked(request):
        if partial and request.url.params.get("filters"):
            return httpx.Response(500, json={"error": {"errors": [{"reason": "internalError"}]}})
        return transport(request)
    sync.run_youtube_sync(run_id, session_factory=environment.factory, paths=environment.paths,
                         client=YouTubeClient("synthetic", transport=httpx.MockTransport(mocked), sleep=lambda _: None))
    assert client.get(BASE).json()["linkedCount"] == 0  # video was published before this record.
    item = environment.db.get(YouTubeVideo, "video000001")
    item.published_at = CREATED.replace(tzinfo=None) + timedelta(days=1)
    environment.db.commit()
    # Match a September export on the next successful/partial run.
    record(environment.paths, title="公開動画", created=CREATED - timedelta(days=40))
    next_id = client.post("/api/intelligence/channels/1/sync").json()["id"]
    sync.run_youtube_sync(next_id, session_factory=environment.factory, paths=environment.paths,
                         client=YouTubeClient("synthetic", transport=httpx.MockTransport(mocked), sleep=lambda _: None))
    assert client.get(BASE).json()["linkedCount"] == 1


def test_record_publication_links_and_survives_job_deletion(example):
    db, job, export, paths = example
    export_id = export.id
    video(db, title=records.build_production_record(job, export, paths).publicationTitle,
          published=datetime(2030, 1, 1))
    records.record_completed_productions(db, job, paths)
    db.expire_all()
    assert db.get(ProductionLink, export.id).youtube_video_id == "video000001"
    db.get(Video, job.video_id).stored_path = str(paths.root / "uploads" / "source.mp4")
    db.commit()
    delete_jobs(db, paths, [job.id], execute=True)
    assert paths.production_record(export_id).is_file()
    assert db.get(ProductionLink, export_id).youtube_video_id == "video000001"
    links.reconcile(db, paths)
    db.commit()
    assert db.get(ProductionLink, export_id) is not None


def test_reconciliation_failure_does_not_fail_record_or_sync(example, monkeypatch, caplog):
    db, job, export, paths = example
    def fail(*args):
        raise RuntimeError("synthetic-private-error")
    monkeypatch.setattr(links, "reconcile", fail)
    records.record_completed_productions(db, job, paths)
    assert paths.production_record(export.id).is_file() and job.status == "completed"
    assert "reconciliation failed" in caplog.text and "synthetic-private-error" not in caplog.text


def test_sync_stays_successful_when_post_commit_reconciliation_fails(client, environment, monkeypatch, caplog):
    run_id = enqueue(client, environment)
    def fail(*args):
        raise RuntimeError("synthetic-private-error")
    monkeypatch.setattr(links, "reconcile", fail)
    sync.run_youtube_sync(run_id, session_factory=environment.factory, paths=environment.paths,
                         client=YouTubeClient("synthetic", transport=httpx.MockTransport(transport)))
    result = client.get("/api/intelligence/channels").json()["channels"][0]["latestRun"]
    assert result["status"] == "success"
    assert "reconciliation failed" in caplog.text and "synthetic-private-error" not in caplog.text
