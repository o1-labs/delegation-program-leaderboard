# delegation-program-leaderboard
## Technologies Used 
***
> Postgresql,
> Html 5,
> Bootstrap 4, 
> Php 8.0,
> Docker
***

## How to change IP address for Leader board UI
1. Open connection.php.

2. Find below code and change the subnet IP with your config IP.
```Javascript
networks:
  mina-network:
    ipam:
     driver: default
     config:
      - subnet: ""
      - subnet: ""
```
3. In `ipv4_address` you have to change IP with your IP.
```Javascript
php:
      ...
      networks:
        mina-network:
          ipv4_address: 
          ipv6_address: 
   ```

***
## How to configure postgress Database
Open connection.php and configure this variables with your credentials and save the file. 
##### $username = "your database username";
##### $password = "your database username";
##### $database_name = "your database name";
##### $port = "your database port";
##### $host = "your database Host Ip address";

## Installing Docker file
1. Copy this directory to home directory in ubuntu.
2. Go to the terminal.
3. Type belowe Commands.
4. * >cd web-dev/
   * >docker-compose up -d

This will install all dependancies and start the container. After finishing the process we will opening the browser with `172.16.238.10`
***

## Note
After any changes in project you have rebuild the docker file by using 
`docker build -t mina-web .`
this command and again run the container .

