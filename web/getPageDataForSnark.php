<?php
require_once("connectionsnark.php");

// Validate and sanitize pageNumber from GET
$pageNumber = isset($_GET['pageNumber']) ? filter_var($_GET['pageNumber'], FILTER_VALIDATE_INT, ['options' => ['default' => 1, 'min_range' => 1]]) : 1;

$perPageCount = 120;

// Check if IGNORE_APPLICATION_STATUS is set to 1
$ignoreApplicationStatus = getenv('IGNORE_APPLICATION_STATUS') == 1;

// Modify SQL query based on IGNORE_APPLICATION_STATUS
$sqlCondition = $ignoreApplicationStatus ? "score IS NOT NULL" : "application_status = TRUE AND score IS NOT NULL";

$sql = "SELECT COUNT(*) FROM nodes WHERE {$sqlCondition}";
if ($result = pg_query($conn, $sql)) {
    $row = pg_fetch_row($result);
    $rowCount = (int)$row[0]; 
    pg_free_result($result);
}

$pagesCount = ceil($rowCount / $perPageCount);
$lowerLimit = ($pageNumber - 1) * $perPageCount;

// Use the modified SQL condition for the main query as well
$sqlQuery = "SELECT block_producer_key, score, score_percent FROM nodes WHERE {$sqlCondition} ORDER BY score DESC";

// Execute the main query and sanitize the results
$results = pg_query($conn, $sqlQuery);
$row = pg_fetch_all($results);

$maxScoreSnark = "
    WITH recentone AS ( 
        SELECT batch_end_epoch end_epoch, 
               extract('epoch' FROM (to_timestamp(batch_end_epoch) - interval '90' day)) start_epoch 
        FROM bot_logs b 
        WHERE file_timestamps <= CURRENT_TIMESTAMP 
        ORDER BY batch_end_epoch DESC 
        LIMIT 1
    )
    SELECT COUNT(1), to_char(to_timestamp(end_epoch), 'DD-MM-YYYY hh24:mi') AS last_modified
    FROM bot_logs, recentone
    WHERE batch_start_epoch >= start_epoch 
      AND batch_end_epoch <= end_epoch
      AND files_processed > -1
    GROUP BY 2
";

// Execute the query
$maxScoreSnarkResult = pg_query($conn, $maxScoreSnark);
$maxScoreRow = pg_fetch_row($maxScoreSnarkResult);

// Sanitize database output before using it
$maxScore = (int)$maxScoreRow[0]; 
$last_modified = htmlspecialchars($maxScoreRow[1], ENT_QUOTES, 'UTF-8'); 

// Ensure to sanitize the JSON output
foreach ($row as &$r) {
    $r['block_producer_key'] = htmlspecialchars($r['block_producer_key'], ENT_QUOTES, 'UTF-8');
    $r['score'] = (float)$r['score']; 
    $r['score_percent'] = (float)$r['score_percent']; 
}

echo json_encode(array('row' => $row, 'rowCount' => $rowCount, 'maxScore' => $maxScore, 'last_modified' => $last_modified));

?>
