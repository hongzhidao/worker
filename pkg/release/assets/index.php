<?php
header('Content-Type: application/json');
echo json_encode(['worker' => 'php', 'path' => $_SERVER['REQUEST_URI']], JSON_THROW_ON_ERROR);
