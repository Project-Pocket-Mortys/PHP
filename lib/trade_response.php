<?php
declare(strict_types=1);
require_once __DIR__ . '/trade_cancellation.php';
require_once __DIR__ . '/trade_membership_guard.php';

final class TradeResponseError extends RuntimeException {
    public function __construct(public int $status, string $code = 'FAILED') {
        parent::__construct($code);
    }
}

/** Native response bodies carry identifiers and a JSON boolean, not credentials. */
function trade_response_body($body): array {
    if (!$body instanceof stdClass) throw new TradeResponseError(400);
    foreach (['trade_request_id', 'trade_offer_id'] as $key) {
        if (!isset($body->$key) || !is_string($body->$key)
            || trim($body->$key) === '' || strlen($body->$key) > 64) {
            throw new TradeResponseError(400);
        }
    }
    if (!isset($body->request_accepted) || !is_bool($body->request_accepted)) {
        throw new TradeResponseError(400);
    }
    return [$body->trade_request_id, $body->trade_offer_id, $body->request_accepted];
}

function trade_response_actor(PDO $pdo, string $session, bool $locked = false): array {
    $suffix = $locked ? ' FOR UPDATE' : '';
    $users = trade_cancellation_rows($pdo, 'SELECT * FROM users WHERE session_id=? ORDER BY id' . $suffix, [$session]);
    if (!$users) throw new TradeResponseError(401);
    if (count($users) !== 1 || $users[0]['session_id'] !== $session) throw new TradeResponseError(409);
    $user = $users[0];
    if (!is_string($user['player_id']) || trim($user['player_id']) === '') throw new TradeResponseError(409);
    $owners = trade_cancellation_rows($pdo, 'SELECT * FROM users WHERE player_id=? ORDER BY id' . $suffix, [$user['player_id']]);
    if (count($owners) !== 1 || $owners[0]['id'] !== $user['id']
        || $owners[0]['player_id'] !== $user['player_id']) throw new TradeResponseError(409);
    return $user;
}

function trade_response_row(PDO $pdo, string $table, string $column, string $id, string $missing): array {
    $rows = trade_cancellation_rows($pdo, "SELECT * FROM $table WHERE $column=? ORDER BY id", [$id]);
    if (!$rows) throw new TradeResponseError(404, $missing);
    if (count($rows) !== 1 || $rows[0][$column] !== $id) throw new TradeResponseError(409);
    return $rows[0];
}

function trade_response_requester(PDO $pdo, array $trade, array $actor): void {
    if ($trade['player_id'] === $actor['player_id']) return;
    // A collated alias of the requester cannot authorize an exact logical ID.
    $query = $pdo->prepare('SELECT id FROM users WHERE id=? AND player_id=?');
    $query->execute([$actor['id'], $trade['player_id']]);
    throw new TradeResponseError($query->fetchColumn() !== false ? 409 : 403);
}

/** A no-op self transfer is valid; changed ownership must affect exactly one row. */
function trade_response_transfer(PDO $pdo, array $morty, string $owner): void {
    if ($morty['player_id'] === $owner) return;
    $query = $pdo->prepare('UPDATE owned_morties SET player_id=? WHERE id=? AND owned_morty_id=? AND player_id=?');
    $query->execute([$owner, $morty['id'], $morty['owned_morty_id'], $morty['player_id']]);
    if ($query->rowCount() !== 1) throw new TradeResponseError(409);
}

function trade_response_apply(PDO $pdo, string $session, string $tradeId, string $offerId, bool $accepted): void {
    if ($pdo->inTransaction()) throw new LogicException('Standalone trade response required');
    try {
        // Keep preflight outside the guard transaction: its membership read must
        // see reservations committed while it waits for the sorted user locks.
        $actor = trade_response_actor($pdo, $session);
        $trade = trade_response_row($pdo, 'trades', 'trade_id', $tradeId, 'TRADE_NO_TRADE_EXISTS');
        trade_response_requester($pdo, $trade, $actor);
        $offer = trade_response_row($pdo, 'trade_offers', 'trade_offer_id', $offerId, 'TRADE_NO_OFFER_EXISTS');
        if ($offer['trade_id'] !== $tradeId) throw new TradeResponseError(409);

        // Preserve the existing shared battle protection for both decisions.
        [$trade, $offer, $morties] = trade_party_guard_lock($pdo, $tradeId, $offerId);
        $currentActor = trade_response_actor($pdo, $session, true);
        if ($currentActor['id'] !== $actor['id'] || $currentActor['player_id'] !== $actor['player_id']) {
            throw new TradeResponseError(409);
        }
        trade_response_requester($pdo, $trade, $currentActor);
        if ($trade['trade_id'] !== $tradeId || $offer['trade_offer_id'] !== $offerId
            || $offer['trade_id'] !== $tradeId) throw new TradeResponseError(409);

        if ($accepted) {
            // Acceptance removes all incoming offers for this exact parent.
            // SQL's legacy collation must not turn an alias into a deletion.
            $siblings = trade_cancellation_rows($pdo, 'SELECT * FROM trade_offers WHERE trade_id=? ORDER BY id FOR UPDATE', [$tradeId]);
            foreach ($siblings as $sibling) {
                if ($sibling['trade_id'] !== $tradeId) throw new TradeResponseError(409);
            }
            $requested = $morties[$trade['morty_trade_id']];
            $offered = $morties[$offer['morty_offer_id']];
            if ($requested['player_id'] !== $trade['player_id'] || $offered['player_id'] !== $offer['player_id']) {
                throw new TradeResponseError(409);
            }
            trade_response_transfer($pdo, $requested, $offer['player_id']);
            trade_response_transfer($pdo, $offered, $trade['player_id']);
            $query = $pdo->prepare('INSERT INTO completed_trades (completed_trade_id,request_player_id,offer_player_id,morty_request_id,morty_offer_id,trade_request_id,trade_offer_id,is_free_trade,fulfilled_at) VALUES (?,?,?,?,?,?,?,?,NOW())');
            $query->execute([bin2hex(random_bytes(16)), $trade['player_id'], $offer['player_id'],
                $trade['morty_trade_id'], $offer['morty_offer_id'], $tradeId, $offerId, $trade['is_free_trade']]);
            if ($query->rowCount() !== 1) throw new TradeResponseError(409);
        }

        if ($accepted) {
            $query = $pdo->prepare('DELETE FROM trade_offers WHERE id=? AND trade_id=?');
            foreach ($siblings as $sibling) {
                $query->execute([$sibling['id'], $tradeId]);
                if ($query->rowCount() !== 1) throw new TradeResponseError(409);
            }
            $query = $pdo->prepare('DELETE FROM trades WHERE id=? AND trade_id=? AND player_id=?');
            $query->execute([$trade['id'], $tradeId, $trade['player_id']]);
            if ($query->rowCount() !== 1) throw new TradeResponseError(409);
        } else {
            $query = $pdo->prepare('DELETE FROM trade_offers WHERE id=? AND trade_offer_id=? AND trade_id=? AND player_id=?');
            $query->execute([$offer['id'], $offerId, $tradeId, $offer['player_id']]);
            if ($query->rowCount() !== 1) throw new TradeResponseError(409);
        }
        $pdo->commit();
    } catch (Throwable $error) {
        if ($pdo->inTransaction()) $pdo->rollBack();
        throw $error;
    }
}

function trade_response_endpoint(PDO $pdo): void {
    try {
        if (($_SERVER['REQUEST_METHOD'] ?? '') !== 'POST') throw new TradeResponseError(405);
        $server = $_SERVER;
        if (!isset($server['HTTP_AUTHORIZATION']) && !isset($server['REDIRECT_HTTP_AUTHORIZATION']) && function_exists('getallheaders')) {
            foreach (getallheaders() as $name => $value) {
                if (strtolower($name) === 'authorization') $server['HTTP_AUTHORIZATION'] = $value;
            }
        }
        $session = trade_cancellation_session($server, $_COOKIE);
        [$tradeId, $offerId, $accepted] = trade_response_body(json_decode(file_get_contents('php://input')));
        trade_response_apply($pdo, $session, $tradeId, $offerId, $accepted);
        respond(200, [null, null]);
    } catch (Throwable $error) {
        if ($pdo->inTransaction()) $pdo->rollBack();
        $expected = $error instanceof TradeResponseError || $error instanceof TradeMembershipError || $error instanceof TradeCancellationError;
        if (!$expected) error_log('Trade response failed: ' . get_class($error));
        respond($expected ? $error->status : 500, ['error' => ['code' => $expected ? $error->getMessage() : 'FAILED']]);
    }
}
