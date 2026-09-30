
import pytest

from test_api_routes import client as client
from test_clip_plan_type_conversion import seed_plan
from app.db import get_db
from app.jobs.clip_plan import load_clip_plan, write_clip_plan
from app.jobs.queue import get_enqueue_clip_plan_boundary_update, get_enqueue_clip_plan_hook_scene_update
from app.main import app
from app.models import Job, Video


def editable_plan(api, *, manual=False, clip_type='normal', duration=30, short_max=75):
    job_id, output = seed_plan(api, normal_count=1, short_count=1, duration=duration, short_max=short_max)
    document = load_clip_plan(output / 'clip_plan.json')
    document.source_duration = 1000
    if manual:
        document.state = 'manual_editing'
        document.settings['workflowMode'] = 'manual'
    with next(app.dependency_overrides[get_db]()) as db:
        job = db.get(Job, job_id)
        db.get(Video, job.video_id).duration = 1000
        if manual:
            job.status = 'awaiting_manual_edit'
            job.settings_json = {**job.settings_json, 'workflowMode': 'manual'}
        db.commit()
    if clip_type == 'short':
        clip = document.clips[1]
        clip.start, clip.end, clip.duration = 0, duration, duration
        clip.hook_scene_start = clip.hook_scene_end = None
    write_clip_plan(document, output / 'clip_plan.json')
    return job_id, output


@pytest.mark.parametrize('action', ['create', 'update', 'boundary'])
@pytest.mark.parametrize('duration,valid', [(89, False), (90, True), (600, True), (601, False)])
def test_normal_adjustment_endpoints(client, action, duration, valid):  # noqa: F811
    job_id, output = editable_plan(client, manual=action != 'boundary')
    before = (output / 'clip_plan.json').read_bytes()
    queued = []
    app.dependency_overrides[get_enqueue_clip_plan_boundary_update] = lambda: lambda *args: queued.append(args)
    prefix = f'/api/jobs/{job_id}/clip-plan/clips'
    if action == 'create':
        response = client.post(prefix, json={'type': 'normal', 'start': 0, 'end': duration})
    elif action == 'update':
        response = client.patch(prefix + '/normal0', json={'type': 'normal', 'start': 0, 'end': duration})
    else:
        response = client.patch(prefix + '/normal0/boundary', json={'start': 0, 'end': duration})
    assert response.status_code == ({'create': 201, 'update': 200, 'boundary': 202}[action] if valid else 422), response.text
    if not valid:
        assert '通常切り抜きは90秒〜10分' in response.json()['detail']
        assert (output / 'clip_plan.json').read_bytes() == before
        assert queued == []
    elif action == 'boundary':
        assert len(queued) == 1  # old 30s clip may be repaired to a valid proposed range


@pytest.mark.parametrize('action', ['create', 'update', 'boundary'])
@pytest.mark.parametrize('duration,valid', [(0.5, True), (75, True), (75.001, False)])
def test_short_adjustment_endpoints(client, action, duration, valid):  # noqa: F811
    job_id, _output = editable_plan(client, manual=action != 'boundary', clip_type='short', duration=76)
    app.dependency_overrides[get_enqueue_clip_plan_boundary_update] = lambda: lambda *args: None
    prefix = f'/api/jobs/{job_id}/clip-plan/clips'
    if action == 'create':
        response = client.post(prefix, json={'type': 'short', 'start': 0, 'end': duration})
    elif action == 'update':
        response = client.patch(prefix + '/short0', json={'type': 'short', 'start': 0, 'end': duration})
    else:
        response = client.patch(prefix + '/short0/boundary', json={'start': 0, 'end': duration})
    assert response.status_code == ({'create': 201, 'update': 200, 'boundary': 202}[action] if valid else 422), response.text


@pytest.mark.parametrize('duration,valid', [(89, False), (90, True), (600, True), (601, False)])
def test_type_change_checks_target_normal_duration(client, duration, valid):  # noqa: F811
    job_id, output = editable_plan(client, clip_type='short', duration=duration)
    before = (output / 'clip_plan.json').read_bytes()
    response = client.patch(f'/api/jobs/{job_id}/clip-plan/clips/short0/type', json={'type': 'normal'})
    assert response.status_code == (200 if valid else 422), response.text
    if not valid:
        assert (output / 'clip_plan.json').read_bytes() == before


@pytest.mark.parametrize('duration,valid', [(75, True), (76, False), (0.5, True)])
def test_type_change_checks_target_short_duration(client, duration, valid):  # noqa: F811
    job_id, _output = editable_plan(client, duration=duration)
    response = client.patch(f'/api/jobs/{job_id}/clip-plan/clips/normal0/type', json={'type': 'short'})
    assert response.status_code == (200 if valid else 422), response.text


@pytest.mark.parametrize('hook_end,valid', [(3, True), (3.001, False)])
def test_hook_scene_total_duration(client, hook_end, valid):  # noqa: F811
    job_id, output = editable_plan(client, clip_type='short', duration=73)
    queued = []
    app.dependency_overrides[get_enqueue_clip_plan_hook_scene_update] = lambda: lambda *args: queued.append(args)
    before = (output / 'clip_plan.json').read_bytes()
    response = client.patch(f'/api/jobs/{job_id}/clip-plan/clips/short0/hook-scene', json={'start': 1, 'end': hook_end})
    assert response.status_code == (202 if valid else 422), response.text
    assert len(queued) == int(valid)
    if not valid:
        assert 'ショートは75秒以内' in response.json()['detail']
        assert (output / 'clip_plan.json').read_bytes() == before


def test_removing_hook_repairs_legacy_over_cap_clip(client):  # noqa: F811
    job_id, output = editable_plan(client, manual=True, clip_type='short', duration=74)
    doc = load_clip_plan(output / 'clip_plan.json')
    doc.clips[1].hook_scene_start, doc.clips[1].hook_scene_end = 1, 3
    write_clip_plan(doc, output / 'clip_plan.json')
    response = client.patch(f'/api/jobs/{job_id}/clip-plan/clips/short0/hook-scene', json={'start': None, 'end': None})
    assert response.status_code == 202, response.text
    assert load_clip_plan(output / 'clip_plan.json').clips[1].hook_scene_start is None


def test_get_and_retry_accept_persisted_out_of_range_settings(client):  # noqa: F811
    job_id, _output = seed_plan(client)
    legacy = {'normalMinDuration': 20, 'normalMaxDuration': 800, 'shortMinDuration': 400, 'shortMaxDuration': 300}
    with next(app.dependency_overrides[get_db]()) as db:
        job = db.get(Job, job_id)
        job.status, job.error_code = 'failed', 'no_usable_selection'
        job.settings_json = {**job.settings_json, **legacy}
        db.commit()
    assert client.get(f'/api/jobs/{job_id}').status_code == 200
    assert client.get(f'/api/jobs/{job_id}/clip-plan').status_code == 200
    retry = client.post(f'/api/jobs/{job_id}/retry')
    assert retry.status_code == 202, retry.text
    with next(app.dependency_overrides[get_db]()) as db:
        source, child = db.get(Job, job_id), db.get(Job, retry.json()['jobId'])
        assert all(source.settings_json[key] == child.settings_json[key] == value for key, value in legacy.items())


def test_boundary_reedit_from_subtitles_uses_same_duration_rules(client):  # noqa: F811
    from app.candidates.select_candidates import CandidateSelection
    from app.jobs.subtitle_review import build_subtitle_review, write_subtitle_review
    job_id, output = editable_plan(client)
    selection = CandidateSelection.model_validate_json((output / 'selected_clips.json').read_text(encoding='utf-8'))
    write_subtitle_review(build_subtitle_review(job_id, selection, []), output / 'subtitle_review.json')
    plan = load_clip_plan(output / 'clip_plan.json')
    plan.state = 'approved'
    write_clip_plan(plan, output / 'clip_plan.json')
    with next(app.dependency_overrides[get_db]()) as db:
        db.get(Job, job_id).status = 'awaiting_subtitle_review'
        db.commit()
    reopened = client.post(f'/api/jobs/{job_id}/subtitle-review/reopen-clip-plan')
    assert reopened.status_code == 200, reopened.text
    assert client.get(f'/api/jobs/{job_id}/clip-plan').json()['boundaryReedit'] is True
    queued = []
    app.dependency_overrides[get_enqueue_clip_plan_boundary_update] = lambda: lambda *args: queued.append(args)
    url = f'/api/jobs/{job_id}/clip-plan/clips/normal0/boundary'
    assert client.patch(url, json={'start': 0, 'end': 89}).status_code == 422
    assert client.patch(url, json={'start': 0, 'end': 90}).status_code == 202
    assert len(queued) == 1
