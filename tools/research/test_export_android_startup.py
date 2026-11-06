"""Pure local receipt checks; no capture, Android, network or database access."""
import copy
import json
from pathlib import Path
import unittest
from unittest.mock import patch

import export_android_startup as receipt


class SelectionReceiptTests(unittest.TestCase):
    def identity_capture(self, sessions=('private-session',), status=200, player='private-player'):
        requests, responses = b'', b''
        for session in sessions:
            body = json.dumps(dict(session_id=session)).encode()
            reply = json.dumps(dict(player_id=player, username='test')).encode()
            requests += b'POST /session/player-details HTTP/1.1\r\nContent-Length: ' + str(len(body)).encode() + b'\r\n\r\n' + body
            responses += b'HTTP/1.1 ' + str(status).encode() + b' OK\r\nContent-Length: ' + str(len(reply)).encode() + b'\r\n\r\n' + reply
        forward, reverse = ('client', 1234, 'server', 8089), ('server', 8089, 'client', 1234)
        flow = {forward: 'request', reverse: 'response'}
        assembled = {'request': (100, requests, []), 'response': (200, responses, [(200, 200 + len(responses), 100 + len(requests))])}
        return flow, assembled

    def fixture(self):
        account = dict(username='test', player_id='private-player', active_deck_id=0)
        fixture = dict(battle='private-battle', names=['primary', 'peer'], before=dict(accounts=[
            dict(account, username='primary'), dict(account, username='peer')], owned=dict(
                decks=[dict(player_id='private-player', deck_id=0, owned_morty_ids='["private-owned"]')],
                owned_morties=[dict(player_id='private-player', owned_morty_id='private-owned', hp=20)])))
        fixture['observations'] = [dict(action='verify', status=dict(persistent_data_unchanged=True,
            startup=dict(state='CANCELLED', cancel_reason='STARTUP_TIMEOUT', claims_for_battle=0,
                         intent_count=2, retired_intent_count=2, selection_count=2,
                         retired_selection_count=2, pair_count=1, retired_pair_count=1),
            roles=dict(primary=dict(state='WORLD'), peer=dict(state='WORLD'))))]
        return account, fixture

    def role(self):
        return dict(counts={'battle:start': 1, 'native_ready': 1, 'session:end': 1, 'native_login': 1,
                           'native_join': 1, 'session:start': 1, 'native_battle_moves': 1, 'battle:turn-result': 0},
                    clean_eof_observed=True, login_and_join_after_session_end=True, timeline=[dict(
                        kind='http', path='/session/battle/move', type='ATTACK', move_id='AttackOutburst',
                        status=200, success=True, actor_is_local_active=True, session_identity='original')])

    def run_export(self, fixture, role, expect=True):
        root = Path(__file__).resolve().parents[2] / '.research/unit-test-no-capture'
        with patch.object(Path, 'read_text', return_value=json.dumps(fixture)), \
                patch.object(Path, 'write_text') as write, \
                patch.object(receipt, 'analyze', side_effect=lambda *args: copy.deepcopy(role)), \
                patch('builtins.print'):
            receipt.export(root, root / 'receipt.json', expect_selections=expect)
        return json.loads(write.call_args.args[0])

    def test_move_allowlist_excludes_private_identifiers(self):
        account, fixture = self.fixture()
        summary = receipt.move_summary(dict(battle_id=fixture['battle'], type='ATTACK',
            owned_morty_id='private-owned', move_id='AttackOutburst', session_id='private-session'),
            dict(success=True), account, fixture)
        self.assertEqual(summary, dict(battle_id='<shared-battle>', type='ATTACK', move_id='AttackOutburst',
                                      actor_is_local_active=True, success=True))
        self.assertNotIn('private', json.dumps(summary))

    def test_unknown_move_cannot_export_owned_identifier(self):
        account, fixture = self.fixture()
        with self.assertRaisesRegex(AssertionError, 'Unknown native attack'):
            receipt.move_summary(dict(battle_id=fixture['battle'], type='ATTACK',
                owned_morty_id='private-owned', move_id='private-owned'), {}, account, fixture)

    def test_rotated_session_requires_authenticated_capture_identity(self):
        account, _ = self.fixture()
        flow, assembled = self.identity_capture()
        with patch.object(receipt, 'assemble', side_effect=lambda rows: assembled[rows]):
            self.assertEqual(receipt.capture_original_session(flow, account, []), 'private-session')

    def test_identity_rejects_wrong_role_failure_and_ambiguous_sessions(self):
        account, _ = self.fixture()
        for options in (dict(player='wrong-role'), dict(status=401), dict(sessions=('first', 'second'))):
            flow, assembled = self.identity_capture(**options)
            with self.subTest(options=options), patch.object(receipt, 'assemble', side_effect=lambda rows: assembled[rows]), self.assertRaises(AssertionError):
                receipt.capture_original_session(flow, account, [])

    def test_pair_receipt_exports_counts(self):
        _, fixture = self.fixture()
        result = self.run_export(fixture, self.role())
        self.assertEqual(result['database_verification']['retired_pair_count'], 1)
        self.assertIn('HP and PP unchanged', result['scope'])
        self.assertNotIn('private', json.dumps(result))

    def test_pair_requires_no_resolution_single_local_native_action(self):
        _, fixture = self.fixture()
        for mutation in ('result', 'duplicate', 'actor', 'http'):
            role = self.role()
            if mutation == 'result':
                role['counts']['battle:turn-result'] = 1
            elif mutation == 'duplicate':
                role['timeline'].append(copy.deepcopy(role['timeline'][0]))
                role['counts']['native_battle_moves'] = 2
            elif mutation == 'actor':
                role['timeline'][0]['actor_is_local_active'] = False
            else:
                role['timeline'][0]['status'] = 409
            with self.subTest(mutation=mutation), self.assertRaises(AssertionError):
                self.run_export(fixture, role)

    def test_pair_requires_last_verified_retired_pair(self):
        _, fixture = self.fixture()
        for change in ('pair', 'guard'):
            current = copy.deepcopy(fixture)
            last = copy.deepcopy(current['observations'][0])
            if change == 'pair':
                last['status']['startup']['retired_pair_count'] = 0
            else:
                last['status']['persistent_data_unchanged'] = False
            current['observations'].append(last)
            with self.subTest(change=change), self.assertRaises(AssertionError):
                self.run_export(current, self.role())

    def test_default_mode_keeps_old_scope_and_database_schema(self):
        _, fixture = self.fixture()
        role = self.role()
        role['timeline'] = []
        role['counts']['native_battle_moves'] = 0
        del role['counts']['battle:turn-result']
        result = self.run_export(fixture, role, expect=False)
        self.assertNotIn('selection_count', result['database_verification'])
        self.assertEqual(result['scope'], 'Existing native-owned parties on dedicated fresh accounts; no battle completion or wider roster compatibility claimed.')


if __name__ == '__main__':
    unittest.main()
