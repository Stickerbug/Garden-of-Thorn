from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = (PROJECT_ROOT / 'templates' / 'story.html').read_text(encoding='utf-8')
SCRIPT = (PROJECT_ROOT / 'static' / 'js' / 'story.js').read_text(encoding='utf-8')


def test_cooperative_experiment_template_and_bindings_are_removed():
    for element_id in (
        'story-coop-entry', 'story-coop-preview-dialog', 'story-coop-combat-dialog',
        'story-coop-no-party', 'story-coop-create', 'story-coop-invite-input',
        'story-coop-forming', 'story-coop-members', 'story-coop-start',
        'story-coop-character-select', 'story-coop-active', 'story-coop-enter-combat',
        'story-coop-combat-refresh', 'story-coop-combat-play-selected',
        'story-coop-combat-ready', 'story-coop-combat-close', 'story-coop-setup-panel',
        'story-coop-opening-panel', 'story-coop-reward-panel', 'story-coop-map-panel',
        'story-coop-rest-panel', 'story-coop-chest-panel', 'story-coop-shop-panel',
        'story-coop-event-panel', 'story-coop-complete-panel', 'story-coop-seeded-backdrop',
    ):
        assert f'id="{element_id}"' not in TEMPLATE
    assert '协作故事实验' not in TEMPLATE
    assert "$('story-coop-entry')?.addEventListener" not in SCRIPT
    assert "$('story-coop-preview-dialog')?.addEventListener" not in SCRIPT
    assert "$('story-coop-combat-dialog')?.addEventListener" not in SCRIPT
    assert "$('story-coop-create')?.addEventListener" not in SCRIPT
    assert "$('story-coop-start')?.addEventListener" not in SCRIPT


def test_multiplayer_demo_entry_script_and_api_namespace_remain():
    assert '多人爬塔' in TEMPLATE
    assert 'id="story-coop-demo-entry"' in TEMPLATE
    assert "$('story-coop-demo-entry')?.addEventListener('click', openCoopDemoLobby);" in SCRIPT
    assert "get('coopdemo') === '1'" in SCRIPT
    assert '/api/coop-demo/run' in SCRIPT
    assert '/api/coop-demo/action' in SCRIPT
