<?php
// Research-only relay. Movement authority, persistence and original timing are unresolved.
if (PHP_SAPI !== 'cli' || getenv('PM_RESEARCH_UDP') !== '1' || getenv('PM_DB_HOST') !== 'db' || getenv('PM_DB_NAME') !== 'pocket_mortys') {
    throw new RuntimeException('Isolated UDP research service required');
}
require '/var/www/html/pocket_f4894h398r8h9w9er8he98he.php';

function guid_text(string $bytes): string {
    $hex = bin2hex($bytes);
    return substr($hex, 0, 8).'-'.substr($hex, 8, 4).'-'.substr($hex, 12, 4).'-'.substr($hex, 16, 4).'-'.substr($hex, 20);
}
function guid_bytes(string $guid): string|false {
    if (!preg_match('/^[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}$/i', $guid)) return false;
    return hex2bin(str_replace('-', '', $guid));
}
function newer_sequence(int $new, int $old): bool {
    return ($new > $old && $new - $old <= 127) || ($old > $new && $old - $new > 127);
}

$socket = stream_socket_server('udp://0.0.0.0:5055', $errno, $error, STREAM_SERVER_BIND);
if (!$socket) throw new RuntimeException('Could not bind research UDP socket');
stream_set_timeout($socket, 1);
$lookup = $pdo->prepare("SELECT u.player_id, u.room_id FROM users u JOIN room_ids r ON r.room_id = u.room_id WHERE u.session_id = ? AND u.state = 'WORLD' LIMIT 1");
$heartbeat = $pdo->prepare("SELECT 1 FROM research_client_heartbeats h JOIN users u ON u.id = h.user_id
    WHERE u.session_id = ? AND h.session_id = u.session_id AND u.player_id = ?
      AND u.room_id = ? AND h.room_id = u.room_id AND u.state = 'WORLD'
      AND EXISTS (SELECT 1 FROM room_ids r WHERE r.room_id = u.room_id)
      AND h.received_at >= CURRENT_TIMESTAMP - INTERVAL 120 SECOND LIMIT 1");
$peers = [];
$stats = ['accepted' => 0, 'forwarded' => 0, 'rejected' => 0, 'old_sequence' => 0, 'send_errors' => 0];
// A bounded research policy, not recovered original-server behavior.
$ttl = 120;
echo "Research UDP relay listening on 5055; no position persistence\n";
while (true) {
    $address = '';
    $data = @stream_socket_recvfrom($socket, 65535, 0, $address);
    $now = hrtime(true) / 1e9;
    foreach ($peers as $session => $peer) {
        if ($now - $peer['seen'] > $ttl) {
            // HTTP liveness can retain only an endpoint already learned from UDP.
            // Server-side last_seen updates are not evidence of a live client.
            $heartbeat->execute([$session, $peer['player'], $peer['room']]);
            if (!$heartbeat->fetchColumn()) unset($peers[$session]);
        }
    }
    if ($data === false) continue;
    if (strlen($data) !== 24 || ord($data[23]) > 4 || (ord($data[22]) >> 4) > 6) {
        $stats['rejected']++;
        continue;
    }
    $session = guid_text(substr($data, 0, 16));
    $lookup->execute([$session]);
    $user = $lookup->fetch(PDO::FETCH_ASSOC);
    $playerBytes = $user ? guid_bytes($user['player_id']) : false;
    if (!$user || $playerBytes === false) {
        unset($peers[$session]);
        $stats['rejected']++;
        continue;
    }
    $sequence = ord($data[16]);
    $previous = $peers[$session] ?? null;
    if ($previous && $previous['room'] === $user['room_id'] && !newer_sequence($sequence, $previous['sequence'])) {
        $stats['old_sequence']++;
        continue;
    }
    if (!$previous && count($peers) >= 256) {
        $stats['rejected']++;
        continue;
    }
    $peers[$session] = ['address' => $address, 'room' => $user['room_id'], 'player' => $user['player_id'],
                         'seen' => $now, 'sequence' => $sequence];
    $stats['accepted']++;
    // Never forward session credentials. Receiver IDs identify players.
    $outbound = $playerBytes.substr($data, 16);
    foreach ($peers as $recipientSession => $peer) {
        if ($recipientSession === $session) continue;
        // Recheck session rotation, account removal and room changes at delivery time.
        $lookup->execute([$recipientSession]);
        $recipient = $lookup->fetch(PDO::FETCH_ASSOC);
        if (!$recipient || $recipient['room_id'] !== $peer['room'] || $recipient['player_id'] !== $peer['player']) {
            unset($peers[$recipientSession]);
            continue;
        }
        if ($recipient['room_id'] !== $user['room_id'] || $recipient['player_id'] === $user['player_id']) continue;
        $sent = @stream_socket_sendto($socket, $outbound, 0, $peer['address']);
        $stats[$sent === 24 ? 'forwarded' : 'send_errors']++;
    }
    // Counters only: raw packets contain session credentials.
    echo json_encode($stats, JSON_UNESCAPED_SLASHES)."\n";
}
