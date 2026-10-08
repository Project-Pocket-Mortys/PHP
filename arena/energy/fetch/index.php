<?php
header("Content-Type: application/json; charset=utf-8");
header("X-Powered-By: Express");
header("Access-Control-Allow-Origin: *");
header("Vary: Accept-Encoding");

//energy fetch

echo '{
	"energy_amount": 100,
	"energy_time": null
}';