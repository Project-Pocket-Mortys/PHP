"""Pure mutation/cleanup guard tests; never starts Compose or touches Android."""
import copy
import json
import unittest

import meeseeks_box_fixture as fixture


class GuardTests(unittest.TestCase):
    def setUp(self):
        self.f = dict(player='player', active='clone', wild='wild', room='room', enemy_hp=1, stock_id=3)
        self.prepared = dict(user=[{'state': 'WORLD'}], morties=[{'owned_morty_id': 'original', 'hp': 20},
                             {'owned_morty_id': 'clone', 'hp': 20}], attacks=[{'pp': 12}],
                             items=[{'id': 3, 'quantity': 8}], decks=[{'party': ['clone', 'original']}])
        self.current = copy.deepcopy(self.prepared)
        self.current['items'][0]['quantity'] = 7
        self.battle = dict(battle_id='battle', player_id='player', player_active_morty='clone',
                           opponent_active_morty='wild', opponent_id='opponent', move_deadline=None,
                           state='COMPLETED', winner='player', opponent_hp=0, player_hp=20)
        self.result = dict(battle_id='battle', outcome='WIN', turn_datas=[dict(type='ITEM',
                           item_id=fixture.ITEM, success=True, owned_morty_id='clone', attacker_player_id='player',
                           defender_player_id='opponent', effect_value=1, attacker_morty_datas=[],
                           defender_morty_datas=[{'owned_morty_id': 'wild', 'hp': 0}])],
                           player_datas={'player': dict(rewards=[], xp_datas=[], attacks_to_learn=[],
                                        owned_items=[{'item_id': fixture.ITEM, 'quantity': 7}])})
        self.events = [self.event('battle:start', battle_start=json.dumps(dict(battle_id='battle', battle_type='PvWM',
                        player={'player_id': 'player'}, opponent={'active_owned_morty': 'wild'}))),
                       self.event('room:wild-morty-state-changed', state='BATTLE', wild_morty_id='wild'),
                       self.event('room:user-state-changed', state='BATTLE'),
                       self.event('battle:move-timer-started', battle_move_timer_started='{"battle_id":"battle"}'),
                       self.event('room:wild-morty-removed', wild_morty_id='wild'),
                       self.event('room:user-state-changed', state='WORLD'),
                       self.event('battle:turn-result', battle_turn_result=json.dumps(self.result))]
        self.native = [dict(path='/session/battle/move/', status=200, response={'success': True}, request=dict(
                            battle_id='battle', type='ITEM', owned_morty_id='clone', move_id=fixture.ITEM))]

    @staticmethod
    def event(name, **kw):
        return dict(event_name=name, room_id='room', player_id='player',
                    only_show_to_player_id='player' if name.startswith('battle:') else None, **kw)

    def validate(self):
        return fixture.validate(self.f, self.prepared, self.current, self.battle, self.events, self.native)

    def test_additive_consumption_leaves_original_stock_and_owned_rows(self):
        self.assertEqual(self.validate(), 1)

    def test_refuses_original_hp_or_ap_change(self):
        for key in ('hp', 'pp'):
            with self.subTest(key=key):
                saved = copy.deepcopy(self.current)
                if key == 'hp':
                    self.current['morties'][0]['hp'] -= 1
                else:
                    self.current['attacks'][0]['pp'] -= 1
                with self.assertRaises(AssertionError):
                    self.validate()
                self.current = saved

    def test_refuses_extra_ai_action_reward_or_double_consumption(self):
        for change in ('ai', 'reward', 'stock'):
            with self.subTest(change=change):
                original = copy.deepcopy(self.events)
                result = copy.deepcopy(self.result)
                if change == 'ai':
                    result['turn_datas'].append({'type': 'ATTACK'})
                elif change == 'reward':
                    result['player_datas']['player']['rewards'] = [{'coins': 1}]
                else:
                    self.current['items'][0]['quantity'] -= 1
                self.events[-1]['battle_turn_result'] = json.dumps(result)
                with self.assertRaises(AssertionError):
                    self.validate()
                self.events = original
                self.current['items'][0]['quantity'] = 7

    def test_refuses_unrelated_state_or_public_terminal_event(self):
        self.events.append(self.event('room:user-state-changed', state='WORLD'))
        with self.assertRaises(AssertionError):
            self.validate()
        self.events.pop()
        self.events[-1]['only_show_to_player_id'] = None
        with self.assertRaises(AssertionError):
            self.validate()

    def test_refuses_wrong_battle_or_actor_http(self):
        self.native[0]['request']['owned_morty_id'] = 'original'
        with self.assertRaises(AssertionError):
            self.validate()


if __name__ == '__main__':
    unittest.main()
