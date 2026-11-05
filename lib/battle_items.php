<?php
declare(strict_types=1);
require_once __DIR__ . '/healing_items.php';

function battle_supported_item(string $item): bool {
    return array_key_exists($item, morty_healing_items())
        || array_key_exists($item, morty_status_cure_items())
        || in_array($item, ['ItemPureHalzinger', 'ItemPurePlutonicRock'], true);
}

/** Apply one planned effect using only locked rows; the caller owns the turn transaction. */
function battle_apply_item(PDO $pdo, string $player, string $opponent, string $target, string $item, array &$party): array {
    $morty = $party[$target];
    $stmt = $pdo->prepare('SELECT id, quantity FROM owned_items WHERE player_id=? AND item_id=? FOR UPDATE');
    $stmt->execute([$player, $item]);
    $items = $stmt->fetchAll(PDO::FETCH_ASSOC);
    $stock = count($items) === 1 ? item_nonnegative_integer($items[0]['quantity']) : null;
    if ($stock === null || $stock <= 0 || $stock > 2147483647) battle_reject(409);

    $attacks = [];
    if ($item === 'ItemPurePlutonicRock') {
        $stmt = $pdo->prepare('SELECT id, attack_id, position, pp, pp_stat FROM owned_attacks WHERE owned_morty_id=? ORDER BY position, id FOR UPDATE');
        $stmt->execute([$target]);
        $attacks = $stmt->fetchAll(PDO::FETCH_ASSOC);
        if (count($attacks) < 1 || count($attacks) > 4) battle_reject(409);
        $maximums = json_decode(file_get_contents(__DIR__ . '/../config/attack_max_ap.json'), true);
        if (!is_array($maximums)) battle_reject(409);
        $ids = $positions = [];
        foreach ($attacks as $attack) {
            $id = (string)$attack['attack_id'];
            $position = item_nonnegative_integer($attack['position']);
            $pp = item_nonnegative_integer($attack['pp']);
            $maximum = item_nonnegative_integer($maximums[$id] ?? null);
            if ($id === '' || isset($ids[$id]) || $position === null || $position > 2147483647
                || isset($positions[$position]) || $pp === null || $maximum === null
                || $maximum <= 0 || $maximum > 2147483647 || $pp > $maximum) battle_reject(409);
            $ids[$id] = $positions[$position] = true;
        }
    }
    $plan = morty_item_effect_plan($item, $morty, $attacks);
    if ($plan === null) battle_reject(409);
    if (array_key_exists('hp', $plan) && $item !== 'ItemPurePlutonicRock') {
        $morty['hp'] = $plan['hp'];
        $pdo->prepare('UPDATE owned_morties SET hp=? WHERE id=? AND player_id=?')->execute([$morty['hp'], $morty['id'], $player]);
    }
    foreach (['is_poisoned', 'is_paralysed'] as $flag) {
        if (array_key_exists($flag, $plan['flags'] ?? [])) {
            $morty[$flag] = $plan['flags'][$flag];
            $pdo->prepare("UPDATE owned_morties SET $flag=? WHERE id=? AND player_id=?")->execute([(int)$morty[$flag], $morty['id'], $player]);
        }
    }
    $changes = [];
    foreach ($plan['attacks'] as $attack) {
        $pdo->prepare('UPDATE owned_attacks SET pp=?, pp_stat=? WHERE id=? AND owned_morty_id=?')->execute([$attack['pp'], $attack['pp'], $attack['id'], $target]);
        $changes[$attack['id']] = $attack['pp'];
    }
    $quantity = $stock - 1;
    $pdo->prepare('UPDATE owned_items SET quantity=? WHERE id=? AND player_id=?')->execute([$quantity, $items[0]['id'], $player]);
    $party[$target] = $morty;
    $snapshot = [
        'owned_morty_id' => $target, 'hp' => (int)$morty['hp'],
        'is_poisoned' => filter_var($morty['is_poisoned'] ?? false, FILTER_VALIDATE_BOOLEAN),
        'is_paralysed' => filter_var($morty['is_paralysed'] ?? false, FILTER_VALIDATE_BOOLEAN),
    ];
    if ($item === 'ItemPurePlutonicRock') {
        $snapshot['owned_attacks'] = [];
        foreach ($attacks as $attack) {
            $snapshot['owned_attacks'][] = [
                'attack_id' => (string)$attack['attack_id'], 'position' => (int)$attack['position'],
                'pp' => $changes[$attack['id']] ?? (int)$attack['pp'],
                'pp_stat' => $changes[$attack['id']] ?? (int)$attack['pp_stat'],
            ];
        }
    }
    return ['action' => [
        'type' => 'ITEM', 'owned_morty_id' => $target, 'item_id' => $item,
        'success' => true, 'effect_value' => $plan['effect_value'],
        'attacker_player_id' => $player, 'defender_player_id' => $opponent,
        'attacker_morty_datas' => [$snapshot], 'defender_morty_datas' => [],
    ], 'owned_item' => ['item_id' => $item, 'quantity' => $quantity]];
}
