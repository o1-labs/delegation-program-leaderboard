# delegation-program-leaderboard
## Technologies Used 
***
> Postgresql,
> Html 5,
> Bootstrap 4, 
> Php 8.0,
> Docker
***

## Installing Docker file
1. Download / Move WEB-DEV folder, to home directory in ubuntu.
2. Create a config file with below paramerters: 
##### DB_SIDECAR_HOST=
##### DB_SIDECAR_PORT=
##### DB_SIDECAR_USER=
##### DB_SIDECAR_PWD=
##### DB_SIDECAR_DB=
##### DB_SNARK_HOST=
##### DB_SNARK_PORT=
##### DB_SNARK_USER=
##### DB_SNARK_PWD=
##### DB_SNARK_DB=
##### API_HOST=

Configure these variables and save the file.

3. Go to the terminal.
4. Type below commands.
5. >docker build -t mina-web .

This will install all dependancies and start the container. After finishing the process we will opening the browser with `172.16.238.10`
***

## Note
After any changes in project you have rebuild the docker file by using 
`docker build -t mina-web .`
this command and again run the container .

