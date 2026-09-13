import json

import pytest

from test_api_routes import client as client
from app.candidates.merge_boundaries import Candidate
from app.candidates.select_candidates import CandidateSelection, write_selected_clips
from app.db import get_db
from app.jobs.clip_plan import build_clip_plan, mark_clip_plan_awaiting_review, write_clip_plan
from app.main import app
from app.models import Job
from app.schemas import JobSettings
from app.storage.paths import get_storage_paths


def seed_plan(api, *, normal_count=2, short_count=1, duration=30):
    video = api.post('/api/videos/upload', files={'file': ('test.mp4', b'qa', 'video/mp4')}).json()
    settings = JobSettings(normalClipCount=normal_count, shortCount=short_count).model_dump(by_alias=True)
    created = api.post('/api/jobs', json={'videoId': video['videoId'], 'settings': settings}).json()
    job_id = created['jobId']
    with next(app.dependency_overrides[get_db]()) as db:
        db.get(Job, job_id).status = 'awaiting_clip_review'
        db.commit()
    normal = [Candidate(id=f'normal{i}', type='normal', start=0, end=duration, duration=duration,
                        title=f'title{i}', transcript_text='本文', boundary_refined=False)
              for i in range(normal_count)]
    shorts = [Candidate(id=f'short{i}', type='short', start=40, end=60, duration=20,
                        title=f'short{i}', transcript_text='本文', boundary_refined=False,
                        hook_scene_start=42, hook_scene_end=44) for i in range(short_count)]
    selection = CandidateSelection(normalClips=normal, shorts=shorts)
    document = mark_clip_plan_awaiting_review(
        build_clip_plan(job_id, selection, settings, source_duration=300), preview_clip_ids=[])
    output = app.dependency_overrides[get_storage_paths]().job_outputs(job_id)
    write_clip_plan(document, output / 'clip_plan.json')
    write_selected_clips(selection, output / 'selected_clips.json')
    (output / 'transcript_segments.json').write_text(json.dumps([
        {'start': 1, 'end': 2, 'text': '字幕'}, {'start': 41, 'end': 42, 'text': '別字幕'}
    ]), encoding='utf-8')
    return job_id, output


def test_plan_converts_both_directions_and_passes_type_to_subtitles(client):  # noqa: F811
    job_id, output = seed_plan(client)
    endpoint = f'/api/jobs/{job_id}/clip-plan/clips/normal0/type'
    original = json.loads((output / 'clip_plan.json').read_text(encoding='utf-8'))
    response = client.patch(endpoint, json={'type': 'short'})
    assert response.status_code == 200, response.text
    converted = response.json()['clips'][0]
    assert (converted['id'], converted['type'], converted['title'], converted['start'], converted['end']) == (
        'normal0', 'short', 'title0', 0, 30)
    assert converted['hookSceneStart'] is None
    assert response.json()['clips'][1:] == original['clips'][1:]
    assert client.patch(endpoint, json={'type': 'short'}).status_code == 200
    saved = json.loads((output / 'selected_clips.json').read_text(encoding='utf-8'))
    assert [c['id'] for c in saved['shorts']] == ['short0', 'normal0']
    assert saved['requestedNormalCount'] == 1
    assert saved['requestedShortCount'] == 2
    response = client.patch(endpoint, json={'type': 'normal'})
    assert response.status_code == 200
    assert response.json()['clips'][0]['type'] == 'normal'
    assert client.patch(endpoint, json={'type': 'short'}).status_code == 200
    assert client.post(f'/api/jobs/{job_id}/clip-plan/approve').status_code == 200
    review = json.loads((output / 'subtitle_review.json').read_text(encoding='utf-8'))
    assert {c['id']: c['type'] for c in review['clips']} == {
        'normal0': 'short', 'normal1': 'normal', 'short0': 'short'}
    assert client.patch(endpoint, json={'type': 'normal'}).status_code == 409


@pytest.mark.parametrize('kwargs,clip_id,target', [
    ({'duration': 76}, 'normal0', 'short'),
    ({'short_count': 24}, 'normal0', 'short'),
    ({'normal_count': 12}, 'short0', 'normal'),
])
def test_plan_conversion_rejects_limits_without_mutation(client, kwargs, clip_id, target):  # noqa: F811
    job_id, output = seed_plan(client, **kwargs)
    before = {p: p.read_bytes() for p in [output / 'clip_plan.json', output / 'selected_clips.json']}
    response = client.patch(f'/api/jobs/{job_id}/clip-plan/clips/{clip_id}/type', json={'type': target})
    assert response.status_code == 422, response.text
    assert all(p.read_bytes() == content for p, content in before.items())


def test_completed_plan_cannot_convert_to_short(client):  # noqa: F811
    job_id, output = seed_plan(client)
    before = (output / 'clip_plan.json').read_bytes()
    with next(app.dependency_overrides[get_db]()) as db:
        db.get(Job, job_id).status = 'completed'
        db.commit()
    assert client.patch(f'/api/jobs/{job_id}/clip-plan/clips/normal0/type', json={'type': 'short'}).status_code == 409
    assert (output / 'clip_plan.json').read_bytes() == before
