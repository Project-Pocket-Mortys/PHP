"""Pure contract checks; no emulator, network, database or private files."""
import copy
import json
from pathlib import Path
import unittest
from unittest.mock import patch

import sanitize_native_trade_cancellation as proof


class NativeTradeProofTests(unittest.TestCase):
    def setUp(self):
        self.user = dict(player_id='private-player', session_id='private-session', coupons=3)
        self.trade = dict(trade_id='private-trade')
        self.before = dict(owned_morties=[dict(owned_morty_id='private-spare')])
        def exchange(path, request, response, ordinal):
            return dict(path=path, request=request, response=response,
                        headers={'cookie': 'session_id=private-session'},
                        request_packet_index=ordinal, response_packet_index=ordinal + 1)
        self.rows = [
            exchange('/trading/request-morty', dict(session_id='private-session',
                player_id='private-player', owned_morty_id='private-spare',
                requested_morty_id='any', request_variant='Normal', is_free_trade=True),
                dict(error='None', coupons=3, trade=dict(trade_id='private-trade',
                    player_id='private-player', morty_trade_id='private-spare',
                    morty_request='any', request_variant='Normal', is_free_trade=True,
                    _created='private-time')), 0),
            exchange('/session/player-details', dict(session_id='private-session', include=['morties']),
                dict(player_id='private-player', coupons=3, owned_morties=[dict(
                    owned_morty_id='private-spare', is_locked=False, is_trading_locked=True)]), 2),
            exchange('/trading/cancel-trade', dict(trade_id='private-trade'), dict(error='None'), 4),
            exchange('/trading/get-trades', dict(session_id='private-session', player_id='private-player'),
                dict(completed_trades=[], trade_attacks=[], trade_mortys=[], trade_offers=[],
                     trade_requests=[], player_cooldown_data=dict(expiry=None, trades=0)), 6),
            exchange('/session/player-details', dict(session_id='private-session', include=['morties']),
                dict(player_id='private-player', coupons=3, owned_morties=[dict(
                    owned_morty_id='private-spare', is_locked=False, is_trading_locked=False)]), 8),
        ]

    def inspect(self, rows=None):
        with patch.object(proof, 'read_fixture', return_value=(
                self.user, 'private-spare', self.trade, self.before, {})), \
             patch.object(proof, 'exchanges', return_value=self.rows if rows is None else rows), \
             patch.object(proof, 'digest', return_value='0' * 64):
            return proof.inspect(Path('unused'), Path('unused'))

    def test_valid_output_contains_no_private_values(self):
        result = self.inspect()
        text = json.dumps(result)
        for value in ('private-player', 'private-session', 'private-spare', 'private-trade', 'private-time'):
            self.assertNotIn(value, text)
        self.assertEqual(result['proof']['trading_lock_details_response_sequence'], [True, False])
        self.assertFalse(result['confirmed_pre_fix_gap']['captured_response_proves_fixed_query'])

    def test_tampered_wire_evidence_fails_closed(self):
        cases = [
            lambda r: r[0]['request'].update(session_id='foreign'),
            lambda r: r[0]['request'].update(extra='unexpected'),
            lambda r: r[0]['request'].update(is_free_trade=1),
            lambda r: r[0]['response']['trade'].update(trade_id='foreign'),
            lambda r: r[2]['request'].update(trade_id='foreign'),
            lambda r: r[2]['request'].update(session_id='unexpected'),
            lambda r: r[2]['headers'].update(cookie='session_id=foreign'),
            lambda r: r[4]['response']['owned_morties'][0].update(is_trading_locked='false'),
            lambda r: r[4]['response']['owned_morties'][0].update(owned_morty_id='foreign'),
            lambda r: r[1].update(response_packet_index=10),
            lambda r: r[4].update(request_packet_index=3),
            lambda r: r[3]['response']['trade_offers'].append({}),
            lambda r: r[3]['response']['player_cooldown_data'].update(expiry='now-fixed'),
        ]
        for number, mutate in enumerate(cases):
            with self.subTest(case=number):
                rows = copy.deepcopy(self.rows)
                mutate(rows)
                with self.assertRaises(ValueError):
                    self.inspect(rows)

    def cooldown(self, expiry='private-expiry', count=1):
        row = copy.deepcopy(self.rows[3])
        row['response']['player_cooldown_data'] = dict(expiry=expiry, trades=count)
        created = {'snapshot': {'users': [{'expiry_trade': 'private-expiry'}]}}
        with patch.object(proof, 'read_fixture', return_value=(
                self.user, 'private-spare', self.trade, self.before, {})), \
             patch.object(proof, 'exchanges', return_value=[row]), \
             patch.object(proof, 'digest', return_value='0' * 64), \
             patch.object(Path, 'read_text', return_value=json.dumps(created)):
            return proof.inspect_cooldown(Path('unused'), Path('unused'))

    def test_post_fix_cooldown_projection_and_redaction(self):
        result = self.cooldown()
        self.assertTrue(result['cooldown_expiry_equals_retained_db_expiry'])
        self.assertTrue(result['cooldown_count_is_integer_one'])
        self.assertFalse(result['gui_behavior_proved'])
        for value in ('private-player', 'private-session', 'private-expiry'):
            self.assertNotIn(value, json.dumps(result))

    def test_post_fix_cooldown_tampering_rejected(self):
        for expiry, count in [('foreign', 1), (None, 1), ('private-expiry', 0),
                              ('private-expiry', True), ('private-expiry', '1')]:
            with self.subTest(expiry=expiry, count=count):
                with self.assertRaises(ValueError):
                    self.cooldown(expiry, count)


if __name__ == '__main__':
    unittest.main()
