"""Additive UUID selection-window regressions; no shared account reseeding."""
import base64
import json
import re
import subprocess
import unittest
import urllib.request
import uuid
from concurrent.futures import ThreadPoolExecutor

import test_battle_lifecycle
from test_http import COMPOSE, ROOT, php, post, sql


class BattleTimeoutTests(unittest.TestCase):
    def setUp(self):
        self.f = test_battle_lifecycle.BattleLifecycleTests(methodName='runTest')
        self.f.setUp()
        self.addCleanup(lambda: self.assertTrue(self.f.doCleanups()))

    def ready(self, **changes):
        request = dict(session_id=self.f.session, battle_id=self.f.battle)
        request.update(changes)
        return post('/session/battle/ready', request)

    def due(self):
        sql(f"UPDATE battles SET move_deadline=UTC_TIMESTAMP(6)-INTERVAL 1 SECOND WHERE battle_id='{self.f.battle}'")

    def expire(self):
        return int(php("require '/var/www/html/pocket_f4894h398r8h9w9er8he98he.php'; "
                       "require '/var/www/html/lib/battle_timeouts.php'; "
                       f"echo battle_timeout_expire_player($pdo,'{self.f.player}');"))

    def result(self):
        rows = sql(f"SELECT * FROM event_queue WHERE room_id='{self.f.room}' AND event_name='battle:turn-result'")
        self.assertEqual(len(rows), 1)
        self.assertEqual((rows[0]['player_id'], rows[0]['only_show_to_player_id']), (self.f.player, self.f.player))
        result = json.loads(rows[0]['battle_turn_result'])
        self.assertEqual(result['battle_id'], self.f.battle)
        return result

    def assert_cancelled_preserving_gameplay(self, before, stream_activity=False):
        after = self.f.snapshot()
        for key in ('morties', 'attacks', 'items', 'decks', 'rooms'):
            self.assertEqual(after[key], before[key], key)
        battle = next(b for b in after['battles'] if b['battle_id'] == self.f.battle)
        self.assertEqual(battle['state'], 'CANCELLED')
        self.assertIsNone(battle['winner'])
        self.assertIsNone(battle['move_deadline'])
        old = next(b for b in before['battles'] if b['battle_id'] == self.f.battle)
        for key in ('player_hp', 'opponent_hp', 'player_active_morty', 'opponent_active_morty'):
            self.assertEqual(battle[key], old[key])
        self.f.assert_world(after)
        peer_after = next(u for u in after['users'] if u['player_id'] == self.f.other_player)
        peer_before = next(u for u in before['users'] if u['player_id'] == self.f.other_player)
        if stream_activity:
            for key in ('last_seen', 'last_event_id'):
                peer_after.pop(key, None)
                peer_before.pop(key, None)
        self.assertEqual(peer_after, peer_before)
        owner_after = dict(next(u for u in after['users'] if u['player_id'] == self.f.player))
        owner_before = dict(next(u for u in before['users'] if u['player_id'] == self.f.player))
        for key in ('state', 'last_seen', 'last_event_id'):
            owner_after.pop(key, None)
            owner_before.pop(key, None)
        self.assertEqual(owner_after, owner_before)
        result = self.result()
        self.assertEqual(result['outcome'], 'ABANDONED')
        self.assertEqual(result['turn_datas'], [])
        self.assertIs(result['battle_abandoned'], False)
        self.assertEqual(result['player_datas'], {'player': {}, 'opponent': {}})
        return after

    def test_ready_duplicate_does_not_extend_or_republish(self):
        self.f.begin()
        self.assertEqual(self.ready(), (200, {'success': True}))
        before = self.f.snapshot()
        self.assertEqual(self.ready(), (200, {'success': True}))
        self.assertEqual(self.f.snapshot(), before)
        timers = [e for e in before['events'] if e['event_name'] == 'battle:move-timer-started']
        self.assertEqual(len(timers), 1)
        self.assertEqual(json.loads(timers[0]['battle_move_timer_started']), dict(battle_id=self.f.battle, timeout=30))
        self.assertEqual(timers[0]['only_show_to_player_id'], self.f.player)
        seconds = sql(f"SELECT TIMESTAMPDIFF(SECOND,UTC_TIMESTAMP(6),move_deadline) AS remaining FROM battles WHERE battle_id='{self.f.battle}'")[0]['remaining']
        self.assertGreaterEqual(int(seconds), 25)
        self.assertLessEqual(int(seconds), 30)

    def test_expiry_is_once_preserves_gameplay_and_releases_claim(self):
        self.f.begin()
        self.assertEqual(self.ready()[0], 200)
        self.due()
        before = self.f.snapshot()
        self.assertEqual(self.expire(), 1)
        after = self.assert_cancelled_preserving_gameplay(before)
        self.assertEqual(self.expire(), 0)
        self.assertEqual(self.f.snapshot(), after)
        self.assertEqual(self.f.start(), (200, {'success': True}))

    def test_late_item_never_consumes_or_hits(self):
        self.f.begin()
        sql(f"INSERT INTO owned_items (player_id,item_id,quantity) VALUES ('{self.f.player}','ItemSerum',1)")
        sql(f"UPDATE owned_morties SET hp=50 WHERE owned_morty_id='{self.f.morty}'")
        sql(f"UPDATE battles SET player_hp=50 WHERE battle_id='{self.f.battle}'")
        self.assertEqual(self.ready()[0], 200)
        self.due()
        before = self.f.snapshot()
        self.assertEqual(self.f.move('ITEM', move_id='ItemSerum')[0], 409)
        self.assert_cancelled_preserving_gameplay(before)

    def test_late_attack_never_spends_pp_or_deals_damage(self):
        self.f.begin()
        self.assertEqual(self.ready()[0], 200)
        self.due()
        before = self.f.snapshot()
        self.assertEqual(self.f.move()[0], 409)
        self.assert_cancelled_preserving_gameplay(before)

    def test_late_ready_does_not_rearm(self):
        self.f.begin()
        self.assertEqual(self.ready()[0], 200)
        self.due()
        before = self.f.snapshot()
        self.assertEqual(self.ready()[0], 409)
        after = self.assert_cancelled_preserving_gameplay(before)
        self.assertEqual(self.ready()[0], 409)
        self.assertEqual(self.f.snapshot(), after)

    def test_successful_move_clears_window_next_ready_gets_new_window(self):
        self.f.begin()
        sql(f"UPDATE battles SET opponent_hp=100 WHERE battle_id='{self.f.battle}'")
        self.assertEqual(self.ready()[0], 200)
        first = sql(f"SELECT move_deadline FROM battles WHERE battle_id='{self.f.battle}'")[0]['move_deadline']
        self.assertIsNotNone(first)
        self.assertEqual(self.f.move(), (200, {'success': True}))
        self.assertIsNone(sql(f"SELECT move_deadline FROM battles WHERE battle_id='{self.f.battle}'")[0]['move_deadline'])
        self.assertEqual(self.expire(), 0)
        self.assertEqual(self.ready()[0], 200)
        second = sql(f"SELECT move_deadline FROM battles WHERE battle_id='{self.f.battle}'")[0]['move_deadline']
        self.assertGreater(second, first)

    def test_rejected_move_retains_window(self):
        self.f.begin()
        self.assertEqual(self.ready()[0], 200)
        self.f.assert_rejected_unchanged(lambda: self.f.move(move_id='NotAnAttack'), 400)
        self.f.assert_rejected_unchanged(lambda: self.f.move('ITEM', move_id='ItemMortyChip'), 501)

    def test_no_ready_and_future_deadlines_are_not_expired(self):
        self.f.begin()
        before = self.f.snapshot()
        self.assertEqual(self.expire(), 0)
        self.assertEqual(self.f.snapshot(), before)
        self.assertEqual(self.ready()[0], 200)
        before = self.f.snapshot()
        self.assertEqual(self.expire(), 0)
        self.assertEqual(self.f.snapshot(), before)

    def test_invalid_sessions_and_foreign_ready_cannot_arm_or_expire(self):
        self.f.begin()
        self.f.assert_rejected_unchanged(lambda: self.ready(session_id='missing'), 401)
        self.f.assert_rejected_unchanged(lambda: self.ready(session_id=self.f.other_session), 403)
        self.f.assert_rejected_unchanged(lambda: self.ready(battle_id='missing'), 404)
        self.assertEqual(self.ready()[0], 200)
        self.due()
        self.f.assert_rejected_unchanged(lambda: self.ready(session_id=self.f.other_session), 403)

    def test_ready_preserves_legacy_failure_envelopes(self):
        self.f.begin()
        self.assertEqual(self.ready(battle_id=None), (400, {'success': False, 'error': 'Error'}))
        self.assertEqual(self.ready(session_id='missing'), (401, {'success': False, 'error': 'Not authenticated'}))
        self.assertEqual(self.ready(session_id=self.f.other_session), (403, {'success': False}))
        self.assertEqual(self.ready(battle_id='missing'), (404, {'success': False}))
        sql(f"UPDATE users SET room_id='' WHERE player_id='{self.f.player}'")
        self.assertEqual(self.ready(), (409, {'success': False, 'error': 'Player is not in a room'}))
        sql(f"UPDATE users SET room_id='{self.f.room}' WHERE player_id='{self.f.player}'")
        sql(f"DELETE FROM room_ids WHERE room_id='{self.f.room}'")
        self.assertEqual(self.ready(), (409, {'success': False, 'error': 'Room does not exist', 'room_id': self.f.room}))

    def test_missing_or_conflicting_origin_is_not_guessed(self):
        self.f.begin()
        self.assertEqual(self.ready()[0], 200)
        self.due()
        sql(f"DELETE FROM event_queue WHERE room_id='{self.f.room}' AND event_name='battle:start'")
        before = self.f.snapshot()
        self.assertEqual(self.expire(), 0)
        self.assertEqual(self.f.snapshot(), before)

    def test_conflicting_spawn_claim_is_not_released(self):
        self.f.begin()
        self.assertEqual(self.ready()[0], 200)
        self.due()
        sql(f"INSERT INTO battles (battle_id,player_id,opponent_id,opponent_active_morty,state) VALUES ('{uuid.uuid4()}','{self.f.other_player}','wild','{self.f.wild}','ACTIVE')")
        before = self.f.snapshot()
        self.assertEqual(self.expire(), 0)
        self.assertEqual(self.f.snapshot(), before)

    def test_other_active_battle_for_same_player_is_not_abandoned(self):
        self.f.begin()
        self.assertEqual(self.ready()[0], 200)
        self.due()
        sql(f"INSERT INTO battles (battle_id,player_id,opponent_id,opponent_active_morty,state) VALUES ('{uuid.uuid4()}','{self.f.player}','wild','{uuid.uuid4()}','ACTIVE')")
        before = self.f.snapshot()
        self.assertEqual(self.expire(), 0)
        self.assertEqual(self.f.snapshot(), before)

    def test_missing_room_or_wrong_user_state_cannot_arm(self):
        self.f.begin()
        sql(f"UPDATE users SET state='WORLD' WHERE player_id='{self.f.player}'")
        self.f.assert_rejected_unchanged(self.ready, 409)
        sql(f"UPDATE users SET state='BATTLE' WHERE player_id='{self.f.player}'")
        sql(f"DELETE FROM room_ids WHERE room_id='{self.f.room}'")
        self.f.assert_rejected_unchanged(self.ready, 409)

    def test_timer_insert_failure_rolls_back_arming(self):
        self.f.begin()
        trigger = 'ready_' + uuid.uuid4().hex
        self.addCleanup(lambda: sql(f'DROP TRIGGER IF EXISTS {trigger}'))
        sql(f"CREATE TRIGGER {trigger} BEFORE INSERT ON event_queue FOR EACH ROW BEGIN IF NEW.player_id='{self.f.player}' AND NEW.event_name='battle:move-timer-started' THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='UUID ready rollback'; END IF; END")
        self.f.assert_rejected_unchanged(self.ready, 500)

    def test_stale_candidate_rechecks_database_deadline_even_with_old_snapshot(self):
        self.f.begin()
        self.assertEqual(self.ready()[0], 200)
        before = self.f.snapshot()
        count = php("require '/var/www/html/pocket_f4894h398r8h9w9er8he98he.php'; "
                    "require '/var/www/html/lib/battle_timeouts.php'; $pdo->beginTransaction(); "
                    f"$user=$pdo->query(\"SELECT * FROM users WHERE player_id='{self.f.player}' FOR UPDATE\")->fetch(); "
                    f"$battle=$pdo->query(\"SELECT * FROM battles WHERE battle_id='{self.f.battle}' FOR UPDATE\")->fetch(); "
                    "$battle['move_deadline']='2000-01-01 00:00:00.000000'; "
                    "echo (int)battle_timeout_expire_locked($pdo,$user,$battle); $pdo->commit();")
        self.assertEqual(count, '0')
        self.assertEqual(self.f.snapshot(), before)

    def test_changed_room_is_not_overwritten(self):
        self.f.begin()
        self.assertEqual(self.ready()[0], 200)
        self.due()
        sql(f"UPDATE users SET room_id='{self.f.other_room}' WHERE player_id='{self.f.player}'")
        before = self.f.snapshot()
        self.assertEqual(self.expire(), 0)
        self.assertEqual(self.f.snapshot(), before)

    def test_concurrent_workers_late_move_and_ready_emit_one_terminal(self):
        self.f.begin()
        self.assertEqual(self.ready()[0], 200)
        self.due()
        before = self.f.snapshot()
        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = [executor.submit(self.expire), executor.submit(self.expire),
                       executor.submit(self.f.move), executor.submit(self.ready)]
            outcomes = [future.result() for future in futures]
        self.assertEqual(outcomes[2][0], 409)
        self.assertEqual(outcomes[3][0], 409)
        self.assertLessEqual(sum(outcomes[:2]), 1)
        self.assert_cancelled_preserving_gameplay(before)

    def test_event_failure_rolls_back_every_expiry_write(self):
        self.f.begin()
        self.assertEqual(self.ready()[0], 200)
        self.due()
        trigger = 'timeout_' + uuid.uuid4().hex
        self.addCleanup(lambda: sql(f'DROP TRIGGER IF EXISTS {trigger}'))
        sql(f"CREATE TRIGGER {trigger} BEFORE INSERT ON event_queue FOR EACH ROW BEGIN IF NEW.player_id='{self.f.player}' AND NEW.event_name='battle:turn-result' THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='UUID timeout rollback'; END IF; END")
        before = self.f.snapshot()
        self.assertEqual(self.expire(), 0)
        self.assertEqual(self.f.snapshot(), before)
        sql(f'DROP TRIGGER {trigger}')
        self.assertEqual(self.expire(), 1)
        self.assert_cancelled_preserving_gameplay(before)

    def test_cli_worker_recovers_disconnected_player(self):
        self.f.begin()
        self.assertEqual(self.ready()[0], 200)
        self.due()
        before = self.f.snapshot()
        subprocess.run(COMPOSE + ['exec', '-T', 'web', 'php', '/var/www/html/tools/research/server/battle-timeouts.php', '--once'],
                       cwd=ROOT, check=True, capture_output=True, text=True, timeout=20)
        self.assert_cancelled_preserving_gameplay(before)

    def test_worker_pages_past_preserved_ambiguous_battle(self):
        second = test_battle_lifecycle.BattleLifecycleTests(methodName='runTest')
        second.setUp()
        self.addCleanup(lambda: self.assertTrue(second.doCleanups()))
        self.f.begin()
        second.begin()
        self.assertEqual(self.ready()[0], 200)
        self.assertEqual(post('/session/battle/ready', dict(session_id=second.session, battle_id=second.battle))[0], 200)
        self.f.execute([
            f"UPDATE battles SET move_deadline='1999-01-01' WHERE battle_id='{self.f.battle}'",
            f"UPDATE battles SET move_deadline='2000-01-01' WHERE battle_id='{second.battle}'",
            f"DELETE FROM event_queue WHERE room_id='{self.f.room}' AND event_name='battle:start'",
        ])
        before = self.f.snapshot()
        result = json.loads(php("require '/var/www/html/pocket_f4894h398r8h9w9er8he98he.php'; "
                               "require '/var/www/html/lib/battle_timeouts.php'; "
                               "$cursor=['deadline'=>'1998-01-01','battle_id'=>'']; "
                               "$a=battle_timeout_sweep($pdo,1,$cursor); $first=$cursor; "
                               "$b=battle_timeout_sweep($pdo,1,$cursor); echo json_encode([$a,$b,$first,$cursor]);"))
        self.assertEqual(result[:2], [0, 1])
        self.assertEqual(result[2]['battle_id'], self.f.battle)
        self.assertEqual(result[3]['battle_id'], second.battle)
        self.assertEqual(self.f.snapshot(), before)
        self.assertEqual(sql(f"SELECT state FROM battles WHERE battle_id='{second.battle}'")[0]['state'], 'CANCELLED')

    def test_additive_migration_preserves_original_schema_rows_and_reapplies(self):
        table = 'timeout_schema_' + uuid.uuid4().hex
        self.addCleanup(lambda: sql(f'DROP TABLE IF EXISTS {table}'))
        source = (ROOT / 'pocket_mortys.sql').read_text(encoding='utf-8')
        original = re.search(r'CREATE TABLE `battles` \(.*?\) ENGINE=.*?;', source, re.S).group(0)
        migration = (ROOT / 'tools/research/server/migrations/004-battle-move-deadline.sql').read_text(encoding='utf-8')
        # MariaDB DDL commits implicitly; keep it outside the fixture DML helper.
        sql(original.replace('`battles`', table))
        sql(f"INSERT INTO {table} (battle_id,player_id,opponent_id,player_hp,opponent_hp) VALUES ('old-battle','old-player','old-opponent',17,9)")
        before = sql(f'SELECT * FROM {table}')[0]
        for _ in range(2):
            sql(re.sub(r'\bbattles\b', table, migration))
        after = sql(f'SELECT * FROM {table}')[0]
        self.assertIsNone(after.pop('move_deadline'))
        self.assertEqual(after, before)
        index = sql(f"SHOW INDEX FROM {table} WHERE Key_name='ix_battle_move_deadline'")
        self.assertEqual([i['Column_name'] for i in index], ['state', 'move_deadline'])

    def test_revoked_stream_cannot_expire_for_replacement_session(self):
        self.f.begin()
        self.assertEqual(self.ready()[0], 200)
        self.due()
        sql(f"UPDATE users SET session_id='{uuid.uuid4()}' WHERE player_id='{self.f.player}'")
        before = self.f.snapshot()
        count = php("require '/var/www/html/pocket_f4894h398r8h9w9er8he98he.php'; "
                    "require '/var/www/html/lib/battle_timeouts.php'; "
                    f"echo battle_timeout_expire_player($pdo,'{self.f.player}',8,'{self.f.session}');")
        self.assertEqual(count, '0')
        self.assertEqual(self.f.snapshot(), before)
        self.assertEqual(self.expire(), 1)

    def test_stale_worker_candidate_cannot_expire_completed_selection(self):
        self.f.begin()
        sql(f"UPDATE battles SET opponent_hp=100 WHERE battle_id='{self.f.battle}'")
        self.assertEqual(self.ready()[0], 200)
        self.assertEqual(self.f.move()[0], 200)
        self.assertEqual(self.ready()[0], 200)
        before = self.f.snapshot()
        count = php("require '/var/www/html/pocket_f4894h398r8h9w9er8he98he.php'; "
                    "require '/var/www/html/lib/battle_timeouts.php'; "
                    f"echo battle_timeout_expire_candidates($pdo,[['player_id'=>'{self.f.player}','battle_id'=>'{self.f.battle}']]);")
        self.assertEqual(count, '0')
        self.assertEqual(self.f.snapshot(), before)

    def connect(self, session):
        token = base64.urlsafe_b64encode(json.dumps(dict(session_id=session)).encode()).decode().rstrip('=')
        stream = urllib.request.urlopen(f'http://127.0.0.1:8087/sse/?since=0&token=e30.{token}.synthetic', timeout=8)
        self.addCleanup(stream.close)
        return stream

    def read_until(self, stream, wanted):
        events = []
        event, data = None, None
        for _ in range(600):
            line = stream.readline().decode().strip()
            if line.startswith('event: '):
                event = line[7:]
            elif line.startswith('data: '):
                data = json.loads(line[6:])
            elif line == '' and event is not None:
                events.append((event, data))
                if event == wanted:
                    return events
                event = data = None
        self.fail(f'No {wanted}: {events}')

    def test_live_sse_expires_without_a_move_and_keeps_result_private(self):
        self.f.begin()
        self.assertEqual(self.ready()[0], 200)
        before = self.f.snapshot()
        owner, peer = self.connect(self.f.session), self.connect(self.f.other_session)
        self.read_until(owner, 'session:start')
        self.read_until(peer, 'session:start')
        self.due()
        seen = self.read_until(owner, 'battle:turn-result')
        self.assertEqual(seen[-1][1]['outcome'], 'ABANDONED')
        self.assert_cancelled_preserving_gameplay(before, stream_activity=True)
        sql(f"INSERT INTO event_queue (room_id,event_name,player_id,emote) VALUES ('{self.f.room}','emote:room','{self.f.player}','marker')")
        peer_events = self.read_until(peer, 'emote:room')
        self.assertFalse(any(name.startswith('battle:') for name, _ in peer_events))


if __name__ == '__main__':
    unittest.main()
