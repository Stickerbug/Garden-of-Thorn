"""金露兑换经验的路由与前端接线契约。"""

from __future__ import annotations

import io
import os
import re
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read(*parts):
    with io.open(os.path.join(ROOT, *parts), 'r', encoding='utf-8', newline='') as handle:
        return handle.read()


class BuyPassXpContractTests(unittest.TestCase):
    def test_route_calls_the_service_with_a_transaction(self):
        source = _read('app.py')
        self.assertIn("@app.route('/api/battle-pass/buy-xp', methods=['POST'])", source)
        self.assertIn('def api_battle_pass_buy_xp():', source)
        self.assertIn('purchase, error = battle_pass.buy_xp(conn, uid)', source)
        block = source.split('def api_battle_pass_buy_xp():', 1)[1]
        block = block.split('@app.route', 1)[0]
        self.assertIn("conn.execute('BEGIN IMMEDIATE')", block)
        self.assertIn('conn.commit()', block)
        self.assertIn("'purchase': purchase", block)
        self.assertNotRegex(block, re.compile(r'except\s*:\s*\n\s*pass'))

    def test_panel_renders_a_buy_xp_button(self):
        source = _read('static', 'js', 'battle-pass.js')
        self.assertIn("payload.xp_buy_cost", source)
        self.assertIn("payload.xp_buy_amount", source)
        self.assertIn('class="bp-buy-xp"', source)
        self.assertIn('data-bp-buy-xp="1"', source)
        self.assertIn("`${API_BASE}/buy-xp`", source)
        self.assertIn('ensureSuccess', source)
        self.assertIn('data-bp-buy-xp="1"', source)
        self.assertIn('state.notice', source)

    def test_styles_exist_for_the_button_and_notice(self):
        source = _read('static', 'css', 'battle-pass.css')
        self.assertIn('#achievements-pass-panel .bp-buy-xp {', source)
        self.assertIn('#achievements-pass-panel .bp-buy-xp[disabled] {', source)
        self.assertIn('#achievements-pass-panel .bp-notice {', source)


if __name__ == '__main__':
    unittest.main()
