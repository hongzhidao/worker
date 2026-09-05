<?php
[$program, $root, $app, $listen, $script] = $argv;
$application = [
    'listen' => $listen,
    'type' => 'php',
    'root' => $app,
    'working_directory' => $app,
    'processes' => 1,
    'options' => ['file' => $root . '/runtime/php.ini'],
];
if ($script === 'auto') {
    $application['index'] = 'index.php';
} else {
    $application['script'] = $script;
}
echo json_encode([
    'applications' => ['app' => $application],
], JSON_THROW_ON_ERROR | JSON_UNESCAPED_SLASHES);
