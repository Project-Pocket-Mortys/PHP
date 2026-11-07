"""Pure synthetic tests: no private receipts, database, emulator or network."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import sanitize_native_trade_offers as proof


class OfferProofTests(unittest.TestCase):
    def setUp(self):
        self.primary = dict(id=1, username='PMTrade01', player_id='secret-primary',
                            session_id='secret-session', active_deck_id='0',
                            coins=10, coupons=3, permits=2, expiry_trade=None)
        self.peer = dict(self.primary, id=2, username='PMTrade02', player_id='secret-peer',
                         session_id='secret-peer-session', expiry_trade='secret-expiry')
        self.spare = dict(id=2, player_id='secret-primary', owned_morty_id='secret-spare',
                          morty_id='MortyDefault', is_locked='false', is_trading_locked='false')
        requested = dict(self.spare, id=4, player_id='secret-peer', owned_morty_id='secret-requested')
        self.parent = dict(trade_id='secret-parent', player_id='secret-peer',
                           morty_trade_id='secret-requested', requested_morty_id='any',
                           request_variant='Normal', is_free_trade=1)
        self.offer = dict(trade_offer_id='secret-offer', player_id='secret-primary',
                          morty_offer_id='secret-spare', trade_id='secret-parent')
        before = dict(users=[self.primary, self.peer], owned_morties=[
            dict(self.spare, id=1, owned_morty_id='secret-party'), self.spare,
            dict(requested, id=3, owned_morty_id='secret-peer-party'), requested],
            owned_attacks=[], owned_items=[], decks=[dict(player_id='secret-primary', deck_id='0',
                owned_morty_ids=json.dumps(['secret-party']))], trades=[self.parent],
            trade_offers=[], completed_trades=[], friend_list=[], event_queue=[], friend_battle_memberships=[])
        self.fixture = dict(primary=self.primary, peer=self.peer, spare=self.spare,
            requested=requested, parent=self.parent, offer=self.offer, before=before, hashes={})
        def row(path, request, response, ordinal):
            return dict(path=path, request=request, response=response, headers={'cookie':'session_id=secret-session'},
                        request_packet_index=ordinal, response_packet_index=ordinal+1)
        returned = dict(self.offer, _created='secret-time', request_user_name='secret-peer',
                        offering_morty_id='MortyDefault', request_morty_id='secret-requested')
        self.rows = [row('/trading/offer-morty', dict(session_id='secret-session', player_id='secret-primary',
            offered_morty_id='secret-spare', trade_request_id='secret-parent'), dict(error='None', offer=returned), 0),
            row('/session/player-details', dict(session_id='secret-session', include=['morties']),
                dict(player_id='secret-primary', coins=10, coupons=3, permits=2, owned_morties=[
                    dict(owned_morty_id='secret-party', is_locked=False, is_trading_locked=False),
                    dict(owned_morty_id='secret-spare', is_locked=False, is_trading_locked=True)]), 2),
            row('/trading/cancel-trade-offer', dict(trade_offer_id='secret-offer'), dict(error='None'), 6)]

    def inspect(self, rows=None, fixed=False):
        with patch.object(proof, 'read_fixture', return_value=self.fixture), \
             patch.object(proof, 'exchanges', return_value=self.rows if rows is None else rows), \
             patch.object(proof, 'digest', return_value='0'*64):
            return proof.inspect(Path('unused'), Path('unused'), fixed)

    def fixed_rows(self):
        rows = copy.deepcopy(self.rows)
        rows[0]['response']['offer'].update(request_user_name='PMTrade02', request_morty_id='MortyDefault')
        listing = dict(path='/trading/get-trades', request=dict(session_id='secret-session', player_id='secret-primary'),
            response=dict(completed_trades=[], trade_requests=[dict(trade_id='secret-parent')],
                          trade_offers=[copy.deepcopy(rows[0]['response']['offer'])]),
            headers={}, request_packet_index=4, response_packet_index=5)
        rows.insert(2, listing)
        return rows

    def test_baseline_and_fixed_have_bounded_redacted_claims(self):
        for result in (self.inspect(), self.inspect(self.fixed_rows(), True)):
            self.assertNotIn('secret-', json.dumps(result))
            self.assertFalse(result['proof']['immediate_native_unlock_proved'])
            self.assertEqual(result['proof']['owned_details_after_cancel_count'], 0)
        self.assertTrue(self.inspect()['gaps']['baseline_username_is_peer_player_id'])
        self.assertEqual(self.inspect(self.fixed_rows(), True)['proof']['metadata_retaining_get_trades_count'], 1)

    def test_identity_cookie_lock_type_order_and_metadata_tampering_rejected(self):
        mutations = [
            lambda r: r[0]['request'].update(player_id='other'),
            lambda r: r[0]['request'].update(extra=True),
            lambda r: r[0]['response']['offer'].update(trade_offer_id='other'),
            lambda r: r[0]['response']['offer'].update(request_user_name='other'),
            lambda r: r[0]['response']['offer'].update(request_morty_id='MortyDefault'),
            lambda r: r[1]['request'].update(session_id='other'),
            lambda r: r[1]['response']['owned_morties'][1].update(is_trading_locked='true'),
            lambda r: r[1]['response']['owned_morties'][1].update(is_trading_locked=1),
            lambda r: r[1]['response']['owned_morties'][1].update(is_trading_locked=False),
            lambda r: r[1].update(response_packet_index=8),
            lambda r: r[2].update(request_packet_index=1),
            lambda r: r[2]['request'].update(session_id='secret-session'),
            lambda r: r[2]['headers'].clear(),
            lambda r: r[2]['headers'].update(cookie='session_id=other'),
            lambda r: r[2]['headers'].update(cookie='session_id=other; session_id=secret-session'),
        ]
        for number, mutate in enumerate(mutations):
            with self.subTest(case=number):
                rows = copy.deepcopy(self.rows)
                mutate(rows)
                with self.assertRaises(ValueError): self.inspect(rows)

    def test_fixed_requires_reload_and_preserved_display_metadata(self):
        rows = self.fixed_rows()
        for field in ('request_user_name', 'offering_morty_id', 'request_morty_id'):
            with self.subTest(field=field):
                changed = copy.deepcopy(rows)
                changed[2]['response']['trade_offers'][0][field] = 'other'
                with self.assertRaises(ValueError): self.inspect(changed, True)
        with self.assertRaises(ValueError): self.inspect([r for r in rows if r['path'] != '/trading/get-trades'], True)

    def documents(self):
        before = copy.deepcopy(self.fixture['before'])
        baseline = copy.deepcopy(before)
        baseline['trades'] = []
        snapshots = [before, copy.deepcopy(before), copy.deepcopy(before), copy.deepcopy(before)]
        snapshots[1]['trade_offers'] = [self.offer]
        snapshots[2]['trade_offers'] = [self.offer]
        def document(snapshot):
            return dict(version=1, accounts=['PMTrade01', 'PMTrade02'], private=True,
                        snapshot=snapshot, identity=proof.identity(snapshot))
        return dict(zip(['baseline', 'observe-before-offer-create', 'observe-offer-created',
            'observe-before-offer-cancel', 'observe-offer-cancelled'], map(document, [baseline] + snapshots)))

    def read_documents(self, documents):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name, document in documents.items():
                (root/(name+'.json')).write_text(json.dumps(document), encoding='utf-8')
            return proof.read_fixture(root)

    def test_fixture_invariants_cover_parent_expiries_resources_and_ownership(self):
        docs = self.documents()
        self.read_documents(docs)
        mutations = [
            lambda s: s['users'][0].update(coins=11),
            lambda s: s['users'][0].update(expiry_trade='changed'),
            lambda s: s['users'][1].update(expiry_trade=None),
            lambda s: s['trades'].clear(),
            lambda s: s['owned_morties'][1].update(player_id='secret-peer'),
            lambda s: s['owned_morties'][1].update(is_trading_locked='true'),
            lambda s: s['decks'][0].update(owned_morty_ids='[]'),
            lambda s: s['completed_trades'].append({}),
        ]
        for number, mutate in enumerate(mutations):
            with self.subTest(case=number):
                changed = copy.deepcopy(docs)
                mutate(changed['observe-offer-created']['snapshot'])
                with self.assertRaises((ValueError, StopIteration)): self.read_documents(changed)

    def wire_packets(self):
        request = b'POST /trading/cancel-trade-offer HTTP/1.1\r\nUser-Agent: UnityApp/2.41.0 (Android)\r\nX-PMClient: synthetic\r\nContent-Length: 2\r\n\r\n{}'
        response = b'HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\n{}'
        key = ('192.0.2.1', 50000, '192.0.2.2', 8087)
        reverse = (key[2], key[3], key[0], key[1])
        return [(key, 100, 1, request), (reverse, 200, 100+len(request), response)]

    def test_parser_requires_exact_unambiguous_ack_and_response_order(self):
        packets = self.wire_packets()
        with patch.object(proof, 'packets', return_value=packets):
            self.assertEqual(len(proof.exchanges(Path('unused'))), 1)
        wrong_ack = copy.deepcopy(packets)
        k, s, a, b = wrong_ack[1]
        wrong_ack[1] = (k, s, a+1, b)
        ambiguous_ack = packets + [(k, s, a+1, b)]
        duplicate_response = packets + [(k, s+len(b), a, b)]
        for changed in (wrong_ack, ambiguous_ack, duplicate_response, list(reversed(packets))):
            with self.subTest(count=len(changed)):
                with patch.object(proof, 'packets', return_value=changed):
                    with self.assertRaises(ValueError): proof.exchanges(Path('unused'))


if __name__ == '__main__':
    unittest.main()
