# Online Examination System - Docker Setup

This project uses Docker and Docker Compose to run the frontend, backend, and Redis cache.

> **Note:** You must have Docker Desktop installed on your machine before running these commands.

## How to Build and Run the Project
1. Open a terminal in the root directory of the project.
2. Run the following command to build and start the containers in the background:
   ```bash
   docker-compose up --build -d
   ```
*(Omit the `-d` flag if you want to see the logs in your terminal)*

## How to Access the Application
Once the containers are successfully running, you can test the application using the following links:
- **Frontend App**: [http://localhost:8080/login.html](http://localhost:8080/login.html)
- **Backend API Docs**: [http://localhost:8000/docs](http://localhost:8000/docs)

## How to Stop Containers
To stop and remove the running containers, open a terminal in the project root and run:
```bash
docker-compose down
```
