<?php
declare(strict_types=1);

function is_private_battle_event(string $event): bool {
    return in_array($event, [
        'battle:start', 'battle:turn-result', 'battle:move-timer-started'
    ], true);
}

/** Explicit recipients override legacy battle targets; payload participants grant no access. */
function event_is_visible_to_player(array $row, string $player_id): bool {
    $recipient = (string)($row['only_show_to_player_id'] ?? '');
    if ($recipient !== '') return $recipient === $player_id;

    if (is_private_battle_event((string)($row['event_name'] ?? ''))) {
        $legacyRecipient = (string)($row['player_id'] ?? '');
        return $legacyRecipient !== '' && $legacyRecipient === $player_id;
    }

    // On public events player_id identifies the subject, not the subscriber.
    return true;
}
