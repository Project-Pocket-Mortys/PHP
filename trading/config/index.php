<?php
header("Content-Type: application/json; charset=utf-8");
header("X-Powered-By: Express");
header("Access-Control-Allow-Origin: *");
header("Vary: Accept-Encoding");

echo '{
	"config_id": "DEFAULT",
	"premium_trade_cost": 3,
	"max_trades": 3,
	"trade_cooldown_minutes": 1440
}';