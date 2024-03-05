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
1. Move terminal to this repo.
2. Create a config file (i.e. config.env) with below parameters: 
##### DB_SNARK_HOST=
##### DB_SNARK_PORT=
##### DB_SNARK_USER=
##### DB_SNARK_PWD=
##### DB_SNARK_DB=

Configure these variables and save the file.

3. Go to the terminal.
4. Type below commands:
5. >docker build -t mina-web .
6. >docker run --env-file ./config.env --name mina-web --restart unless-stopped -p 80:80 -p 443:443 -i -t -d  mina-web

This will install all dependancies and start the container. After finishing the process we will opening the browser with `127.0.0.1`
***

## Note
After any changes in project you have rebuild the docker file by using 
`docker build -t mina-web .`
this command and again run the container .

