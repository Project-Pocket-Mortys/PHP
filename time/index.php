<?php
header('Content-Type: application/json');

echo json_encode([
    "utc_timestamp" => round(microtime(true) * 1000)
]);

/* unlock instantly
// UNIX timestamp in seconds (MOST LIKELY EXPECTED)
$serverTime = time();

// response
echo json_encode([
    "serverTime" => $serverTime
]);
*/