import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
APP = (ROOT / 'app.py').read_text(encoding='utf-8')
DB = (ROOT / 'db.py').read_text(encoding='utf-8')
HANDLING_JS = (ROOT / 'static' / 'js' / 'handling.js').read_text(encoding='utf-8')
HANDLING_CSS = (ROOT / 'static' / 'css' / 'handling.css').read_text(encoding='utf-8')


class StoryCheckMonitorTests(unittest.TestCase):
    def test_failure_table_and_queries_exist(self):
        self.assertIn('CREATE TABLE IF NOT EXISTS story_checkpoint_failures', DB)
        self.assertIn('def record_story_checkpoint_failure(', DB)
        self.assertIn('def list_story_checkpoint_failures(', DB)
        self.assertIn('def story_checkpoint_failure_summary(', DB)

    def test_handling_api_uses_the_module_alias(self):
        self.assertIn("@app.route('/api/feedback/handling/story-checkpoints')", APP)
        self.assertIn('db_module.list_story_checkpoint_failures(', APP)
        self.assertIn('db_module.story_checkpoint_failure_summary(', APP)
        self.assertNotIn('\n            items = db.list_story_checkpoint_failures(', APP)

    def test_handling_page_lists_story_check_failures(self):
        self.assertIn('/api/feedback/handling/story-checkpoints?limit=20', HANDLING_JS)
        self.assertIn('爬塔校验失败', HANDLING_JS)
        self.assertIn('hd-story-check', HANDLING_JS)
        self.assertIn('爬塔校验 ${state.storyCheckpointTotal}', HANDLING_JS)
        self.assertIn('hasStoryChecks', HANDLING_JS)
        self.assertIn('.hd-story-check { border-left: 3px solid', HANDLING_CSS)

    def test_reason_labels_cover_every_server_reason(self):
        for reason in ('mismatch', 'invalid_action', 'engine_error'):
            self.assertIn(f'  {reason}:', HANDLING_JS)


if __name__ == '__main__':
    unittest.main()
