<?php
declare(strict_types=1);
header('Content-Type: application/json; charset=utf-8');
require __DIR__ . '/../../../pocket_f4894h398r8h9w9er8he98he.php';
require_once __DIR__ . '/../../../lib/preparation_writer_guard.php';

if (($_SERVER['REQUEST_METHOD'] ?? '') !== 'POST') {
    header('Allow: POST');
    respond(405, ['error' => ['code' => 'FAILED']]);
}
$body = json_decode(file_get_contents('php://input'), true);
foreach (['session_id', 'recipe_id'] as $field) {
    if (!is_array($body) || !is_string($body[$field] ?? null) || trim($body[$field]) === '') {
        respond(400, ['error' => ['code' => 'FAILED']]);
    }
}

try {
    $user = preparation_writer_lock($pdo, $body['session_id']);
    if ($user['state'] !== 'WORLD') {
        $pdo->rollBack();
        respond(409, ['error' => ['code' => 'FAILED']]);
    }
    $catalogFile = __DIR__ . '/../../../config/crafting_recipes.json';
    if (!is_file($catalogFile)) throw new RuntimeException('Crafting catalog missing');
    $catalog = json_decode(file_get_contents($catalogFile), true, 512, JSON_THROW_ON_ERROR);
    $recipe = $catalog[$body['recipe_id']] ?? null;
    if (!is_array($recipe)) {
        $pdo->rollBack();
        respond(400, ['error' => ['code' => 'RECIPE_ID_INVALID']]);
    }
    $ingredients = $recipe['ingredients'] ?? [];
    $resultId = $recipe['result']['item_id'] ?? null;
    $resultAmount = $recipe['result']['quantity'] ?? null;
    if (!$ingredients || !is_string($resultId) || $resultAmount !== 1) {
        throw new RuntimeException('Invalid crafting catalog');
    }
    foreach ($ingredients as $itemId => $count) {
        if (!is_string($itemId) || !is_int($count) || $count <= 0) {
            throw new RuntimeException('Invalid ingredient catalog');
        }
    }
    $touchedIds = array_values(array_unique([...array_keys($ingredients), $resultId]));
    $placeholders = implode(',', array_fill(0, count($touchedIds), '?'));
    $query = $pdo->prepare("SELECT id, item_id, quantity FROM owned_items WHERE player_id = ? AND item_id IN ($placeholders) ORDER BY id FOR UPDATE");
    $query->execute([$user['player_id'], ...$touchedIds]);
    $inventory = [];
    foreach ($query as $row) {
        // Existing inventory has no unique (player_id,item_id) constraint.
        if (!in_array($row['item_id'], $touchedIds, true) || isset($inventory[$row['item_id']])) {
            $pdo->rollBack();
            respond(409, ['error' => ['code' => 'FAILED']]);
        }
        // Native SetItemsFromDicts converts these absolute counts to Int16.
        $quantity = filter_var($row['quantity'], FILTER_VALIDATE_INT,
            ['options' => ['min_range' => 0, 'max_range' => 32767]]);
        if ($row['quantity'] === null || $quantity === false) {
            $pdo->rollBack();
            respond(409, ['error' => ['code' => 'FAILED']]);
        }
        $inventory[$row['item_id']] = ['id' => $row['id'], 'quantity' => $quantity];
    }
    foreach ($ingredients as $itemId => $count) {
        if (($inventory[$itemId]['quantity'] ?? 0) < $count) {
            $pdo->rollBack();
            respond(409, ['error' => ['code' => 'RECIPE_ITEM_NOT_OWNED']]);
        }
    }
    // Net quantities also handle an output that occurs among ingredients.
    $quantities = [];
    foreach ($touchedIds as $itemId) {
        $quantities[$itemId] = ($inventory[$itemId]['quantity'] ?? 0) - ($ingredients[$itemId] ?? 0);
    }
    $quantities[$resultId] += $resultAmount;
    // Android crafting UI checks result count < 10 for every inspected recipe.
    if ($quantities[$resultId] > 10) {
        $pdo->rollBack();
        respond(409, ['error' => ['code' => 'RECIPE_ITEM_RESULT_LIMIT']]);
    }
    $update = $pdo->prepare('UPDATE owned_items SET quantity = ? WHERE id = ? AND player_id = ?');
    $insert = $pdo->prepare('INSERT INTO owned_items (player_id, item_id, quantity) VALUES (?, ?, ?)');
    $ownedItems = [];
    foreach ($quantities as $itemId => $quantity) {
        if (isset($inventory[$itemId])) {
            $update->execute([$quantity, $inventory[$itemId]['id'], $user['player_id']]);
        } else {
            $insert->execute([$user['player_id'], $itemId, $quantity]);
        }
        $ownedItems[] = ['item_id' => $itemId, 'quantity' => $quantity];
    }
    $pdo->commit();
    respond(200, [
        // Absolute values, including zeroes for consumed ingredient stacks.
        'owned_items' => $ownedItems,
        'result' => [
            'type' => 3,
            'item_id' => $resultId,
            'quantity' => $quantities[$resultId],
            'amount' => $resultAmount,
            'amount_received' => $resultAmount,
        ],
    ]);
} catch (Throwable $error) {
    if ($pdo->inTransaction()) $pdo->rollBack();
    if (!$error instanceof FriendError) error_log('Recipe crafting failed: ' . get_class($error));
    respond($error instanceof FriendError ? $error->status : 500, ['error' => ['code' => 'FAILED']]);
}
