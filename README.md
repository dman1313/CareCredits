# CareCredit

A centralized CPD (Continuing Professional Development) portal for Malaysian doctors to discover, register for, and track medical training. Featuring a searchable dashboard to filter courses by location, fee, difficulty, and CPD points, the app simplifies annual license renewal.

## Overview

CareCredit is built using a modern containerized architecture with three core components:

1. **Frontend (TypeScript)**: A responsive web application built with Next.js, React, and Tailwind CSS, providing an intuitive interface for doctors to browse and manage CPD courses.
2. **Backend (Python)**: A RESTful API built with FastAPI that manages user data, course registrations, and CPD tracking. The backend connects to a PostgreSQL database for persistent storage.
3. **Scraper API Service (Python)**: A dedicated microservice that gathers up-to-date information about medical training courses, including details like course descriptions, dates, locations, and CPD points.

## Prerequisites

Before you begin, make sure you have the following installed on your machine:

- [Docker](https://docs.docker.com/get-docker/)
- [Docker Compose](https://docs.docker.com/compose/install/) (usually included with Docker Desktop)
- **Git**: For version control and cloning the repository.

> **Note for Local Development:** If you plan to run the frontend locally without Docker, you will need [Node.js 20+](https://nodejs.org/) and [pnpm](https://pnpm.io/installation) installed.

## Quick Start

### 1. Clone the repository

```bash
git clone https://github.com/dman1313/CareCredits.git
cd carecredit
```

### 2. Create local variables
```bash
cp .env.example .env
```

Edit the .env file and ensure the following variables are set correctly:
- Database: POSTGRES_DB, POSTGRES_USER,POSTGRES_PASSWORD
- Backend: SECRET_KEY, ALGORITHM, ACCESS_TOKEN_EXPIRE_MINUTES
- Ports: Ensure POSTGRES_PORT (default 5432) does not conflict with local services.

### 3. Build and run with docker

Use Docker Compose to build and start all services (PostgreSQL, FastAPI Backend, and Next.js Frontend)

```bash
docker compose up --build
```

This command will:
1. Build the Docker images for the backend and frontend.
2. Start the PostgreSQL database.
3. Initialize the database schema using init.sql.
4. Start the FastAPI backend.
5. Start the Next.js frontend.

### 4. Acces the App

- Frontend: Open http://localhost:3000 in your browser.
- Backend API Docs: Open http://localhost:8000/docs to view the Swagger UI.
- Database: Connect via localhost on port 5432 using the credentials from your .env file.