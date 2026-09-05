<?php
if ($argv[1] === '--config') {
    [$program, $mode, $root, $filename] = $argv;
    $configuration = json_decode(file_get_contents($filename), false, 512, JSON_THROW_ON_ERROR);
    foreach (($configuration->applications ?? new stdClass()) as $application) {
        if (explode(' ', $application->type ?? '')[0] === 'php') {
            $application->options ??= new stdClass();
            $application->options->file ??= $root . '/runtime/php.ini';
        }
    }
    echo json_encode($configuration, JSON_THROW_ON_ERROR | JSON_UNESCAPED_SLASHES);
    exit;
}
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
