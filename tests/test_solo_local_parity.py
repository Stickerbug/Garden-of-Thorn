# -*- coding: utf-8 -*-
"""原服务器训练场与浏览器本地运行器的模组和消息口径对照。"""

import json
import unittest

import app
import solo_local_runner as runner


class SoloLocalParityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        disabled = app.runtime_disabled_content('solo')
        runner.initialize(json.dumps({
            'disabled_card_ids': sorted(disabled['cards']),
            'disabled_mod_files': sorted(disabled['mods']),
        }))
        cls.server_loadout = app._cached_official_solo_loadout([])

    def test_official_v2_loadout_hash_matches_server(self):
        self.assertEqual(
            runner.initialize.v2_loadout.loadout_hash,
            self.server_loadout['v2_loadout'].loadout_hash,
        )

    def test_card_ids_match_server_runtime_disables(self):
        server_allowed = set(self.server_loadout['allowed_card_ids'] or [])
        self.assertEqual(set(runner.initialize.allowed_card_ids), server_allowed)

    def test_response_trigger_types_match_server(self):
        for def_id in ('Basic', 'Rose', 'Sewage', 'MagicSewage'):
            card = {'def_id': def_id}
            engine = app.create_solo_engine(['Basic'], ['Basic'], loadout=self.server_loadout)
            self.assertEqual(
                runner._response_trigger_types(engine, card),
                app._response_trigger_types_for_card(engine, card),
            )


if __name__ == '__main__':
    unittest.main()
