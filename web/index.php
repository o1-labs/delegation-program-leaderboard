<?php
ini_set('display_errors','Off');
ini_set('error_reporting', E_ALL );
?>
<!DOCTYPE html>
<html lang="en">
   <head>
      <meta charset="UTF-8">
      <meta http-equiv="X-UA-Compatible" content="IE=edge">
      <meta name="viewport" content="width=device-width, initial-scale=1.0">
      <title>Uptime Leaderboard</title>
      <link rel="icon" type="image/x-icon" href="./assets/images/favicon.ico"> 
      <link rel="stylesheet" href="https://stackpath.bootstrapcdn.com/bootstrap/4.4.1/css/bootstrap.min.css" integrity="sha384-Vkoo8x4CGsO3+Hhxv8T/Q5PaXtkKtu6ug5TOeNV6gBiFeWPGFN9MuhOf23Q9Ifjh" crossorigin="anonymous">
      <script src="https://code.jquery.com/jquery-3.4.1.slim.min.js" integrity="sha384-J6qa4849blE2+poT4WnyKhv5vZF5SrPo0iEjwBvKU7imGFAV0wwj1yYfoRSJoZ+n" crossorigin="anonymous"></script>
      <script src="https://cdn.jsdelivr.net/npm/popper.js@1.16.0/dist/umd/popper.min.js" integrity="sha384-Q6E9RHvbIyZFJoft+2mJbHaEWldlvI9IOYy5n3zV9zzTtmI3UksdQRVvoxMfooAo" crossorigin="anonymous"></script>
      <script src="https://stackpath.bootstrapcdn.com/bootstrap/4.4.1/js/bootstrap.min.js" integrity="sha384-wfSDF2E50Y2D1uUdj0O3uMBJnjuUD4Ih7YwaYd1iqfktj0Uod8GCExl3Og8ifwB6" crossorigin="anonymous"></script>
      <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.4.0/font/bootstrap-icons.css">
      <link rel="stylesheet" href="assets/css/custom.css">
      <link rel="stylesheet" href="assets/css/responsive.css">
      
      <script src="https://ajax.googleapis.com/ajax/libs/jquery/2.1.3/jquery.min.js"></script>
   </head>
   <body>
      
   <div class="minabg">
      <div class="mina-banner">
         <div class="bannerFlex">
            <div class="bannerAnnouncement"> Find the list of delegated block producers
               <a class="Mina-Refrance-color" href="<?php $myarray = include 'config.php'; $Configurl =  $myarray[1];  echo $Configurl;  ?>" target="_blank">here</a>
            </div>
         </div>
      </div>
      
      <div class="container">
         <!-- Logo And Header Section Start -->
         <div class="row mb-3 minalogo">
            <img src="assets/images/Mina_Wordmark.svg" alt="Mina" height="70px" width="150px" class="mina-main-logo d-block mx-auto mx-md-0">
         </div>
         <div class="row mina-subheader-text">
            <div class="subheader">
               <p class="mina-subheader-text-font">Block Producers Uptime Tracker </p>
            </div>
         </div>
         <!-- Logo And Header Section End -->
         <!-- Top Button and Link Section Start -->
         <div class="row justify-content-center">
            <!-- <div class="uptime-lederboard-topButton"></div> -->
            <div class=" mx-0 px-0 topButton ">
               <button type="button" class="delegationButton nav-link active" onclick="window.open('<?php $config = include 'config.php'; echo $config['DELEGATION_FORM_URL']; ?>')">APPLY FOR DELEGATION <i class="bi bi-arrow-right "></i>
               </button>
               <div class="bottomPlate for-normal" id="leaderBoardbtn">
               </div>
            </div>
         </div>
         <!-- Top Button and Link Section End -->
         <div class="row mb-4">
         <div class="col-12 col-md-6 mx-0 px-0 Link-responcive">
            <div class="Snark-work-Uptime-text">
               <p>Ranking for the Mina Foundation Uptime Leaderboard are based on data from the Snark-work Uptime System.</p>
            </div>
            </div>
            <div class="col-12 col-md-6 mx-0 px-0 Link-responcive">
               <div class="d-xl-flex justify-content-end  mb-2">
                  <div class="flex-column d-sm-block mina-delegation-links">
                     <div class="text-left"><a class="Mina-Refrance-color alignment-link" href="<?php $config = include 'config.php'; echo $config['DELEGATION_POLICY_URL']; ?>" target="_blank">Mina Foundation Delegation Policy</a><i class="ml-2 bi bi-box-arrow-up-right Mina-Refrance-color"></i></div>
                     <div class="text-left"><a class="Mina-Refrance-color alignment-link" href="<?php $config = include 'config.php'; echo $config['DELEGATION_GUIDELINES_URL']; ?>" target="_blank">Delegation Program Participation Guidelines</a><i class="ml-2 bi bi-box-arrow-up-right Mina-Refrance-color"></i></div>
                     <div class="text-left"><a class="Mina-Refrance-color alignment-link" href="<?php $config = include 'config.php'; echo $config['API_DOCS_URL']; ?>" target="_blank">MINA Open API for Uptime Data</a><i class="ml-2 bi bi-box-arrow-up-right Mina-Refrance-color"></i></div>
                  </div>
               </div>
               <!-- for mobile view -->
               <!-- <div class="d-flex flex-row">
                  <div class="d-flex d-sm-none">
                     <div class="p-1"><a class="Mina-Refrance-color alignment-link" href="<?php $config = include 'config.php'; echo $config['FOUNDATION_PROGRAM_URL']; ?>" target="_blank">Foundation Delegation Program</a><i class="ml-2 bi bi-box-arrow-up-right Mina-Refrance-color"></i></div>
                     <div class="p-1"><a class="Mina-Refrance-color alignment-link" href="<?php $config = include 'config.php'; echo $config['FOUNDATION_GUIDELINES_URL']; ?>" target="_blank">Delegation Program Participation Guidelines</a><i class="ml-2 bi bi-box-arrow-up-right Mina-Refrance-color"></i></div>
                  </div>
               </div> -->
               <!-- <div class="row Link-responcive"> -->
               <!-- <a class="Mina-Refrance-color ml-auto alignment-link" href="https://medium.com/o1labs/o-1-labs-delegation-policy-786bf96f9fdd" target="_blank">O(1) Labs Delegation Policy</a><i class="ml-2 bi bi-box-arrow-up-right Mina-Refrance-color"></i> -->
               <!-- </div> -->
            </div>
         </div>
         </div>
</div>
         
         <!-- Tab and Search Section Start -->
         <div class="container">
         <div class="container mb-3 mt-0 mx-sm-0 performance-Container">
            <div class="responcive-tab">
               <div class="row justify-content-between">
               <div class="col-12 col-sm-12 col-md-4 col-lg-4 col-xl-4  px-0 mx-0 mb-5">
                     <div class="row d-flex flex-column">
                        <label class="search_label">find participant</label>
                        <input type="search" class="form-control mb-2 mt-2 search-box" id="search-input" placeholder="Filter by BP key" onkeyup="search_result()">
                     </div>
               </div>
               <div class="tableTabs col-12 col-sm-12 col-md-12 col-lg-12 col-xl-7  px-0 mx-0 mb-5">
               <ul class="row nav nav-pills text-center">
                              <a data-toggle="pill" class="nav-link active   d-flex align-items-center justify-content-center " href="#Data-table" aria-controls="Data-table" aria-selected="true" id="table-one" onclick='showDataForTabOne (10, 1, 0)'>
                                 <div class="beta-text">
                                 Snark-Work Uptime System
                                 </div>
                              </a>
                           <!-- <div class="bottom-plate-tab"></div> -->
                        </ul>

               </div>
               </div>
            </div>
         </div>
         <!-- Tab and Search Section End -->
      </div>
      <!-- Data Table Section Start -->
      <div id="result"></div>
      <div id="result2"></div>
      <div id="loaderSpin"></div>
      <!-- Data Table Section End -->
      <script type="text/javascript">
         var tabledataSnark ;
          function getRecordsForSnark(perPageCount, pageNumber ) {
         console.log("getRecordsForSnark");
          $.ajax({
              type: "GET",
              url: "getPageDataForSnark.php",
              data: {pageNumber: pageNumber},

              cache: false,
              beforeSend: function() {
                  $('#loaderSpin').html('<div class="spinner-border d-flex mx-auto" role="status"><span class="sr-only">Loading...</span></div>');

              },
              success: function(response) {
                  // alert(response);
                  tabledataSnark = response;
                  
                          if ($('#table-one').attr("aria-controls") === "Data-table" && $('#table-one').hasClass('active'))  {
                              showDataForTabOne (10, 1, 0);
                           }
              
                  $('#loaderSpin').html('');
              },

          });
         }

          function showDataForTabOne(perPageCount, pageNumber, pagestart , input ) {
            if(!input){
             input = document.getElementById('search-input').value;
             if(input.length === 0) {
               input = null
             if(!input){input = null}
             }
            }
          $.ajax({
              type: "POST",
              url: "showDataForTabOne.php",
              data: {perPageCount:perPageCount,pageNumber: pageNumber ,pagestart:pagestart, tabledata : tabledataSnark , search_input : input},

              cache: false,
              success: function(html) {
                  $('#loaderSpin').html('');
                  $("#result").html('');
                  $("#result2").html('');
                  $("#result").html(html);
                  $('.Snark-work-Uptime-text').show();
              },

          });
         }

         function search_result() {
            //alert('demo');
          let input = document.getElementById('search-input').value
          input=input.toLowerCase();
          showDataForTabOne (10, 1, 0, input);
         }
          $(document).ready(function() {
          console.log("$(document).ready");
              getRecordsForSnark(10, 1);

              $('input[type=search]').on('search', function () {
                  showDataForTabOne (10, 1, 0);
              });
          });
      </script>
   </body>
</html>