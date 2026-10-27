<?php
function get_active_deck_morties(PDO $pdo, string $player_id): array {

    /* ---------------- 1. GET ACTIVE DECK ---------------- */
    $q = $pdo->prepare("
        SELECT d.deck_id, d.owned_morty_ids
        FROM decks d
        JOIN users u ON u.player_id = d.player_id AND u.active_deck_id = d.deck_id
        WHERE d.player_id = ?
        LIMIT 1
    ");
    $q->execute([$player_id]);
    $deck = $q->fetch(PDO::FETCH_ASSOC);

    if (!$deck || !$deck["owned_morty_ids"]) {
        return [];
    }

    $raw = $deck["owned_morty_ids"];

    /* ---------------- 2. PARSE MORTY IDS ---------------- */
    $morty_ids = json_decode($raw, true);

    if (!is_array($morty_ids)) {
        // fallback if stored as CSV
        $morty_ids = array_filter(array_map('trim', explode(',', $raw)));
    }

    if (empty($morty_ids)) {
        return [];
    }

    /* ---------------- 3. LOAD MORTIES ---------------- */
    $in = implode(',', array_fill(0, count($morty_ids), '?'));

    $q = $pdo->prepare("
        SELECT
            owned_morty_id,
            morty_id,
            hp,
            variant,
            is_locked,
            is_trading_locked,
            fight_pit_id
        FROM owned_morties
        WHERE owned_morty_id IN ($in) AND player_id = ?
    ");
    $q->execute([...$morty_ids, $player_id]);

    $morties = $q->fetchAll(PDO::FETCH_ASSOC);

    /* ---------------- 4. NORMALIZE TYPES ---------------- */
    foreach ($morties as &$m) {
        $m["hp"] = (int)$m["hp"];

        $m["is_locked"] = filter_var(
            $m["is_locked"],
            FILTER_VALIDATE_BOOLEAN
        );

        $m["is_trading_locked"] = filter_var(
            $m["is_trading_locked"],
            FILTER_VALIDATE_BOOLEAN
        );

        $m["fight_pit_id"] = (
    empty($m["fight_pit_id"]) ||
    strtolower((string)$m["fight_pit_id"]) === "null"
)
    ? null
    : $m["fight_pit_id"];
    }
    unset($m);

    /* ---------------- 5. PRESERVE ORIGINAL DECK ORDER ---------------- */
    $ordered = [];

    foreach ($morty_ids as $id) {
        foreach ($morties as $m) {
            if ($m["owned_morty_id"] === $id) {
                $ordered[] = $m;
                break;
            }
        }
    }

    return $ordered;
}
