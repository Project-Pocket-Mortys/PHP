<?php
header("Content-Type: application/json; charset=utf-8");
header("X-Powered-By: Express");
header("Access-Control-Allow-Origin: *");
header("Vary: Accept-Encoding");

echo '{
	"event_data": [],
	"next_event_active": "2026-02-02T14:00:00.000Z"
}';