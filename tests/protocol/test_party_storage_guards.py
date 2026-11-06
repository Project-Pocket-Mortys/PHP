"""Storage writers must not bypass a shared party claim; isolated UUIDs only."""
import json
import unittest
import uuid

import test_friend_battle_party_snapshots as parties
from test_http import post, sql


class PartyStorageGuardTests(unittest.TestCase):
    def setUp(self):
        self.p = parties.FriendBattlePartySnapshotTests(methodName='runTest')
        self.addCleanup(self.p.doCleanups)
        self.p.setUp()
        self.storage = str(uuid.uuid4())
        self.p.ids.append(self.storage)
        sql("INSERT INTO owned_morties (player_id,owned_morty_id,morty_id,hp,hp_stat,is_locked,is_trading_locked) "
            f"VALUES ('{self.p.b}','{self.storage}','MortyDefault',25,100,'false','false')")
        sql(f"INSERT INTO owned_attacks (owned_morty_id,attack_id,position,pp,pp_stat) VALUES ('{self.storage}','AttackLick',0,2,10)")

    def test_both_claimed_users_block_item_lock_preview_and_release(self):
        for actor, living, released in ((self.p.a,self.p.ids[1],self.p.ids[0]),(self.p.b,self.p.ids[2],self.storage)):
            for route, body in [
                ('use-item',dict(owned_morty_id=living,item_id='ItemSerum')),
                ('owned_morties/lock',dict(owned_morty_id=living,is_locked=True)),
                ('owned_morties/attempt-release-multiple',dict(owned_morty_ids=[released])),
                ('owned_morties/release-multiple',dict(owned_morty_ids=[released]))]:
                with self.subTest(actor=actor,route=route):
                    before=self.p.gameplay()
                    self.assertEqual(post('/session/'+route,dict(session_id=actor,**body))[0],409)
                    self.assertEqual(self.p.gameplay(),before)

    def test_cancellation_reopens_item_lock_and_release(self):
        self.assertEqual(self.p.m.cancel(self.p.battle),{'ok':None})
        self.assertEqual(post('/session/use-item',dict(session_id=self.p.b,owned_morty_id=self.p.ids[2],item_id='ItemSerum'))[0],200)
        self.assertEqual(post('/session/owned_morties/lock',dict(session_id=self.p.b,owned_morty_id=self.p.ids[2],is_locked=True))[0],200)
        self.assertEqual(post('/session/owned_morties/release-multiple',dict(session_id=self.p.b,owned_morty_ids=[self.storage]))[0],200)

    def foreign_deck(self):
        sql(f"UPDATE users SET active_deck_id=0 WHERE player_id='{self.p.c}'")
        sql(f"DELETE FROM decks WHERE player_id='{self.p.c}'")
        sql(f"INSERT INTO decks (player_id,deck_id,owned_morty_ids) VALUES ('{self.p.c}',0,{parties.quoted(json.dumps([self.p.ids[1]]))})")

    def test_stale_foreign_deck_cannot_heal_reserved_owned_attacks(self):
        self.foreign_deck()
        before=self.p.gameplay()
        self.assertEqual(post('/session/heal',{'session_id':self.p.c}),(409,{'error':{'code':'FAILED'}}))
        self.assertEqual(self.p.gameplay(),before)

    def test_globally_ambiguous_heal_id_rejects_all_changes(self):
        self.foreign_deck()
        sql(f"INSERT INTO owned_morties (player_id,owned_morty_id,morty_id,hp,hp_stat) VALUES ('{self.p.c}','{self.p.ids[1]}','MortyDefault',1,50)")
        before=self.p.gameplay()
        self.assertEqual(post('/session/heal',{'session_id':self.p.c}),(409,{'error':{'code':'FAILED'}}))
        self.assertEqual(self.p.gameplay(),before)


if __name__=='__main__':
    unittest.main()
