<?php
header('Content-Type: application/json; charset=utf-8');
require __DIR__ . '/../../pocket_f4894h398r8h9w9er8he98he.php';
require_once __DIR__ . '/../../lib/trade_cancellation.php';
trade_cancellation_endpoint($pdo, false);
