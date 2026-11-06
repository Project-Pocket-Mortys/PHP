<?php
declare(strict_types=1);

/** Research fixture only: select native offline SDK startup once, then assets. */
function research_online_status(bool $offlineOnce, string $stateFile): int {
    if (!$offlineOnce) return 204;
    $lockPath = $stateFile.'.lock';
    if (is_link($lockPath) || is_link($stateFile)) return 503;
    $lock = @fopen($lockPath, 'c+');
    if ($lock === false) return 503;
    $file = false;
    try {
        if (!flock($lock, LOCK_EX)) return 503;
        clearstatcache(true, $stateFile);
        if (is_link($stateFile)) return 503;
        $exists = file_exists($stateFile);
        if ($exists && !is_file($stateFile)) return 503;
        $file = @fopen($stateFile, $exists ? 'r+' : 'x+');
        if ($file === false) return 503;
        $raw = stream_get_contents($file);
        if ($raw === false) return 503;
        $count = 0;
        if ($exists) {
            $state = json_decode($raw, true);
            if (!is_array($state) || array_keys($state) !== ['schema_version', 'probe_count']
                || $state['schema_version'] !== 1 || !is_int($state['probe_count'])
                || $state['probe_count'] < 1 || $state['probe_count'] === PHP_INT_MAX) return 503;
            $count = $state['probe_count'];
        }
        $next = json_encode(['schema_version' => 1, 'probe_count' => $count + 1], JSON_THROW_ON_ERROR);
        if (!rewind($file) || !ftruncate($file, 0)
            || fwrite($file, $next) !== strlen($next) || !fflush($file)) return 503;
        return $count === 0 ? 503 : 204;
    } finally {
        if (is_resource($file)) fclose($file);
        fclose($lock);
    }
}

if (PHP_SAPI !== 'cli') {
    header('Cache-Control: no-store');
    http_response_code(research_online_status(
        getenv('PM_RESEARCH_OFFLINE_SDK_ONCE') === '1',
        '/tmp/pocket-research-offline-sdk-once.json'
    ));
}
