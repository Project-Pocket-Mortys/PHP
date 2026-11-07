<?php
declare(strict_types=1);

const TRADE_REFERENCE_SOURCES = [
    ['trades', 'morty_trade_id'],
    ['trade_offers', 'morty_offer_id'],
];

/** Read-only projection: preserve stored locks and derive durable reservations. */
function trade_reference_projection(string $ownedColumn): string {
    if (!preg_match('/^[a-z_]+\.[a-z_]+$/D', $ownedColumn)) throw new LogicException('Trusted SQL column required');
    $parts = [];
    foreach (TRADE_REFERENCE_SOURCES as [$table, $column]) {
        $parts[] = "EXISTS (SELECT 1 FROM $table trade_ref WHERE trade_ref.$column = $ownedColumn)";
    }
    return '(' . implode(' OR ', $parts) . ')';
}

/** Caller holds the owner's user and actual instance locks before any writes. */
function trade_reference_any_locked(PDO $pdo, array $ownedIds): bool {
    if (!$pdo->inTransaction()) throw new LogicException('Locked trade reference check requires transaction');
    if (!$ownedIds) return false;
    $ownedIds = array_values(array_unique($ownedIds, SORT_STRING));
    sort($ownedIds, SORT_STRING);
    $in = implode(',', array_fill(0, count($ownedIds), '?'));
    // Explicit current reads, including orphan/stale references, like release.
    // Do not filter by declared owner or compare SQL-collated IDs in PHP.
    foreach (TRADE_REFERENCE_SOURCES as [$table, $column]) {
        $query = $pdo->prepare("SELECT id FROM $table WHERE $column IN ($in) ORDER BY id LIMIT 1 FOR UPDATE");
        $query->execute($ownedIds);
        if ($query->fetchColumn() !== false) return true;
    }
    return false;
}
