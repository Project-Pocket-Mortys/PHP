<?php
declare(strict_types=1);
require_once __DIR__ . '/battle_membership_guard.php';

final class TradeMembershipError extends RuntimeException {
    public function __construct(public int $status, string $code = 'FAILED') {
        parent::__construct($code);
    }
}

/** Logical identities use legacy nonunique columns; ambiguity cannot authorize writes. */
function trade_party_guard_row(PDO $pdo, string $table, string $column, string $value, bool $locked = false): array {
    $query = $pdo->prepare("SELECT * FROM $table WHERE $column=? ORDER BY id" . ($locked ? ' FOR UPDATE' : ''));
    $query->execute([$value]);
    $rows = $query->fetchAll(PDO::FETCH_ASSOC);
    if (count($rows) !== 1 || $rows[0][$column] !== $value) throw new TradeMembershipError(409);
    return $rows[0];
}

/**
 * Internal ownership-freeze guard, not recovered trade authorization policy.
 * Returns an open transaction holding all declared and actual owners' user locks.
 * All preflight reads occur before beginTransaction: membership sees a fresh view
 * only after waiting for every user lock, including a concurrent reservation.
 */
function trade_party_guard_lock(PDO $pdo, string $tradeId, string $offerId): array {
    if ($pdo->inTransaction()) throw new LogicException('Standalone trade guard required');
    $trade = trade_party_guard_row($pdo, 'trades', 'trade_id', $tradeId);
    $offer = trade_party_guard_row($pdo, 'trade_offers', 'trade_offer_id', $offerId);
    $mortyIds = [$trade['morty_trade_id'], $offer['morty_offer_id']];
    foreach ($mortyIds as $id) {
        if (!is_string($id) || trim($id) === '') throw new TradeMembershipError(409);
    }
    $mortyIds = array_values(array_unique($mortyIds, SORT_STRING));
    sort($mortyIds, SORT_STRING);
    $morties = [];
    $players = [$trade['player_id'], $offer['player_id']];
    foreach ($mortyIds as $id) {
        $morties[$id] = trade_party_guard_row($pdo, 'owned_morties', 'owned_morty_id', $id);
        $players[] = $morties[$id]['player_id'];
    }
    foreach ($players as $player) {
        if (!is_string($player) || trim($player) === '') throw new TradeMembershipError(409);
    }
    $players = array_values(array_unique($players, SORT_STRING));
    sort($players, SORT_STRING);
    $users = [];
    foreach ($players as $player) $users[$player] = trade_party_guard_row($pdo, 'users', 'player_id', $player);

    $pdo->beginTransaction();
    foreach ($players as $player) {
        $user = trade_party_guard_row($pdo, 'users', 'player_id', $player, true);
        if ($user['id'] !== $users[$player]['id']) throw new TradeMembershipError(409);
    }
    if (trade_party_guard_row($pdo, 'trades', 'trade_id', $tradeId, true) !== $trade
        || trade_party_guard_row($pdo, 'trade_offers', 'trade_offer_id', $offerId, true) !== $offer) {
        throw new TradeMembershipError(409);
    }
    foreach ($mortyIds as $id) {
        if (trade_party_guard_row($pdo, 'owned_morties', 'owned_morty_id', $id, true) !== $morties[$id]) {
            throw new TradeMembershipError(409);
        }
    }
    foreach ($players as $player) {
        if (battle_has_shared_membership($pdo, $player)) throw new TradeMembershipError(409);
    }
    return [$trade, $offer, $morties];
}
