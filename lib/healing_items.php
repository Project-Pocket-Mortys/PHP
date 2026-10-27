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

// Database stats are nullable integers; never turn malformed data into zero HP.
function item_nonnegative_integer($value): ?int {
    if (!is_int($value) && !is_string($value)) return null;
    $integer = filter_var($value, FILTER_VALIDATE_INT, ['options' => ['min_range' => 0]]);
    return $integer === false ? null : $integer;
}

// A null plan means no applicable effect. Build it before changing any rows.
function morty_item_effect_plan(string $itemId, array $morty, array $attacks): ?array {
    $hp = item_nonnegative_integer($morty['hp'] ?? null);
    $maximum = item_nonnegative_integer($morty['hp_stat'] ?? null);
    if ($hp === null || $maximum === null || $maximum <= 0 || $hp > $maximum) return null;

    if ($itemId === 'ItemPureHalzinger') {
        return $hp === 0 ? ['hp' => $maximum, 'attacks' => [], 'effect_value' => 100] : null;
    }
    if ($hp === 0) return null;
    if ($itemId === 'ItemPurePlutonicRock') {
        // The Android client derives maximum AP from AttackInfo, not this row.
        static $attackMaximums = null;
        if ($attackMaximums === null) {
            $catalog = __DIR__ . '/../config/attack_max_ap.json';
            $attackMaximums = is_file($catalog) ? json_decode(file_get_contents($catalog), true) : [];
        }
        if (!is_array($attackMaximums)) return null;
        $changes = [];
        $hasDeficit = false;
        foreach ($attacks as $attack) {
            $pp = item_nonnegative_integer($attack['pp'] ?? null);
            $ppMaximum = item_nonnegative_integer($attackMaximums[$attack['attack_id'] ?? ''] ?? null);
            if ($pp === null || $ppMaximum === null || $ppMaximum <= 0 || $pp > $ppMaximum) return null;
            if ($pp < $ppMaximum) $hasDeficit = true;
            if ($pp < $ppMaximum || item_nonnegative_integer($attack['pp_stat'] ?? null) !== $ppMaximum) {
                $changes[] = ['id' => $attack['id'], 'pp' => $ppMaximum];
            }
        }
        return $hasDeficit ? ['hp' => $hp, 'attacks' => $changes, 'effect_value' => 100] : null;
    }
    $healers = morty_healing_items();
    if (!array_key_exists($itemId, $healers) || $hp >= $maximum) return null;
    $restored = min($maximum - $hp, $healers[$itemId] ?? ($maximum - $hp));
    return ['hp' => $hp + $restored, 'attacks' => [], 'effect_value' => $restored];
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
