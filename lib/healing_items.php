<?php
declare(strict_types=1);

// Android MP ItemInfo identities + Android EN descriptions.
// Null amount means full HP. See docs/protocol/use-item-data.md.
function morty_healing_items(): array {
    return [
        'ItemSerum' => 20,
        'ItemGreatSerum' => 50,
        'ItemSensationalSerum' => 200,
        'ItemPureSerum' => null,
        'ItemEasterEgg' => 30,
        'ItemPumpkin' => 30,
        'ItemSpicyBBQPizza' => 200,
        'ItemBreakfastMedley' => 200,
    ];
}

function item_updated_morty(PDO $pdo, array $morty): array {
    $result = [];
    foreach (['owned_morty_id', 'morty_id', 'variant'] as $field) {
        $result[$field] = (string)($morty[$field] ?? ($field === 'variant' ? 'Normal' : ''));
    }
    foreach (['level', 'xp', 'hp', 'hp_stat', 'attack_stat', 'defence_stat',
              'speed_stat', 'evolution_points', 'xp_lower', 'xp_upper'] as $field) {
        $result[$field] = (int)($morty[$field] ?? 0);
    }
    foreach (['is_locked', 'is_trading_locked'] as $field) {
        $result[$field] = filter_var($morty[$field] ?? false, FILTER_VALIDATE_BOOLEAN);
    }
    $fightPit = (string)($morty['fight_pit_id'] ?? '');
    $result['fight_pit_id'] = $fightPit === '' || strtolower($fightPit) === 'null' ? null : $fightPit;
    $query = $pdo->prepare('SELECT attack_id, position, pp, pp_stat FROM owned_attacks WHERE owned_morty_id = ? ORDER BY position');
    $query->execute([$morty['owned_morty_id']]);
    $result['owned_attacks'] = [];
    foreach ($query as $attack) {
        $result['owned_attacks'][] = [
            'attack_id' => (string)$attack['attack_id'],
            'position' => (int)$attack['position'],
            'pp' => (int)$attack['pp'],
            'pp_stat' => (int)$attack['pp_stat'],
        ];
    }
    return $result;
}
