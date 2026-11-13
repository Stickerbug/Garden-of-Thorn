import app


def test_local_mode_routes_are_registered():
    rules = {rule.rule: rule.methods for rule in app.app.url_map.iter_rules()}
    for path in (
        '/api/story/run/local/start',
        '/api/story/run/local/checkpoint',
        '/api/story/run/local/resume',
        '/api/story/run/local/finish',
    ):
        assert path in rules, path
        assert 'POST' in rules[path], path
    assert '/api/story/run/local/metrics' in rules
    assert 'GET' in rules['/api/story/run/local/metrics']


def test_local_mode_service_is_wired_into_app():
    assert app.story_local is not None
    for name in ('start_run', 'submit_checkpoint', 'resume_run', 'finish_run', 'metrics_snapshot'):
        assert callable(getattr(app.story_local, name)), name
