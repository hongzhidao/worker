<?php
$body = file_get_contents('php://input');
$timezone = new DateTimeZone('Asia/Tokyo');
if (mb_strlen('worker') !== 6 || !class_exists('DOMDocument') || !class_exists('PDO')) {
    throw new RuntimeException('A packaged extension is missing.');
}
header('Content-Type: application/json');
echo json_encode([
    'flavor' => 'php', 'method' => $_SERVER['REQUEST_METHOD'], 'body' => $body,
    'sha256' => hash('sha256', $body), 'extensions' => get_loaded_extensions(),
    'timezone' => $timezone->getName(),
], JSON_THROW_ON_ERROR);
