<?php
declare(strict_types=1);

/** Display metadata only; never manufacture names from logical instance IDs. */
function trade_offer_metadata(PDO $pdo, string $tradeId, string $offerPlayerId, string $offeredId): array {
    $parent = $pdo->prepare('SELECT player_id, morty_trade_id FROM trades WHERE trade_id = ? LIMIT 2');
    $parent->execute([$tradeId]);
    $parents = $parent->fetchAll(PDO::FETCH_ASSOC);
    if (count($parents) !== 1) return [];
    $trade = $parents[0];
    // Aggregate scalar subqueries avoid multiplying offers through legacy
    // nonunique logical keys. Unknown/ambiguous sources remain absent.
    $query = $pdo->prepare('
        SELECT
          (SELECT CASE WHEN COUNT(*) = 1 THEN MAX(username) ELSE NULL END
             FROM users WHERE player_id = ?) AS request_user_name,
          (SELECT CASE WHEN COUNT(*) = 1 THEN MAX(morty_id) ELSE NULL END
             FROM owned_morties WHERE owned_morty_id = ? AND player_id = ?) AS offering_morty_id,
          (SELECT CASE WHEN COUNT(*) = 1 THEN MAX(morty_id) ELSE NULL END
             FROM owned_morties WHERE owned_morty_id = ? AND player_id = ?) AS request_morty_id
    ');
    $query->execute([$trade['player_id'], $offeredId, $offerPlayerId,
                     $trade['morty_trade_id'], $trade['player_id']]);
    $row = $query->fetch(PDO::FETCH_ASSOC);
    return array_filter($row, static fn($value): bool => is_string($value) && $value !== '');
}
