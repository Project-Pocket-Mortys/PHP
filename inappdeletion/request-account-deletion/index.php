<?php
// inappdeletion/request-account-deletion
header("Content-Type: application/json; charset=utf-8");
header("X-Powered-By: Express");
header("Access-Control-Allow-Origin: *");
header("Vary: Accept-Encoding");

$input = file_get_contents('php://input');
$data = json_decode($input, true);

$player_id = $data['uuid'];

//echo $player_id;