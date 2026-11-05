<?php
// owned_morties/absorb
error_reporting(E_ALL);
ini_set('display_errors', 0);
header('Content-Type: application/json; charset=utf-8');
header('X-Powered-By: Express');
header('Access-Control-Allow-Origin: *');
require __DIR__ . '/../../../pocket_f4894h398r8h9w9er8he98he.php';
require_once __DIR__ . '/../../../lib/morty_absorb.php';
morty_absorb_endpoint($pdo);
