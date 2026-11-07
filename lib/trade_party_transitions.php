<?php
declare(strict_types=1);

require_once __DIR__ . '/trade_references.php';

final class TradePartyTransitionError extends RuntimeException {
    public function __construct(public int $status = 409) {
        parent::__construct('FAILED');
    }
}

/** The caller already holds the authenticated owner's user lock. */
function trade_party_transition_rows(PDO $pdo, string $sql, array $args): array {
    if (!$pdo->inTransaction()) throw new LogicException('Party transition requires transaction');
    $query = $pdo->prepare($sql);
    $query->execute($args);
    return $query->fetchAll(PDO::FETCH_ASSOC);
}

/** Lock the exact target row before an edit or activation; absence allows insert. */
function trade_party_transition_target(PDO $pdo, array $user, int $deckId): ?array {
    $rows = trade_party_transition_rows($pdo,
        'SELECT * FROM decks WHERE player_id=? AND deck_id=? ORDER BY id FOR UPDATE',
        [$user['player_id'], $deckId]);
    if (!$rows) return null;
    if (count($rows) !== 1 || $rows[0]['player_id'] !== $user['player_id']) {
        throw new TradePartyTransitionError();
    }
    return $rows[0];
}

/** Reject malformed saved parties instead of silently activating an empty subset. */
function trade_party_transition_decode($raw): array {
    if (!is_string($raw)) throw new TradePartyTransitionError();
    $ids = json_decode($raw);
    if (!is_array($ids)) $ids = json_decode(stripcslashes($raw));
    if (!is_array($ids)) throw new TradePartyTransitionError();
    $seen = [];
    foreach ($ids as $id) {
        if (!is_string($id) || trim($id) === '' || isset($seen[$id])) {
            throw new TradePartyTransitionError();
        }
        $seen[$id] = true;
    }
    return $ids;
}

/**
 * Every party member must resolve to one exact, owned instance. Durable trade
 * references are global, including orphaned rows and legacy collated aliases.
 * Ordinary manual/favorite locks do not prohibit using a Morty in a party.
 */
function trade_party_transition_ids(PDO $pdo, array $user, array $ids): void {
    $seen = [];
    foreach ($ids as $id) {
        if (!is_string($id) || trim($id) === '' || isset($seen[$id])) {
            throw new TradePartyTransitionError();
        }
        $seen[$id] = true;
    }
    $sorted = $ids;
    sort($sorted, SORT_STRING);
    foreach ($sorted as $id) {
        $rows = trade_party_transition_rows($pdo,
            'SELECT * FROM owned_morties WHERE owned_morty_id=? ORDER BY id FOR UPDATE', [$id]);
        if (count($rows) !== 1 || $rows[0]['owned_morty_id'] !== $id
            || $rows[0]['player_id'] !== $user['player_id']) throw new TradePartyTransitionError();
        $stored = $rows[0]['is_trading_locked'];
        $locked = ($stored === null || $stored === '') ? false
            : filter_var($stored, FILTER_VALIDATE_BOOLEAN, FILTER_NULL_ON_FAILURE);
        if ($locked !== false) throw new TradePartyTransitionError();
    }
    if (trade_reference_any_locked($pdo, $ids)) throw new TradePartyTransitionError();
}
