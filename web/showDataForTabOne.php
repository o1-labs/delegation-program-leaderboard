<?php

$ShowScoreColumn = true;
$MaintenanceMode = false;

// Sanitize and validate the POST data
$tabledata = json_decode($_POST['tabledata'], true);

// Ensure that tabledata contains only the allowed keys
$allowedKeys = ['rowCount', 'maxScore', 'last_modified', 'row'];
$tabledata = array_intersect_key($tabledata, array_flip($allowedKeys));

// Validate and sanitize the remaining keys
$rowCount = isset($tabledata['rowCount']) ? (int)$tabledata['rowCount'] : 0;
$maxScore = isset($tabledata['maxScore']) ? (int)$tabledata['maxScore'] : 0;
$last_modified = isset($tabledata['last_modified']) ? htmlspecialchars($tabledata['last_modified'], ENT_QUOTES, 'UTF-8') : '';

// Validate pageNumber and perPageCount
$SearchInputData = isset($_POST['search_input']) ? htmlspecialchars($_POST['search_input'], ENT_QUOTES, 'UTF-8') : null;
$pageNumber = isset($_POST['pageNumber']) ? filter_var($_POST['pageNumber'], FILTER_VALIDATE_INT) : 1;
$perPageCount = isset($_POST['perPageCount']) ? filter_var($_POST['perPageCount'], FILTER_VALIDATE_INT) : 10;

$pagesCount = ceil($rowCount / $perPageCount);
$lowerLimit = ($pageNumber - 1) * $perPageCount;
$pagestart = isset($_POST['pagestart']) ? filter_var($_POST['pagestart'], FILTER_VALIDATE_INT) : 0;

// Ensure that rows contain only allowed fields
$rowData = isset($tabledata['row']) && is_array($tabledata['row']) ? $tabledata['row'] : [];
$allowedRowKeys = ['block_producer_key', 'score', 'score_percent'];

foreach ($rowData as $key => $row) {
    // Remove any keys that are not in the allowedRowKeys whitelist
    $rowData[$key] = array_intersect_key($row, array_flip($allowedRowKeys));

    // Sanitize each value in the row
    $rowData[$key]['block_producer_key'] = isset($rowData[$key]['block_producer_key']) ? htmlspecialchars($rowData[$key]['block_producer_key'], ENT_QUOTES, 'UTF-8') : '';
    $rowData[$key]['score'] = isset($rowData[$key]['score']) ? (float)$rowData[$key]['score'] : 0;
    $rowData[$key]['score_percent'] = isset($rowData[$key]['score_percent']) ? (float)$rowData[$key]['score_percent'] : 0;
}

if ($SearchInputData !== null) {
    $newArray = array();
    foreach ($rowData as $key => $rowDataKey) {
        if (stripos(strtolower($rowDataKey['block_producer_key']), $SearchInputData) !== false) {
            $rowDataKey['index'] = $key + 1;
            $newArray[$key] = $rowDataKey;
        }
    }
    $rowData = $newArray;
    $rowCount = count($newArray);
    $pagesCount = ceil($rowCount / $perPageCount);
}

$row = array_slice($rowData, $pagestart, $perPageCount);
$counter = $lowerLimit + 1;

?>
<div class="container mb-0 mt-0 performance-Container">

<div class="selectNav">
    <p class="selectNav_perpage_title mr13px">Results Per Page</p>
    <select class="selectNav_selector mr13px" value="<?php echo htmlspecialchars($perPageCount, ENT_QUOTES, 'UTF-8') ?>" onchange="showDataForTabOne(this.value, '<?php echo 1; ?>', '<?php echo 0; ?>');">
       <?php for ($x = 10; $x <= 100; $x+=10) { ?>
          <option value="<?php echo htmlspecialchars($x, ENT_QUOTES, 'UTF-8') ?>" <?php if($perPageCount == $x) echo 'selected' ?>><?php echo htmlspecialchars($x, ENT_QUOTES, 'UTF-8') ?></option>
       <?php } ?>
    </select>
    <ul class="selectNav_list">
    
    <li>
        <a class="<?php if($pageNumber > 1) { echo 'page-active '; } else { echo 'page-disable'; } ?>" href="javascript:void(0);" onclick="showDataForTabOne('<?php echo htmlspecialchars($perPageCount, ENT_QUOTES, 'UTF-8'); ?>', '<?php if($pageNumber <= 1){ echo $pageNumber; } else { echo ($pageNumber - 1); } ?>', '<?php echo ($lowerLimit - $perPageCount); ?>');">Prev</a>
    </li>
    <li>
      <a class="<?php if($pageNumber <= 1) { echo 'page-disable'; } else { echo 'page-active'; } ?>" href="javascript:void(0);" tabindex="-1" onclick="showDataForTabOne('<?php echo htmlspecialchars($perPageCount, ENT_QUOTES, 'UTF-8'); ?>', '<?php echo 1; ?>', '<?php echo 0; ?>');">1</a>
    </li>
    <li>
      <a class="<?php if($pageNumber == 2) { echo 'page-disable'; } else { echo 'page-active'; } ?>" href="javascript:void(0);" tabindex="-1" onclick="showDataForTabOne('<?php echo htmlspecialchars($perPageCount, ENT_QUOTES, 'UTF-8'); ?>', '<?php echo 2; ?>', '<?php echo 0; ?>');">2</a>
    </li>
    <li>.
        <?php if($pageNumber>2 && ($pageNumber <($pagesCount-1))) { ?>
      <a class="page-disable" href="javascript:void(0);" tabindex="-1" onclick="showDataForTabOne('<?php echo htmlspecialchars($perPageCount, ENT_QUOTES, 'UTF-8'); ?>', '<?php echo $pageNumber; ?>', '<?php echo 0; ?>');"><?php echo $pageNumber ?></a>
        <?php } else echo '.' ?>
    .</li>
    
    <li>
      <a class="<?php if($pageNumber == $pagesCount-1) { echo 'page-disable'; } else { echo 'page-active'; } ?>" href="javascript:void(0);" onclick="showDataForTabOne('<?php echo htmlspecialchars($perPageCount, ENT_QUOTES, 'UTF-8'); ?>', '<?php echo $pagesCount-1; ?>', '<?php echo (($pagesCount - 2) * $perPageCount); ?>');"><?php echo $pagesCount-1?></a>
    </li>
    <li>
      <a class="<?php if($pageNumber == $pagesCount) { echo 'page-disable'; } else { echo 'page-active'; } ?>" href="javascript:void(0);" onclick="showDataForTabOne('<?php echo htmlspecialchars($perPageCount, ENT_QUOTES, 'UTF-8'); ?>', '<?php echo $pagesCount; ?>', '<?php echo (($pagesCount - 1) * $perPageCount); ?>');"><?php echo $pagesCount ?></a>
    </li>
    <li>
        <a class="<?php if($pageNumber == $pagesCount) { echo 'page-disable'; } else { echo 'page-active'; } ?>" href="javascript:void(0);" onclick="showDataForTabOne('<?php echo htmlspecialchars($perPageCount, ENT_QUOTES, 'UTF-8'); ?>', '<?php if($pageNumber >= $pagesCount){ echo $pageNumber; } else { echo ($pageNumber + 1); } ?>', '<?php echo ($lowerLimit + $perPageCount); ?>');">Next</a>
    </li>
  </ul>

  <span class="list_last_update d-sm-block">Last updated <?php echo htmlspecialchars($last_modified, ENT_QUOTES, 'UTF-8') ?></span>

</div>
</div>


<div class="container pr-0 pl-0 mt-0 mb-5 tab-content">
        <div class="table-responsive table-responsive-sm table-responsive-md table-responsive-lg table-responsive-xl tab-pane fade show active" id="Data-table" role="tabpanel" aria-labelledby="Data-table">
            <table class="table table-striped text-center">
                <thead>
                    <tr class="border-top-0">
                        <th scope="col">RANK</th>
                        <th scope="col" class="text-left">PUBLIC KEY</th>
                        <?php if($ShowScoreColumn == true){ ?>
                        <th scope="col">SCORE(90-Day)</th>
                        <?php } ?>
                        <th scope="col">%(Max Score <?php echo htmlspecialchars($maxScore, ENT_QUOTES, 'UTF-8') ?>) </th>
                    </tr>
                </thead>
                <tbody class="">
                <tr style="<?php if($MaintenanceMode != true) {echo 'display: none;';}?>">
                    <td colspan="<?php if($ShowScoreColumn != true) {echo '3';} else {echo '4';}?>">
                        <div class="wrap">
                            <i class="bi bi-exclamation-triangle-fill" style="font-size: 5rem; color: #b0afaf;"></i>
                            <h1 class="maintenanceText">Under Maintenance</h1>
                        </div>
                    </td>
                </tr>
                <?php if($MaintenanceMode != true){
                foreach ($row as $key => $data) { ?>
                    
                    <tr>
                        <td scope="row"><?php if($SearchInputData != null) { echo htmlspecialchars($data['index'], ENT_QUOTES, 'UTF-8'); } else { echo $counter; } ?></td>
                        <td><?php echo htmlspecialchars($data['block_producer_key'], ENT_QUOTES, 'UTF-8'); ?></td>
                        <?php if($ShowScoreColumn == true){ ?>
                        <td><?php echo htmlspecialchars($data['score'], ENT_QUOTES, 'UTF-8'); ?></td>
                        <?php } ?>
                        <td><?php echo htmlspecialchars($data['score_percent'], ENT_QUOTES, 'UTF-8'); ?> %</td>
                    </tr>
                <?php $counter++;
                }
            } ?>
                </tbody>
            </table>
        </div>
</div>

<div class="container mb-0 mt-0 performance-Container">

<div class="selectNav" style="position:relative" >
    <p class="selectNav_perpage_title mr13px">Results Per Page</p>
    <select class="selectNav_selector mr13px" value="<?php echo htmlspecialchars($perPageCount, ENT_QUOTES, 'UTF-8') ?>" onchange="showDataForTabOne(this.value, '<?php echo 1; ?>', '<?php echo 0; ?>');">
       <?php for ($x = 10; $x <= 100; $x+=10) { ?>
          <option value="<?php echo htmlspecialchars($x, ENT_QUOTES, 'UTF-8') ?>" <?php if($perPageCount==$x)echo 'selected' ?> ><?php echo htmlspecialchars($x, ENT_QUOTES, 'UTF-8') ?></option>
       <?php } ?>
    </select>
    <ul class="selectNav_list">
    
    <li >
        <a class="<?php if($pageNumber > 1) {echo 'page-active ';} else {echo 'page-disable';}?>" href="javascript:void(0);" onclick="showDataForTabOne('<?php echo htmlspecialchars($perPageCount, ENT_QUOTES, 'UTF-8'); ?>', '<?php if($pageNumber <= 1){ echo $pageNumber; } else { echo ($pageNumber - 1); } ?>', '<?php echo ($lowerLimit - $perPageCount); ?>');">Prev</a></li>

    </li>
    


    <li >
      <a class="<?php if($pageNumber <= 1) {echo 'page-disable';} else {echo 'page-active';}?>" href="javascript:void(0);" tabindex="-1" onclick="showDataForTabOne('<?php echo htmlspecialchars($perPageCount, ENT_QUOTES, 'UTF-8'); ?>', '<?php echo 1; ?>', '<?php echo 0; ?>');">1</a>
    </li>
    <li >
      <a class="<?php if($pageNumber ==2 ) {echo 'page-disable';} else {echo 'page-active';}?>"href="javascript:void(0);" tabindex="-1" onclick="showDataForTabOne('<?php echo htmlspecialchars($perPageCount, ENT_QUOTES, 'UTF-8'); ?>', '<?php echo 2; ?>', '<?php echo 0; ?>');">2</a>
    </li>
    <li>.
        <?php if($pageNumber>2 && ($pageNumber <($pagesCount-1))) { ?>
      <a class="page-disable" href="javascript:void(0);" tabindex="-1" onclick="showDataForTabOne('<?php echo htmlspecialchars($perPageCount, ENT_QUOTES, 'UTF-8'); ?>', '<?php echo $pageNumber; ?>', '<?php echo 0; ?>');"><?php echo $pageNumber ?></a>
        <?php } else echo '.' ?>
        
    .</li>
    
    <li >
      <a class="<?php if($pageNumber == $pagesCount-1) {echo 'page-disable';} else {echo 'page-active';}?>" href="javascript:void(0);" onclick="showDataForTabOne('<?php echo htmlspecialchars($perPageCount, ENT_QUOTES, 'UTF-8'); ?>', '<?php echo $pagesCount-1; ?>', '<?php echo (($pagesCount - 2) * $perPageCount); ?>');"><?php echo $pagesCount-1?></a>
    </li>
    <li >
      <a class="<?php if($pageNumber == $pagesCount) {echo 'page-disable';} else {echo 'page-active';}?>" href="javascript:void(0);" onclick="showDataForTabOne('<?php echo htmlspecialchars($perPageCount, ENT_QUOTES, 'UTF-8'); ?>', '<?php echo $pagesCount; ?>', '<?php echo (($pagesCount - 1) * $perPageCount); ?>');"><?php echo $pagesCount ?></a>
    </li>
    <li >
        <a class="<?php if($pageNumber == $pagesCount) {echo 'page-disable';} else {echo 'page-active';}?>" href="javascript:void(0);" onclick="showDataForTabOne('<?php if($pageNumber >= $pagesCount){ echo $pageNumber; } else { echo ($pageNumber + 1); } ?>', '<?php echo ($lowerLimit + $perPageCount); ?>');">Next</a>
    </li>
    <!-- <li class = "mr-3 mt-1 p-2 d-none d-md-block">Page <?php echo $pageNumber; ?> of <?php echo $pagesCount; ?></li> -->
  </ul>


</div>
</div>

    </div>
    
    <div style="height: 30px;"></div>

