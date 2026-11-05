<?php
declare(strict_types=1);

/** Any claim blocks world actions, including orphaned or malformed claims. */
function battle_has_shared_membership(PDO $pdo, string $player): bool {
    $query = $pdo->prepare('SELECT battle_id FROM friend_battle_memberships WHERE player_id=?');
    $query->execute([$player]);
    return $query->fetch(PDO::FETCH_ASSOC) !== false;
}
