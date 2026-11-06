#!/usr/bin/env python3
"""Run the reviewed additive suites against the isolated Compose backend.

Explicit selection excludes the older globally reseeding account/battle tests.
Individual suites create and clean synthetic UUID fixtures. Apply migrations and
start the local services first; --udp additionally needs the localhost relay.
"""
import argparse
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
MODULES = [
    'test_http.AssetServingTests', 'test_emulator_environment', 'test_capture',
    'test_heartbeats', 'test_room_membership_migration', 'test_leave_room',
    'test_join_room_ownership', 'test_sse_sessions', 'test_sse_membership',
    'test_sse_rooms', 'test_sse_event_privacy', 'test_sse_rejoin_generation',
    'test_sse_snapshot_boundary', 'test_morty_lock', 'test_morty_absorb_protection', 'test_morty_absorb_eligibility', 'test_use_item',
    'test_full_restore_items', 'test_status_cure_items', 'test_full_recover', 'test_morty_ailment_snapshots',
    'test_morty_release', 'test_crafting', 'test_friend_lifecycle', 'test_friend_battle_invites', 'test_friend_invite_stream', 'test_friend_battle_membership', 'test_shared_battle_guards', 'test_friend_battle_preparation_deadlines', 'test_friend_battle_preparation_integration', 'test_friend_battle_party_snapshots', 'test_party_writer_guards', 'test_party_storage_guards', 'test_trade_party_guard', 'test_shiny_potion', 'test_shiny_potion_battles',
    'test_battle_lifecycle', 'test_battle_world_guards', 'test_battle_switching', 'test_battle_items', 'test_battle_timeouts',
]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--udp', action='store_true', help='also exercise localhost UDP relay and endpoint ownership')
    parser.add_argument('--shared-battle-stream', action='store_true', help='also exercise opt-in stream-web on localhost:8089 (start shared-battle-stream profile first)')
    args = parser.parse_args()
    sys.path.insert(0, str(ROOT / 'tests/protocol'))
    from test_http import php, sql
    if php("echo getenv('PM_DB_HOST').':'.getenv('PM_PUBLIC_ORIGIN');") != 'db:http://localhost:8087':
        raise RuntimeError('Expected isolated Compose backend on localhost:8087')
    if not sql("SHOW COLUMNS FROM users LIKE 'room_membership_generation'"):
        raise RuntimeError('Apply the additive research migrations before running this suite')
    if not {'is_poisoned', 'is_paralysed'}.issubset({column['Field'] for column in sql('SHOW COLUMNS FROM owned_morties')}):
        raise RuntimeError('Apply migration 003-morty-ailments.sql before running the item/snapshot suites')
    if not sql("SHOW COLUMNS FROM battles LIKE 'move_deadline'"):
        raise RuntimeError('Apply migration 004-battle-move-deadline.sql before running battle suites')
    if not sql("SHOW COLUMNS FROM users LIKE 'shiny_potion_expires_at'"):
        raise RuntimeError('Apply migration 005-shiny-potion-expiry.sql before running account/battle suites')
    if not sql("SHOW TABLES LIKE 'friend_battle_invites'"):
        raise RuntimeError('Apply migration 006-friend-battle-invitations.sql before running invitation/SSE suites')
    if not sql("SHOW TABLES LIKE 'friend_battle_memberships'") or not sql("SHOW TABLES LIKE 'friend_battle_sessions'"):
        raise RuntimeError('Apply migration 007-shared-battle-membership.sql before running world/shared membership suites')
    if not sql("SHOW COLUMNS FROM friend_battle_sessions LIKE 'prepare_deadline'") or not sql("SHOW COLUMNS FROM friend_battle_sessions LIKE 'cancel_reason'"):
        raise RuntimeError('Apply migration 008-friend-battle-preparation-deadline.sql before running SSE/preparation suites')
    if not sql("SHOW TABLES LIKE 'friend_battle_party_snapshots'"):
        raise RuntimeError('Apply migration 009-friend-battle-party-snapshots.sql before running party snapshot suites')
    if not sql("SHOW TABLES LIKE 'friend_battle_start_views'") or not sql("SHOW COLUMNS FROM friend_battle_sessions LIKE 'start_views_created_at'"):
        raise RuntimeError('Apply migration 010-friend-battle-start-views.sql before running private start suites')
    if not sql("SHOW TABLES LIKE 'friend_battle_startups'") or not sql("SHOW TABLES LIKE 'friend_battle_start_intents'"):
        raise RuntimeError('Apply migration 011-friend-battle-startup.sql before running shared startup suites')
    modules = MODULES + ['test_friend_battle_start_views', 'test_start_context_writer_guards', 'test_crafting_pickup_preparation_guards', 'test_friend_battle_startup'] + (['test_udp_relay', 'test_udp_endpoint_ownership'] if args.udp else [])
    if args.shared_battle_stream:
        for table in ['friend_battle_streams','friend_battle_stream_bindings','friend_battle_start_attempts']:
            if not sql("SHOW TABLES LIKE '"+table+"'"):
                raise RuntimeError('Apply migration 012-friend-battle-transport.sql before running transport suites')
        modules.append('test_friend_battle_transport')
    suite = unittest.defaultTestLoader.loadTestsFromNames(modules)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    raise SystemExit(main())
