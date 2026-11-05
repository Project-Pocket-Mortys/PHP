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
    'test_sse_snapshot_boundary', 'test_morty_lock', 'test_use_item',
    'test_full_restore_items', 'test_status_cure_items', 'test_morty_ailment_snapshots',
    'test_morty_release', 'test_crafting',
    'test_battle_lifecycle', 'test_battle_world_guards', 'test_battle_switching', 'test_battle_items', 'test_battle_timeouts',
]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--udp', action='store_true', help='also exercise localhost UDP relay and endpoint ownership')
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
    modules = MODULES + (['test_udp_relay', 'test_udp_endpoint_ownership'] if args.udp else [])
    suite = unittest.defaultTestLoader.loadTestsFromNames(modules)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    raise SystemExit(main())
