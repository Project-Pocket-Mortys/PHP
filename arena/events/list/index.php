<?php
header("Content-Type: application/json; charset=utf-8");
header("X-Powered-By: Express");
header("Access-Control-Allow-Origin: *");
header("Vary: Accept-Encoding");

echo '{
	"events": [{
		"event_id": "dace4578-cdca-11ef-a9a1-3f079e2d6aa5",
		"current_phase": "active",
		"reward_time_remaining": 318892832,
		"phase_time_remaining": 316792832,
		"data_time": "2026-01-29T16:25:07.168Z",
		"starting_energy": 100,
		"energy_refill_time_minutes": 10,
		"battle_energy_cost": 0,
		"battle_premium_energy_cost": 0,
		"max_regen_energy": 100,
		"maintenance": false
	}]
}';

/*
echo '{
	"events": [{
		"event_id": "dace4578-cdca-11ef-a9a1-3f079e2d6aa5",
		"current_phase": "active",
		"reward_time_remaining": 602952601,
		"phase_time_remaining": 600852601,
		"data_time": "2026-01-26T09:30:47.399Z",
		"starting_energy": 100,
		"energy_refill_time_minutes": 10,
		"battle_energy_cost": 0,
		"battle_premium_energy_cost": 0,
		"max_regen_energy": 100,
		"maintenance": false
	}]
}';
*/