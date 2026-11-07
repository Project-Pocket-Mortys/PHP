"""Pure paired identity and path checks; no database or device access."""
import copy
import unittest

from native_trade_offer_fixture import ACCOUNTS, ROOT, baseline_identity, identity, safe_path


class NativeTradeOfferFixtureTests(unittest.TestCase):
    def snapshot(self):
        return {'users': [{'id': index, 'username': account, 'player_id': f'player-{index}'}
                          for index, account in enumerate(ACCOUNTS)],
                'owned_morties': [{'id': index * 2 + offset, 'player_id': f'player-{index}',
                                  'owned_morty_id': f'morty-{index}-{offset}'}
                                 for index in range(2) for offset in range(2)],
                'trade_offers': []}

    def baseline(self):
        snapshot = self.snapshot()
        return {'version': 1, 'accounts': list(ACCOUNTS), 'snapshot': snapshot,
                'identity': identity(snapshot)}

    def test_identity_is_stable_across_row_order_and_session_changes(self):
        snapshot = self.snapshot()
        changed = copy.deepcopy(snapshot)
        changed['users'].reverse()
        changed['owned_morties'].reverse()
        changed['users'][0]['session_id'] = 'new-session'
        self.assertEqual(identity(snapshot), identity(changed))

    def test_identity_binds_owner_and_instance_rows(self):
        snapshot = self.snapshot()
        for field in ('id', 'owned_morty_id'):
            changed = copy.deepcopy(snapshot)
            changed['owned_morties'][0][field] = 100 if field == 'id' else 'changed'
            self.assertNotEqual(identity(snapshot), identity(changed))
        snapshot['owned_morties'][0]['player_id'] = 'other-owner'
        with self.assertRaises(ValueError):
            identity(snapshot)

    def test_rejects_other_accounts_and_duplicate_instances(self):
        snapshot = self.snapshot()
        snapshot['users'][0]['username'] = 'PMStartup01'
        with self.assertRaises(ValueError):
            identity(snapshot)
        snapshot = self.snapshot()
        snapshot['owned_morties'][0]['owned_morty_id'] = snapshot['owned_morties'][2]['owned_morty_id']
        with self.assertRaises(ValueError):
            identity(snapshot)

    def test_baseline_anchor_cannot_disagree_with_private_snapshot(self):
        baseline = self.baseline()
        self.assertEqual(baseline_identity(baseline), baseline['identity'])
        baseline['snapshot']['users'][0]['id'] = 'different-user-row'
        with self.assertRaises(ValueError):
            baseline_identity(baseline)

    def test_peer_request_and_friendship_allowed_but_no_primary_baseline_offer(self):
        baseline = self.baseline()
        baseline['snapshot']['trades'] = [{'player_id': 'player-1'}]
        baseline['snapshot']['friend_list'] = [{'player_id_a': 'player-0', 'player_id_b': 'player-1'}]
        baseline['snapshot']['trade_offers'] = [{'player_id': 'player-1'}]
        baseline_identity(baseline)
        baseline['snapshot']['trade_offers'].append({'player_id': 'player-0'})
        with self.assertRaises(ValueError):
            baseline_identity(baseline)

    def test_receipts_remain_under_research(self):
        for path in (ROOT, ROOT / 'docs', ROOT / '.research/../tools'):
            with self.subTest(path=path), self.assertRaises(ValueError):
                safe_path(path)
        self.assertEqual(safe_path(ROOT / '.research/pair-test-unused'), ROOT / '.research/pair-test-unused')


if __name__ == '__main__':
    unittest.main()
