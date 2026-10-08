<?php
// lib/auth.php

function require_user_by_session(PDO $pdo, string $session_id): array {
    $stmt = $pdo->prepare("
        SELECT *
        FROM users
        WHERE session_id = ?
        LIMIT 1
    ");
    $stmt->execute([$session_id]);
    $u = $stmt->fetch(PDO::FETCH_ASSOC);

    if (!$u) {
        http_response_code(401);
        echo json_encode(["error" => "Not authenticated"], JSON_UNESCAPED_SLASHES);
        exit;
    }

    return $u;
}

/** helper: tags stored as JSON string or array */
function normalize_tags($tags): array {
    if (is_array($tags)) return $tags;
    if (is_string($tags)) {
        $decoded = json_decode($tags, true);
        return is_array($decoded) ? $decoded : [];
    }
    return [];
}