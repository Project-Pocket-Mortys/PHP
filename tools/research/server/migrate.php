<?php
if (PHP_SAPI !== 'cli' || getenv('PM_DB_HOST') !== 'db' || getenv('PM_DB_NAME') !== 'pocket_mortys') {
    throw new RuntimeException('Isolated research database required');
}
require '/var/www/html/pocket_f4894h398r8h9w9er8he98he.php';
// Ordered, additive and repeatable; no modification to the original SQL dump.
foreach (glob(__DIR__.'/migrations/*.sql') as $file) {
    $pdo->exec(file_get_contents($file));
    echo basename($file)." applied\n";
}
