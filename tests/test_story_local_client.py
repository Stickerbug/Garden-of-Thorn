import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
STORY_HTML = (ROOT / 'templates' / 'story.html').read_text(encoding='utf-8')
STORY_JS = (ROOT / 'static' / 'js' / 'story.js').read_text(encoding='utf-8')
LOCAL_JS = (ROOT / 'static' / 'js' / 'story-local.js').read_text(encoding='utf-8')
WORKER_JS = (ROOT / 'static' / 'story-engine' / 'engine-worker.js').read_text(encoding='utf-8')


class StoryLocalClientContractTests(unittest.TestCase):
    def test_local_module_loads_before_the_story_script(self):
        self.assertIn('story-local.js', STORY_HTML)
        self.assertLess(STORY_HTML.index('story-local.js'), STORY_HTML.index('js/story.js'))

    def test_worker_accepts_step_messages(self):
        self.assertIn('step_in_worker', WORKER_JS)
        self.assertIn("type === 'step'", WORKER_JS)

    def test_story_actions_route_through_the_local_module(self):
        self.assertIn("const STORY_LOCAL_MODE = new URLSearchParams(location.search).get('local') === '1';", STORY_JS)
        self.assertIn('const storyLocalActive = () => STORY_LOCAL_MODE', STORY_JS)
        self.assertIn('async function localStoryAction(', STORY_JS)
        self.assertIn('if (storyLocalActive()) return localStoryAction(', STORY_JS)
        self.assertIn('window.GtnStoryLocal.start(', STORY_JS)

    def test_checkpoints_follow_floors_and_combats(self):
        self.assertIn('function checkpointKind(', LOCAL_JS)
        self.assertIn("return 'combat';", LOCAL_JS)
        self.assertIn("return 'floor';", LOCAL_JS)
        self.assertIn("'/api/story/run/local/checkpoint'", LOCAL_JS)
        self.assertIn('error.status === 409', LOCAL_JS)


if __name__ == '__main__':
    unittest.main()
