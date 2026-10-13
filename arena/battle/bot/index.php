<?php
header("Content-Type: application/json; charset=utf-8");
header("X-Powered-By: Express");
header("Access-Control-Allow-Origin: *");
header("Vary: Accept-Encoding");

echo '{
	"event_id": "dace41f4-cdca-11ef-acec-8f82efc7517f",
	"shard_id": 3,
	"target_trophy_count": 79,
	"attacker_score": 100,
	"defender_score": 75,
	"energy": 100,
	"used_energy": true,
	"attacker_rank": 548,
	"found_opponent": true,
	"is_real_opponent": false
}';