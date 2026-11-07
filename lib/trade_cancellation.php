<?php
declare(strict_types=1);
require_once __DIR__ . '/trade_refresh.php';

final class TradeCancellationError extends RuntimeException {
    public function __construct(public int $status, string $code = 'FAILED') {
        parent::__construct($code);
    }
}

/** Native bodies contain only the listing ID; credentials travel over HTTP. */
function trade_cancellation_session(array $server, array $cookies): string {
    $cookie = $cookies['session_id'] ?? null;
    if ($cookie !== null && (!is_string($cookie) || trim($cookie) === '')) throw new TradeCancellationError(401);
    $header = $server['HTTP_AUTHORIZATION'] ?? $server['REDIRECT_HTTP_AUTHORIZATION'] ?? null;
    $bearer = null;
    if ($header !== null) {
        if (!is_string($header) || !preg_match('/^Bearer ([^\s,]+)$/iD', $header, $matches)) throw new TradeCancellationError(401);
        $bearer = $matches[1];
    }
    if ($cookie !== null && $bearer !== null && !hash_equals($cookie, $bearer)) throw new TradeCancellationError(401);
    $session = $bearer ?? $cookie;
    if (!is_string($session) || trim($session) === '' || strlen($session) > 255) throw new TradeCancellationError(401);
    return $session;
}

function trade_cancellation_id($body, string $key): string {
    if (!$body instanceof stdClass || array_keys(get_object_vars($body)) !== [$key]
        || !is_string($body->$key) || trim($body->$key) === '' || strlen($body->$key) > 64) throw new TradeCancellationError(400);
    return $body->$key;
}

function trade_cancellation_rows(PDO $pdo, string $sql, array $args): array {
    $query = $pdo->prepare($sql); $query->execute($args);
    return $query->fetchAll(PDO::FETCH_ASSOC);
}

/** Listing-only deletion: no ownership, stored locks, stock or refund changes. */
function trade_cancellation_apply(PDO $pdo, string $session, string $id, bool $offer): void {
    if ($pdo->inTransaction()) throw new LogicException('Standalone cancellation required');
    try {
        $pdo->beginTransaction();
        $users = trade_cancellation_rows($pdo, 'SELECT * FROM users WHERE session_id=? ORDER BY id FOR UPDATE', [$session]);
        if (!$users) throw new TradeCancellationError(401);
        if (count($users) !== 1 || $users[0]['session_id'] !== $session) throw new TradeCancellationError(409);
        $user = $users[0];
        $owners = trade_cancellation_rows($pdo, 'SELECT id FROM users WHERE player_id=? ORDER BY id FOR UPDATE', [$user['player_id']]);
        if (count($owners) !== 1 || $owners[0]['id'] !== $user['id']) throw new TradeCancellationError(409);
        $tradeId = $id;
        if ($offer) {
            // Discover the parent first; revalidate the child under locks below.
            $offers = trade_cancellation_rows($pdo, 'SELECT * FROM trade_offers WHERE trade_offer_id=? ORDER BY id', [$id]);
            if (!$offers) throw new TradeCancellationError(404, 'TRADE_NO_SUCH_OFFER');
            if (count($offers) !== 1 || $offers[0]['trade_offer_id'] !== $id) throw new TradeCancellationError(409);
            $tradeId = $offers[0]['trade_id'];
        }
        $trades = trade_cancellation_rows($pdo, 'SELECT * FROM trades WHERE trade_id=? ORDER BY id FOR UPDATE', [$tradeId]);
        if (!$trades && !$offer) throw new TradeCancellationError(404);
        if ($trades && (count($trades) !== 1 || $trades[0]['trade_id'] !== $tradeId)) throw new TradeCancellationError(409);
        $trade = $trades[0] ?? null;
        $recipients = [];
        if ($offer) {
            $current = trade_cancellation_rows($pdo, 'SELECT * FROM trade_offers WHERE trade_offer_id=? ORDER BY id FOR UPDATE', [$id]);
            if (!$current) throw new TradeCancellationError(404, 'TRADE_NO_SUCH_OFFER');
            if (count($current) !== 1 || $current[0] !== $offers[0]) throw new TradeCancellationError(409);
            if ($current[0]['player_id'] !== $user['player_id']) throw new TradeCancellationError(403);
            $query = $pdo->prepare('DELETE FROM trade_offers WHERE id=? AND trade_offer_id=? AND trade_id=? AND player_id=?');
            $query->execute([$current[0]['id'], $id, $tradeId, $user['player_id']]);
            if ($query->rowCount() !== 1) throw new TradeCancellationError(409);
            if ($trade !== null) $recipients[] = $trade['player_id'];
        } else {
            if ($trade['player_id'] !== $user['player_id']) throw new TradeCancellationError(403);
            $children = trade_cancellation_rows($pdo, 'SELECT * FROM trade_offers WHERE trade_id=? ORDER BY id FOR UPDATE', [$id]);
            foreach ($children as $child) {
                if ($child['trade_id'] !== $id) throw new TradeCancellationError(409);
            }
            $remove = $pdo->prepare('DELETE FROM trade_offers WHERE id=? AND trade_id=?');
            foreach ($children as $child) {
                $remove->execute([$child['id'], $id]);
                if ($remove->rowCount() !== 1) throw new TradeCancellationError(409);
                $recipients[] = $child['player_id'];
            }
            $query = $pdo->prepare('DELETE FROM trades WHERE id=? AND trade_id=? AND player_id=?');
            $query->execute([$trade['id'], $id, $user['player_id']]);
            if ($query->rowCount() !== 1) throw new TradeCancellationError(409);
        }
        // Notify counterparts after the authoritative removal, atomically.
        // Never echo to the actor: its local saved-offer cleanup can race SSE.
        // Malformed legacy owners have no deliverable identity; withdrawal
        // still succeeds rather than retaining an otherwise removable row.
        $recipients = array_values(array_filter($recipients, static fn($recipient) =>
            is_string($recipient) && trim($recipient) !== '' && strlen($recipient) <= 255
            && $recipient !== $user['player_id']));
        if ($recipients) trade_refresh_publish($pdo, $recipients,
            $offer ? 'trade:offer-submit' : 'trade:offer-rejected');
        $pdo->commit();
    } catch (Throwable $error) {
        if ($pdo->inTransaction()) $pdo->rollBack();
        throw $error;
    }
}

function trade_cancellation_endpoint(PDO $pdo, bool $offer): void {
    try {
        if (($_SERVER['REQUEST_METHOD'] ?? '') !== 'POST') throw new TradeCancellationError(405);
        $server = $_SERVER;
        // Apache can expose Authorization only through getallheaders(). Never
        // silently ignore an explicit credential when a cookie is also present.
        if (!isset($server['HTTP_AUTHORIZATION']) && !isset($server['REDIRECT_HTTP_AUTHORIZATION'])) {
            foreach (getallheaders() as $name => $value) {
                if (strtolower($name) === 'authorization') $server['HTTP_AUTHORIZATION'] = $value;
            }
        }
        $session = trade_cancellation_session($server, $_COOKIE);
        $id = trade_cancellation_id(json_decode(file_get_contents('php://input')), $offer ? 'trade_offer_id' : 'trade_id');
        trade_cancellation_apply($pdo, $session, $id, $offer);
        respond(200, ['error' => 'None']);
    } catch (Throwable $error) {
        if ($pdo->inTransaction()) $pdo->rollBack();
        if (!$error instanceof TradeCancellationError) error_log('Trade cancellation failed: '.get_class($error));
        respond($error instanceof TradeCancellationError ? $error->status : 500,
            ['error' => ['code' => $error instanceof TradeCancellationError ? $error->getMessage() : 'FAILED']]);
    }
}
