<?php
//bootcamp
header("Content-Type: application/json; charset=utf-8");
http_response_code(400);
echo '{
  "success": false,
  "error": "MAX_MORTIES_REACHED"
}';