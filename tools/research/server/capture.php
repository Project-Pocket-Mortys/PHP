<?php
// Loaded only by the isolated research image. Never buffer the SSE transport.
if (PHP_SAPI !== 'cli' && !str_starts_with(parse_url($_SERVER['REQUEST_URI'], PHP_URL_PATH), '/sse')) {
    function researchSanitize($value) {
        $secrets = ['session_id', 'secret', 'token', 'authorization', 'cookie', 'set-cookie',
            'password', 'email', 'consent_identifier', 'receipt', 'recovery_code', 'username',
            'device_id', 'advertising_id', 'idfa', 'idfv', 'access_token', 'refresh_token',
            'session_url', 'recovery_code_hash'];
        if (is_object($value)) {
            foreach ($value as $key => $item) {
                $value->$key = in_array(strtolower($key), $secrets, true) ? '[REDACTED]' : researchSanitize($item);
            }
        } elseif (is_array($value)) {
            $value = array_map('researchSanitize', $value);
        }
        return $value;
    }
    function researchBody($raw) {
        $decoded = json_decode($raw);
        return json_last_error() === JSON_ERROR_NONE ? researchSanitize($decoded)
            : ['omitted' => 'non-JSON or malformed content', 'size' => strlen($raw)];
    }
    $researchRequest = researchBody(file_get_contents('php://input'));
    ob_start(function ($buffer) use ($researchRequest) {
        $record = [
            'evidence_kind' => 'replacement-server runtime; not original-server evidence',
            'time_utc' => gmdate('c'), 'method' => $_SERVER['REQUEST_METHOD'],
            'path' => parse_url($_SERVER['REQUEST_URI'], PHP_URL_PATH),
            'request' => $researchRequest, 'status' => http_response_code(),
            'response' => researchBody($buffer)
        ];
        file_put_contents('/tmp/pocket-research-http.jsonl', json_encode($record) . "\n", FILE_APPEND | LOCK_EX);
        return $buffer;
    });
}
