<?php
header("Content-Type: application/json; charset=utf-8");
header("X-Powered-By: Express");
header("Access-Control-Allow-Origin: *");

require '../../pocket_f4894h398r8h9w9er8he98he.php';
require_once __DIR__ . '/../../lib/trade_response.php';

trade_response_endpoint($pdo);
