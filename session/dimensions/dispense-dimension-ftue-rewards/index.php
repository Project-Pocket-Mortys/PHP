<?php
header("Content-Type: application/json; charset=utf-8");
header("X-Powered-By: Express");
header("Access-Control-Allow-Origin: *");
header("Vary: Accept-Encoding");

echo '{
	"rewards": [{
		"id": "AvatarFrank",
		"amount": 1,
		"type": "AVATAR",
		"player_avatar_id": "AvatarFrank"
	}]
}';
?>