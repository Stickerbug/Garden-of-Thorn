# -*- coding: utf-8 -*-
"""乱中有序：40 张自组卡组、无天赋选卡与全卡放逐。"""

import gc
import os
import sqlite3
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock

import app
from cards import CARD_DEFS, CardInstance
import db
from game_engine import EquipmentInstance, GameEngine
import ordered_decks


POSITIVE_IDS = [
    card_id for card_id, card_def in CARD_DEFS.items()
    if str(getattr(card_def, 'card_type', '') or '') != 'root'
    and int(getattr(card_def, 'count', 0) or 0) > 0
]
POSITIVE_ID = 'Basic' if 'Basic' in POSITIVE_IDS else POSITIVE_IDS[0]
EQUIPMENT_IDS = [
    card_id for card_id, card_def in CARD_DEFS.items()
    if str(getattr(card_def, 'card_type', '') or '') == 'root'
    and int(getattr(card_def, 'count', 0) or 0) > 0
]
EQUIPMENT_ID = EQUIPMENT_IDS[0]
ZERO_WEIGHT_ID = next(
    card_id for card_id, card_def in CARD_DEFS.items()
    if int(getattr(card_def, 'count', 0) or 0) <= 0
)
VALID_DECK = (POSITIVE_IDS[:14] * 3)[:ordered_decks.ORDERED_DECK_SIZE]


class OrderedDeckRuleTests(unittest.TestCase):
    def test_exact_size_zero_weight_and_equipment_limit(self):
        self.assertEqual(ordered_decks.validate_ordered_cards(VALID_DECK), '')
        self.assertIn('40', ordered_decks.validate_ordered_cards(VALID_DECK[:-1]))
        zero_deck = [POSITIVE_ID] * 39 + [ZERO_WEIGHT_ID]
        self.assertIn('权重为0', ordered_decks.validate_ordered_cards(zero_deck))
        six_equipment = [EQUIPMENT_IDS[0]] * 3 + [EQUIPMENT_IDS[1]] * 3 + VALID_DECK[:34]
        self.assertIn('最多5', ordered_decks.validate_ordered_cards(six_equipment))
        five_equipment = [EQUIPMENT_IDS[0]] * 3 + [EQUIPMENT_IDS[1]] * 2 + VALID_DECK[:35]
        self.assertEqual(ordered_decks.validate_ordered_cards(five_equipment), '')

    def test_copy_limit_and_sewage_exception(self):
        over_limit = [POSITIVE_ID] * 4 + VALID_DECK[:36]
        self.assertIn('每种卡最多3张', ordered_decks.validate_ordered_cards(over_limit))
        self.assertEqual(ordered_decks.validate_ordered_cards(['Sewage'] * 40), '')

    def test_code_roundtrip_and_mode_separation(self):
        code = ordered_decks.encode_ordered_deck('测试卡组', VALID_DECK)
        self.assertTrue(code.startswith('O'))
        decoded, error = ordered_decks.decode_ordered_deck(code)
        self.assertIsNone(error)
        self.assertEqual(decoded['cards'], VALID_DECK)
        self.assertIsNone(decoded['opening_event_id'])
        fancy_code = __import__('fancy_decks').encode_fancy_deck('旧模式', [POSITIVE_ID] * 15, None)
        decoded, error = ordered_decks.decode_ordered_deck(fancy_code)
        self.assertIsNone(decoded)
        self.assertIn('无效', error)

    def test_crud_and_active_slot(self):
        conn = sqlite3.connect(':memory:')
        conn.row_factory = sqlite3.Row
        try:
            result, error = ordered_decks.save_ordered_deck_conn(
                conn, 7, 1, '一', VALID_DECK, True,
            )
            self.assertIsNone(error)
            self.assertTrue(result['saved'])
            result, error = ordered_decks.save_ordered_deck_conn(
                conn, 7, 2, '二', VALID_DECK, True,
            )
            self.assertIsNone(error)
            active = ordered_decks.get_active_ordered_deck_conn(conn, 7)
            self.assertEqual(active['slot'], 2)
            self.assertEqual(len(active['cards']), 40)
            ordered_decks.delete_ordered_deck_conn(conn, 7, 2)
            self.assertIsNone(ordered_decks.get_active_ordered_deck_conn(conn, 7))
        finally:
            conn.close()

    def test_clear_all_ordered_decks(self):
        conn = sqlite3.connect(':memory:')
        conn.row_factory = sqlite3.Row
        try:
            for slot in (1, 2):
                _, error = ordered_decks.save_ordered_deck_conn(
                    conn, 7, slot, f'卡组{slot}', VALID_DECK, slot == 2,
                )
                self.assertIsNone(error)
            self.assertEqual(ordered_decks.clear_ordered_decks_conn(conn), 2)
            self.assertEqual(ordered_decks.list_ordered_decks_conn(conn, 7), [])
        finally:
            conn.close()


class OrderedDeckApiTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.old_db_path = db.DB_PATH
        db.DB_PATH = os.path.join(self.temp_dir.name, 'ordered.sqlite3')
        db.init_db()
        app.app.config.update(TESTING=True)
        self.client = app.app.test_client()
        self.auth = mock.patch.object(
            app, '_require_account_json', return_value=(123, 'tester', None),
        )
        self.auth.start()

    def tearDown(self):
        self.auth.stop()
        db.release_wal_keeper()
        db.DB_PATH = self.old_db_path
        gc.collect()
        self.temp_dir.cleanup()

    def test_save_list_and_code_api(self):
        saved = self.client.post('/api/ordered-decks', json={
            'slot': 1, 'name': 'API卡组', 'cards': VALID_DECK, 'active': True,
        })
        self.assertEqual(saved.status_code, 200, saved.get_json())
        listed = self.client.get('/api/ordered-decks').get_json()
        self.assertEqual(listed['decks'][0]['cards'], VALID_DECK)
        self.assertTrue(listed['decks'][0]['active'])
        encoded = self.client.post('/api/ordered-decks/code', json={
            'action': 'encode', 'name': 'API卡组', 'cards': VALID_DECK,
        }).get_json()
        self.assertTrue(encoded['code'].startswith('O'))
        decoded = self.client.post('/api/ordered-decks/code', json={
            'action': 'decode', 'code': encoded['code'],
        }).get_json()
        self.assertEqual(decoded['deck']['cards'], VALID_DECK)
        rejected = self.client.post('/api/ordered-decks', json={
            'slot': 1, 'cards': [EQUIPMENT_IDS[0]] * 3 + [EQUIPMENT_IDS[1]] * 3 + [POSITIVE_ID] * 34,
        })
        self.assertEqual(rejected.status_code, 400)


class OrderedMatchTests(unittest.TestCase):
    def test_start_match_loads_decks_without_talents(self):
        room = SimpleNamespace(engine=GameEngine(), player_sids=['ordered-a', 'ordered-b'])
        original_players = dict(app.players)
        app.players.clear()
        app.players.update({
            'ordered-a': {'user_id': 101},
            'ordered-b': {'user_id': 202},
        })
        try:
            with (
                mock.patch.object(app, 'get_db_connection', return_value=mock.MagicMock()),
                mock.patch.object(
                    app.ordered_decks, 'get_active_ordered_deck_conn',
                    side_effect=lambda conn, uid: {'cards': VALID_DECK, 'active': True},
                ),
                mock.patch.object(app, 'record_room_replay_keyframe'),
                mock.patch.object(app, '_fancy_start_game', return_value=True) as start_game,
            ):
                self.assertTrue(app._ordered_start_match(room))
            self.assertEqual(room.engine.draft_picks, [VALID_DECK, VALID_DECK])
            self.assertEqual(room.engine.opening_event_picks, [None, None])
            self.assertEqual(room.engine.player_ready, [True, True])
            self.assertTrue(room.engine._ordered_all_exile)
            self.assertTrue(room.engine._ordered_skip_opening_events)
            start_game.assert_called_once_with(room)
        finally:
            app.players.clear()
            app.players.update(original_players)

    def test_engine_skips_opening_events_and_exiles_initial_and_created_cards(self):
        engine = GameEngine()
        engine.allowed_card_ids = set(VALID_DECK)
        engine.draft_picks = [list(VALID_DECK), list(VALID_DECK)]
        engine.opening_event_options = [[], []]
        engine.opening_event_picks = [None, None]
        engine.opening_event_sub_choices = [{}, {}]
        engine.player_draft_started = [True, True]
        engine.player_ready = [True, True]
        engine._ordered_all_exile = True
        engine._ordered_skip_opening_events = True
        with mock.patch.object(
            engine, '_apply_opening_event', side_effect=AssertionError('不应触发天赋'),
        ):
            self.assertTrue(engine.start_game(skip_pregame_validation=True, mulligan=False))
        for player in engine.players:
            self.assertEqual(len(player.hand) + len(player.deck), 40)
            self.assertTrue(all(
                'exile' in card.instance_flags for card in [*player.hand, *player.deck]
            ))
        created = CardInstance(POSITIVE_ID)
        engine._remember_created_card(created)
        self.assertIn('exile', created.instance_flags)
        entering = CardInstance(POSITIVE_ID)
        entering.instance_flags.clear()
        engine._handle_card_enter_hand(0, entering)
        self.assertIn('exile', entering.instance_flags)
        self.assertIn('exile', engine._effective_card_flags(entering))
        self.assertEqual(engine.opening_event_picks, [None, None])

    def test_destroyed_exile_equipment_enters_exile_instead_of_discard(self):
        engine = GameEngine()
        engine._ordered_all_exile = True
        equipment = EquipmentInstance(CardInstance(EQUIPMENT_ID), 0)
        equipment.card_instance.instance_flags.clear()
        engine.players[0].equipment.append(equipment)
        self.assertTrue(engine._destroy_equipment(0, equipment, check_protection=False))
        self.assertIn(equipment.card_instance, engine.players[0].exile)
        self.assertNotIn(equipment.card_instance, engine.players[0].discard)

        ordinary_engine = GameEngine()
        ordinary = EquipmentInstance(CardInstance(EQUIPMENT_ID), 0)
        ordinary.card_instance.instance_flags.clear()
        ordinary_engine.players[0].equipment.append(ordinary)
        self.assertTrue(ordinary_engine._destroy_equipment(0, ordinary, check_protection=False))
        self.assertIn(ordinary.card_instance, ordinary_engine.players[0].discard)
        self.assertNotIn(ordinary.card_instance, ordinary_engine.players[0].exile)


if __name__ == '__main__':
    unittest.main()
