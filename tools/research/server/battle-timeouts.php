<?php
declare(strict_types=1);
// Isolated research scheduler. --once is useful for cron and bounded validation.
if (PHP_SAPI !== 'cli') {
    http_response_code(404);
    exit;
}
if (getenv('PM_DB_HOST') !== 'db' || getenv('PM_DB_NAME') !== 'pocket_mortys') {
    fwrite(STDERR, "Isolated research database required\n");
    exit(1);
}
require __DIR__ . '/../../../pocket_f4894h398r8h9w9er8he98he.php';
require_once __DIR__ . '/../../../lib/battle_timeouts.php';
$once = in_array('--once', $argv, true);
$cursor = null;
do {
    try {
        $expired = battle_timeout_sweep($pdo, 100, $cursor);
        if ($expired > 0 || $once) fwrite(STDOUT, "Expired $expired battle selections\n");
    } catch (Throwable $error) {
        error_log('Battle timeout sweep failed: ' . $error->getMessage());
        if ($once) exit(1);
    }
    if (!$once) usleep(1000000);
} while (!$once);
