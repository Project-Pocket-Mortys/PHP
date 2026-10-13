<?php
header("Content-Type: application/json; charset=utf-8");
header("X-Powered-By: Express");
header("Access-Control-Allow-Origin: *");
header("Vary: Accept-Encoding");

$response = json_encode([
    "dimension_1_owned" => true,
	"dimension_2_owned" => true,
	"dimension_3_owned" => true,
	"dimension_4_owned" => true,
	"dimension_5_owned" => true,
	"dimension_6_owned" => true,
	"dimension_7_owned" => true
], JSON_UNESCAPED_SLASHES);

echo $response;